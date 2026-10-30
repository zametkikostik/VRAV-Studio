from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    secret_key: str = "dev-secret-change-me"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
