from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "System Agent"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    AI_MODEL: str = "qwen-vl-plus"
    AI_CHAT_MODEL: str = ""        # Non-reasoning model for chat/tasks (e.g. qwen-plus)
    AI_ANALYSIS_MODEL: str = ""    # Reasoning model for scoring/image analysis (e.g. mimo-v2.5-pro)

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"

    @property
    def chat_model(self) -> str:
        return self.AI_CHAT_MODEL or self.AI_MODEL

    @property
    def analysis_model(self) -> str:
        return self.AI_ANALYSIS_MODEL or self.AI_MODEL


@lru_cache
def get_settings() -> Settings:
    return Settings()
