# Partial gRPC error bursts originating at productcatalogservice — mechanism unresolved

## What we saw first

The page came in with three alerting services: loadgenerator and productcatalogservice together, and frontend fifteen seconds behind them. Blast radius was counted at seven services, severity critical, and one edge in the graph was crossed without measurement, so the picture was never complete from the start.

Taking productcatalogservice as the anchor, the first thing that actually held up was the error-status curve. The service had been emitting exactly zero gRPC error-status spans — not "low", zero, across 298 samples spanning 92 minutes before onset. Then at T+0 (14:43:45 wall clock) the ratio moved off the floor and crossed the 5% line. Alerts fired at roughly T+2m. That two-minute lag is consistent with alert evaluation windows, not with a second, separate event.

So the sequence a responder should carry forward: productcatalogservice degrades, loadgenerator notices because its synthetic traffic starts failing, frontend notices because it calls productcatalogservice. Frontend is an observer here, not a source.

> Evidence `tr_449236056283`:

```
<tool_result id="tr_449236056283" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T13:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T11:43:55.172647+00:00..2026-09-17T13:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=368 mean=0.003281 min=0 max=0.09186 sd=0.01435
  baseline window: n=298 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_96dc4093bd20`:

```
<tool_result id="tr_96dc4093bd20" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T13:43:55.172647+00:00..2026-09-17T14:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.009432 min=0 max=0.09186 sd=0.02316
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Shape of the degradation

This was never a hard down. Peak error ratio was about 9.2%; the window mean sat under 1%. Roughly nine in ten calls kept succeeding throughout. If you arrive at this record expecting a crash-loop or a total outage, adjust — the service stayed up and mostly served.

The variance is the interesting part. Standard deviation during the affected window exceeded the mean, with minima back at zero. That is the signature of intermittent bursts, not a steady elevated floor. A single bad replica taking a fixed slice of traffic would produce a flat step; this did not. Whatever the cause, it came and went on a timescale shorter than the sampling interval.

Two separate baseline pulls, one over 32 minutes and one over 92, agreed on onset time and on the clean prior. That is the strongest thing in this record.

> Evidence `tr_449236056283`:

```
<tool_result id="tr_449236056283" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T13:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T11:43:55.172647+00:00..2026-09-17T13:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=368 mean=0.003281 min=0 max=0.09186 sd=0.01435
  baseline window: n=298 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_96dc4093bd20`:

```
<tool_result id="tr_96dc4093bd20" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T13:43:55.172647+00:00..2026-09-17T14:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.009432 min=0 max=0.09186 sd=0.02316
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Dead end: the log queries never touched the service

Both log dispatches went to Loki with the selector `{service="product-catalog-service"}` — hyphenated. That label value does not exist in this Loki instance. Both came back with a well-formed empty response over the full window.

This cost us the most. It is very easy to read two empty log results and conclude the service was quiet around onset. It was not quiet; we simply asked a question about a label that matches nothing. The second dispatch was explicitly meant to correct the first and repeated the same hyphenated form.

Worth noting what the emptiness does *not* mean: it is not a Loki outage or an ingestion gap. The backend answered normally. It answered a question about a service that, by that name, does not exist.

If you are reading this to continue the investigation, re-run with the unhyphenated `productcatalogservice` before doing anything else. Nothing about the mechanism can be named until that returns.

> Evidence `tr_eb39421849d1`:

```
<tool_result id="tr_eb39421849d1" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_eb39421849d1>
```

> Evidence `tr_4d08495d31fb`:

```
<tool_result id="tr_4d08495d31fb" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_4d08495d31fb>
```

## Dead end: the change-history window started too late

Two change-history queries were run against productcatalogservice. Both returned nothing. Both began at 14:45:45 — two minutes *after* onset — and ran forward roughly twenty-four hours.

What this genuinely establishes: nothing changed on the service during or after the event. No deploy churned mid-incident, no scaling action, no flag flip during the window, and recovery was not driven by any logged change. Those are real eliminations and they are worth keeping.

What it does not establish, and what was briefly mistaken for an answer: whether anything changed in the hours *before* T+0. That interval was never queried. An empty result forward of onset says nothing about a trigger that landed at T-10m. The question stands wide open.

> Evidence `tr_8a97a12d5c6d`:

```
<tool_result id="tr_8a97a12d5c6d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T14:45:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8a97a12d5c6d>
```

> Evidence `tr_03436b58de35`:

```
<tool_result id="tr_03436b58de35" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T14:45:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_03436b58de35>
```

## What was never asked at all

The metric work returned error ratios and nothing else. No latency percentiles were pulled for productcatalogservice or for anything it calls. No CPU, memory, file-descriptor, or restart-count series were retrieved.

That means two whole families of explanation — slow or failing downstream calls, and saturation of the service's own resources — are untested rather than eliminated. They were not ruled out; they were never examined. Do not read their absence from this record as evidence against them.

The unmeasured edge in the topology compounds this. There is a hop in the call graph we have no telemetry on, and any explanation routed through it is currently invisible.

> Evidence `tr_96dc4093bd20`:

```
<tool_result id="tr_96dc4093bd20" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T13:43:55.172647+00:00..2026-09-17T14:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.009432 min=0 max=0.09186 sd=0.02316
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Where this landed

Not established. Confidence low. No fix class identified.

What can be said with confidence: productcatalogservice is at or nearest the origin. It was provably clean before T+0, it degraded abruptly at T+0 in intermittent partial bursts, and the alert ordering puts frontend downstream of it as an observer. It is at minimum a participant in the failure path — the "healthy service, problem is elsewhere" reading is dead.

What cannot be said: why. Every avenue that would have named a mechanism was either mis-addressed (logs, wrong label value, twice) or mis-scoped (change history, window starting after onset, twice) or never opened (latency, resources).

Three things to do on pickup, in order. First, re-run the log query with the unhyphenated service name across T-5m to T+5m. Second, re-run change history over the several hours *preceding* T+0. Third, pull latency percentiles and resource saturation for the service and its immediate downstream neighbours across the same window. Naming the class of failure before those three return would be a guess dressed as a finding.

> Evidence `tr_449236056283`:

```
<tool_result id="tr_449236056283" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T13:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T11:43:55.172647+00:00..2026-09-17T13:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=368 mean=0.003281 min=0 max=0.09186 sd=0.01435
  baseline window: n=298 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_96dc4093bd20`:

```
<tool_result id="tr_96dc4093bd20" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" template="error-ratio" baseline="2026-09-17T13:43:55.172647+00:00..2026-09-17T14:15:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.009432 min=0 max=0.09186 sd=0.02316
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_eb39421849d1`:

```
<tool_result id="tr_eb39421849d1" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_eb39421849d1>
```

> Evidence `tr_4d08495d31fb`:

```
<tool_result id="tr_4d08495d31fb" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T14:15:45.583000+00:00..2026-09-17T14:47:35.993353+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_4d08495d31fb>
```

> Evidence `tr_8a97a12d5c6d`:

```
<tool_result id="tr_8a97a12d5c6d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T14:45:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8a97a12d5c6d>
```

> Evidence `tr_03436b58de35`:

```
<tool_result id="tr_03436b58de35" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T14:45:45.583000+00:00..2026-09-17T14:47:35.993353+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_03436b58de35>
```

