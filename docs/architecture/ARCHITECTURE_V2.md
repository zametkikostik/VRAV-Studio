# VRAV Studio — Architecture V2

## Goals
- Single codebase for Desktop (Electron) and VDS (server)
- Next.js + TypeScript, FastAPI, PostgreSQL, Redis + Celery, FFmpeg
- AI Gateway with BYOK + VRAV Cloud
- Adapters: xAI, OpenRouter, RouterAI
- Billing: subscriptions + usage credits + self-hosted licenses
- White-label, Stripe + YooKassa
- No float for money. Immutable credit ledger. Idempotent webhooks.

## C4 Context
User → Desktop (Electron+Next) or Browser → VRAV Platform
  (AI Gateway, Billing, License, Project/Timeline, Workers)
→ Postgres, Redis, Object Storage, FFmpeg
→ External AI + Payment providers

## Containers
Desktop Shell · Web Frontend · FastAPI · AI Gateway · Billing · Celery · Postgres · Redis · Storage

## Dependency rules
core ← everything · adapters → only ports · desktop/web → public API only

## Money rules
NUMERIC(19,4) · credit_ledger append-only · reserve→commit/release · webhook UNIQUE(provider, event_id)
