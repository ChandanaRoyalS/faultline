# Quiet-world baseline — 2026-08-23T06:16:32+00:00 to 2026-08-23T07:01:32+00:00

45 minutes, 15s step, no fault injected. Load generator running.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `checkoutservice` | 10.91% | 0.00% | 66.67% | 66.67% | 9.2 |
| `loadgenerator` | 5.52% | 0.00% | 31.17% | 28.98% | 10.0 |
| `frontend` | 5.18% | 0.00% | 29.42% | 27.82% | 10.0 |
| `emailservice` | 4.77% | 0.00% | 100.00% | 36.84% | 2.5 |
| `productcatalogservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `recommendationservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `loadgenerator` | 49ms | 47ms | 93ms | 48ms | 0.0 |
| `frontend` | 42ms | 37ms | 53ms | 43ms | 0.0 |
| `checkoutservice` | 41ms | 2ms | 1060ms | 48ms | 0.5 |
| `cartservice` | 22ms | 2ms | 360ms | 240ms | 2.0 |
| `shippingservice` | 13ms | 9ms | 36ms | 30ms | 0.0 |
| `quoteservice` | 8ms | 7ms | 10ms | 8ms | 0.0 |
| `recommendationservice` | 4ms | 4ms | 6ms | 5ms | 0.0 |
| `paymentservice` | 3ms | 2ms | 6ms | 6ms | 0.0 |
| `productcatalogservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `emailservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `adservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `accountingservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `currencyservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `frauddetectionservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |

## Alerts that fired on an unfaulted world

| Alert | Service | minutes firing | first | last |
|---|---|---:|---|---|
| ServiceHighErrorRate | frontend | 8.0 | 2026-08-23T06:40:47+00:00 | 2026-08-23T06:48:32+00:00 |
| ServiceHighErrorRate | loadgenerator | 8.0 | 2026-08-23T06:40:47+00:00 | 2026-08-23T06:48:32+00:00 |
| ServiceHighErrorRate | checkoutservice | 7.2 | 2026-08-23T06:41:02+00:00 | 2026-08-23T06:48:02+00:00 |
| ServiceNoTraffic | accountingservice | 2.5 | 2026-08-23T06:44:02+00:00 | 2026-08-23T06:46:17+00:00 |
| ServiceNoTraffic | frauddetectionservice | 2.5 | 2026-08-23T06:44:02+00:00 | 2026-08-23T06:46:17+00:00 |
| ServiceNoTraffic | shippingservice | 2.5 | 2026-08-23T06:44:02+00:00 | 2026-08-23T06:46:17+00:00 |
| ServiceNoTraffic | cartservice | 2.2 | 2026-08-23T06:44:17+00:00 | 2026-08-23T06:46:17+00:00 |
| ServiceNoTraffic | currencyservice | 2.2 | 2026-08-23T06:44:02+00:00 | 2026-08-23T06:46:02+00:00 |
| ServiceNoTraffic | emailservice | 2.2 | 2026-08-23T06:44:02+00:00 | 2026-08-23T06:46:02+00:00 |
| ServiceNoTraffic | quoteservice | 2.2 | 2026-08-23T06:44:02+00:00 | 2026-08-23T06:46:02+00:00 |
| ServiceHighErrorRate | emailservice | 0.5 | 2026-08-23T06:48:17+00:00 | 2026-08-23T06:48:32+00:00 |

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
