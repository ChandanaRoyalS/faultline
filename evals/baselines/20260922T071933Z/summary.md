# Quiet-world baseline — 2026-09-22T07:19:33+00:00 to 2026-09-22T08:04:34+00:00

45 minutes, 15s step, no fault injected. Load generator running.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `fraud-detection` | 0.67% | 0.00% | 2.22% | 1.96% | 0.0 |
| `ad` | 0.42% | 0.00% | 1.18% | 1.14% | 0.0 |
| `flagd` | 0.36% | 0.00% | 1.48% | 1.31% | 0.0 |
| `recommendation` | 0.34% | 0.00% | 0.94% | 0.89% | 0.0 |
| `product-reviews` | 0.21% | 0.00% | 0.60% | 0.57% | 0.0 |
| `accounting` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `frontend-proxy` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `load-generator` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `accounting` | 13853ms | 10750ms | 15000ms | 15000ms | 45.2 |
| `fraud-detection` | 92ms | 87ms | 98ms | 98ms | 0.0 |
| `load-generator` | 43ms | 40ms | 44ms | 44ms | 0.0 |
| `product-reviews` | 43ms | 39ms | 44ms | 44ms | 0.0 |
| `frontend-proxy` | 37ms | 33ms | 39ms | 39ms | 0.0 |
| `frontend` | 34ms | 29ms | 37ms | 36ms | 0.0 |
| `checkout` | 23ms | 10ms | 28ms | 27ms | 0.0 |
| `product-catalog` | 4ms | 3ms | 4ms | 4ms | 0.0 |
| `recommendation` | 4ms | 3ms | 5ms | 4ms | 0.0 |
| `email` | 3ms | 2ms | 4ms | 4ms | 0.0 |
| `shipping` | 2ms | 2ms | 3ms | 3ms | 0.0 |
| `ad` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `cart` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `currency` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `flagd` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `payment` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `quote` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `image-provider` | 2ms | 2ms | 2ms | 2ms | 0.0 |

## Alerts that fired on an unfaulted world

| Alert | Service | minutes firing | first | last |
|---|---|---:|---|---|
| ServiceHighLatency | accounting | 45.2 | 2026-09-22T07:19:33+00:00 | 2026-09-22T08:04:33+00:00 |

## Queries (world `v2`, rate window `[5m]`)

Every table above is smoothed over `[5m]`, which is the window this world's alert rules evaluate. **The two are the same quantity and a capture in which they differ is unreadable**: the tables describe one instrument and `alerts-firing` describes another. See `faultline.tools.spanmetrics.WorldMetrics.rate_window`.

### error-ratio

```promql
sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))
```

### call-rate

```promql
sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))
```

### latency-p95

```promql
histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket[5m])))
```

### alerts-firing

```promql
ALERTS{alertstate="firing"}
```

