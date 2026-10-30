# VRAV Studio

AI-assisted video production platform — **unified Desktop (Electron) + cloud (VDS)**.

## Product MVP

| Area | What you get |
|------|----------------|
| Web app | Login, dashboard, projects, billing, BYOK settings |
| API | Auth, orgs, projects, assets, timelines, AI chat/stream, billing, licenses, GDPR |
| AI | mock, xAI, OpenRouter, RouterAI + encrypted BYOK |
| Commercial | Credits ledger, Stripe/YooKassa sandbox, self-hosted licenses |
| Ops | Docker, Helm, CI, backups, loadtest, cutover |

## Quick start

```bash
cp .env.example .env
docker compose -f infra/docker/docker-compose.dev.yml up -d

cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=".:../../packages/ai-gateway"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Production

See `docs/runbooks/GO_LIVE.md` and `CUTOVER.md`.

## License

Proprietary — VRAV. All rights reserved unless otherwise agreed.
