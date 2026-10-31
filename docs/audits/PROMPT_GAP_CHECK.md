# Prompt gap check

## Done on main
- Architecture, monorepo, FastAPI / Next / Electron skeleton
- Auth, orgs, projects, assets, timelines
- AI gateway (mock, xAI, OpenRouter, RouterAI) + BYOK
- Editing plan (mock / brief / LLM) + apply + render
- Jobs: non-blocking Celery enqueue; GET /jobs/{id} polls AsyncResult
- Billing: server pricing; Stripe amount/currency match + server credits; YooKassa API verify
- License paid-order gate + plan caps
- WS collab JWT + membership
- Credits reserve/commit/release; stream finally; Celery beat stale release
- Email password reset; GDPR; rate limit
- White-label models/API; Helm; docker-compose; CI
- Web PlanRenderPanel + editingApi
- Regression suites: test_iteration0_all_p0, test_main_commits_regression

## Residual
- Stripe signed-event test vector in CI (needs test secret)
- Full HTTP e2e with Postgres beyond offline FFmpeg script
- Electron production installers / code signing
- Subscriptions / recurrent billing polish
- WS Redis pub/sub multi-replica
- Deep vision/footage analysis pipeline
