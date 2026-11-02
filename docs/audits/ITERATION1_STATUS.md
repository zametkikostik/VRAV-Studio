# Iteration 1 — Security hardening status

```bash
cd apps/api && env -u DATABASE_URL -u REDIS_URL \
  PYTHONPATH=".:../../packages/ai-gateway:../../packages/core" \
  SECRET_KEY=ci-secret-key-for-tests python -m pytest -q tests/
```

Local: **164 passed**.

| ID | Status | Evidence |
|----|--------|----------|
| P0-A–E | PASS | `test_security_iteration1_p0.py` |
| P1-A–E | PASS | `test_security_iteration1_p1.py` |
| P1-F token revoke/rotation | PASS | `revoked_jtis`, `token_version`, logout, refresh rotate; `test_p1f_*` |
| P1-G reset/email + WS ticket | PASS | `test_p1g_*`, `POST /collab/ticket` |
| P2-B / P2-I | PASS | |
| Other P2 | BLOCKED/PARTIAL | |
