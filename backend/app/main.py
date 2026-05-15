from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.core.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.user.router import router as user_router
from app.modules.score.router import router as score_router
from app.modules.task.router import router as task_router
from app.modules.chat.router import router as chat_router
from app.modules.weight.router import router as weight_router
from app.modules.goals.router import router as goals_router

settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(score_router)
app.include_router(task_router)
app.include_router(chat_router)
app.include_router(weight_router)
app.include_router(goals_router)

import os
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}


from app.services.scheduler_service import start_scheduler


@app.on_event("startup")
async def startup():
    start_scheduler()
