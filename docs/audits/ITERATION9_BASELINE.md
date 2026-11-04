# Iteration 9 — Baseline Audit (Read-Only)

**Date:** 2026-11-04  
**Branch inspected:** `main`  
**HEAD SHA:** `409261e06e3c5bcc975b73cd786352ae3fd4672f`  
**Prior iteration:** Iteration 8 (merged PR #21)  
**Scope:** Read-only. No application code modified during this phase.

Classification:

| Tag | Meaning |
|-----|---------|
| **CONFIRMED** | Verified in source at HEAD |
| **SUSPECTED** | Plausible; needs Postgres behavioral proof |
| **DEFERRED** | Needs infra / live provider sandbox |

---

## 1. CI status at HEAD

| Run | Conclusion | HEAD | URL |
|-----|------------|------|-----|
| **41898291480** | **success** | `409261e` | https://github.com/zametkikostik/VRAV-Studio/actions/runs/41898291480 |

Workflow `.github/workflows/ci.yml`:

- **unit:** `pytest -q tests/` without Postgres service.
- **e2e:** Postgres 16 + Redis; `alembic upgrade head`; `scripts/e2e_render_offline.py`.

**CONFIRMED:** Unit + offline e2e green at HEAD.  
**CONFIRMED:** No dedicated PostgreSQL billing concurrency job.  
**CONFIRMED:** No full HTTP product E2E job (auth → upload → plan → render → credits).

---

## 2. Iteration 8 assets present on main

| Asset | Status |
|-------|--------|
| Migration `014_order_checkout_snapshot.py` | Present |
| `Order.plan_id`, `credits_to_grant`, `pricing_kind`, `provider`, `snapshot` | Present (nullable) |
| `apps/api/app/services/billing_grant.py` | Present |
| `load_order_for_update` (`SELECT … FOR UPDATE`) | Present |
| Stripe/YooKassa checkout persists snapshot | Present |
| Fail-closed `amount_missing` / `currency_missing` | Present on both webhooks |
| Grant uses frozen `credits_to_grant` (no re-price on grant) | Present |
| Source tests `test_billing_order_snapshot.py` | Present |

---

## 3. Architecture (billing path)

```
Checkout → Order{amount, currency, credits_to_grant, snapshot}
       → Provider session (metadata.order_id)

Webhook → signature / API verify
       → WebhookEvent insert (unique provider + provider_event_id)
       → amount/currency vs Order
       → load_order_for_update
       → grant_paid_order_credits → Payment + CreditService.topup
```

DB constraints (CONFIRMED in models/migrations):

- `uq_payment_provider_id` on `(provider, provider_payment_id)`
- `uq_payment_order_succeeded` partial unique on `order_id WHERE status='succeeded'` (migration 010)
- `uq_webhook_provider_event` on `(provider, provider_event_id)`

---

## 4. Confirmed remaining defects (Iteration 9 P0 targets)

### Y9-1 — YooKassa: payment ID used as webhook event identity (CONFIRMED)

In `billing_yookassa.py`:

```python
event_id = result.payment_id
…
db.add(WebhookEvent(… provider_event_id=str(event_id), … processed_at=…))
# THEN status check:
if not result.verified_via_api or result.status != "succeeded":
    return ignored  # but WebhookEvent already reserved for this payment_id
```

**Effect:** First notification for a payment (often `pending`) inserts `WebhookEvent` keyed by **payment id**. A later `succeeded` notification for the **same payment** hits `already_processed` and **never grants credits**.

**CONFIRMED** defect against Iter9 requirement “pending must not permanently suppress succeeded”.

### Y9-2 — Stripe same pattern risk (CONFIRMED for event-id uniqueness; lower severity if Stripe event IDs are unique per delivery)

Stripe uses `result.raw["id"]` (Stripe event id) when present — better separation than YooKassa.  
Still inserts `WebhookEvent` before full financial validation; failed validation marks event processed without a retryable state model.

### Y9-3 — `grant_paid_order_credits` marks order paid before payment uniqueness check (CONFIRMED)

```python
order.status = "paid"          # line before dup payment check
dup = await db.execute(… provider_payment_id …)
if dup is not None:
    return "payment_already_recorded", None  # order already status=paid, no Payment/credit
```

**CONFIRMED:** Can leave `order.status == "paid"` without a corresponding succeeded Payment / credit grant for this path.

### Y9-4 — Non-positive amount/grant gate is OR-logic (CONFIRMED)

```python
if amount <= 0 and grant <= 0:
    return "zero_amount", None
```

Allows `amount <= 0` with `grant > 0` (and vice versa) to proceed. Violates “amount must be strictly positive” / consistent financial validation.

### Y9-5 — No Postgres concurrency / state-transition behavioral suite (CONFIRMED)

Billing tests are predominantly source-string and unit mocks (`test_billing_order_snapshot.py`, `test_stripe_*`, `test_yookassa_*`).  
No test exercises overlapping sessions + real `FOR UPDATE` / unique constraint races on Postgres.

### Y9-6 — Webhook processing states incomplete (CONFIRMED)

`WebhookEvent` has `processed_at` / `processing_error` only. No explicit RECEIVED / PROCESSING / RETRYABLE_FAILURE / TERMINAL_FAILURE.  
Failed pending YooKassa still “consumes” the unique key (see Y9-1).

### Y9-7 — Snapshot integrity soft only (CONFIRMED)

Snapshot columns nullable; no DB trigger preventing mutation of `snapshot` / `credits_to_grant` after insert. Application does not re-write snapshot on grant (good), but immutability is not enforced at DB level.

### Y9-8 — Credit reservation uniqueness (SUSPECTED)

`CreditReservation.idempotency_key` is nullable without a confirmed partial unique index in model/migration review for scoped uniqueness. Needs migration inventory verification in Phase 8/9 implementation.

---

## 5. What Iteration 8 already fixed (do not regress)

- Server-side pricing at checkout (`resolve_checkout_price`).
- Immutable *intent* of credits via Order columns + snapshot JSON.
- No grant from provider metadata alone when snapshot missing (`missing_snapshot`).
- Amount/currency mismatch ignore paths.
- Order row lock before grant.
- Migration 010 one succeeded payment per order.
- Stripe `construct_event` / production secret rules (existing payment service).
- YooKassa API fetch verification flag (`verified_via_api`).

---

## 6. Test & CI gaps for Iter9

| Requirement | Current evidence |
|-------------|------------------|
| Pending → succeeded YooKassa | **Missing** behavioral test; code path broken (Y9-1) |
| Concurrent webhooks | **Missing** Postgres test |
| HTTP E2E product flow | **Missing** (only offline render) |
| Live/sandbox provider | **DEFERRED (INFRA SCOPE)** |

---

## 7. Production blockers ordered for Iteration 9

1. **P0** Fix YooKassa event identity vs payment identity + pending→succeeded.  
2. **P0** Fix grant sequence (payment uniqueness / constraints before or with atomic paid+grant).  
3. **P0** Strict positive amount and grant validation.  
4. **P0** PostgreSQL behavioral tests (concurrency + state transitions).  
5. **P1** Credit reservation matrix + idempotency constraint review.  
6. **P1** HTTP E2E + CI job with Postgres.  
7. **DEFERRED** Live Stripe/YooKassa sandbox verification.

---

## 8. Explicit non-actions (this document phase)

- No application code changes.
- No migration changes.
- No claim that green CI proves financial correctness under retries.

## 9. Recommended next step

Branch: `recovery/iteration-9-billing-integrity` from `409261e`.  
First code change: YooKassa webhook idempotency key strategy + grant sequence fix + regression tests, then Postgres integration suite.

**Financial readiness at baseline: NOT READY** (Y9-1 alone is a showstopper for YooKassa success-after-pending).
