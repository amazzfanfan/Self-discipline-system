from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from urllib.parse import urlparse


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "System Agent"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    APP_TIMEZONE: str = "Asia/Shanghai"
    ENABLE_SCHEDULER: bool = True
    SCHEDULER_IN_API: bool = True
    SCHEDULER_PERSIST_JOBS: bool = True
    SCHEDULER_REDIS_URL: str = ""
    MAX_UPLOAD_SIZE_MB: int = 8

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_STORAGE_URI: str = ""

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
    TEMP_UPLOAD_RETENTION_HOURS: int = 24
    NOTIFICATION_RETENTION_DAYS: int = 90

    # Optional Web Push delivery. Station notifications continue to work when unset.
    WEB_PUSH_VAPID_PUBLIC_KEY: str = ""
    WEB_PUSH_VAPID_PRIVATE_KEY: str = ""
    WEB_PUSH_VAPID_EMAIL: str = ""
    WEB_PUSH_ALLOWED_HOST_SUFFIXES: list[str] = [
        "googleapis.com",
        "push.services.mozilla.com",
        "notify.windows.com",
        "push.apple.com",
    ]

    @property
    def chat_model(self) -> str:
        return self.AI_CHAT_MODEL or self.AI_MODEL

    @property
    def analysis_model(self) -> str:
        return self.AI_ANALYSIS_MODEL or self.AI_MODEL

    def validate_runtime_security(self) -> None:
        if self.ENVIRONMENT.lower() != "production":
            return

        weak_secrets = {
            "change-me-in-production",
            "your-secret-key-change-in-production",
            "local-development-secret-change-me",
            "zengfan",
            "123456",
            "admin",
            "root",
        }
        if len(self.SECRET_KEY) < 32 or self.SECRET_KEY.lower() in weak_secrets:
            raise RuntimeError("Production requires a random SECRET_KEY of at least 32 characters")
        if self.DEBUG:
            raise RuntimeError("Production must run with DEBUG=false")
        if not self.AUTH_COOKIE_SECURE:
            raise RuntimeError("Production requires AUTH_COOKIE_SECURE=true")
        if not self.AI_API_KEY:
            raise RuntimeError("Production requires AI_API_KEY")
        if not self.CORS_ORIGINS or "*" in self.CORS_ORIGINS:
            raise RuntimeError("Production requires an explicit CORS_ORIGINS allowlist")
        if not self.RATE_LIMIT_STORAGE_URI or self.RATE_LIMIT_STORAGE_URI == "memory://":
            raise RuntimeError("Production requires a shared RATE_LIMIT_STORAGE_URI")
        if self.ENABLE_SCHEDULER and not self.SCHEDULER_PERSIST_JOBS:
            raise RuntimeError("Production scheduler requires persistent jobs")
        for origin in self.CORS_ORIGINS:
            parsed = urlparse(origin)
            if parsed.scheme != "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                raise RuntimeError("Production CORS origins must be non-local HTTPS origins")


@lru_cache
def get_settings() -> Settings:
    return Settings()
