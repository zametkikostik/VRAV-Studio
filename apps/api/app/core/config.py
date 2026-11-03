from functools import lru_cache

from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    secret_key: str = ""
    encryption_key: str = ""
    license_signing_key: str = ""
    trust_proxy_headers: bool = False
    trusted_proxies: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    metrics_token: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+asyncpg://vrav:vrav@localhost:5432/vrav"
    database_url_sync: str = "postgresql://vrav:vrav@localhost:5432/vrav"
    redis_url: str = "redis://localhost:6379/0"

    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    auth_rate_limit_per_minute: int = 30
    cors_origins: str = ""

    log_level: str = "INFO"
    log_json: bool = False

    password_reset_url: str = "https://app.vrav.local/reset"
    email_provider: str = "console"

    gdpr_retention_days: int = 30

    max_upload_bytes: int = 500 * 1024 * 1024
    allow_manual_credit_topup: bool = False

    # Sentry (empty DSN = disabled)
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("environment") or "development")
        if isinstance(env, str):
            env = env.lower()
        weak = {"", "dev-secret-change-me", "change-me", "changeme", "secret"}
        if env == "production" and (not v or v.strip() in weak):
            raise ValueError("SECRET_KEY must be set in production")
        if not v or v.strip() in {"", "dev-secret-change-me"}:
            import secrets

            return secrets.token_urlsafe(32)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
