# VRAV Studio Helm Chart

```bash
helm upgrade --install vrav ./infra/helm/vrav-studio \
  -n vrav --create-namespace \
  --set secrets.SECRET_KEY=... \
  --set secrets.DATABASE_URL=... \
  --set secrets.REDIS_URL=... \
  --set image.api=registry.example/vrav/api:0.1.0 \
  --set image.worker=registry.example/vrav/worker:0.1.0
```

Optional ingress:
```bash
--set ingress.enabled=true --set ingress.host=studio.example.com
```
