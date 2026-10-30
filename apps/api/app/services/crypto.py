"""Application-level encryption for secrets (BYOK API keys)."""
from __future__ import annotations

import base64
import hashlib
import os


def _secret_key() -> str:
    try:
        from app.core.config import get_settings

        return get_settings().secret_key
    except Exception:
        return os.getenv("SECRET_KEY", "dev-secret-change-me")


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(_secret_key().encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_secret(token: bytes) -> str:
    return _fernet().decrypt(token).decode("utf-8")


def key_hint(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "…" + api_key[-4:]
