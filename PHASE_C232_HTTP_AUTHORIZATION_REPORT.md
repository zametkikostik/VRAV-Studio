# PHASE C.2.3.2 — HTTP-Level Multi-Tenant Authorization

## Status
**PASS** (harness repaired — event-loop isolation)

## Root cause of CI failure (run 42712552295)

`pytest.ini` / `pyproject.toml` set:

```
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

Each test therefore runs on a **fresh event loop**.

Production `app/db/session.py` creates a **module-level** `AsyncEngine` and `AsyncSessionLocal` at import time. ASGI requests via `Depends(get_db)` use that global pool.

The original C.2.3.2 module also opened a **second** engine per test for seeding (`_engine_session()`), called `create_app()` (which continues to use the global engine for HTTP), then disposed only the seed engine.

After the first test, pooled asyncpg connections remained bound to a closed loop. Subsequent tests raised:

- `RuntimeError: got Future attached to a different loop`
- `RuntimeError: Event loop is closed`
- SQLAlchemy `AsyncAdaptedQueuePool` / asyncpg lifecycle errors

Result: 11 passed / 11 failed of 22 collected.

## Repair (test-only)

File: `apps/api/tests/test_phase_c232_http_authorization.py`

1. `_http_harness()` async context manager creates a **NullPool** `AsyncEngine` inside the test’s current loop.
2. Overrides `app.dependency_overrides[get_db]` so every ASGI request uses sessions from that engine only.
3. Seeds tenants through the same session factory (committed data visible to HTTP).
4. On exit: closes the HTTP client, clears dependency overrides, `await engine.dispose()`.

No production code, models, migrations, or authorization policy changes.

## Scenarios preserved (22)

| Area | Coverage |
|------|----------|
| Project GET | owner 200, editor 200, outsider 404, owner_b 404 |
| Project PATCH | owner/editor 200+DB, outsider/owner_b 404 + no mutation |
| Project DELETE | outsider/owner_b 404 + `deleted_at` null; owner/editor 204 then re-read 404 |
| Asset list | owner/editor only asset_a; outsider/owner_b 404 |
| Asset download | cross-project ID 404; outsider/owner_b 404 no storage leak; soft-deleted 404 |
| Org list | outsider/owner_b 403; owner 200 and only project_a |

Policy note unchanged: membership-only gate; `OrganizationMember.role` is not evaluated.

## CI

- Branch: `fix/phase-c232-async-test-lifecycle`
- Base: `main` (includes merged C.2.3.1)
- PostgreSQL 16 service, migrate, then C.2.3.1 (20 passed) then C.2.3.2 (22 passed, 0 skipped)
- No change to CI gate numbers; same enforce-22-passed step

## Verification commands

```bash
# requires DATABASE_URL=postgresql+asyncpg://...
cd apps/api
pytest tests/test_phase_c232_http_authorization.py -v --tb=short
# expect: 22 passed, 0 skipped

# stability
for i in 1 2 3; do
  pytest tests/test_phase_c232_http_authorization.py -q --tb=line || exit 1
done
```

## Limitations

- NullPool is intentional for loop isolation; slightly higher connect overhead in this module only.
- Storage backend may still return 404 for seeded assets that never received a real object put; assertions accept 200 or 404 and forbid path leakage.

## Phase D

Still **BLOCKED** pending independent review of this repaired HTTP matrix.
