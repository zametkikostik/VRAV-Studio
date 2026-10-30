# Production cutover

## T-24h
- [ ] Freeze risky migrations
- [ ] Confirm Stripe/YooKassa webhook URLs
- [ ] Desktop builds published with signatures/checksums
- [ ] Load test on staging green

## T-0
```bash
export IMAGE_API=registry.example/vrav/api:0.2.1
export IMAGE_WORKER=registry.example/vrav/worker:0.2.1
export SECRETS_FILE=infra/secrets/production.env
./scripts/cutover.sh
```

## Rollback
```bash
helm rollback vrav -n vrav
./scripts/backup/restore_postgres.sh /path/to/pre-cutover.dump
```
