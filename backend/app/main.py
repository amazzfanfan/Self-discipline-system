from contextlib import asynccontextmanager
import hmac
import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import async_session
from app.core.rate_limit import limiter
from app.core.client_ip import is_loopback_client
from app.core.http_middleware import (
    RequestBodyLimitMiddleware,
    RequestMetricsMiddleware,
    SecurityHeadersMiddleware,
)
from app.modules.auth.router import router as auth_router
from app.modules.behavior.router import router as behavior_router
from app.modules.chat.router import router as chat_router
from app.modules.goals.router import router as goals_router
from app.modules.score.router import router as score_router
from app.modules.task.router import router as task_router
from app.modules.user.router import router as user_router
from app.modules.weight.router import router as weight_router
from app.modules.notification.router import router as notification_router
from app.services.cache_service import cache_is_ready, get_background_worker_status
from app.services.ai_budget_service import AIBudgetExceeded
from app.services.capacity_service import CapacityExceeded, CapacityUnavailable
from app.services.metrics_service import increment_metric, metrics_snapshot
from app.services.scheduler_service import scheduler, start_scheduler

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime_security()
    if settings.ENABLE_SCHEDULER and settings.SCHEDULER_IN_API:
        start_scheduler()
    yield
    if settings.SCHEDULER_IN_API and scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, version="9.0.0", lifespan=lifespan)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    await increment_metric("rate_limit:rejected")
    response = _rate_limit_exceeded_handler(request, exc)
    response.headers.setdefault("Retry-After", "60")
    return response


@app.exception_handler(AIBudgetExceeded)
async def ai_budget_exceeded_handler(_: Request, exc: AIBudgetExceeded):
    status_code = 429 if exc.scope == "user" else 503
    return JSONResponse(
        {
            "detail": {
                "code": "ai_budget_exceeded",
                "scope": exc.scope,
                "resource": exc.resource,
                "message": "AI 使用额度已达到保护上限，请稍后再试。",
            }
        },
        status_code=status_code,
        headers={"Retry-After": "3600"},
    )


@app.exception_handler(CapacityExceeded)
async def ai_capacity_exceeded_handler(_: Request, exc: CapacityExceeded):
    return JSONResponse(
        {
            "detail": {
                "code": "ai_capacity_busy",
                "resource": exc.kind,
                "message": "当前 AI 请求较多，系统已启动过载保护，请稍后重试。",
            }
        },
        status_code=503,
        headers={"Retry-After": "2"},
    )


@app.exception_handler(CapacityUnavailable)
async def ai_capacity_unavailable_handler(_: Request, __: CapacityUnavailable):
    return JSONResponse(
        {
            "detail": {
                "code": "ai_capacity_unavailable",
                "message": "AI 协调服务暂时不可用，请稍后重试。",
            }
        },
        status_code=503,
        headers={"Retry-After": "5"},
    )


app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    safe_errors = [
        {
            "location": list(error.get("loc", ())),
            "type": error.get("type"),
            "message": error.get("msg"),
        }
        for error in exc.errors()
    ]
    logger.warning("Request validation failed path=%s errors=%s", request.url.path, safe_errors)
    return await request_validation_exception_handler(request, exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestMetricsMiddleware)

app.include_router(auth_router)
app.include_router(behavior_router)
app.include_router(user_router)
app.include_router(score_router)
app.include_router(task_router)
app.include_router(chat_router)
app.include_router(weight_router)
app.include_router(goals_router)
app.include_router(notification_router)


@app.get("/health", tags=["health"])
@limiter.exempt
async def health():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
@limiter.exempt
async def readiness():
    database_ready = False
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            database_ready = True
    except Exception:
        database_ready = False

    redis_ready = await cache_is_ready()
    worker_status = await get_background_worker_status() if redis_ready else {"ready": False}
    worker_ready = bool(worker_status.get("ready"))
    payload = {
        "status": "ready" if database_ready and redis_ready and worker_ready else "unavailable",
        "components": {
            "database": database_ready,
            "redis": redis_ready,
            "worker": worker_status,
        },
    }
    return (
        payload
        if database_ready and redis_ready and worker_ready
        else JSONResponse(payload, status_code=503)
    )


@app.get("/internal/metrics", include_in_schema=False)
@limiter.exempt
async def internal_metrics(
    request: Request,
    x_ops_token: str | None = Header(default=None, alias="X-Ops-Token"),
):
    configured = settings.OPS_METRICS_TOKEN
    token_valid = bool(
        configured
        and x_ops_token
        and hmac.compare_digest(configured, x_ops_token)
    )
    local_development = (
        settings.ENVIRONMENT.lower() != "production"
        and not configured
        and is_loopback_client(request)
    )
    if not token_valid and not local_development:
        raise HTTPException(404, "Not found")
    try:
        return await metrics_snapshot()
    except Exception as exc:
        logger.warning("Metrics snapshot unavailable: %s", exc)
        raise HTTPException(503, "Metrics unavailable") from exc
