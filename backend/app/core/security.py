from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

settings = get_settings()
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    # Existing installations may still contain bcrypt hashes. New passwords use
    # Argon2 and are transparently upgraded after the next successful login.
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    try:
        return password_hash.verify(plain, hashed)
    except Exception:
        return False


def needs_password_rehash(hashed: str) -> bool:
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        return True
    try:
        return password_hash.current_hasher.check_needs_rehash(hashed)
    except Exception:
        return True


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict, *, jti: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
