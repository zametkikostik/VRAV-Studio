# VRAV Studio — Local Smoke Checklist

Run on a machine with Docker + FFmpeg. Do not mark PASS without evidence.

## 1. Infra
```bash
cd infra/docker && docker compose -f docker-compose.dev.yml up -d
# wait health: postgres + redis
```

## 2. API migrate + start
```bash
cd apps/api
export DATABASE_URL=postgresql+asyncpg://vrav:vrav@localhost:5432/vrav
export REDIS_URL=redis://localhost:6379/0
alembic -c alembic.ini upgrade head   # includes 009 tariff seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3. Worker (optional)
```bash
cd apps/worker
celery -A worker.celery_app worker -l info
```

## 4. Unit (no DB)
```bash
cd apps/api
pytest tests/test_pricing.py tests/test_render.py tests/test_plan_generate.py tests/test_plan_from_brief.py -q
python ../../scripts/e2e_render_offline.py
```

## 5. HTTP (with DB)
1. Register / login → JWT  
2. Create org + project  
3. Upload sample mp4  
4. `POST /editing/plans/generate` mode=heuristics  
5. Create timeline, `POST /editing/plans/apply`  
6. `POST /jobs/render/timeline`  
7. `GET /jobs/{id}/export`  
8. `POST /billing/checkout` with plan_id=credits_100 (sandbox only)

## Production gates already in code
- Manual top-up blocked in production  
- Webhook signature / YooKassa fetch  
- Server-side pricing  
- JWT type=access in production  

## Explicit non-claims
Vision AI analysis and multi-tenant load tests are out of scope until measured separately.
