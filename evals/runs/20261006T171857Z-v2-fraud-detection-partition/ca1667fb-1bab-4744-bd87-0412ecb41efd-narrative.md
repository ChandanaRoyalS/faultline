# fraud-detection alert traced to a telemetry export path that could not resolve its collector

## What was visible, in order

A critical alert fired on fraud-detection; nothing else paged. T+0 is that alert.

The unfiltered log tail was the most useful pull. For the first eight minutes of the retained window (about T-30m to T-22m) the service is plainly healthy — order records consumed in sequence, counter incrementing, no errors. At roughly T+1m the same process is still alive and still logging, which immediately killed the theory that it had been terminated or restarted at the alert moment.

The exception present was a transport-layer failure in the telemetry export path: the agent could not resolve the hostname of its metrics collector. The stack is entirely HTTP-client and exporter frames, with no fraud-detection application classes in it.

> Evidence `tr_cd23ed25ab17`:

```
<tool_result id="tr_cd23ed25ab17" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-06T16:56:32.535392+00:00  2026-10-06 16:56:32 - fraud-detection - Consumed record with orderId: e1f8f549-c1a6-11f1-a373-4a0582158971, and updated total count to: 3584 trace_id=804ac5f42c946824b180b19c8c679904 span_id=1fe77223efdb2816 trace_flags=01 
2026-10-06T16:56:46.168702+00:00  2026-10-06 16:56:46 - fraud-detection - Consumed record with orderId: ea16e92a-c1a6-11f1-a373-4a0582158971, and updated total count to: 3585 trace_id=a35f709d8c09389fa1f4ab22222f215c span_id=7b2552416504f1e3 trace_flags=01 
2026-10-06T16:56:58.110536+00:00  2026-10-06 16:56:58 - fraud-detection - Consumed record with orderId: f1343f4e-c1a6-11f1-a373-4a0582158971, and updated total count to: 3586 trace_id=6bf94363a06a0b8d1058d2ddb422bacf span_id=8a217a915646a41b trace_flags=01 
2026-10-06T16:57:11.039020+00:00  2026-10-06 16:57:11 - fraud-detection - Consumed record with orderId: f8e8daed-c1a6-11f1-a373-4a0582158971, and updated total count to: 3587 trace_id=95755b22f444e8bb707bd843a6ed336a span_id=0a7b4d73a3333f0a trace_flags=01 
```

## Narrowing the pattern

Filtering logs to exception headers turned one event into a shape. The unresolvable-host error recurs on a near-exact ~60s cadence from about T-22m onward — the signature of a fixed-interval export retry loop, not request-driven traffic. One instance carries an extended header attributing it to a temporary name-resolution failure, which distinguishes this from a collector that is up but refusing connections, or a TLS problem: the failure happens before any connect attempt.

The series pauses between roughly T-14m and T-6m, then resumes — resolution apparently worked, or the exporter backed off. A separate sporadic family (an interrupted-IO timeout followed by a cancellation line) appears three times at unrelated moments; the trace tail near the alert does not belong to it.

Caveat: that filter kept only throwable headers, so the surrounding non-exception context around the alert minute was never retrieved.

> Evidence `tr_e6c992444e81`:

```
<tool_result id="tr_e6c992444e81" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" contains="Exception">
selector: {service="fraud-detection"} |= "Exception"
2026-10-06T17:03:44.365552+00:00  java.io.InterruptedIOException: timeout
2026-10-06T17:03:44.365820+00:00  Caused by: java.io.IOException: Canceled
2026-10-06T17:04:43.042754+00:00  java.net.UnknownHostException: otel-collector
2026-10-06T17:05:41.883647+00:00  java.net.UnknownHostException: otel-collector
```

> Evidence `tr_cd23ed25ab17`:

```
<tool_result id="tr_cd23ed25ab17" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-06T16:56:32.535392+00:00  2026-10-06 16:56:32 - fraud-detection - Consumed record with orderId: e1f8f549-c1a6-11f1-a373-4a0582158971, and updated total count to: 3584 trace_id=804ac5f42c946824b180b19c8c679904 span_id=1fe77223efdb2816 trace_flags=01 
2026-10-06T16:56:46.168702+00:00  2026-10-06 16:56:46 - fraud-detection - Consumed record with orderId: ea16e92a-c1a6-11f1-a373-4a0582158971, and updated total count to: 3585 trace_id=a35f709d8c09389fa1f4ab22222f215c span_id=7b2552416504f1e3 trace_flags=01 
2026-10-06T16:56:58.110536+00:00  2026-10-06 16:56:58 - fraud-detection - Consumed record with orderId: f1343f4e-c1a6-11f1-a373-4a0582158971, and updated total count to: 3586 trace_id=6bf94363a06a0b8d1058d2ddb422bacf span_id=8a217a915646a41b trace_flags=01 
2026-10-06T16:57:11.039020+00:00  2026-10-06 16:57:11 - fraud-detection - Consumed record with orderId: f8e8daed-c1a6-11f1-a373-4a0582158971, and updated total count to: 3587 trace_id=95755b22f444e8bb707bd843a6ed336a span_id=0a7b4d73a3333f0a trace_flags=01 
```

## Dead end: hunting an error spike

Two metric pulls were made; both returned only the span error ratio. No throughput, latency, heap, restart count, GC or consumer-lag series ever came back.

Around the alert the error ratio averaged ~0.4% (peak ~3%) against a baseline near 22.7% — an order of magnitude better going into the incident, the opposite of a failing-requests signature.

Two traps. Roughly half the incident-window samples have no defined ratio, which looks like the service going quiet — but most baseline samples are undefined too, so the intermittent no-traffic pattern predates the incident. And the wider pull's apparent move 'from zero' is a baseline that returned no samples at all; that zero is missing data, not a regression. That wider window also does not contain the alert minute in UTC.

> Evidence `tr_e14805e67815`:

```
<tool_result id="tr_e14805e67815" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" template="error-ratio" baseline="2026-10-06T16:24:42.652315+00:00..2026-10-06T16:56:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=84 mean=0.004123 min=0 max=0.0303 sd=0.008983
  baseline window: n=72 mean=0.2271 min=0 max=1 sd=0.4161
```

> Evidence `tr_3fa6a9b23618`:

```
<tool_result id="tr_3fa6a9b23618" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T05:26:31.664000+00:00..2026-10-06T11:26:31.664000+00:00" template="error-ratio" baseline="2026-10-05T23:26:31.664000+00:00..2026-10-06T05:26:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=573 mean=0.006527 min=0 max=0.02439 sd=0.007946
  baseline window: no samples
```

## Dead end: looking for a change to blame

Three change-log queries — one on fraud-detection, two on flagd — all returned completely empty. No deployments, config pushes, flag edits or resource-limit edits.

The important caveat: every one of those windows starts at the alert timestamp and runs forward about twenty-four hours. The hours before onset were never queried. So a concurrent or post-onset change as trigger, a mid-incident flag toggle, and an unlogged corrective change are all excluded — a pre-onset change is not. flagd was never examined in logs or metrics, only in the change log.

> Evidence `tr_bddf69fee5c9`:

```
<tool_result id="tr_bddf69fee5c9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T17:26:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_bddf69fee5c9>
```

> Evidence `tr_f56ce30cef2d`:

```
<tool_result id="tr_f56ce30cef2d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T17:26:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_f56ce30cef2d>
```

> Evidence `tr_cd87ab1bf25f`:

```
<tool_result id="tr_cd87ab1bf25f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T17:26:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_cd87ab1bf25f>
```

## What turned out not to matter

Do not re-walk these. The service being down or crash-looping: it logs past the alert and metrics sample continuously. An error storm: the error ratio went down, and exception volume is one per minute on a fixed cadence. Business-logic failure in fraud scoring or a fraud dependency: the stack names a telemetry collector and contains no application classes. A rollback as remediation: there is no recorded change to roll back in the window queried. A closed port or TLS problem: the failure is name resolution, which precedes connection. And the dashboard gap does not mean the service stopped working — it is explained by the exporter.

> Evidence `tr_cd23ed25ab17`:

```
<tool_result id="tr_cd23ed25ab17" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-06T16:56:32.535392+00:00  2026-10-06 16:56:32 - fraud-detection - Consumed record with orderId: e1f8f549-c1a6-11f1-a373-4a0582158971, and updated total count to: 3584 trace_id=804ac5f42c946824b180b19c8c679904 span_id=1fe77223efdb2816 trace_flags=01 
2026-10-06T16:56:46.168702+00:00  2026-10-06 16:56:46 - fraud-detection - Consumed record with orderId: ea16e92a-c1a6-11f1-a373-4a0582158971, and updated total count to: 3585 trace_id=a35f709d8c09389fa1f4ab22222f215c span_id=7b2552416504f1e3 trace_flags=01 
2026-10-06T16:56:58.110536+00:00  2026-10-06 16:56:58 - fraud-detection - Consumed record with orderId: f1343f4e-c1a6-11f1-a373-4a0582158971, and updated total count to: 3586 trace_id=6bf94363a06a0b8d1058d2ddb422bacf span_id=8a217a915646a41b trace_flags=01 
2026-10-06T16:57:11.039020+00:00  2026-10-06 16:57:11 - fraud-detection - Consumed record with orderId: f8e8daed-c1a6-11f1-a373-4a0582158971, and updated total count to: 3587 trace_id=95755b22f444e8bb707bd843a6ed336a span_id=0a7b4d73a3333f0a trace_flags=01 
```

> Evidence `tr_e6c992444e81`:

```
<tool_result id="tr_e6c992444e81" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" contains="Exception">
selector: {service="fraud-detection"} |= "Exception"
2026-10-06T17:03:44.365552+00:00  java.io.InterruptedIOException: timeout
2026-10-06T17:03:44.365820+00:00  Caused by: java.io.IOException: Canceled
2026-10-06T17:04:43.042754+00:00  java.net.UnknownHostException: otel-collector
2026-10-06T17:05:41.883647+00:00  java.net.UnknownHostException: otel-collector
```

> Evidence `tr_e14805e67815`:

```
<tool_result id="tr_e14805e67815" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" template="error-ratio" baseline="2026-10-06T16:24:42.652315+00:00..2026-10-06T16:56:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=84 mean=0.004123 min=0 max=0.0303 sd=0.008983
  baseline window: n=72 mean=0.2271 min=0 max=1 sd=0.4161
```

## Where it landed, and what is still open

fraud-detection is not failing requests; it is failing to reach its telemetry collector. From about T-22m it cannot resolve the collector hostname, retries once a minute, pauses mid-window, resumes — while still consuming order records with a span error ratio well below its own baseline. Assessment: a connectivity or name-resolution break to the collector, whose visible symptom is a hole in this service's metrics. Fix class: reconnect. Confidence medium.

Three gaps, in the order I would close them. First, what actually tripped the alert is unestablished — no spike, collapse or restart was seen; the metrics-hole explanation is only a hypothesis, so read the alert rule. Second, the spread is unmeasured: no other service was checked for the same unresolvable-host error and the collector itself was never queried, so the cause could sit in the collector or in cluster-wide name resolution. Third, run a change-log lookback covering the hours before onset for both services.

> Evidence `tr_e6c992444e81`:

```
<tool_result id="tr_e6c992444e81" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" contains="Exception">
selector: {service="fraud-detection"} |= "Exception"
2026-10-06T17:03:44.365552+00:00  java.io.InterruptedIOException: timeout
2026-10-06T17:03:44.365820+00:00  Caused by: java.io.IOException: Canceled
2026-10-06T17:04:43.042754+00:00  java.net.UnknownHostException: otel-collector
2026-10-06T17:05:41.883647+00:00  java.net.UnknownHostException: otel-collector
```

> Evidence `tr_cd23ed25ab17`:

```
<tool_result id="tr_cd23ed25ab17" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T16:56:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-06T16:56:32.535392+00:00  2026-10-06 16:56:32 - fraud-detection - Consumed record with orderId: e1f8f549-c1a6-11f1-a373-4a0582158971, and updated total count to: 3584 trace_id=804ac5f42c946824b180b19c8c679904 span_id=1fe77223efdb2816 trace_flags=01 
2026-10-06T16:56:46.168702+00:00  2026-10-06 16:56:46 - fraud-detection - Consumed record with orderId: ea16e92a-c1a6-11f1-a373-4a0582158971, and updated total count to: 3585 trace_id=a35f709d8c09389fa1f4ab22222f215c span_id=7b2552416504f1e3 trace_flags=01 
2026-10-06T16:56:58.110536+00:00  2026-10-06 16:56:58 - fraud-detection - Consumed record with orderId: f1343f4e-c1a6-11f1-a373-4a0582158971, and updated total count to: 3586 trace_id=6bf94363a06a0b8d1058d2ddb422bacf span_id=8a217a915646a41b trace_flags=01 
2026-10-06T16:57:11.039020+00:00  2026-10-06 16:57:11 - fraud-detection - Consumed record with orderId: f8e8daed-c1a6-11f1-a373-4a0582158971, and updated total count to: 3587 trace_id=95755b22f444e8bb707bd843a6ed336a span_id=0a7b4d73a3333f0a trace_flags=01 
```

> Evidence `tr_cd87ab1bf25f`:

```
<tool_result id="tr_cd87ab1bf25f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T17:26:31.664000+00:00..2026-10-06T17:28:20.675685+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_cd87ab1bf25f>
```

