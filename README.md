# VRAV Studio

**AI-first видео-редактор и платформа для коллаборации.**

VRAV Studio объединяет возможности Zoom, Slack, Notion и профессионального видеомонтажа в единую среду, управляемую ИИ. Загрузите свои материалы, опишите задачу на естественном языке, и AI-комбайн самостоятельно найдёт нужные фрагменты, смонтирует таймлайн и отрендерит готовое видео.

## Ключевые возможности

- **AI Video Generation**: Промпт → RAG-поиск по ассетам → AI-монтаж → FFmpeg рендер.
- **Semantic Asset Search**: Поиск по видео и аудио с использованием векторных эмбеддингов (RAG).
- **Real-time Collaboration**: WebSocket синхронизация прогресса рендера и состояния таймлайна.
- **Production-Ready Backend**: Rate limiting, Circuit Breaker, Prometheus metrics, Sentry error tracking, immutable credit ledger.
- **Modern Frontend**: Next.js + Tailwind CSS + React Query + Zustand.
- **Commercial core**: Stripe + YooKassa, подписки, usage credits, self-hosted licenses, white-label hooks.

## Технологический стек

| Layer | Stack |
|-------|--------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL, Redis, Celery |
| **Frontend** | Next.js (App Router), TypeScript, Tailwind CSS, Zustand, React Query |
| **AI & Media** | AI Gateway (BYOK: xAI, OpenRouter, RouterAI), FFmpeg, pgvector |
| **Billing** | Stripe, YooKassa, immutable credit ledger (INSERT-only) |
| **Ops** | Docker Compose, Helm, GitHub Actions (unit + e2e) |

## Quick Start (Local Development)

### 1. Clone

```bash
git clone https://github.com/zametkikostik/VRAV-Studio.git
cd VRAV-Studio
```

### 2. Environment

```bash
cp .env.example .env
# Edit secrets if needed. Defaults work for local dev with Docker Postgres/Redis.
cp apps/web/.env.example apps/web/.env.local
```

### 3. Infrastructure

```bash
docker compose -f infra/docker/docker-compose.dev.yml up -d
```

### 4. Database migrations

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=".:../../packages/ai-gateway:../../packages/core"
export SECRET_KEY=dev-local-secret-change-me
alembic -c alembic.ini upgrade head
cd ../..
```

### 5. Backend API

```bash
cd apps/api
source .venv/bin/activate
export PYTHONPATH=".:../../packages/ai-gateway:../../packages/core"
export SECRET_KEY=dev-local-secret-change-me
uvicorn app.main:app --reload --port 8000
```

Optional worker (render jobs):

```bash
cd apps/worker
celery -A worker.celery_app worker -l info
```

### 6. Frontend

```bash
cd apps/web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

API docs (when API is up): [http://localhost:8000/docs](http://localhost:8000/docs).

## Demo Scenario (End-to-End Flow)

1. **Register / Login** — создайте аккаунт.
2. **Create Project** — новый проект в Dashboard.
3. **Upload Assets** — 2–3 видео/аудио в **Manage Assets**.
4. **AI Generation** — **AI Chat**, промпт, например:
   *«Сделай динамичный 15-секундный ролик о переезде, используй мои видео и добавь текстовые титры»*.
5. **Watch Progress** — прогресс-бар рендера (polling / WebSocket).
6. **Download** — ссылка на готовое видео при `completed`.
7. **Billing** — баланс и ledger: списание usage credits.

## Production readiness checklist

- [x] Rate limiting on AI endpoints (generate / search / chat)
- [x] Circuit breaker for external APIs (xAI, OpenRouter, Stripe, YooKassa)
- [x] Prometheus metrics (`GET /metrics`)
- [x] Sentry error tracking (optional DSN)
- [x] Immutable credit ledger (INSERT-only)
- [x] Stripe + YooKassa webhooks with signature / API verification
- [x] GitHub Actions CI (unit + e2e)

## Repository layout

```
apps/api       FastAPI backend
apps/web       Next.js frontend
apps/worker    Celery workers
apps/desktop   Electron shell (shared API)
packages/      Shared libraries (ai-gateway, core, …)
infra/         Docker, Helm, Alembic
```

## Security notes

- Never commit real `SECRET_KEY`, Stripe live keys, or Sentry DSNs.
- Production requires a strong `SECRET_KEY` (validator enforces this).
- Manual credit top-up is disabled outside development unless explicitly enabled.
- Webhook processing is idempotent by `provider_event_id`.

## License

Proprietary — see repository owner for commercial terms.
