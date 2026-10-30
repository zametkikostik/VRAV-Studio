# Staging load test

```bash
export API_BASE=https://staging-api.example.com
pip install httpx
python scripts/loadtest/load_credits.py --users 20 --requests 50
```

## Pass criteria
- error rate < 1%
- p95 latency < 2s for mock chat
- no 5xx spike
- credit ledger consistent
