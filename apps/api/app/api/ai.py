import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.ai import AIUsageEvent
from app.models.organization import OrganizationMember
from app.schemas.ai import ChatRequestIn, ChatResponseOut, UsageOut
from app.services.ai_gateway import estimate_credits, run_chat
from app.services.credits import CreditService, InsufficientCreditsError, release_in_new_tx
from vrav_ai.protocol import ChatMessage, ChatRequest

router = APIRouter(prefix="/ai", tags=["ai"])

DEFAULT_RESERVE_CREDITS = Decimal("1.0000")


@router.get("/providers")
async def list_providers():
    from app.services.ai_gateway import get_router

    reg = get_router().registry
    out = []
    for pid in reg.list_ids():
        p = reg.get(pid)
        if p is None:
            continue
        out.append({"id": p.id, "capabilities": p.capabilities.model_dump()})
    return out


@router.post("/chat", response_model=ChatResponseOut)
async def chat(body: ChatRequestIn, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of organization")

    credit_svc = CreditService(db)
    idem = f"ai-chat:{user.id}:{uuid.uuid4()}"
    try:
        reservation = await credit_svc.reserve(
            organization_id=org_id,
            amount=DEFAULT_RESERVE_CREDITS,
            idempotency_key=idem,
        )
    except InsufficientCreditsError:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient credits")

    request = ChatRequest(
        model=body.model,
        messages=[ChatMessage(role=m.role, content=m.content) for m in body.messages],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        stream=False,
    )

    try:
        response = await run_chat(
            request,
            db=db,
            user_id=user.id,
            organization_id=org_id,
        )
    except ValueError:
        await release_in_new_tx(reservation.id)
        raise HTTPException(status_code=400, detail="Request failed")
    except RuntimeError:
        await release_in_new_tx(reservation.id)
        raise HTTPException(status_code=503, detail="Request failed")
    except Exception:
        await release_in_new_tx(reservation.id)
        raise HTTPException(status_code=502, detail="Provider error")

    provider_id = "mock"
    if "/" in body.model:
        provider_id = body.model.split("/", 1)[0]
    elif body.model.startswith("grok"):
        provider_id = "xai"

    usage = response.usage
    actual_cost = estimate_credits(usage.input_tokens, usage.output_tokens)
    if usage.cost_credits is not None:
        actual_cost = Decimal(str(usage.cost_credits))

    try:
        await credit_svc.settle(reservation.id, actual_cost)
    except Exception:
        await credit_svc.commit(reservation.id)

    byok_used = False
    if isinstance(response.raw, dict):
        byok_used = bool(response.raw.get("byok"))

    event = AIUsageEvent(
        id=uuid.uuid4(),
        organization_id=org_id,
        user_id=user.id,
        provider_id=provider_id,
        model_id=body.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens or (usage.input_tokens + usage.output_tokens),
        cost_credits=actual_cost,
        metadata_={"byok": byok_used},
    )
    db.add(event)
    await db.flush()

    return ChatResponseOut(
        content=response.content,
        model=response.model or body.model,
        usage=UsageOut(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost_credits=float(actual_cost),
        ),
        provider=provider_id,
    )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequestIn, user: CurrentUser, db: DbSession):
    """SSE streaming chat."""
    import json
    from fastapi.responses import StreamingResponse
    from app.services.ai_gateway import (
        get_router,
        resolve_byok_api_key,
        _make_provider,
        estimate_credits,
    )
    from vrav_ai.registry import ProviderRegistry
    from vrav_ai.router import AIRouter
    from vrav_ai.adapters.mock import MockAIProvider

    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of organization")

    credit_svc = CreditService(db)
    idem = f"ai-stream:{user.id}:{uuid.uuid4()}"
    try:
        reservation = await credit_svc.reserve(org_id, DEFAULT_RESERVE_CREDITS, idempotency_key=idem)
    except InsufficientCreditsError:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    request = ChatRequest(
        model=body.model,
        messages=[ChatMessage(role=m.role, content=m.content) for m in body.messages],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        stream=True,
    )
    provider_id = body.model.split("/", 1)[0] if "/" in body.model else "mock"
    byok = await resolve_byok_api_key(db, user_id=user.id, organization_id=org_id, provider_id=provider_id)
    if byok:
        reg = ProviderRegistry()
        reg.register(MockAIProvider())
        reg.register(_make_provider(provider_id, byok))
        stream_router = AIRouter(reg)
    else:
        stream_router = get_router()

    async def event_gen():
        usage_tokens = {"in": 0, "out": 0}
        settled = False
        try:
            async for chunk in stream_router.stream_chat(request):
                if chunk.usage:
                    usage_tokens["in"] = chunk.usage.input_tokens
                    usage_tokens["out"] = chunk.usage.output_tokens
                yield f"data: {json.dumps(chunk.model_dump())}\n\n"
            cost = estimate_credits(usage_tokens["in"], usage_tokens["out"])
            try:
                await credit_svc.settle(reservation.id, cost)
            except Exception:
                await credit_svc.commit(reservation.id)
            settled = True
            event = AIUsageEvent(
                id=uuid.uuid4(),
                organization_id=org_id,
                user_id=user.id,
                provider_id=provider_id,
                model_id=body.model,
                input_tokens=usage_tokens["in"],
                output_tokens=usage_tokens["out"],
                total_tokens=usage_tokens["in"] + usage_tokens["out"],
                cost_credits=Decimal(str(cost)),
                metadata_={"stream": True, "byok": bool(byok)},
            )
            db.add(event)
            await db.flush()
            yield f"data: {json.dumps({'done': True, 'cost_credits': float(cost)})}\n\n"
        except Exception:
            try:
                if not settled:
                    await release_in_new_tx(reservation.id)
                    settled = True
            except Exception:
                pass
            yield f"data: {json.dumps({'error': 'stream failed'})}\n\n"
        finally:
            if not settled:
                try:
                    await release_in_new_tx(reservation.id)
                except Exception:
                    pass

    return StreamingResponse(event_gen(), media_type="text/event-stream")
