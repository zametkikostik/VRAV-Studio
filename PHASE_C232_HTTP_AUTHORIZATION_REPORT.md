# PHASE C.2.3.2 — HTTP-Level Multi-Tenant Authorization Verification Report

## 1. Baseline
- **Expected baseline commit**: `d5c58563bb15aaae3f8541b357f040ac7e26523c`
- **Verified main HEAD at branch creation**: `d5c58563bb15aaae3f8541b357f040ac7e26523c`
- **Branch**: `test/phase-c232-http-authorization`
- **Head commit** (after test + CI + report): see PR
- **PR title**: `test(c232): HTTP-level multi-tenant authorization verification`

## 2. Scope
Strictly **test-only** security verification:
- Real FastAPI ASGI HTTP requests (`httpx.ASGITransport` + `AsyncClient`)
- Real PostgreSQL 16 (same CI service as C.2.3.1)
- Real authentication tokens (`create_access_token`)
- No production code changes
- No mocks of authorization, DB sessions, or HTTP responses
- Existing C.2.3.1 internal-helper matrix preserved (20 tests)

## 3. PostgreSQL / CI
- **PostgreSQL image**: `postgres:16-alpine`
- **DATABASE_URL**: `postgresql+asyncpg://vrav:vrav@localhost:5432/vrav`
- **Exact test command**:
  ```bash
  pytest tests/test_phase_c232_http_authorization.py -v --tb=short
  ```
- **Enforced counts**: 22 passed, 0 skipped (hard-fail on any skip/fail)
- **Preserved gates**: C.2.3.1 (20 passed), Phase B.2.1, Billing, Unit, Web, E2E, Docker Runtime

## 4. Test module
`apps/api/tests/test_phase_c232_http_authorization.py` — **22 tests**

### Identities (seeded via `c231_pg_helpers._seed_two_tenants`)
| Identity   | Role on Org A | Membership Org B |
|-----------|---------------|------------------|
| Owner A   | owner         | none             |
| Editor A  | editor        | none             |
| Outsider  | none          | none             |
| Owner B   | none          | owner            |

### Endpoints exercised (real routes from `projects.py` / `assets_upload.py`)
| Scenario | Method + path |
|----------|---------------|
| Project read | `GET /projects/{id}` |
| Project update | `PATCH /projects/{id}` |
| Project soft-delete | `DELETE /projects/{id}` |
| Org project list | `GET /organizations/{org_id}/projects` |
| Asset list | `GET /projects/{id}/assets` |
| Asset content | `GET /projects/{id}/assets/{asset_id}/content` |

## 5. Role policy (documented, not redefined)

From production code inspection (`_get_project_for_user`, `_project_for_user`, `_require_org_member`):

- **Project access** is **membership-only**. `OrganizationMember.role` is **not** evaluated.
- Owner and Editor therefore share the same project read / update / soft-delete / asset list / download surface under the current contract.
- Outsider and cross-tenant Owner B receive **404** on project-scoped routes (intentional non-disclosure) and **403** on org-member-gated list routes.

This is **POLICY DECISION REQUIRED** if product intent is stricter RBAC (e.g. editor cannot delete). Tests assert **current** behavior only; they do not introduce a new policy.

## 6. Scenario coverage
22 HTTP scenarios: Owner A / Editor A / Outsider / Owner B × read / update / soft-delete / asset list / download / cross-project IDOR / org list, with DB state assertions on denied mutations.

## 7. Security assertions covered
- Denied requests return existing intentional status codes (404 project-scoped, 403 org-member).
- No unauthorized resource body on denial.
- Denied mutations leave DB fields unchanged (`name`, `deleted_at`).
- Soft-deleted projects inaccessible via normal read.
- Soft-deleted assets rejected on content route.
- Cross-tenant / cross-project asset IDs cannot bypass project membership.
- Denial responses do not leak `storage_key`, local paths, or signed URLs.

## 8. Production defects
None discovered that require stopping this PR.

## 9. Changed files
- `apps/api/tests/test_phase_c232_http_authorization.py` (new)
- `.github/workflows/ci.yml` (extend e2e job with C.2.3.2 gate)
- `PHASE_C232_HTTP_AUTHORIZATION_REPORT.md` (this file)

## 10. CI run URLs
To be filled after PR checks complete.

## 11. Phase gate
Phase C.2.3.2 is **PASS** only when CI shows 22 passed / 0 skipped, C.2.3.1 remains 20 passed, all jobs green, no production code changes.

**Phase D — Editing Plan — remains BLOCKED** pending independent review of this evidence.
