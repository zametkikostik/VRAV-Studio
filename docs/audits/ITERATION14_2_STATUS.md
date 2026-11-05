# Iteration 14.2 — API Contract Hardening & Upload Reliability

| Area | Status | Evidence |
|------|--------|----------|
| Upload asset type validation | PASS | `upload_policy.ALLOWED_ASSET_TYPES` |
| MIME and size validation | PASS | chunked read + MIME prefixes |
| Bounded-memory upload | PARTIAL | SpooledTemporaryFile + chunked local put |
| Storage cleanup after DB failure | PASS (code) | `storage.delete` after flush failure |
| Public DTO storage-key exposure | PASS | `test_public_asset_out_has_no_storage_key` |
| Public JobOut output_key | PASS | `test_public_job_out_has_no_output_key_or_paths` |
| S3/MinIO media processing | DEFERRED (INFRA SCOPE) | HTTP 501 on media jobs |
| Live ASR | DEFERRED (INFRA SCOPE) | not integrated |
