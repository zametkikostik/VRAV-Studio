# VRAV Studio

AI-assisted video production platform — **unified Desktop (Electron) + cloud (VDS)**.

## Product MVP

| Area | What you get |
|------|----------------|
| Web app | Login, dashboard, projects, billing, BYOK settings |
| API | Auth, orgs, projects, assets, timelines, AI, billing, licenses, GDPR |
| Editing | Plan (mock / brief heuristics / LLM JSON), apply timeline, FFmpeg render, export |
| AI | mock, xAI, OpenRouter, RouterAI + encrypted BYOK |
| Commercial | Credits ledger, server-side pricing, Stripe/YooKassa sandbox, licenses |
| Ops | Docker, Helm, CI, smoke checklist, backups |

## Quick start

```bash
cp .env.example .env
# Postgres + Redis
docker compose -f infra/docker/docker-compose.dev.yml up -d

# API
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=".:../../packages/ai-gateway"
alembic -c alembic.ini upgrade head   # through 009 tariff seed
uvicorn app.main:app --reload --port 8000

# Optional worker
cd apps/worker
celery -A worker.celery_app worker -l info

# Web
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# open http://localhost:3000
```

## Editing pipeline (API)

```
POST /editing/plans/generate   # or /from-brief /mock
POST /editing/plans/validate
POST /editing/plans/apply
POST /jobs/render/timeline     # Celery if up, else inline FFmpeg
GET  /jobs/{id}                # polls Celery when running
GET  /jobs/{id}/export
```

Offline FFmpeg check (no DB):

```bash
python scripts/e2e_render_offline.py
```

## Desktop
```bash
cd apps/web && npm run dev   # terminal 1
cd apps/desktop && npm i && npm run dev
```

## Tests
```bash
cd apps/api && PYTHONPATH=.:../../packages/ai-gateway pytest -q
# subset without heavy deps:
pytest tests/test_pricing.py tests/test_render.py tests/test_plan_generate.py tests/test_plan_from_brief.py -q
```

## Ops docs
- `docs/ops/SMOKE_CHECKLIST.md` — local smoke steps  
- `docs/audits/PRODUCTION_READINESS.md` — gates  
- `docs/product/AI_VIDEO_PIPELINE.md` — plan → render  

## Production
See `docs/runbooks/GO_LIVE.md` and `CUTOVER.md` if present.  
**Do not enable live payment keys or `ALLOW_MANUAL_CREDIT_TOPUP` in production without review.**

## License
Proprietary — VRAV. All rights reserved unless otherwise agreed.
