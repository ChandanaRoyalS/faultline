# Exact queries behind every file in metrics/. Re-runnable.

## error-ratio

```promql
sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))
```

## call-rate

```promql
sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))
```

## latency-p95

```promql
histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))
```

## alerts-firing

```promql
ALERTS{alertstate="firing"}
```

## runtime

```promql
{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="shipping"}
```
