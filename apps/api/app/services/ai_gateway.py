"""API-facing AI Gateway: registry, per-request BYOK providers, usage estimate."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

_ROOT = Path(__file__).resolve().parents[3]
_AI_PKG = _ROOT / "packages" / "ai-gateway"
if str(_AI_PKG) not in sys.path:
    sys.path.insert(0, str(_AI_PKG))

from vrav_ai.adapters.mock import MockAIProvider
from vrav_ai.adapters.openrouter import OpenRouterProvider
from vrav_ai.adapters.routerai import RouterAIProvider
from vrav_ai.adapters.xai import XAIProvider
from vrav_ai.protocol import ChatRequest, ChatResponse
from vrav_ai.registry import ProviderRegistry
from vrav_ai.router import AIRouter

CREDITS_PER_1K_TOKENS = Decimal("1.0")


def build_default_registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(MockAIProvider())
    reg.register(XAIProvider(api_key=os.getenv("XAI_API_KEY") or None))
    reg.register(OpenRouterProvider(api_key=os.getenv("OPENROUTER_API_KEY") or None))
    reg.register(RouterAIProvider(api_key=os.getenv("ROUTERAI_API_KEY") or None))
    return reg


_default_registry: ProviderRegistry | None = None
_default_router: AIRouter | None = None


def get_router() -> AIRouter:
    global _default_registry, _default_router
    if _default_router is None:
        _default_registry = build_default_registry()
        _default_router = AIRouter(_default_registry)
    return _default_router


def estimate_credits(input_tokens: int, output_tokens: int) -> Decimal:
    total = input_tokens + output_tokens
    return (Decimal(total) / Decimal(1000) * CREDITS_PER_1K_TOKENS).quantize(Decimal("0.0001"))


def _provider_id_from_model(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    if model.startswith("grok"):
        return "xai"
    return "mock"


def _make_provider(provider_id: str, api_key: str | None) -> Any:
    if provider_id == "mock":
        return MockAIProvider()
    if provider_id == "xai":
        return XAIProvider(api_key=api_key or os.getenv("XAI_API_KEY") or None)
    if provider_id == "openrouter":
        return OpenRouterProvider(api_key=api_key or os.getenv("OPENROUTER_API_KEY") or None)
    if provider_id == "routerai":
        return RouterAIProvider(api_key=api_key or os.getenv("ROUTERAI_API_KEY") or None)
    raise ValueError(f"Unknown provider: {provider_id}")


async def resolve_byok_api_key(
    db: Any,
    *,
    user_id: UUID,
    organization_id: UUID,
    provider_id: str,
) -> str | None:
    try:
        from sqlalchemy import select

        from app.models.ai_connection import UserAIConnection
        from app.services.crypto import decrypt_secret

        result = await db.execute(
            select(UserAIConnection).where(
                UserAIConnection.user_id == user_id,
                UserAIConnection.organization_id == organization_id,
                UserAIConnection.provider_id == provider_id,
                UserAIConnection.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        if row is None or not row.encrypted_api_key:
            return None
        return decrypt_secret(row.encrypted_api_key)
    except Exception:
        return None


async def run_chat(
    request: ChatRequest,
    *,
    db: Any = None,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
) -> ChatResponse:
    provider_id = _provider_id_from_model(request.model)
    byok_key: str | None = None

    if db is not None and user_id is not None and organization_id is not None:
        byok_key = await resolve_byok_api_key(
            db, user_id=user_id, organization_id=organization_id, provider_id=provider_id
        )

    if byok_key:
        reg = ProviderRegistry()
        reg.register(MockAIProvider())
        reg.register(_make_provider(provider_id, byok_key))
        for pid in ("xai", "openrouter", "routerai"):
            if pid != provider_id:
                reg.register(_make_provider(pid, None))
        router = AIRouter(reg)
    else:
        router = get_router()

    import time

    from app.core.circuit_breaker import CircuitOpenError, get_breaker
    from app.core.metrics import classify_ai_error, note_ai_request

    async def _do_chat(r=router):
        return await r.chat(request)

    t0 = time.perf_counter()
    breaker = get_breaker(provider_id) if provider_id != "mock" else None
    try:
        if breaker is not None:
            response = await breaker.call(_do_chat)
        else:
            response = await _do_chat()
        latency = time.perf_counter() - t0
        in_tok = int(getattr(response.usage, "input_tokens", 0) or 0) if response.usage else 0
        out_tok = int(getattr(response.usage, "output_tokens", 0) or 0) if response.usage else 0
        note_ai_request(
            provider=provider_id,
            model=request.model,
            status="success",
            latency_s=latency,
            prompt_tokens=in_tok,
            completion_tokens=out_tok,
        )
    except CircuitOpenError:
        latency = time.perf_counter() - t0
        note_ai_request(
            provider=provider_id,
            model=request.model,
            status="error",
            latency_s=latency,
            error_type="circuit_open",
        )
        fallback_order = [p for p in ("xai", "openrouter", "routerai", "mock") if p != provider_id]
        last_err: Exception | None = None
        response = None
        for fb in fallback_order:
            try:
                fb_req = request.model_copy(update={"model": "mock/default" if fb == "mock" else f"{fb}/default"})
                if fb == "mock":
                    response = await MockAIProvider().chat(fb_req)
                    provider_id = "mock"
                else:
                    reg = ProviderRegistry()
                    reg.register(MockAIProvider())
                    reg.register(_make_provider(fb, None))
                    fb_router = AIRouter(reg)
                    fb_breaker = get_breaker(fb)

                    async def _fb_call(r=fb_router, rq=fb_req):
                        return await r.chat(rq)

                    response = await fb_breaker.call(_fb_call)
                    provider_id = fb
                break
            except Exception as e:
                last_err = e
                continue
        if response is None:
            raise CircuitOpenError(provider_id) from last_err
    except Exception as e:
        latency = time.perf_counter() - t0
        note_ai_request(
            provider=provider_id,
            model=request.model,
            status="error",
            latency_s=latency,
            error_type=classify_ai_error(e),
        )
        raise

    if response.usage and response.usage.cost_credits is None:
        response.usage.cost_credits = float(
            estimate_credits(response.usage.input_tokens, response.usage.output_tokens)
        )
    if response.raw is None:
        response.raw = {}
    if isinstance(response.raw, dict):
        response.raw = {**response.raw, "byok": bool(byok_key), "provider_id": provider_id}
    return response
