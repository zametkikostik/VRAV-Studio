# VRAV Studio

**AI-first видео-редактор для YouTube-создателей и продакшенов.**

Забудьте о ручном поиске фрагментов и дорогих лимитах токенов. VRAV Studio автономно находит нужный материал в ваших исходниках, генерирует инфографику и монтирует черновой ролик за минуты, а не часы.

## Как мы решаем главные боли монтажа

1. **Лимиты токенов?** → AI Gateway с BYOK и умным роутингом (RouterAI) использует дешёвые модели для рутины и дорогие только для креатива. Экономия до 80% на API.
2. **Не может найти нужный момент?** → RAG Semantic Search анализирует транскрибации и визуальные теги ваших видео. Просто напишите: *«найди момент, где я говорю про релокацию»*.
3. **Нужна инфографика и титры?** → AI генерирует процедурный таймлайн (`overlay` треки), и FFmpeg автоматически накладывает текст и графику поверх видео.
4. **Часы в Premiere Pro?** → AI делает ~90% черновой сборки. Вы получаете готовый MP4 (или план монтажа для финального лоска).

## Технологический стек

| Layer | Stack |
|-------|--------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL (+ pgvector), Redis, Celery |
| **Frontend** | Next.js (App Router), TypeScript, Tailwind CSS, React Query, Zustand |
| **AI & Media** | AI Gateway (xAI, OpenRouter, RouterAI + BYOK), FFmpeg Compiler |
| **Billing** | Stripe, YooKassa, immutable credit ledger (INSERT-only) |
| **Production** | Rate limiting, Circuit Breaker, Prometheus `/metrics`, Sentry, CI (unit + e2e) |

## Quick Start (Local Development)

### 1. Клонирование

```bash
git clone https://github.com/zametkikostik/VRAV-Studio.git
cd VRAV-Studio
```

### 2. Окружение

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
# Настройте API-ключи (или оставьте dev-значения для локальных тестов)
```

### 3. Инфраструктура

```bash
docker compose -f infra/docker/docker-compose.dev.yml up -d
```

### 4. Миграции БД

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=".:../../packages/ai-gateway:../../packages/core"
export SECRET_KEY=dev-local-secret-change-me
alembic -c alembic.ini upgrade head
cd ../..
```

### 5. Backend

```bash
cd apps/api
source .venv/bin/activate
export PYTHONPATH=".:../../packages/ai-gateway:../../packages/core"
export SECRET_KEY=dev-local-secret-change-me
uvicorn app.main:app --reload --port 8000
```

Опционально worker (рендер-джобы):

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

Откройте [http://localhost:3000](http://localhost:3000).  
API docs: [http://localhost:8000/docs](http://localhost:8000/docs).

## Demo Scenario (End-to-End YouTube Workflow)

1. **Login** — войдите в систему.
2. **Create Project** — проект *«Relocation Vlog»*.
3. **Upload Assets** — 2–3 исходных видео в **Manage Assets** (транскрипт / embeddings для RAG).
4. **AI Generation** — **AI Chat**, промпт:  
   *«Сделай динамичный 30-секундный ролик о переезде, используй мои видео, добавь текстовые титры с ключевыми фразами»*.
5. **Watch Progress** — прогресс-бар рендера (polling / WebSocket).
6. **Download** — готовый MP4 при статусе `completed`.
7. **Check Billing** — прозрачное списание credits в **Billing** (immutable ledger).

## Production readiness checklist

- [x] Rate limiting на AI endpoints (generate / search / chat)
- [x] Circuit breaker для внешних API (xAI, OpenRouter, Stripe, YooKassa)
- [x] Prometheus metrics (`GET /metrics`)
- [x] Sentry error tracking (optional DSN)
- [x] Immutable credit ledger (только INSERT)
- [x] Stripe + YooKassa webhooks (подпись / API-verify, idempotent)
- [x] GitHub Actions CI (unit + e2e)

## Repository layout

```
apps/api       FastAPI backend
apps/web       Next.js frontend
apps/worker    Celery workers
apps/desktop   Electron shell (общий API)
packages/      Shared libraries (ai-gateway, core, …)
infra/         Docker, Helm, Alembic
```

## Security notes

- Не коммитьте реальные `SECRET_KEY`, live Stripe keys или Sentry DSN.
- В production обязателен сильный `SECRET_KEY` (валидатор это проверяет).
- Manual credit top-up по умолчанию выключен вне development.
- Webhook events идемпотентны по `provider_event_id`.

## License

Proprietary — условия у владельца репозитория.
