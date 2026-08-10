import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_password_rehash,
    verify_password,
)
from app.models.score import DimensionEnum, UserScore
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.cache_service import (
    consume_refresh_session,
    revoke_refresh_session,
    store_refresh_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _refresh_ttl() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=_refresh_ttl(),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        domain=settings.AUTH_COOKIE_DOMAIN,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        domain=settings.AUTH_COOKIE_DOMAIN,
        path="/api/auth",
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


async def _issue_session(response: Response, user_id: str) -> TokenResponse:
    jti = uuid.uuid4().hex
    refresh_token = create_refresh_token({"sub": user_id}, jti=jti)
    if not await store_refresh_session(jti, user_id, _refresh_ttl()):
        raise HTTPException(503, "登录会话服务暂不可用")
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=create_access_token({"sub": user_id}))


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db, scope="function")):
    email = str(req.email).strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        nickname=req.nickname.strip(),
    )
    db.add(user)
    await db.flush()
    for dimension in DimensionEnum:
        db.add(UserScore(user_id=user.id, dimension=dimension, score=50.0))
    return {"message": "registered"}


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    email = str(req.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    if needs_password_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
        await db.flush()
    return await _issue_session(response, str(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response):
    token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "refresh":
        _clear_refresh_cookie(response)
        raise HTTPException(401, "Invalid refresh token")

    user_id = str(payload.get("sub", ""))
    jti = str(payload.get("jti", ""))
    if not user_id or not jti or not await consume_refresh_session(jti, user_id):
        _clear_refresh_cookie(response)
        raise HTTPException(401, "Refresh token expired or already used")
    return await _issue_session(response, user_id)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response):
    token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    payload = decode_token(token) if token else None
    if payload and payload.get("type") == "refresh" and payload.get("jti"):
        await revoke_refresh_session(str(payload["jti"]))
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response
