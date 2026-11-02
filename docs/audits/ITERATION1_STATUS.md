# Iteration 1 — Security hardening status

```bash
cd apps/api && env -u DATABASE_URL -u REDIS_URL \
  PYTHONPATH=".:../../packages/ai-gateway:../../packages/core" \
  SECRET_KEY=ci-secret-key-for-tests python -m pytest -q tests/
```

Local result: **157 passed**.

| ID | Status | Evidence |
|----|--------|----------|
| P0-A–E | PASS | `test_security_iteration1_p0.py` |
| P1-A metrics path + token | PASS | `normalize_path`, `METRICS_TOKEN`; `test_p1a_*` |
| P1-B release_in_new_tx | PASS | `credits.release_in_new_tx`; AI uses it; `test_p1b_*` |
| P1-C settle actual cost | PASS | `CreditService.settle`; chat path; `test_p1c_*` |
| P1-D SVG attachment + nosniff | PASS | `assets_upload`; `test_p1d_*` |
| P1-E render bounds + reserve | PASS | jobs Field bounds + 1 credit reserve; `test_p1e_*` |
| P1-F token revoke/rotation | BLOCKED | needs `revoked_jti` table |
| P1-G reset token / email redact | PASS | no API echo; console email redacts; `test_p1g_*` |
| P1-G WS ticket | PARTIAL | JWT query still |
| P2-B storage / P2-I CORS | PASS | |
| Other P2 | BLOCKED/PARTIAL | |
