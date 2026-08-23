# Exact queries behind every file in metrics/. Re-runnable.

## error-ratio

```promql
sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))
```

## call-rate

```promql
sum by(service_name) (rate(calls_total[2m]))
```

## latency-p95

```promql
histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))
```

## alerts-firing

```promql
ALERTS{alertstate="firing"}
```
