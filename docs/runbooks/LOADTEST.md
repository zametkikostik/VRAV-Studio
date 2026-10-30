# Staging load test

## Prerequisites
- Staging API up, Postgres, Redis
- Mock AI provider (no external cost)

## Run
```bash
export API_BASE=https://staging-api.example.com
pip install httpx
python scripts/loadtest/load_credits.py --users 20 --requests 50
```

## Pass criteria (suggested)
- error rate < 1%
- p95 latency < 2s for mock chat
- no 5xx spike on `/metrics`
- credit ledger consistent (spot-check org balance)

## Credit concurrency
The test hammers `/ai/chat` which reserve→commit. Watch for 402 under insufficient credits (raise topup in script).
