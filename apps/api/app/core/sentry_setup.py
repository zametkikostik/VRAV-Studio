"""Optional Sentry integration. No-op when DSN is empty or SDK missing."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("vrav.sentry")


def filter_sensitive_data(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Strip tokens/passwords from outgoing Sentry events."""
    try:
        request = event.get("request") or {}
        headers = request.get("headers")
        if isinstance(headers, dict):
            for k in list(headers.keys()):
                if k.lower() in ("authorization", "cookie", "x-api-key"):
                    headers[k] = "[REDACTED]"
        data = request.get("data")
        if isinstance(data, dict):
            for key in (
                "password",
                "password_confirm",
                "new_password",
                "secret_key",
                "api_key",
                "token",
                "refresh_token",
            ):
                if key in data:
                    data[key] = "[REDACTED]"
    except Exception as e:
        logger.debug("sentry filter error: %s", e)
    return event


def init_sentry(settings) -> bool:
    """Initialize Sentry if DSN is set. Returns True if enabled."""
    dsn = (getattr(settings, "sentry_dsn", None) or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("sentry-sdk not installed; Sentry disabled")
        return False

    integrations = [StarletteIntegration(), FastApiIntegration()]
    try:
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        integrations.append(SqlalchemyIntegration())
    except Exception:
        pass
    try:
        from sentry_sdk.integrations.redis import RedisIntegration

        integrations.append(RedisIntegration())
    except Exception:
        pass

    env = getattr(settings, "sentry_environment", None) or getattr(settings, "environment", "development")
    rate = float(getattr(settings, "sentry_traces_sample_rate", 0.1) or 0.0)

    sentry_sdk.init(
        dsn=dsn,
        environment=str(env),
        traces_sample_rate=rate,
        integrations=integrations,
        before_send=filter_sensitive_data,
        send_default_pii=False,
    )
    logger.info("Sentry initialized environment=%s", env)
    return True
