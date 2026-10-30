# Kubernetes (skeleton)

Apply order:
```bash
kubectl apply -f namespace.yaml
kubectl create secret generic vrav-secrets -n vrav \
  --from-literal=SECRET_KEY=... \
  --from-literal=DATABASE_URL=... \
  --from-literal=REDIS_URL=...
kubectl apply -f api-deployment.yaml
kubectl apply -f worker-deployment.yaml
```

Images must be built and pushed to your registry first (`vrav/api:latest`, `vrav/worker:latest`).
Postgres/Redis/MinIO are expected as managed services or separate Helm charts.
