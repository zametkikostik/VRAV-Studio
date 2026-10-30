#!/usr/bin/env bash
set -euo pipefail
NS="${NS:-vrav}"
CHART="${CHART:-./infra/helm/vrav-studio}"
SECRETS_FILE="${SECRETS_FILE:-./infra/secrets/production.env}"
IMAGE_API="${IMAGE_API:?set IMAGE_API}"
IMAGE_WORKER="${IMAGE_WORKER:?set IMAGE_WORKER}"
test -f "$SECRETS_FILE"
if command -v sops >/dev/null; then
  sops -d "$SECRETS_FILE" | kubectl create secret generic vrav-secrets -n "$NS" \
    --from-env-file=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
fi
helm upgrade --install vrav "$CHART" -n "$NS" --create-namespace \
  --set image.api="$IMAGE_API" \
  --set image.worker="$IMAGE_WORKER" \
  --set env.ENVIRONMENT=production
echo "Cutover script finished"
