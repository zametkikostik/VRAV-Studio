# Production Readiness

**Updated:** 2026-10-31

## Must-pass before live traffic

| Gate | Status |
|------|--------|
| Manual credit top-up disabled in production | DONE |
| Webhook signature / YooKassa fetch verify | DONE |
| Credits only after paid webhook | DONE |
| Server-side checkout pricing | DONE |
| Upload size + content-type limits | DONE |
| License issue/revoke roles | DONE |
| JWT type=access in production | DONE |
| Tariff plan seed migration 009 | DONE (code) |
| Real AI footage analysis | NOT DONE |
| HTTP e2e on Postgres | NOT RUN in this environment |
| Celery async render in production | PARTIAL (inline fallback) |
| Live payment keys + monitoring | OPS |

## Evidence
- Unit: pricing 6 passed, yookassa fetch, render, editing plan
- Offline e2e: `scripts/e2e_render_offline.py` PASS
- GitHub main includes security + billing + render packs

## Explicit non-claims
Not production-ready for real AI editing quality or multi-tenant load testing until Postgres e2e and AI plan generation are verified.
