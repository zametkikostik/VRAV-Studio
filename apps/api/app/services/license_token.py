"""Offline-capable signed license tokens (JWT)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

ISSUER = "vrav-license"


def _signing_key() -> str:
    key = os.getenv("LICENSE_SIGNING_KEY") or os.getenv("SECRET_KEY")
    if key:
        return key
    try:
        from app.core.config import get_settings

        return get_settings().secret_key
    except Exception:
        return "dev-secret-change-me"


def issue_offline_token(
    *,
    license_key: str,
    license_id: str,
    max_installations: int,
    features: dict[str, Any] | None,
    valid_until: datetime | None = None,
    ttl_days: int = 30,
) -> str:
    now = datetime.now(timezone.utc)
    exp = valid_until if valid_until else now + timedelta(days=ttl_days)
    if valid_until and valid_until < exp:
        exp = valid_until
    payload = {
        "iss": ISSUER,
        "sub": license_key,
        "license_id": license_id,
        "max_installations": max_installations,
        "features": features or {},
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _signing_key(), algorithm="HS256")


def verify_offline_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, _signing_key(), algorithms=["HS256"], issuer=ISSUER)
    except JWTError:
        return None
