import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.rate_limit import auth_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services.email import get_email_provider

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.post("/register", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: DbSession):
    if not await auth_limiter.allow(f"reg:{_client_key(request)}"):
        raise HTTPException(status_code=429, detail="Too many requests")
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        id=uuid.uuid4(),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return TokenPairResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(body: LoginRequest, request: Request, db: DbSession):
    if not await auth_limiter.allow(f"login:{_client_key(request)}"):
        raise HTTPException(status_code=429, detail="Too many requests")
    result = await db.execute(select(User).where(User.email == body.email.lower(), User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return TokenPairResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(body: RefreshRequest, request: Request):
    if not await auth_limiter.allow(f"refresh:{_client_key(request)}"):
        raise HTTPException(status_code=429, detail="Too many requests")
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload["sub"]
    return TokenPairResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
    )


@router.post("/password-reset/request")
async def password_reset_request(body: PasswordResetRequest, request: Request, db: DbSession):
    if not await auth_limiter.allow(f"pwreset:{_client_key(request)}"):
        raise HTTPException(status_code=429, detail="Too many requests")
    settings = get_settings()
    result = await db.execute(select(User).where(User.email == body.email.lower(), User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    resp: dict = {"status": "ok"}
    if user:
        token = create_access_token(f"reset:{user.id}", expires_delta=timedelta(hours=1))
        reset_base = getattr(settings, "password_reset_url", None) or "https://app.vrav.local/reset"
        link = f"{reset_base}?token={token}"
        text = (
            f"Password reset for VRAV Studio\n\n"
            f"Open this link within 1 hour:\n{link}\n\n"
            f"If you did not request this, ignore the email."
        )
        html = f"<p>Password reset for VRAV Studio</p><p><a href=\"{link}\">Reset password</a></p>"
        try:
            await get_email_provider().send(
                to=user.email,
                subject="VRAV Studio — password reset",
                text=text,
                html=html,
            )
        except Exception:
            pass
        if settings.environment != "production":
            resp["reset_token"] = token
    return resp


@router.post("/password-reset/confirm")
async def password_reset_confirm(body: PasswordResetConfirm, db: DbSession):
    payload = decode_token(body.token, expected_type="access")
    if not payload:
        payload = decode_token(body.token)
    if not payload or not str(payload.get("sub", "")).startswith("reset:"):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user_id = str(payload["sub"]).split(":", 1)[1]
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(body.new_password)
    await db.flush()
    return {"status": "password_updated"}
