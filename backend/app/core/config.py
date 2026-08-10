from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "System Agent"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    APP_TIMEZONE: str = "Asia/Shanghai"
    ENABLE_SCHEDULER: bool = True
    MAX_UPLOAD_SIZE_MB: int = 8

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_NAME: str = "system_refresh"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "strict"
    AUTH_COOKIE_DOMAIN: str | None = None

    # AI
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    AI_MODEL: str = "qwen-plus"
    AI_CHAT_MODEL: str = ""        # Non-reasoning model for chat/tasks (e.g. qwen-plus)
    AI_ANALYSIS_MODEL: str = ""    # Reasoning model for scoring/image analysis (e.g. mimo-v2.5-pro)

    # LLM Configuration
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT: int = 30
    LLM_FALLBACK_MODEL: str = ""
    LLM_FALLBACK_API_KEY: str = ""
    LLM_FALLBACK_BASE_URL: str = ""
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 1500

    # Embedding Configuration
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSION: int = 1536

    # Face++ skin analysis. Credentials must never be committed to source.
    FACEPLUSPLUS_API_KEY: str = ""
    FACEPLUSPLUS_API_SECRET: str = ""
    FACEPLUSPLUS_API_URL: str = "https://api-cn.faceplusplus.com/facepp/v1/skinanalyze"
    FACEPLUSPLUS_TIMEOUT_SECONDS: int = 30
    FACEPLUSPLUS_CACHE_TTL_SECONDS: int = 2592000

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Privacy and retention
    TRACE_RETENTION_DAYS: int = 30
    PHOTO_RETENTION_DAYS: int = 365

    @property
    def chat_model(self) -> str:
        return self.AI_CHAT_MODEL or self.AI_MODEL

    @property
    def analysis_model(self) -> str:
        return self.AI_ANALYSIS_MODEL or self.AI_MODEL

    def validate_runtime_security(self) -> None:
        if self.ENVIRONMENT.lower() == "production" and self.SECRET_KEY in {
            "change-me-in-production",
            "your-secret-key-change-in-production",
            "local-development-secret-change-me",
        }:
            raise RuntimeError("Production requires a unique SECRET_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
