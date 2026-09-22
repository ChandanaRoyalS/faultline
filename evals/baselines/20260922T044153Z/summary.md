# Quiet-world baseline — 2026-09-22T04:41:53+00:00 to 2026-09-22T05:26:54+00:00

45 minutes, 15s step, no fault injected. Load generator running.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `recommendation` | 3.74% | 0.00% | 100.00% | 14.29% | 4.0 |
| `fraud-detection` | 3.33% | 0.00% | 33.33% | 33.33% | 4.0 |
| `ad` | 3.10% | 0.00% | 33.33% | 33.33% | 4.0 |
| `product-reviews` | 3.04% | 0.00% | 100.00% | 7.14% | 4.0 |
| `flagd` | 1.09% | 0.00% | 10.00% | 7.69% | 6.0 |
| `accounting` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `accounting` | 15000ms | 15000ms | 15000ms | 15000ms | 40.0 |
| `flagd` | 2653ms | 2ms | 15000ms | 15000ms | 8.0 |
| `fraud-detection` | 1569ms | 2ms | 15000ms | 15000ms | 4.0 |
| `ad` | 1552ms | 2ms | 15000ms | 15000ms | 4.0 |
| `recommendation` | 1532ms | 2ms | 15000ms | 15000ms | 4.0 |
| `product-reviews` | 1494ms | 6ms | 15000ms | 15000ms | 4.0 |
| `load-generator` | 45ms | 39ms | 48ms | 47ms | 0.0 |
| `frontend-proxy` | 38ms | 8ms | 44ms | 43ms | 0.0 |
| `frontend` | 35ms | 12ms | 42ms | 41ms | 0.0 |
| `checkout` | 25ms | 14ms | 38ms | 36ms | 0.0 |
| `product-catalog` | 4ms | 2ms | 7ms | 6ms | 0.0 |
| `email` | 3ms | 2ms | 7ms | 5ms | 0.0 |
| `cart` | 2ms | 2ms | 6ms | 3ms | 0.0 |
| `shipping` | 2ms | 2ms | 4ms | 4ms | 0.0 |
| `currency` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `image-provider` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `payment` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `quote` | 2ms | 2ms | 2ms | 2ms | 0.0 |

## Alerts that fired on an unfaulted world

| Alert | Service | minutes firing | first | last |
|---|---|---:|---|---|
| ServiceHighLatency | accounting | 28.0 | 2026-09-22T04:50:53+00:00 | 2026-09-22T05:18:38+00:00 |
| ServiceHighLatency | accounting | 2.0 | 2026-09-22T05:22:53+00:00 | 2026-09-22T05:24:38+00:00 |

## Queries (world `v2`)

### error-ratio

```promql
sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[2m]))
```

### call-rate

```promql
sum by(service_name) (rate(traces_span_metrics_calls_total[2m]))
```

### latency-p95

```promql
histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket[2m])))
```

### alerts-firing

```promql
ALERTS{alertstate="firing"}
```

