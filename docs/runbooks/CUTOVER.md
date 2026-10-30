# Production cutover

## T-24h
- [ ] Freeze risky migrations
- [ ] Confirm Stripe/YooKassa webhook URLs
- [ ] Desktop builds published with signatures/checksums
- [ ] Load test on staging green

## T-1h
- [ ] Final Postgres + storage backup
- [ ] Announce maintenance window

## T-0
```bash
export IMAGE_API=registry.example/vrav/api:0.2.1
export IMAGE_WORKER=registry.example/vrav/worker:0.2.1
./scripts/cutover.sh
```

## T+15m
- [ ] Login + create project + mock chat
- [ ] License verify from Desktop
- [ ] Sandbox payment check
- [ ] Watch `/metrics` and logs

## Rollback
```bash
helm rollback vrav -n vrav
./scripts/backup/restore_postgres.sh /path/to/pre-cutover.dump
```
