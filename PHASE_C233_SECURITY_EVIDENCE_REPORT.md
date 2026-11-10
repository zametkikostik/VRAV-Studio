# PHASE C.2.3.3 — Final Multi-Tenant Security Evidence Closure

## Status
**PARTIAL** pending independent CI log review after PR green run.

Classification notes:
- Positive authorized download with exact bytes: covered by new tests (requires CI confirmation).
- Negative cross-tenant download: covered.
- RBAC role boundary: **POLICY DECISION REQUIRED** (documented, not changed).

## Baseline
`970e0920a893ed27b546b0ab81c74fc8d24f2b8c`

## Scope
Test-only. No production Python/TS/SQL/migrations/authorization changes.

### Changed files
1. `apps/api/tests/test_phase_c233_security_evidence.py` (new, 8 tests)
2. `.github/workflows/ci.yml` (C.2.3.3 gate after C.2.3.2, before HTTP E2E smoke)
3. `PHASE_C233_SECURITY_EVIDENCE_REPORT.md`

### Preserved
- C.2.3.1: 20 passed gate
- C.2.3.2: 22 passed gate (NullPool harness intact)
- HTTP API E2E smoke after security gates

## Storage
Uses production `LocalStorageProvider` (`STORAGE_BACKEND=local`, `LOCAL_STORAGE_PATH=/tmp/vrav-c233-storage`).
Tests plant real object bytes via `get_storage().put(...)` matching seeded `Asset.storage_key`, then call
`GET /projects/{id}/assets/{asset_id}/content`.

## Test matrix (8)

| ID | Scenario | Expect |
|----|----------|--------|
| A1 | Owner A download planted object | 200 + exact PAYLOAD_A |
| A2 | Editor A download (membership contract) | 200 + exact PAYLOAD_A |
| B1 | Outsider → project A asset | 404, no payload leak |
| B2 | Owner B → project A asset | 404, no payload leak |
| B3 | asset_b under project_a path (owner A) | 404, no payload leak |
| B4 | asset_a under project_b path (owner A) | 404, no payload leak |
| B5 | Soft-deleted asset_a (owner A) | 404, no payload leak |
| B6 | Outsider → project B asset | 404, no payload leak |

## POLICY DECISION REQUIRED
Observed production behavior (unchanged in this PR):
- Project/asset gates use **OrganizationMember membership** + `deleted_at IS NULL`.
- `OrganizationMember.role` is **not** evaluated as a separate project-level permission boundary
  for GET/PATCH/DELETE project or asset content download in the tested routes.
- Editor membership currently receives the same project-level access surface as owner membership
  for the covered scenarios.

Product must decide whether role-based restriction is required. This is **not** auto-classified as a defect.

## CI command
```bash
pytest tests/test_phase_c233_security_evidence.py -v --tb=short
# enforce: 8 passed, 0 skipped
```

## Limitations
- Local FS storage only in this gate (not S3/MinIO path).
- Unit job still runs full `pytest tests/` without DATABASE_URL → C.2.3.x modules skip there by design; e2e job is the mandatory gate.
- Overall multi-tenant security assurance is not PASS solely because CI is green; independent log review required.

## Phase D
**BLOCKED** until independent review of CI evidence for C.2.3.1 / C.2.3.2 / C.2.3.3.
