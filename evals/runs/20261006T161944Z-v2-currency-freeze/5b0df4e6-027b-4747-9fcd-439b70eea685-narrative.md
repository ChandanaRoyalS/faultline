# fraud-detection goes quiet; ten-service fan-out with no error signal

## What was visible, in order

The page arrives wide: ten services in the blast radius, critical, seven unmeasured edges crossed, and seven services alerting at the same instant roughly T+8m. The orienting fact, worth absorbing before touching any tool, is that nothing in this incident ever reports an error — every query you reach for is tuned to find errors and will come back clean.

Set T+0 at the last line fraud-detection ever wrote. For the half hour before it, the service emits nothing but routine Kafka consume messages with a strictly monotonic running total, 3108 up to 3302, spaced seconds to tens of seconds apart. Then it stops. The query window extends nearly ten minutes further and retains the newest lines, so the silence is real. No startup banner, no counter reset — not crash-looping. No slowdown in cadence approaching the cutoff — not a gradual stall. Every line well-formed with valid trace and span ids — the logging path was healthy to the end.

The error ratio does not rise; its mean falls to about three fifths of baseline, with more intervals having no traffic at all than in the baseline. That is the shape of a service producing less work, not failing more work, and it closes off any step-change from a change at onset.

Traces are the weak leg. They cease entirely about twenty minutes before the log cutoff. The spans that exist are healthy — a few milliseconds to ninety, no error status, no outbound children, no latency ramp. The twenty-minute discrepancy is unexplained and may be a sampling or pipeline artifact; anything resting on the traces inherits that doubt.

> Evidence `tr_c06c3e2e7b18`:

```
<tool_result id="tr_c06c3e2e7b18" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-06T15:55:36.974859+00:00  2026-10-06 15:55:36 - fraud-detection - Consumed record with orderId: 5f11ead3-c19e-11f1-a373-4a0582158971, and updated total count to: 3108 trace_id=d18f74d15a29bfde6393b9baad331466 span_id=37a2bb3410b36ffa trace_flags=01 
2026-10-06T15:55:37.868635+00:00  2026-10-06 15:55:37 - fraud-detection - Consumed record with orderId: 5f9f2d68-c19e-11f1-a373-4a0582158971, and updated total count to: 3109 trace_id=1c95ce5959ebab16bed94d005b4f528f span_id=17717a9a520d0252 trace_flags=01 
2026-10-06T15:55:44.773693+00:00  2026-10-06 15:55:44 - fraud-detection - Consumed record with orderId: 63b752fb-c19e-11f1-a373-4a0582158971, and updated total count to: 3110 trace_id=739358a981ece8039a63eae0f3a604f1 span_id=eb78f1bc98cb96c9 trace_flags=01 
2026-10-06T15:55:47.020420+00:00  2026-10-06 15:55:47 - fraud-detection - Consumed record with orderId: 6512e14a-c19e-11f1-a373-4a0582158971, and updated total count to: 3111 trace_id=7a84f2330840745719cfb6d18077c45e span_id=a0ed4d2c01610781 trace_flags=01 
```

> Evidence `tr_28722c05a59a`:

```
<tool_result id="tr_28722c05a59a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" template="error-ratio" baseline="2026-10-06T15:21:39.620930+00:00..2026-10-06T15:55:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=108 mean=0.171 min=0 max=1 sd=0.3537
  baseline window: n=116 mean=0.2789 min=0 max=1 sd=0.447
```

> Evidence `tr_0d7b36f19ec1`:

```
<tool_result id="tr_0d7b36f19ec1" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00">
service: fraud-detection
10 trace(s) shown of 10 found, 20 spans; offsets are from each trace's root

trace 2a343f165e6ad126  root fraud-detection/orders receive  56.9ms  started 2026-10-06T15:56:14.617828+00:00  2 spans
  +0.0ms fraud-detection/orders receive 56.9ms [self 56.8ms]
```

## Dead ends worth keeping

Blaming the upstream producer consumed real effort and produced almost nothing. The traces cannot answer it: every fraud-detection trace is rooted at its own receive span, with no producer parent crossing the queue boundary, so checkout can be neither implicated nor exonerated there. Checkout's logs cannot answer it either — a query for every line of any severity across the full window returned nothing, including the healthy baseline portion, so there is no healthy-then-silent transition to find and no timestamps to correlate. Checkout's error ratio was flat at exactly zero for every sample in both windows, which rules out checkout as an error origin; the series reporting continuously weakly suggests it was alive, but a ratio can persist through a traffic collapse, so whether checkout was still publishing after T+0 is unresolved.

The change log was queried three times — fraud-detection, checkout with a one-hop radius, flagd — and came back empty each time. All three made the same mistake: the window starts at the alert and runs twenty-four hours forward. What that establishes is narrow but real — nothing was deployed, scaled, rolled back or reconfigured after onset, so no in-flight rollout, autoscaling churn, neighbour-service change or silent remediation is in play. What it does not establish is anything about the hours before onset. Nobody looked. Treat that interval as unexamined, not cleared.

> Evidence `tr_0d7b36f19ec1`:

```
<tool_result id="tr_0d7b36f19ec1" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00">
service: fraud-detection
10 trace(s) shown of 10 found, 20 spans; offsets are from each trace's root

trace 2a343f165e6ad126  root fraud-detection/orders receive  56.9ms  started 2026-10-06T15:56:14.617828+00:00  2 spans
  +0.0ms fraud-detection/orders receive 56.9ms [self 56.8ms]
```

> Evidence `tr_26d73e3b2186`:

```
<tool_result id="tr_26d73e3b2186" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_26d73e3b2186>
```

> Evidence `tr_b2c75b06eb89`:

```
<tool_result id="tr_b2c75b06eb89" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" template="error-ratio" baseline="2026-10-06T15:21:39.620930+00:00..2026-10-06T15:55:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=136 mean=0 min=0 max=0 sd=0
  baseline window: n=136 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_4201adab941e`:

```
<tool_result id="tr_4201adab941e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T16:25:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" radius="also_affected" hops="1">
no changes recorded for checkout over this window
</tool_result:tr_4201adab941e>
```

## Where it lands, and what was never checked

Best-supported reading: the fraud-detection process stopped doing anything shortly after T+0 without complaining — present enough to hold its consumer and socket state, but emitting no logs, no spans, no output. Dependents waiting on work that never completed produced the fan-out at T+8m. Fix class: restart. Confidence is low; the verdict rests mainly on the shape of the log cutoff, the corroborating traces carry an unexplained offset, and the metrics are equally consistent with the service being starved of input.

Unexamined, in order of how much it would have changed the answer. First, fraud-detection's own resource telemetry — memory, threads, GC, file descriptors, container restart and OOM status. A process wedged by memory pressure or a saturated thread pool looks identical in logs and traces to the conclusion reached here; check this first next time. Second, the broker and consumer-group lag — a broker-side stall would silence a healthy consumer the same way. Third, the seven unmeasured edges and the six other alerting services were never dispatched against; seven services alerting simultaneously is at least as consistent with a shared upstream as with fraud-detection alone, and nothing here tests that.

> Evidence `tr_c06c3e2e7b18`:

```
<tool_result id="tr_c06c3e2e7b18" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-06T15:55:36.974859+00:00  2026-10-06 15:55:36 - fraud-detection - Consumed record with orderId: 5f11ead3-c19e-11f1-a373-4a0582158971, and updated total count to: 3108 trace_id=d18f74d15a29bfde6393b9baad331466 span_id=37a2bb3410b36ffa trace_flags=01 
2026-10-06T15:55:37.868635+00:00  2026-10-06 15:55:37 - fraud-detection - Consumed record with orderId: 5f9f2d68-c19e-11f1-a373-4a0582158971, and updated total count to: 3109 trace_id=1c95ce5959ebab16bed94d005b4f528f span_id=17717a9a520d0252 trace_flags=01 
2026-10-06T15:55:44.773693+00:00  2026-10-06 15:55:44 - fraud-detection - Consumed record with orderId: 63b752fb-c19e-11f1-a373-4a0582158971, and updated total count to: 3110 trace_id=739358a981ece8039a63eae0f3a604f1 span_id=eb78f1bc98cb96c9 trace_flags=01 
2026-10-06T15:55:47.020420+00:00  2026-10-06 15:55:47 - fraud-detection - Consumed record with orderId: 6512e14a-c19e-11f1-a373-4a0582158971, and updated total count to: 3111 trace_id=7a84f2330840745719cfb6d18077c45e span_id=a0ed4d2c01610781 trace_flags=01 
```

> Evidence `tr_28722c05a59a`:

```
<tool_result id="tr_28722c05a59a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T15:55:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" template="error-ratio" baseline="2026-10-06T15:21:39.620930+00:00..2026-10-06T15:55:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=108 mean=0.171 min=0 max=1 sd=0.3537
  baseline window: n=116 mean=0.2789 min=0 max=1 sd=0.447
```

> Evidence `tr_1cf0b3a5763f`:

```
<tool_result id="tr_1cf0b3a5763f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T16:25:31.664000+00:00..2026-10-06T16:29:23.707070+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_1cf0b3a5763f>
```

