# Iteration 8 — Baseline Audit

**Date:** 2026-11-04  
**Branch inspected:** `main`  
**HEAD SHA:** `9ef6dac7af4c2b21dd8ee852212d23dc218900a1`  
**Scope:** Read-only audit. No application code was modified during Phase 0.

Classification legend used below:

| Tag | Meaning |
|-----|---------|
| **CONFIRMED** | Verified in source or by public CI run evidence |
| **SUSPECTED** | Plausible defect; needs behavioral proof |
| **DEFERRED** | Cannot verify without infra/credentials in this environment |

---

## 1. Repository & CI status

### 1.1 Recent history (main)

| SHA | Note |
|-----|------|
| `9ef6dac` | Merge PR #20 — Iter7 Final Demo Prep (YouTube README) |
| `5cbb56b` | Merge PR #18 — Billing UI + modular billing routes |
| Prior | Iter6 hardening, Iter5 RAG/AI agent, security P0 packs |

### 1.2 CI (GitHub Actions workflow `CI`)

Workflow: `.github/workflows/ci.yml`

Jobs:

1. **unit** — `pytest -q tests/` in `apps/api` without Postgres/Redis env (in-process / mocks).
2. **e2e** — Postgres 16 + Redis services; `alembic upgrade head`; offline render script; optional web build.

Public recent runs on `main` (CONFIRMED via GitHub API):

| Run | Conclusion | HEAD | URL |
|-----|------------|------|-----|
| 41894400488 | **success** | `9ef6dac` | https://github.com/zametkikostik/VRAV-Studio/actions/runs/41894400488 |
| 41893594652 | success | `3a14c27` | https://github.com/zametkikostik/VRAV-Studio/actions/runs/41893594652 |
| 41892218856 | success | `5cbb56b` | https://github.com/zametkikostik/VRAV-Studio/actions/runs/41892218856 |

**CONFIRMED:** Unit + e2e CI green at current HEAD.  
**CONFIRMED:** Unit job does **not** run PostgreSQL-backed billing concurrency tests (no DB service on unit job).

---

## 2. Architecture snapshot

### 2.1 Backend (`apps/api`)

- FastAPI + SQLAlchemy async + Alembic
- Modular billing: `billing.py` (router/helpers), `billing_plans.py`, `billing_checkout.py` (Stripe), `billing_yookassa.py`, `billing_ledger.py`
- AI Gateway package: `packages/ai-gateway`
- Services: credits, payment, yookassa, pricing, render, ffmpeg_compiler, rag_search, ai_agent, license, etc.

### 2.2 Frontend (`apps/web`)

Next.js App Router pages present under `src/app/`:

- Auth: login/register
- Dashboard, projects, assets, timeline, AI chat, search, billing
- Settings

**CONFIRMED:** UI routes exist for Iter7 surfaces.  
**DEFERRED:** Full browser E2E against live API not executed in this audit.

### 2.3 Worker (`apps/worker`)

- Celery app with `beat_schedule` including `vrav.credits.release_stale`
- Task `credits_release_stale` in `worker/tasks.py`

**CONFIRMED:** Beat entry and task name exist in code.  
**DEFERRED:** Live Beat process execution not observed in this environment.

### 2.4 Desktop (`apps/desktop`)

Electron shell (`electron/`, `electron-builder.yml`) present.

**DEFERRED:** Code signing / packaged installer not verified.

### 2.5 Infra

- Docker Compose (dev/prod/redis-ha)
- Helm chart `infra/helm/vrav-studio`
- Alembic versions `001`–`013` under `infra/alembic/versions/`
- Migrations applied in CI e2e job

---

## 3. Database & migrations

| Rev | Purpose |
|-----|---------|
| 001–003 | Users/orgs, projects/assets/jobs, AI usage |
| 004 | Billing core |
| 005–006 | Licenses, white-label |
| 007–008 | BYOK, timelines/collab |
| 009 | Tariff seed |
| **010** | Partial unique index `uq_payment_order_succeeded` on `payments(order_id) WHERE status='succeeded'` |
| 011 | JWT revoke / token_version |
| 012 | Asset transcript + embedding |
| 013 | API request logs |

**CONFIRMED:** Double-grant at payment-row level is constrained by migration 010.  
**CONFIRMED:** `Order` model fields: `id`, `organization_id`, `subscription_id`, `amount`, `currency`, `status`, `created_at` — **no** `plan_id`, **no** `credits_to_grant`, **no** immutable pricing snapshot JSON.

---

## 4. Billing architecture (P0 focus)

### 4.1 Checkout

`create_checkout` / YooKassa checkout:

- Server-side `resolve_checkout_price`
- Persists `Order` with amount/currency only
- Puts `plan_id` and `credits_to_grant` into **provider metadata**, not into Order columns

**CONFIRMED:** No immutable order snapshot table/column for plan/credits at checkout time.

### 4.2 Stripe webhook (`billing_checkout.py`)

Present guards (CONFIRMED in source):

- Signature via `StripePaymentProvider.handle_webhook` → `construct_event` / verify path
- WebhookEvent unique `(provider, provider_event_id)`
- Pay status gate (`paid` / `succeeded` / …)
- Order lookup by metadata `order_id`
- Amount / currency mismatch → ignore
- Prior succeeded payment on order → `order_already_paid`
- Unique provider payment id

Grant path (CONFIRMED):

- Credits recomputed with `resolve_checkout_price(db, plan_id=…)` at webhook time
- **Not** taken solely from a frozen order snapshot

**CONFIRMED gaps vs Iteration 8 requirements:**

| Requirement | Status |
|-------------|--------|
| Immutable checkout snapshot on Order | **Missing** (CONFIRMED) |
| `SELECT … FOR UPDATE` on order during grant | **Missing** in checkout handlers (CONFIRMED: zero `for_update` in billing_checkout/yookassa) |
| Fail-closed on missing amount/currency | **Partial** — mismatch checked when present; need behavioral proof for null amount |
| Explicit webhook processing states (RECEIVED/PROCESSING/…) | **Not modeled** — only WebhookEvent insert + processed_at (CONFIRMED) |
| Behavioral Postgres tests for concurrent double-grant | **Not primary** — many tests are source `read_text()` assertions (CONFIRMED) |

### 4.3 YooKassa (`billing_yookassa.py` + `services/yookassa.py`)

**CONFIRMED:**

- `handle_webhook` with provider verification path (`verified_via_api`)
- Rejects when not `succeeded` or not verified
- Amount/currency mismatch vs order
- `order_already_paid` path
- Credits via `resolve_checkout_price` at grant time (same snapshot gap)

**SUSPECTED:**

- Notification vs payment identity handling under rapid pending→succeeded retries needs DB-backed tests
- Concurrent duplicate webhooks rely on unique indexes + app checks without row lock on Order

### 4.4 Credit ledger (`services/credits.py`)

**CONFIRMED:**

- `CreditAccount` with non-negative checks
- `reserve` / `commit` / `release` / `topup`
- Account row `with_for_update()` on mutate paths
- Ledger entries on reserve/commit/release
- Idempotency key support on reservations
- Stale reservation release task registered

**SUSPECTED:**

- Concurrent reservation race beyond single-row lock scenarios not proven in CI unit job
- Webhook `topup` path may not share the same serialization story as order payment uniqueness

---

## 5. AI Gateway & media pipeline

| Component | Evidence | Notes |
|-----------|----------|-------|
| AI Gateway adapters | Code in packages + API | mock / xAI / OpenRouter / RouterAI |
| RAG / embeddings | Migration 012, services | **DEFERRED** quality of real embeddings |
| TimelineDefinition + FFmpeg compiler | `ffmpeg_compiler.py`, Iter4 tests | Argv-only (no shell) — CONFIRMED pattern in prior work |
| Render | `render.py`, offline e2e script | CI e2e runs offline script — CONFIRMED success at HEAD |
| AI agent generate | Endpoint + tests | Mock-friendly; **DEFERRED** live provider quality |

**CONFIRMED:** Product README claims autonomous high-quality montage; deep visual analysis still marked NOT DONE in older `PRODUCTION_READINESS.md` (2026-10-31). Treat marketing claims as **aspirational** until Phase 4 behavioral tests expand.

---

## 6. WebSocket & multi-replica

- `ws_jobs.py` — job progress; auth before accept; DB poll pattern
- `ws_collab.py` — collab tickets; in-process `_tickets` (source tests assert `_tickets`)

**CONFIRMED:** Collab ticket store is process-local.  
**CONFIRMED:** Multi-replica shared room bus (Redis Pub/Sub) not evidenced as complete for collab.  
→ Multi-instance WS collab: **DEFERRED (INFRA SCOPE)** / architecture limitation to document, not PASS.

---

## 7. Test coverage (apps/api)

- ~57 test modules, ~250 `test_*` functions (count from source)
- Mix of:
  - Unit / pure logic
  - Source-string security regressions (billing, JWT, etc.)
  - Some async service tests with mocks

**CONFIRMED:** Primary Stripe/YooKassa financial correctness proofs are largely **source substring** tests (`test_stripe_billing_amount.py`, parts of `test_security_*`), not PostgreSQL concurrent behavioral suites.

**CONFIRMED gap for Iter8 Phase 2:** need DB-backed tests listed in the engineering prompt (missing amount, concurrent webhooks, pending→success YooKassa, etc.).

---

## 8. Security risks (billing-centric)

| ID | Finding | Class |
|----|---------|-------|
| B1 | No immutable order snapshot for plan/credits; grant re-resolves plan at webhook time | **CONFIRMED** defect vs target design |
| B2 | No `FOR UPDATE` on Order during credit grant | **CONFIRMED** |
| B3 | Webhook lifecycle states not explicit (retryable vs terminal) | **CONFIRMED** |
| B4 | Financial correctness mainly source-asserted | **CONFIRMED** test gap |
| B5 | Credits metadata in provider payload could diverge from DB order amount (mitigated by amount check; credits still re-priced) | **CONFIRMED** / residual |
| B6 | Multi-replica collab WS | **CONFIRMED** limitation |
| B7 | Live payment / sandbox provider E2E | **DEFERRED (INFRA SCOPE)** |
| B8 | Electron code signing | **DEFERRED (INFRA SCOPE)** |

Older security packs (YooKassa API verify, Stripe construct_event, license paid-order gate, rate limits, Sentry, circuit breaker) remain in tree and CI is green — treat as **working baseline**, not to be rewritten.

---

## 9. Production blockers (ordered)

1. **P0** Immutable checkout snapshot + webhook validation against snapshot  
2. **P0** Atomic order lock + proven single credit grant under concurrency (Postgres tests)  
3. **P0** Expand YooKassa state-transition behavioral tests  
4. **P1** Credit reservation concurrency matrix beyond current unit coverage  
5. **P1** Honest documentation of AI/FFmpeg capability boundaries  
6. **P2** Multi-replica WS strategy  
7. **OPS** Live keys, monitoring, signed desktop builds  

---

## 10. Explicit non-actions (Phase 0)

- No application logic changes in Phase 0  
- No billing rewrites in this step  
- No test deletions  
- No claim of production-ready payments beyond existing CI green + known gaps above  

---

## 11. Recommended next step

**Step 1:** Continue on branch `recovery/iteration-8-stabilization` (from `9ef6dac`).  
**Step 2:** Implement immutable order snapshot + migration (preserve historical orders).  
**Step 3:** Row-level lock + idempotent grant; then PostgreSQL behavioral tests.

Do not mark Stripe/YooKassa financial safety **PASS** until Phase 2 tests execute against Postgres with concurrent delivery scenarios.
