# Backup & Restore

## Daily Postgres
```bash
export DATABASE_URL_SYNC=postgresql://vrav:vrav@localhost:5432/vrav
export BACKUP_DIR=/var/backups/vrav
export BACKUP_KEEP=14
./scripts/backup/backup_postgres.sh
```

Cron example:
```
15 2 * * * cd /opt/vrav && BACKUP_DIR=/var/backups/vrav ./scripts/backup/backup_postgres.sh
```

## Restore drill (staging monthly)
1. Provision empty DB
2. `./scripts/backup/restore_postgres.sh /var/backups/vrav/vrav_YYYYMMDD.dump`
3. `alembic upgrade head`
4. Smoke: `/health/db`, login, list projects

## Object storage
```bash
./scripts/backup/backup_storage.sh
```

## RPO/RTO targets (suggested)
- RPO ≤ 24h (logical dumps) or ≤ 5m with WAL archiving on managed Postgres
- RTO ≤ 2h after restore drill success
