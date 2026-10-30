# Go-Live Checklist

## Implemented in repo
- [x] Auth refresh + rate limit (Redis multi-replica)
- [x] Password reset email providers
- [x] GDPR export/delete + purge job
- [x] Metrics + request logs
- [x] Stripe SDK hook + live key guard
- [x] Backup/restore scripts
- [x] Desktop signing/notarize config
- [x] Load test script
- [x] Helm chart

## Must do on your infrastructure
- [ ] Managed Postgres + WAL / snapshots
- [ ] Restore drill
- [ ] Encrypt secrets (SOPS)
- [ ] Staging deploy + load test
- [ ] Live webhooks Stripe/YooKassa
- [ ] Windows/macOS certs in CI
- [ ] DNS + TLS + monitoring
- [ ] Flip `STRIPE_ALLOW_LIVE=1` only at cutover
