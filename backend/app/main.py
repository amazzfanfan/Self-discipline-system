from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import async_session
from app.modules.auth.router import router as auth_router
from app.modules.behavior.router import router as behavior_router
from app.modules.chat.router import router as chat_router
from app.modules.goals.router import router as goals_router
from app.modules.score.router import router as score_router
from app.modules.task.router import router as task_router
from app.modules.user.router import router as user_router
from app.modules.weight.router import router as weight_router
from app.modules.notification.router import router as notification_router
from app.services.cache_service import cache_is_ready
from app.services.scheduler_service import scheduler, start_scheduler

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime_security()
    if settings.ENABLE_SCHEDULER:
        start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, version="9.0.0", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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
async def health():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness():
    database_ready = False
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            database_ready = True
    except Exception:
        database_ready = False

    redis_ready = await cache_is_ready()
    payload = {
        "status": "ready" if database_ready and redis_ready else "unavailable",
        "components": {"database": database_ready, "redis": redis_ready},
    }
    return payload if database_ready and redis_ready else JSONResponse(payload, status_code=503)
