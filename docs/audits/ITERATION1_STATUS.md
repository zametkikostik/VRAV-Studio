# Iteration 1 — Security hardening status

Local command:
```bash
cd apps/api && env -u DATABASE_URL -u REDIS_URL \
  PYTHONPATH=".:../../packages/ai-gateway:../../packages/core" \
  SECRET_KEY=ci-secret-key-for-tests python -m pytest -q tests/
```

Result at fix time: **147 passed**.

| ID | Status | Evidence / tests |
|----|--------|------------------|
| P0-A SECRET_KEY fail-closed | PASS | `_assert_production_secrets` in `app/main.py`; `test_p0a_*` |
| P0-B Stripe unsigned only dev/test | PASS | `payment.py` verify_signature; `test_p0b_*` |
| P0-C no fake checkout in production | PASS | `create_checkout` raises without SDK in prod; `test_p0c_*` |
| P0-D order lock + unique succeeded payment | PASS | `with_for_update` on Order; migration `010_*`; `test_p0d_*` |
| P0-E XFF trust only with TRUST_PROXY_HEADERS | PASS | `auth._client_key`; `test_p0e_*` |
| P1-A metrics | PARTIAL | Not fully gated |
| P1-B credit release separate TX | PARTIAL | Stream finally present |
| P1-C settle actual cost | PARTIAL | Not shipped |
| P1-D SVG XSS | PARTIAL | TBD |
| P1-E render bounds | PARTIAL | width/height/fps/clips bounds; no render billing yet |
| P1-F token revoke | BLOCKED | Needs revoked_jti |
| P1-G WS ticket | PARTIAL | JWT query still |
| P2-B storage path | PASS | resolve + is_relative_to |
| P2-I CORS | PASS | no `*` + credentials |
| Other P2 | BLOCKED/PARTIAL | See table in repo |
