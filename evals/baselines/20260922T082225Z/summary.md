# Quiet-world baseline — 2026-09-22T08:22:25+00:00 to 2026-09-22T09:07:26+00:00

45 minutes, 15s step, no fault injected. Load generator running.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `fraud-detection` | 0.67% | 0.00% | 2.70% | 2.22% | 0.0 |
| `ad` | 0.36% | 0.00% | 1.10% | 1.03% | 0.0 |
| `recommendation` | 0.25% | 0.00% | 0.81% | 0.74% | 0.0 |
| `flagd` | 0.23% | 0.00% | 0.81% | 0.77% | 0.0 |
| `product-reviews` | 0.19% | 0.00% | 0.68% | 0.58% | 0.0 |
| `accounting` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `frontend-proxy` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `load-generator` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `fraud-detection` | 92ms | 87ms | 99ms | 98ms | 0.0 |
| `accounting` | 91ms | 84ms | 95ms | 94ms | 0.0 |
| `load-generator` | 39ms | 37ms | 40ms | 40ms | 0.0 |
| `product-reviews` | 38ms | 35ms | 41ms | 40ms | 0.0 |
| `frontend-proxy` | 37ms | 35ms | 38ms | 38ms | 0.0 |
| `frontend` | 32ms | 28ms | 35ms | 34ms | 0.0 |
| `checkout` | 18ms | 10ms | 24ms | 23ms | 0.0 |
| `email` | 4ms | 3ms | 8ms | 6ms | 0.0 |
| `product-catalog` | 4ms | 3ms | 4ms | 4ms | 0.0 |
| `recommendation` | 4ms | 3ms | 4ms | 4ms | 0.0 |
| `ad` | 2ms | 2ms | 4ms | 3ms | 0.0 |
| `shipping` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `cart` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `currency` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `flagd` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `image-provider` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `payment` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `quote` | 2ms | 2ms | 2ms | 2ms | 0.0 |

## Alerts that fired on an unfaulted world

| Alert | Service | minutes firing | first | last |
|---|---|---:|---|---|
| ServiceHighLatency | accounting | 0.2 | 2026-09-22T08:22:25+00:00 | 2026-09-22T08:22:25+00:00 |

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
histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))
```

### alerts-firing

```promql
ALERTS{alertstate="firing"}
```

