# Iteration 0 status

**GitHub HEAD at write time:** see latest main commits.

| ID | Topic | Status |
|----|-------|--------|
| P0.1 YooKassa | API-verified only; yk_test rejected in prod | PASS (unit) |
| P0.2 Licenses | paid order_id + PLAN_CAPS | PARTIAL (unit policy) |
| P0.3 Stripe | construct_event production fail-closed | PARTIAL (unit) |
| P0.4 Amount match | YooKassa path; Stripe billing path | PARTIAL |
| P0.5 Render non-blocking | no async_result.get; no inline FFmpeg | PARTIAL |
| P0.6 WS collab | JWT + project membership before accept | PARTIAL (structure tests) |
| P0.7 Credits | stream finally release; release_stale | PARTIAL |

## Test command (local)
```bash
cd apps/api && PYTHONPATH=.:../../packages/ai-gateway \\
  pytest tests/test_yookassa_security.py tests/test_stripe_webhook_security.py \\
         tests/test_license_issue_policy.py tests/test_ws_collab_auth.py -q
```
Last local run: **15 passed**.

## Remaining
- Live Stripe signed-event test vector
- HTTP e2e with Postgres
- Full jobs.py on main if diverged
- Wire CreditService.release_stale_reservations to call credits_stale helper if method missing on remote
- Celery beat schedule for vrav.credits.release_stale
