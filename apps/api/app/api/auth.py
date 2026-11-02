import uuid
from datetime import datetime, timedelta, timezone

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
from app.services.token_revoke import is_jti_revoked, revoke_jti

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
    """Client IP for rate limits. XFF only if TRUST_PROXY_HEADERS and peer is trusted."""
    import ipaddress

    settings = get_settings()
    peer = request.client.host if request.client else "unknown"
    if not getattr(settings, "trust_proxy_headers", False):
        return peer

    trusted_raw = getattr(settings, "trusted_proxies", "") or ""
    networks = []
    for part in trusted_raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    try:
        peer_addr = ipaddress.ip_address(peer)
        peer_trusted = any(peer_addr in net for net in networks) if networks else False
    except ValueError:
        peer_trusted = False

    if peer_trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer


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
    ver = int(getattr(user, "token_version", 0) or 0)
    return TokenPairResponse(
        access_token=create_access_token(user.id, token_version=ver),
        refresh_token=create_refresh_token(user.id, token_version=ver),
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
    ver = int(getattr(user, "token_version", 0) or 0)
    return TokenPairResponse(
        access_token=create_access_token(user.id, token_version=ver),
        refresh_token=create_refresh_token(user.id, token_version=ver),
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(body: RefreshRequest, request: Request, db: DbSession):
    if not await auth_limiter.allow(f"refresh:{_client_key(request)}"):
        raise HTTPException(status_code=429, detail="Too many requests")
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if await is_jti_revoked(db, payload.get("jti")):
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    try:
        uid = uuid.UUID(str(payload["sub"]))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    result = await db.execute(select(User).where(User.id == uid, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    token_ver = int(payload.get("ver") or 0)
    user_ver = int(getattr(user, "token_version", 0) or 0)
    if token_ver != user_ver:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if payload.get("jti") and payload.get("exp"):
        await revoke_jti(
            db,
            str(payload["jti"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
            user_id=user.id,
        )
    return TokenPairResponse(
        access_token=create_access_token(user.id, token_version=user_ver),
        refresh_token=create_refresh_token(user.id, token_version=user_ver),
    )


@router.post("/logout")
async def logout(request: Request, db: DbSession, body: RefreshRequest | None = None):
    """Revoke presented access token (Bearer) and optional refresh token body."""
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        access = auth_header.split(" ", 1)[1].strip()
        payload = decode_token(access, expected_type="access")
        if payload and payload.get("jti") and payload.get("exp"):
            uid = None
            try:
                uid = uuid.UUID(str(payload["sub"]))
            except Exception:
                pass
            await revoke_jti(
                db,
                str(payload["jti"]),
                expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
                user_id=uid,
            )
    if body and body.refresh_token:
        rp = decode_token(body.refresh_token, expected_type="refresh")
        if rp and rp.get("jti") and rp.get("exp"):
            uid = None
            try:
                uid = uuid.UUID(str(rp["sub"]))
            except Exception:
                pass
            await revoke_jti(
                db,
                str(rp["jti"]),
                expires_at=datetime.fromtimestamp(int(rp["exp"]), tz=timezone.utc),
                user_id=uid,
            )
    return {"status": "logged_out"}


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
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    await db.flush()
    return {"status": "password_updated"}
