# C.2.5 Final Evidence Closeout

**Project:** VRAV Studio  
**Repository:** `zametkikostik/VRAV-Studio`  
**Scope:** C.2.5 — Stage A, Stage B, Stage B.1  
**Status:** **PASS — frozen C.2.5 scope completed**  
**Evidence run:** `43747594404`  
**Evidence commit:** `e1885e0c0fbab98dd802af19da2536cc11be176e`  
**Branch:** `recovery/vrav-c25-stage-b`  
**Database used in CI:** PostgreSQL `16.15`

---

## 1. Executive result

The frozen C.2.5 scope passed in GitHub Actions run `43747594404` on commit `e1885e0c0fbab98dd802af19da2536cc11be176e`.

- GitHub Actions run conclusion: **SUCCESS**.
- Unit job: **SUCCESS**.
- E2E job: **SUCCESS**.
- Stage A Security Audit: **6 passed**.
- Stage B Organization Lifecycle: **11 passed**.
- Stage B.1 Concurrency: **5 passed, 0 skipped, 0 failures, 0 errors**.
- Stage B.1 JUnit gate: `tests=5 skipped=0 failures=0 errors=0`.
- PostgreSQL CI service: **16.15**.

This closeout applies only to the frozen C.2.5 scope. It is **not** a claim that Stage C has been implemented, nor a blanket certification that the entire product is production-ready.

## 2. Immutable evidence coordinates

| Item | Value |
|---|---|
| Repository | `zametkikostik/VRAV-Studio` |
| Branch | `recovery/vrav-c25-stage-b` |
| Commit | `e1885e0c0fbab98dd802af19da2536cc11be176e` |
| Parent commit | `2c531649f51728b54456353f6e8b6ce2bee58f9b` |
| Baseline commit | `36e9f1bbd03fef5601f8f1e708287b903cb90b76` |
| GitHub Actions run | `43747594404` |
| Unit job ID | `132914209302` |
| E2E job ID | `132914372073` |
| Database | PostgreSQL `16.15` |

Links:

- [Successful GitHub Actions run](https://github.com/zametkikostik/VRAV-Studio/actions/runs/43747594404)
- [Evidence commit](https://github.com/zametkikostik/VRAV-Studio/commit/e1885e0c0fbab98dd802af19da2536cc11be176e)
- [Stage B.1 artifact](https://github.com/zametkikostik/VRAV-Studio/actions/runs/43747594404/artifacts/14174029324)

## 3. Change-scope verification

The successful implementation commit is exactly two files ahead of baseline `36e9f1bbd03fef5601f8f1e708287b903cb90b76`.

Files changed:

1. `.github/workflows/ci.yml` — CI wiring and artifact/log handling.
2. `apps/api/tests/test_phase_c25_stage_b1_concurrency.py` — Stage B.1 concurrency and rollback tests.

No production application code, database schema, migration, RBAC policy, or GDPR implementation was changed by this Stage B.1 fix.

The preceding failed test attempt exposed a test-instrumentation ordering issue: the second request's backend PID was being captured only after entering the lock wait. The successful fix captures the HTTP backend PID before the `FOR UPDATE` wait and verifies blocking directly with `pg_blocking_pids()`. Synthetic probe connections are not used for the decisive lock assertion.

## 4. Acceptance results

### Stage A — Security Audit

**PASS**

- Result: **6 passed**.
- All six named Stage A tests passed in the successful E2E job.
- CI used PostgreSQL `16.15`.

### Stage B — Organization Lifecycle

**PASS**

- Result: **11 passed**.
- Stage B completed successfully in the successful E2E job.

### Stage B.1 — Concurrency and audit rollback

**PASS**

| Scenario | Expected invariant | Result |
|---|---|---|
| C1A — two concurrent transfers from the same owner | Exactly one transfer succeeds; final ownership and audit state remain consistent | PASS |
| C2a — revoke target before transfer | Revoke returns `204`; transfer returns `404`; original owner remains owner; one revoke audit and no transfer audit | PASS |
| C2b — transfer before revoke | Transfer returns `200`; revoking the new owner returns `409`; new owner remains owner; one transfer audit and no revoke audit | PASS |
| C4 — concurrent duplicate member add | One request returns `201`, the other `409`; exactly one membership row and one member-added audit | PASS |
| Transfer audit write failure | Transaction rolls back; original owner remains; no successful transfer audit remains | PASS |

Stage B.1 test summary:

```text
5 passed, 3 warnings
JUnit: tests=5 skipped=0 failures=0 errors=0
```

The concurrency tests verify the actual HTTP request backend PIDs and the PostgreSQL lock relationship. The decisive assertion checks that `pg_blocking_pids(second_request_pid)` contains the first request's backend PID.

## 5. Supporting regression evidence

The same successful CI run also completed the following regression suites:

| Suite | Result |
|---|---:|
| C.2.3.1 | 20 passed, 0 skipped |
| C.2.3.2 | 22 passed, 0 skipped |
| C.2.3.3 | 8 passed, 0 skipped |
| C.2.4 | 14 passed, 0 skipped |
| B.2.1 Segment Index | 13 passed |
| Billing PostgreSQL integration | 15 passed |
| Generic Unit Tests | 489 passed, 90 skipped |
| Ruff | PASS |
| Migration 018 isolated upgrade → downgrade → upgrade | PASS |

**Skip accounting:** the Stage B.1 zero-skip gate is specific to the five Stage B.1 tests. The general unit-test suite separately reports **90 skipped** tests; these are not to be represented as zero.

## 6. CI artifacts and integrity digests

The following artifacts were reported for successful run `43747594404`:

| Artifact | Artifact ID | SHA-256 |
|---|---:|---|
| `c25-stage-b-pytest-log` | `14175021327` | `00ea7092e87e1ff2c5c028d3d9aec16126779ab8af603a52209a41964c183d04` |
| `c25-stage-a-security-audit-log` | `14174684672` | `9ad194bfb866cf0a71f3dd44bd1a37686e323278058b7d39495aba13ecd428b6` |
| `c25-stage-b1-concurrency-log` | `14174029324` | `1cd036afb6f52a96e2745511c53ce56efcdf44f6dd0675eb7a20bf0055c46a84` |

The Stage B.1 artifact contains the PostgreSQL test log and JUnit XML (`/tmp/c25_b1_pg.txt` and `/tmp/c25_b1_junit.xml`) as configured by the workflow.

## 7. Warnings and known limitations

The successful run contains warnings. They did not fail the current CI run, but they remain recorded here rather than being silently suppressed.

1. Stage B.1 emitted three `RuntimeWarning` instances referring to `Connection._cancel` being a coroutine that was never awaited. They appeared during C2b, C4, and transfer-audit rollback test cleanup.
2. Pytest emitted a configuration warning indicating that it was ignoring pytest configuration in `pyproject.toml`.
3. Other regression suites also emitted warnings; their tests passed.
4. The 90 skipped generic unit tests remain visible in the unit-test summary and are outside the Stage B.1 zero-skip gate.

These warnings are **non-blocking for this recorded CI result**, but the async cleanup warning should be investigated separately. Do not silence or reclassify it as resolved without a specific fix and fresh CI evidence.

## 8. Explicitly out of scope

This closeout does not authorize or certify any of the following:

- Stage C implementation or execution.
- GDPR purge race scenarios.
- New migrations or schema changes beyond the tested Migration 018 cycle.
- Partial unique owner-index redesign.
- Missing-user foreign-key redesign.
- RBAC redesign or policy expansion.
- Admin self-revoke policy changes.
- Production-code changes unrelated to the frozen C.2.5 scope.
- A general production-readiness certification for VRAV Studio.

## 9. Final disposition

**C.2.5 frozen scope: PASS / COMPLETE.**

The PASS is supported by the successful GitHub Actions run `43747594404`, commit `e1885e0c0fbab98dd802af19da2536cc11be176e`, PostgreSQL `16.15`, and the recorded test/artifact evidence above.

Recommended handling:

- Preserve this report and the referenced CI artifacts as the C.2.5 closeout record.
- Do not make further Stage B.1 code changes unless a concrete defect is identified.
- Keep the three async cleanup warnings visible for a separately scoped investigation.
- Treat Stage C as **not started / not authorized** until separately approved.

---

**Evidence boundary:** This document consolidates the CI logs, run metadata, commit comparison, and artifact metadata reviewed for run `43747594404`. Any later rerun, commit, artifact expiration, or repository change must be recorded as a new evidence event; it must not silently rewrite this historical result.
