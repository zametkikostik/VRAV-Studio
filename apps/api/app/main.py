from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai import router as ai_router
from app.api.ai_connections import router as ai_connections_router
from app.api.assets_upload import router as upload_router
from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.gdpr import router as gdpr_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.license import router as license_router
from app.api.metrics import router as metrics_router
from app.api.organizations import router as orgs_router
from app.api.projects import router as projects_router
from app.api.timelines import router as timelines_router
from app.api.white_label import router as white_label_router
from app.api.ws_collab import router as ws_collab_router
from app.api.editing import router as editing_router
from app.api.rag import router as rag_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


def _assert_production_secrets(settings) -> None:
    """Fail closed: production must not use default/short SECRET_KEY."""
    if settings.environment != "production":
        return
    sk = (settings.secret_key or "").strip()
    weak = {"", "dev-secret-change-me", "change-me", "changeme", "secret"}
    if sk in weak or len(sk) < 32:
        raise RuntimeError(
            "Production requires SECRET_KEY with length >= 32 and not a known default"
        )
    enc = (getattr(settings, "encryption_key", None) or "").strip()
    if enc and len(enc) < 16:
        raise RuntimeError("ENCRYPTION_KEY is set but too short (min 16)")
    lic = (getattr(settings, "license_signing_key", None) or "").strip()
    if lic and len(lic) < 16:
        raise RuntimeError("LICENSE_SIGNING_KEY is set but too short (min 16)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _assert_production_secrets(settings)
    setup_logging(settings.log_level, json_logs=settings.log_json or settings.environment == "production")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    _assert_production_secrets(settings)
    app = FastAPI(title="VRAV Studio API", version="0.2.2", lifespan=lifespan)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not origins:
        origins = (
            ["http://localhost:3000", "http://127.0.0.1:3000"]
            if settings.environment == "development"
            else ["https://studio.example.com"]
        )
    allow_creds = True
    if origins == ["*"]:
        allow_creds = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    for r in (
        health_router,
        metrics_router,
        auth_router,
        orgs_router,
        projects_router,
        upload_router,
        ai_router,
        ai_connections_router,
        billing_router,
        jobs_router,
        license_router,
        white_label_router,
        timelines_router,
        gdpr_router,
        ws_collab_router,
        editing_router,
        rag_router,
    ):
        app.include_router(r)
    return app


app = create_app()
