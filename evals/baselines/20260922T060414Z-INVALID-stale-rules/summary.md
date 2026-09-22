# Quiet-world baseline — 2026-09-22T06:04:14+00:00 to 2026-09-22T06:49:14+00:00

45 minutes, 15s step, no fault injected. Load generator running.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `fraud-detection` | 0.75% | 0.00% | 11.11% | 9.09% | 3.0 |
| `ad` | 0.34% | 0.00% | 4.76% | 3.23% | 0.0 |
| `flagd` | 0.30% | 0.00% | 2.94% | 2.50% | 0.0 |
| `recommendation` | 0.26% | 0.00% | 4.55% | 2.33% | 0.0 |
| `product-reviews` | 0.16% | 0.00% | 2.08% | 1.79% | 0.0 |
| `accounting` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `accounting` | 13463ms | 9167ms | 15000ms | 15000ms | 45.2 |
| `fraud-detection` | 1081ms | 77ms | 15000ms | 15000ms | 3.0 |
| `flagd` | 665ms | 2ms | 15000ms | 2ms | 2.0 |
| `load-generator` | 43ms | 38ms | 46ms | 45ms | 0.0 |
| `product-reviews` | 42ms | 10ms | 48ms | 45ms | 0.0 |
| `frontend-proxy` | 37ms | 28ms | 42ms | 41ms | 0.0 |
| `frontend` | 33ms | 23ms | 40ms | 38ms | 0.0 |
| `checkout` | 23ms | 9ms | 33ms | 30ms | 0.0 |
| `product-catalog` | 4ms | 2ms | 5ms | 5ms | 0.0 |
| `recommendation` | 4ms | 3ms | 9ms | 5ms | 0.0 |
| `email` | 3ms | 2ms | 7ms | 6ms | 0.0 |
| `shipping` | 2ms | 2ms | 5ms | 3ms | 0.0 |
| `ad` | 2ms | 2ms | 4ms | 4ms | 0.0 |
| `currency` | 2ms | 2ms | 3ms | 3ms | 0.0 |
| `cart` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `image-provider` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `payment` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `quote` | 2ms | 2ms | 2ms | 2ms | 0.0 |

## Alerts that fired on an unfaulted world

| Alert | Service | minutes firing | first | last |
|---|---|---:|---|---|
| ServiceHighLatency | accounting | 45.2 | 2026-09-22T06:04:14+00:00 | 2026-09-22T06:49:14+00:00 |

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

