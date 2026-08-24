# Quiet-world baseline — 2026-08-24T03:37:42+00:00 to 2026-08-24T04:22:42+00:00

45 minutes, 15s step, no fault injected. Load generator running.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `checkoutservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `emailservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `frontend` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `loadgenerator` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `productcatalogservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `recommendationservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `loadgenerator` | 48ms | 47ms | 48ms | 48ms | 0.0 |
| `frontend` | 42ms | 41ms | 43ms | 43ms | 0.0 |
| `checkoutservice` | 38ms | 35ms | 39ms | 39ms | 0.0 |
| `shippingservice` | 12ms | 9ms | 39ms | 29ms | 0.0 |
| `quoteservice` | 8ms | 7ms | 9ms | 8ms | 0.0 |
| `recommendationservice` | 4ms | 4ms | 5ms | 5ms | 0.0 |
| `paymentservice` | 2ms | 2ms | 7ms | 4ms | 0.0 |
| `productcatalogservice` | 2ms | 2ms | 3ms | 3ms | 0.0 |
| `emailservice` | 2ms | 2ms | 4ms | 2ms | 0.0 |
| `adservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `cartservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `accountingservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `currencyservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `frauddetectionservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |

## Alerts that fired on an unfaulted world

None. The world was quiet for the whole window.

## Queries

### error-ratio

```promql
sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))
```

### call-rate

```promql
sum by(service_name) (rate(calls_total[2m]))
```

### latency-p95

```promql
histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))
```

### alerts-firing

```promql
ALERTS{alertstate="firing"}
```

