# Production Security Checklist

## Before deploying to production

### 1. Secrets
- [ ] `SECRET_KEY` set, length >= 32, not a known default
- [ ] `ENCRYPTION_KEY` / `LICENSE_SIGNING_KEY` set when used
- [ ] `DATABASE_URL` uses TLS where available (`sslmode=require`)
- [ ] `REDIS_URL` is private network or TLS (`rediss://`)
- [ ] `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` from live dashboard
- [ ] `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` configured
- [ ] No secrets committed to the repository

### 2. Environment
```bash
ENVIRONMENT=production
SECRET_KEY=<random-64-chars>
RATE_LIMIT_BACKEND=redis
TRUST_PROXY_HEADERS=1
TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12,127.0.0.1
CORS_ORIGINS=https://studio.example.com
METRICS_TOKEN=<random>
```

### 3. Rate limiting
- [ ] Redis reachable from all API replicas
- [ ] In-memory rate limiter not used in production
- [ ] `AUTH_RATE_LIMIT_PER_MINUTE` tuned

### 4. Proxy trust
- [ ] `TRUST_PROXY_HEADERS` only behind a known load balancer
- [ ] `TRUSTED_PROXIES` matches LB/private CIDRs
- [ ] Direct public access cannot spoof `X-Forwarded-For`

### 5. Payments
- [ ] Stripe/YooKassa webhooks use signed verification
- [ ] Idempotency on `provider_event_id`
- [ ] Amount/currency match server pricing
- [ ] No manual credit top-up in production

### 6. Auth sessions
- [ ] Migration `011` applied (`revoked_jtis`, `users.token_version`)
- [ ] Logout and password-reset invalidate sessions

### 7. Collab / uploads
- [ ] Prefer `POST /collab/ticket` over JWT in query
- [ ] Upload size limits and storage path containment enabled

### 8. Headers / TLS
- [ ] HTTPS only at the edge
- [ ] Security headers middleware enabled
- [ ] Metrics endpoint gated with `METRICS_TOKEN` if exposed

### 9. Ops
- [ ] `alembic upgrade head`
- [ ] Database backups encrypted and tested
- [ ] Log level INFO/WARNING, structured logs in production
