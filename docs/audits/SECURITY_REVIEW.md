# Security Review

## Iteration 0 fixes
| Finding | Fix |
|---------|-----|
| Credit minting | Production blocks manual top-up; admin/owner only |
| Stripe/YooKassa unsigned | Production rejects missing secret |
| Stripe paid → credits | Webhook grants once (idempotent) |
| License | owner/admin role |
| Upload | max_upload_bytes + content-type |
| JWT | production requires type=access |
