# Phase C.2.5 — Stage B Evidence Record

## Repository and branch

| Field | Value |
|-------|--------|
| Repository | `zametkikostik/VRAV-Studio` |
| Authorized branch | `recovery/vrav-c25-stage-b` |
| Verified commit SHA | `754fb0020c32b59125b717bb5046e946f9ea79d5` |
| Commit subject | `style(c25): resolve lifecycle Ruff gate findings` |

## GitHub Actions

| Field | Value |
|-------|--------|
| Run URL | https://github.com/zametkikostik/VRAV-Studio/actions/runs/43639985426 |
| Run ID | `43639985426` |
| Conclusion | **SUCCESS** (as reported for this commit; independently re-confirmed only via run URL reference in this evidence task) |

## PostgreSQL

| Field | Value |
|-------|--------|
| CI service image | `postgres:16.15-alpine` (workflow pin on this branch) |
| Verified server version | **16.15** (per successful Actions run report) |

## CI job results (from verified successful run on `754fb00`)

| Gate | Result |
|------|--------|
| Ruff (Stage B paths) | PASS |
| Generic unit tests | **489 passed, 90 skipped** |
| C.2.3.1 multi-tenant authorization | **20 passed, 0 skipped** |
| C.2.3.2 HTTP authorization | **22 passed, 0 skipped** |
| C.2.3.3 HTTP security evidence | **8 passed, 0 skipped** |
| C.2.4 organization RBAC HTTP | **14 passed, 0 skipped** |
| C.2.5 Stage B lifecycle | **11 passed, 0 skipped** |
| Migration 018 isolated upgrade → downgrade 017 → upgrade | **PASS** |

Notes:

- The **90 skipped** unit tests are the generic unit job only. They must **not** be described as “zero skips.”
- Mandatory PostgreSQL suites above each enforce zero skips in CI steps for that suite.

## Stage B lifecycle suite

| Field | Value |
|-------|--------|
| Module | `apps/api/tests/test_phase_c25_org_member_lifecycle.py` |
| Collection | 11 async tests (source inventory on `754fb00`) |
| CI step | `pytest tests/test_phase_c25_org_member_lifecycle.py -v --tb=short -ra` |
| Artifact name | `c25-stage-b-pytest-log` |
| Artifact SHA256 | **NOT VERIFIED** in this evidence pass (artifact bytes not re-downloaded) |

### Test inventory (source)

1. `test_list_members_owner_admin_ok_others_denied`
2. `test_add_member_and_duplicate_and_inactive_and_invalid_role`
3. `test_admin_cannot_assign_admin_owner_can`
4. `test_patch_role_idempotent_and_owner_protection`
5. `test_revoke_policies_and_owner_self_protection`
6. `test_transfer_ownership_and_invariant`
7. `test_soft_delete_org_and_404_and_project_remains`
8. `test_audit_failure_rolls_back_mutation`
9. `test_rejected_ops_do_not_write_success_audit`
10. `test_owner_invariant_inactive_owner_fail_closed`
11. `test_owner_invariant_soft_deleted_owner_fail_closed`

## Production artifacts (Stage A audit infrastructure)

| Path | Role |
|------|------|
| `infra/alembic/versions/018_security_audit_events.py` | Migration 018 |
| `apps/api/app/models/security_audit.py` | `SecurityAuditEvent` ORM |
| `apps/api/app/services/security_audit.py` | `record_security_audit()` allowlisted writer |

### `record_security_audit()` behavior (source inspection)

- Stages row on caller’s `AsyncSession` via `session.add`.
- **Never commits**; no background tasks.
- Allowlisted `event_type`: `member_added`, `member_role_changed`, `member_revoked`, `ownership_transferred`, `organization_deleted`.
- Allowlisted `outcome`: `success`, `denied`, `error`.
- `details` keys restricted to: `target_member_id`, `previous_owner_user_id`, `new_owner_user_id`, `reason_code`, `org_slug`.
- Invalid `event_type` / `outcome` → `ValueError`.
- Hash-chain / integrity chaining: **not implemented** in this project scope (source inspection).

## Stage A dedicated regression coverage

| Item | Status |
|------|--------|
| Dedicated Stage A test module | **ABSENT** on this branch |
| CI step for Stage A audit service | **ABSENT** (C.2.3.3 is not a substitute) |
| Allowlist / sanitization unit coverage | **MISSING** as dedicated suite |
| Isolated audit insert + read-back | **MISSING** as dedicated suite |
| Forced audit failure → mutation rollback | **PARTIAL** — covered via Stage B `test_audit_failure_rolls_back_mutation` (lifecycle path only) |
| Rejected ops without success audit | **PARTIAL** — Stage B `test_rejected_ops_do_not_write_success_audit` |

## Limitations and unresolved gaps

1. No dedicated Stage A security-audit regression module or CI gate.
2. Artifact SHA256 for `c25-stage-b-pytest-log` not re-verified in this pass.
3. Stage B.1 (concurrency, exact audit cardinality certification) **NOT STARTED**.
4. Missing-Owner-user invariant path not testable under current FKs (`users.id` referenced by membership and `owner_user_id`).
5. This document records evidence for commit `754fb00` / run `43639985426` as supplied and cross-checked against branch source; it does not re-execute the full Actions pipeline.

## Scope confirmation

- Branch: `recovery/vrav-c25-stage-b` only for this evidence work.
- `main`, PR #54, `fix/phase-c24-rbac`: not modified by this evidence task.
- Stage B.1: not started.
