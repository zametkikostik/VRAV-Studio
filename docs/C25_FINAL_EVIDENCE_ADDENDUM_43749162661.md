# C.2.5 Final Evidence Addendum — Run 43749162661

**Project:** VRAV Studio  
**Repository:** `zametkikostik/VRAV-Studio`  
**Document type:** Evidence addendum (documentation only)  
**Branch:** `recovery/vrav-c25-stage-b`  

This addendum **references** the original closeout:

- `docs/C25_FINAL_EVIDENCE_CLOSEOUT.md`
- Original evidence run: **`43747594404`**
- Original evidence commit: **`e1885e0c0fbab98dd802af19da2536cc11be176e`**

It records a **subsequent** successful verification run. It does **not** rewrite or replace the original closeout.

---

## 1. Distinction of evidence runs

| Item | Original closeout | This addendum |
|------|-------------------|---------------|
| GitHub Actions run | `43747594404` | **`43749162661`** |
| Run URL | (see closeout) | https://github.com/zametkikostik/VRAV-Studio/actions/runs/43749162661 |
| Commit | `e1885e0c0fbab98dd802af19da2536cc11be176e` | **`628186a44f150adf427c61b6b2c1bcf0b7c850d9`** |
| Parent | `2c531649f51728b54456353f6e8b6ce2bee58f9b` | **`e1885e0c0fbab98dd802af19da2536cc11be176e`** |
| Commit message | (B.1 PID-before-lock fix) | `Add files via upload` |
| Conclusion | SUCCESS | **SUCCESS** |

Both runs are on branch `recovery/vrav-c25-stage-b`. PostgreSQL service version for this addendum run: **16.15**.

---

## 2. Run conclusion (API-verified coordinates)

| Field | Value |
|-------|--------|
| Run ID | `43749162661` |
| Status | `completed` |
| Conclusion | **`success`** |
| Head branch | `recovery/vrav-c25-stage-b` |
| Head SHA | `628186a44f150adf427c61b6b2c1bcf0b7c850d9` |
| Unit job | **SUCCESS** |
| E2E job | **SUCCESS** |

---

## 3. Test results (as verified for this run)

| Gate | Result |
|------|--------|
| Ruff | **PASS** |
| Generic unit tests | **489 passed, 90 skipped** |
| Migration 018 upgrade → downgrade → upgrade | **PASS** |
| Billing PostgreSQL integration | **15 passed** |
| B.2.1 Segment Index | **13 passed** |
| C.2.3.1 | **20 passed, 0 skipped** |
| C.2.3.2 | **22 passed, 0 skipped** |
| C.2.3.3 | **8 passed, 0 skipped** |
| C.2.4 | **14 passed, 0 skipped** |
| C.2.5 Stage A | **6 passed** |
| C.2.5 Stage B | **11 passed** |
| C.2.5 Stage B.1 | **5 passed, 0 skipped, 0 failures, 0 errors** |
| Stage B.1 JUnit | `tests=5 skipped=0 failures=0 errors=0` |

**Note:** The Stage B.1 **zero-skip** gate applies only to the Stage B.1 module. It is **not** the same as the generic unit job’s **90 skipped** tests. Do not describe the unit job as “zero skips.”

---

## 4. Artifacts (run `43749162661`)

| Suite | Artifact name | Artifact ID | SHA-256 digest | Expired |
|-------|---------------|-------------|----------------|---------|
| Stage A | `c25-stage-a-security-audit-log` | **14175647591** | `d14e360495b7aadd5579e361c0602969bb9038a954d700ed4c6eb16599895890` | **false** |
| Stage B | `c25-stage-b-pytest-log` | **14175049972** | `b3e33b25729e1a385b4793fab76f66e8b50f6fa07aa44be0634f193ec31e7f37` | **false** |
| Stage B.1 | `c25-stage-b1-concurrency-log` | **14175209142** | `6b7dead5650b01288c9ad8610fca6935659e5aaed0d585f049445a5807ec7db2` | **false** |

Digests recorded from the GitHub Actions Artifacts API (`digest` field; values above are the hex portion of `sha256:<hex>`).

---

## 5. Warnings — remain visible (not fixed by this addendum)

| Warning | Status |
|---------|--------|
| Stage B.1: three `RuntimeWarning`: `coroutine 'Connection._cancel' was never awaited` | **OPEN** — not suppressed |
| Pytest: `ignoring pytest config in pyproject.toml` | **OPEN** |
| Generic unit tests: **90 skipped** | **EXPECTED / OPEN** as unit-job characteristic |
| CI runner: Node.js 20 deprecation warnings for Actions dependencies | **OPEN** (infra/tooling) |

This addendum does **not** claim these warnings are resolved.

---

## 6. Branch protection

| Item | Value | Classification |
|------|--------|----------------|
| Branch | `recovery/vrav-c25-stage-b` | — |
| `protected` (GitHub metadata) | **false** | — |
| Branch protection enabled | **false** | — |
| Required status checks | **none** | — |
| Engineering classification | **DEFERRED (INFRA SCOPE)** | Do not enable or change settings in this documentation task |

---

## 7. C.2.5 conclusion (preserved)

The frozen C.2.5 scope (Stage A, Stage B, Stage B.1) remains **PASS** on the evidence recorded in the original closeout and is **re-confirmed** by successful run **`43749162661`** on commit **`628186a…`**.

- **Stage C:** **NOT STARTED / NOT AUTHORIZED**
- This document is **not** a general production-readiness certification for the full product.
- Scope remains limited to the frozen C.2.5 PostgreSQL security/lifecycle/concurrency gates listed above.

---

## 8. Document control

| Field | Value |
|-------|--------|
| Path | `docs/C25_FINAL_EVIDENCE_ADDENDUM_43749162661.md` |
| Related closeout | `docs/C25_FINAL_EVIDENCE_CLOSEOUT.md` |
| Task type | Documentation-only evidence addendum |
| Application code changes | **None** |
| CI workflow changes | **None** |
