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
    # Onboarding accepts up to four 8 MiB photos in one multipart request.
    MAX_REQUEST_BODY_MB: int = 40

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 2.0
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 5.0
    RATE_LIMIT_STORAGE_URI: str = ""
    DEFAULT_RATE_LIMIT: str = "120/minute"
    CHAT_RATE_LIMIT: str = "20/minute"
    CHAT_IP_RATE_LIMIT: str = "60/minute"
    UPLOAD_RATE_LIMIT: str = "10/hour"
    UPLOAD_IP_RATE_LIMIT: str = "30/hour"
    ASSESSMENT_RATE_LIMIT: str = "10/hour"
    ASSESSMENT_IP_RATE_LIMIT: str = "30/hour"
    TRUSTED_PROXY_CIDRS: list[str] = ["127.0.0.1/32", "::1/128"]

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

    # Distributed Agent/AI admission control. Redis leases make the limits
    # effective across multiple API and worker processes.
    AGENT_LOCK_TTL_SECONDS: int = 180
    AGENT_LOCK_WAIT_SECONDS: float = 0.25
    AI_MAX_CONCURRENCY: int = 8
    EMBEDDING_MAX_CONCURRENCY: int = 4
    FACEPLUS_MAX_CONCURRENCY: int = 3
    AI_GATE_WAIT_SECONDS: float = 2.0
    AI_GATE_LEASE_SECONDS: int = 90

    # Conservative token/call budgets. A request reserves its maximum possible
    # output before contacting the provider and releases unused tokens later.
    AI_BUDGET_ENFORCEMENT: bool = True
    AI_USER_DAILY_CALL_LIMIT: int = 200
    AI_GLOBAL_DAILY_CALL_LIMIT: int = 5000
    AI_USER_DAILY_TOKEN_LIMIT: int = 300000
    AI_GLOBAL_DAILY_TOKEN_LIMIT: int = 5000000

    # Background Redis Stream consumer controls.
    WORKER_CONCURRENCY: int = 4
    WORKER_AI_CONCURRENCY: int = 2
    WORKER_BATCH_SIZE: int = 10
    WORKER_STALE_JOB_IDLE_MS: int = 300000

    # Internal observability endpoint. In development an unset token permits
    # loopback access only; production requires a token.
    OPS_METRICS_TOKEN: str = ""
    SECURITY_HEADERS_ENABLED: bool = True

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
        if not self.TRUSTED_PROXY_CIDRS:
            raise RuntimeError("Production requires an explicit TRUSTED_PROXY_CIDRS allowlist")
        if not self.OPS_METRICS_TOKEN or len(self.OPS_METRICS_TOKEN) < 24:
            raise RuntimeError("Production requires an OPS_METRICS_TOKEN of at least 24 characters")
        if min(
            self.AI_MAX_CONCURRENCY,
            self.EMBEDDING_MAX_CONCURRENCY,
            self.FACEPLUS_MAX_CONCURRENCY,
            self.WORKER_CONCURRENCY,
            self.WORKER_AI_CONCURRENCY,
        ) < 1:
            raise RuntimeError("Production concurrency limits must be positive")
        if self.WORKER_AI_CONCURRENCY > self.WORKER_CONCURRENCY:
            raise RuntimeError("WORKER_AI_CONCURRENCY cannot exceed WORKER_CONCURRENCY")
        if not self.AI_BUDGET_ENFORCEMENT:
            raise RuntimeError("Production requires AI_BUDGET_ENFORCEMENT=true")
        if min(
            self.AI_USER_DAILY_CALL_LIMIT,
            self.AI_GLOBAL_DAILY_CALL_LIMIT,
            self.AI_USER_DAILY_TOKEN_LIMIT,
            self.AI_GLOBAL_DAILY_TOKEN_LIMIT,
        ) < 1:
            raise RuntimeError("Production AI budget limits must be positive")
        if self.AI_USER_DAILY_CALL_LIMIT > self.AI_GLOBAL_DAILY_CALL_LIMIT:
            raise RuntimeError("User AI call budget cannot exceed the global budget")
        if self.AI_USER_DAILY_TOKEN_LIMIT > self.AI_GLOBAL_DAILY_TOKEN_LIMIT:
            raise RuntimeError("User AI token budget cannot exceed the global budget")
        if self.ENABLE_SCHEDULER and not self.SCHEDULER_PERSIST_JOBS:
            raise RuntimeError("Production scheduler requires persistent jobs")
        for origin in self.CORS_ORIGINS:
            parsed = urlparse(origin)
            if parsed.scheme != "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                raise RuntimeError("Production CORS origins must be non-local HTTPS origins")


@lru_cache
def get_settings() -> Settings:
    return Settings()
