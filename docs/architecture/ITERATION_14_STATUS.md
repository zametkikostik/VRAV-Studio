# Iteration 14 — Backups, SOPS, Desktop signing, load test

## Delivered
1. **Postgres + storage backup/restore scripts** + `docs/runbooks/BACKUP_RESTORE.md`
2. **SOPS/age secrets template** `infra/secrets/`
3. **Desktop code signing / notarize** electron-builder + `DESKTOP_SIGNING.md`
4. **Async load test** `scripts/loadtest/load_credits.py` + `LOADTEST.md`
5. Updated **GO_LIVE.md** checklist

## Repo status
Architectural + production-hardening code path is complete.
Remaining work is **operational**: real certs, cloud managed services, live payment credentials, restore drills.
