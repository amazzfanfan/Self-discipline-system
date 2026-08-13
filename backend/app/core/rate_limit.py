from slowapi import Limiter

from app.core.client_ip import get_client_ip
from app.core.config import get_settings
from app.core.security import decode_token


settings = get_settings()


def ip_rate_limit_key(request) -> str:
    return f"ip:{get_client_ip(request)}"


def user_or_ip_rate_limit_key(request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        payload = decode_token(authorization.split(" ", 1)[1].strip())
        subject = str((payload or {}).get("sub", ""))
        if payload and payload.get("type") == "access" and subject:
            return f"user:{subject[:80]}"
    return ip_rate_limit_key(request)


limiter = Limiter(
    key_func=ip_rate_limit_key,
    default_limits=[settings.DEFAULT_RATE_LIMIT],
    storage_uri=settings.RATE_LIMIT_STORAGE_URI or "memory://",
)
