from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
import os

import bcrypt
from jose import JWTError, jwt


def _settings():
    try:
        from app.core.config import get_settings
        return get_settings()
    except Exception:
        class S:
            secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
            algorithm = "HS256"
            access_token_expire_minutes = 60 * 24
            refresh_token_expire_days = 30
            environment = os.getenv("ENVIRONMENT", "development")
        return S()


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw = plain.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
    *,
    token_version: int = 0,
) -> str:
    settings = _settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
        "jti": str(uuid4()),
        "ver": int(token_version),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
    *,
    token_version: int = 0,
) -> str:
    settings = _settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=getattr(settings, "refresh_token_expire_days", 30))
    )
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid4()),
        "ver": int(token_version),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str, expected_type: str | None = None) -> dict | None:
    settings = _settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if expected_type and payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


def decode_access_token(token: str) -> str | None:
    payload = decode_token(token, expected_type="access")
    if payload:
        sub = payload.get("sub")
        return str(sub) if sub else None

    settings = _settings()
    env = getattr(settings, "environment", os.getenv("ENVIRONMENT", "development"))
    if str(env).lower() == "production":
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") == "refresh":
            return None
        if payload.get("type") not in (None, "access"):
            return None
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None
