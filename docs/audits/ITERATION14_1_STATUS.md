# Iteration 14.1 — Regression Recovery

## Regression matrix (vs 5a41f61)

| Item | Classification | Fix |
|------|----------------|-----|
| DELETE /projects/{id} removed | unintended regression | restored |
| create status draft→active | unintended regression | restored draft |
| list scenes without order_by | unintended regression | restored order_index |
| create_asset without storage.put | unintended regression | restored empty put |
| upload unbounded file.read() | security regression | restored chunked read + MIME |
| keyframes only local FS | infrastructure limitation | 501 for non-local backends |
| dual assets UI routes | partial | shared ProjectAssetsPage |

## Storage

| Backend | Keyframe serve | Analysis |
|---------|----------------|----------|
| local | supported | supported |
| S3/MinIO | DEFERRED (501) | DEFERRED (INFRA SCOPE) |

## Evidence

- `test_iteration14_1_regressions.py`
