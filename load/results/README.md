# Versioned k6 results

Store reviewed JSON summaries here as `YYYY-MM-DD-<environment>-<sha>.json`. Never benchmark
production without approval and never include credentials in result files.

Generate a reproducible summary with:

```bash
k6 run \
  --summary-export "load/results/$(date -u +%F)-local-$(git rev-parse --short HEAD).json" \
  -e BASE_URL=http://localhost:8000 load/k6.js
```

Record the k6 version, commit SHA, environment, CPU/memory limits, and whether the service was
warmed up in the adjacent Markdown notes. A result is accepted only when `http_req_failed < 1%`
and `p(95) < 1500 ms`, matching the thresholds in the scenario.
