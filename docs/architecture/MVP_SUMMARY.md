# VRAV Studio V2 — Blueprint complete

## Stack
Desktop (Electron) + VDS (Docker/Helm) · Next.js · FastAPI · Postgres · Redis/Celery · FFmpeg
AI: mock, xAI, OpenRouter, RouterAI · BYOK · credits ledger · Stripe + YooKassa sandbox
Licenses · White-label · S3/MinIO · Timelines · Collab · Helm

## Commands
```bash
cd apps/api && PYTHONPATH=.:../../packages/ai-gateway pytest -q
docker compose -f infra/docker/docker-compose.yml up -d --build
helm upgrade --install vrav ./infra/helm/vrav-studio -n vrav --create-namespace
```

## Honest gaps
- Collab HTTP event log + WS rooms (not full CRDT)
- Payment providers sandbox stubs in automated tests
- Confirm RouterAI production base URL with vendor
