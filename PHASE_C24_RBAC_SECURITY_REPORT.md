# PHASE C.2.4 — Organization-Scoped RBAC Security Report

**Branch:** `fix/phase-c24-rbac`  
**Baseline (origin/main):** `f7722c0239c77281b8ba922186e424fa0f849fb3`  
**Local PostgreSQL evidence:** 14 passed, 0 skipped (PostgreSQL 16.15)

## Architecture
- Organization-scoped roles on existing `OrganizationMember.role`
- Central policy: `app/services/rbac.py`
- DB role only; JWT claims never trusted
- Non-members → 404; insufficient role → 403
- Authoritative owner: `organizations.owner_user_id`

## Permission matrix
| Action | Owner | Admin | Editor | Viewer |
|--------|-------|-------|--------|--------|
| Read / download / keyframe / timeline list | ✓ | ✓ | ✓ | ✓ |
| Create / update / upload / timeline mutate | ✓ | ✓ | ✓ | ✗ |
| Delete project | ✓ | ✓ | ✗ | ✗ |
| Manage members / assign editor·viewer | ✓ | ✓ | ✗ | ✗ |
| Assign admin / transfer / delete org | ✓ | ✗ | ✗ | ✗ |

## Migration 017
- Force owner_user_id → owner
- Extra legacy owners → admin
- Unknown/empty/null → viewer
- CHECK constraint verified on live DB

## Route coverage
- projects.py, assets_upload.py, timelines.py, asset_keyframes.py — wired to RBAC
- organizations.py member-mgmt routes still absent (PARTIAL)

## Local test evidence
```
======================= 14 passed, 9 warnings in 24.28s ========================
```

## CI
Gate requires exact `(^|[^0-9])14 passed` with zero failed/skipped.
C.2.3.1 (20), C.2.3.2 (22), C.2.3.3 (8) gates preserved.

## Status
| Area | Status |
|------|--------|
| RBAC policy + migration | PASS |
| projects/assets/timelines/keyframes | PASS (when fully wired on branch) |
| Local PostgreSQL 16 tests | PASS (14/14) |
| CI Actions evidence | DEFERRED (pending full push + Actions) |
| Member-management HTTP | PARTIAL |
| Application-wide RBAC claim | PARTIAL (covered surfaces) |
