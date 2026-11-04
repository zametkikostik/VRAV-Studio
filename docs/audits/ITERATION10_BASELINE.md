# Iteration 10 — Baseline Audit (Read-Only)

**Date:** 2026-11-04  
**Branch inspected:** `main`  
**HEAD SHA:** `ae2e9f505c919fc640df973024c3404e4a4ad025`  
**Prior:** Iteration 9 merged PR #22  
**Scope:** Read-only. No application code modified in Phase 0.

Classification: **CONFIRMED** | **SUSPECTED** | **DEFERRED (INFRA SCOPE)**

---

## 1. CI at baseline

| Item | Value |
|------|--------|
| Latest referenced run | https://github.com/zametkikostik/VRAV-Studio/actions/runs/41905075038 |
| Jobs | unit, e2e, web (reported green by operator) |
| e2e includes | offline render, Postgres billing tests, HTTP E2E smoke |

**CONFIRMED:** Iter9 assets are on main (YooKassa `payment_id:event_type`, grant sequence, Postgres integration tests, HTTP E2E path fix).

---

## 2. Safeguards already in place (do not regress)

| Safeguard | Evidence |
|-----------|----------|
| Order checkout snapshot fields + migration 014 | models + alembic |
| Grant from frozen `credits_to_grant` | `billing_grant.py` |
| `SELECT … FOR UPDATE` on order | `load_order_for_update` |
| Payment insert before `order.status=paid` | `billing_grant.py` |
| Fail-closed missing amount/currency | Stripe + YooKassa webhooks |
| YooKassa notification key ≠ payment id alone | `notification_id = f"{payment_id}:{event_type}"` |
| Unique payment constraints | `uq_payment_provider_id`, `uq_payment_order_succeeded` |
| Postgres behavioral tests | `test_billing_postgres_integration.py` (skip without DATABASE_URL) |

---

## 3. Confirmed defects / gaps for Iteration 10

### I10-1 — Stripe grant result handling incomplete (CONFIRMED)

YooKassa handles:

- `order_already_paid`
- `missing_snapshot`
- `invalid_amount` / `invalid_grant` / `payment_already_recorded`

Stripe only special-cases `order_already_paid` and `missing_snapshot`.  
For `invalid_amount`, `invalid_grant`, `payment_already_recorded` (and any future non-`granted` reason), Stripe falls through to:

```json
{"status": "processed", "credits_granted": null}
```

**CONFIRMED:** Webhook can report **processed** without a successful grant. Violates “never report successful processing when payment was not granted.”

### I10-2 — WebhookEvent marked processed before grant completes (CONFIRMED)

Both Stripe and YooKassa insert `WebhookEvent` with `processed_at` **before** amount checks and `grant_paid_order_credits`.

Effects:

- Financial rejection still consumes the unique event key (usually OK for terminal ignore).
- Transient DB failure **after** event insert but **before** grant may not retry if the event is treated as already processed.
- No explicit states: RECEIVED / PROCESSING / RETRYABLE_FAILURE / TERMINAL.

### I10-3 — HTTP E2E weak assertions / not pure HTTP for billing (CONFIRMED)

`scripts/e2e_http_api.py`:

- Prints `/health` status; does not `assert` 200.
- Org/project success not strictly required.
- Billing verified via **direct** `grant_paid_order_credits` service call, not webhook HTTP endpoint.

Does not satisfy Iter10 requirement that HTTP smoke assert status/schema and not call service functions as “HTTP tests.”

### I10-4 — Pricing_kind invariants not explicit in grant path (CONFIRMED)

`pricing.py` kinds: `credits`, `subscription`, `license` (license has `credits=0`).

Grant allows `grant == 0` if `amount > 0` (valid for license).  
No explicit test that:

- `kind=credits` requires `credits_to_grant > 0`
- client cannot override snapshot
- Stripe zero-decimal currencies handled correctly (if any are supported)

### I10-5 — Provider sandbox verification absent (DEFERRED / missing)

No optional tests gated on `STRIPE_*` / `YOOKASSA_*` sandbox secrets.  
No CI distinction for sandbox PASS vs SKIP.

### I10-6 — Concurrent webhook HTTP path (SUSPECTED)

Postgres tests cover concurrent **grant** helper sessions.  
Concurrent delivery of the **same Stripe event id** / same YooKassa notification_id through the full webhook HTTP handler is less directly tested.

### I10-7 — Failure mid-ledger (SUSPECTED)

No behavioral test that forces ledger insert failure after Payment insert and asserts full rollback (depends on session transaction boundaries in FastAPI `get_db`).

---

## 4. Pricing / credit model (as coded)

| kind | typical credits | amount |
|------|-----------------|--------|
| credits | > 0 | > 0 |
| subscription | may be > 0 | > 0 |
| license | 0 | > 0 |

Grant must not reject legitimate zero-credit license orders solely because credits are zero; must reject non-positive **amount**.

---

## 5. Production blockers ordered for Iteration 10

1. **P0** Align Stripe webhook outcomes with YooKassa for all grant reasons.  
2. **P0** Safer webhook processing semantics (avoid “processed” without grant; retryable vs terminal).  
3. **P0** Expand Postgres tests: duplicate event, payment on other order, rollback invariants.  
4. **P1** Harden `e2e_http_api.py` assertions; webhook HTTP fixtures.  
5. **P1** Optional sandbox tests (SKIP when no secrets).  
6. **P1** Evidence matrix + readiness docs.

---

## 6. Explicit non-actions (Phase 0)

- No application code changes.
- No migration changes.
- No claim of live-payment production readiness.

## 7. Financial readiness at baseline

**NOT READY** for live money — pending I10-1 consistency fix, stronger webhook state semantics, and sandbox evidence (DEFERRED until credentials).

Recommended branch: `recovery/iteration-10-billing-closure` from `ae2e9f5`.
