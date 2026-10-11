# Critical payment alert with no payment-side symptom: trace export endpoint left on loopback

## What the responder saw first

The page came from payment, severity critical, with a declared blast radius of three services. Onset was recorded at 19:29:16. The first thing worth saying about this incident is the thing that took longest to accept: nothing in payment's own behaviour ever looked wrong. Every instrument that should have shown the critical condition either returned nothing or returned health.

The working window throughout was roughly T-30m to T+2m around onset. Two edges of the three-service blast radius were never measured at all — no specialist was dispatched against the other two services — so everything below is payment-local.

## First line of attack: payment error logs (dead end, but informative)

The obvious move was to look for payment screaming. A Loki filter for lines containing "error" across the full window — which fully contains the 19:29:16 onset — returned zero lines. Not a thin result: an empty one. That single empty answer closed off several hypotheses at once. No exporter or collector error text, no connection-refused pattern, no RPC timeout pattern, nothing. The incident narrative could not be anchored in payment's own error logging, and the responder had to go elsewhere.

> Evidence `tr_8d91e69b300f`:

```
<tool_result id="tr_8d91e69b300f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" contains="error">
no log lines matched {service="payment"} |= "error" over this window
</tool_result:tr_8d91e69b300f>
```

## Unfiltered payment logs: a trap worth documenting

Dropping the filter and pulling all payment logs returned content, but truncated — only the oldest handful and newest few dozen lines survived, and the entire middle, including the onset minute, was discarded. It is easy to read that result as "payment was fine" and move on. It is not evidence of that; the incident minute simply is not in it.

What the retained lines do establish is real and useful: the selector matched the intended Node.js payment service, logging and shipping were working at both ends of the window, and the newest retained record — about two minutes after onset — is an info-level entry recording a card transaction completing successfully, with trace and span ids attached. Payment was not crashed, not hung, and not blanket-rejecting at window close.

> Evidence `tr_24b2e5ff92f3`:

```
<tool_result id="tr_24b2e5ff92f3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment"}
2026-10-09T18:59:24.730527+00:00  {
2026-10-09T18:59:24.730588+00:00    resource: {
2026-10-09T18:59:24.730592+00:00      attributes: {
2026-10-09T18:59:24.730596+00:00        'process.pid': 1,
```

## Metrics: two queries, both empty, and why that mattered

Span-derived error ratio for payment was queried twice. Both runs returned no samples — in the incident window and in the preceding baseline window alike. The tooling reported "no departure from baseline," which reads as reassuring and means nothing; it is an artifact of comparing emptiness to emptiness.

The important inference was the baseline being equally empty. That rules out the tempting story that the metric gap began at onset. The denominator — total calls regardless of status — was also empty, so payment had no span-metrics series under that label selector at all, across the whole hour. The practical consequence for a future responder: abandon the traces_span_metrics family for this service and go to runtime and transport series instead. Request rate, latency percentiles, heap, GC, event-loop lag and pool counts were never actually queried here and remain unmeasured.

> Evidence `tr_45a53db95206`:

```
<tool_result id="tr_45a53db95206" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" template="error-ratio" baseline="2026-10-09T18:27:13.867268+00:00..2026-10-09T18:59:16.664000+00:00">
service: payment
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_8a968aa941ab`:

```
<tool_result id="tr_8a968aa941ab" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" template="error-ratio" baseline="2026-10-09T18:27:13.867268+00:00..2026-10-09T18:59:16.664000+00:00">
service: payment
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment"}[5m]))
  incident window: no samples
  baseline window: no samples
```

## Traces: health up to a point, then silence

Sampled checkout traces showed payment participating normally: a gRPC Charge server span plus an inner charge span in every trace, server spans around 0.6–1.4ms, inner work 0.3–0.6ms, no error status anywhere, and the full checkout sequence completing through empty-cart, email and order publish. Where latency existed it was attributed to load-generator root self-time, not to any service hop, so neither payment nor checkout's other dependencies were the slow link.

Two caveats the responder should carry forward. First, several quote-service spans reported negative offsets against their trace root — clock skew in that part of the fleet. It muddies offset reading but does not touch the payment measurements. Second, and decisively: the sampled traces stop at 19:21:18. The query window ran to 19:31:19 and not one sampled trace falls at or near onset. Payment tracing demonstrably worked through 19:21:18; its state at 19:29:16 is unobserved, not proven absent.

> Evidence `tr_fb545a7a5108`:

```
<tool_result id="tr_fb545a7a5108" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00">
service: payment
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 1b3e20ba653a01a7  root load-generator/user_checkout_single  53.2ms  started 2026-10-09T19:14:46.122698+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 53.2ms [self 12.0ms]
```

## The change record, which is where it broke open

Five changes landed on payment in the hour before onset, all from the same automated platform actor, all touching one environment variable: the OTLP traces exporter endpoint. No deploys, no releases, no flag flips, no credential or certificate rotation, no dependency bumps, and no changes attributed to a human operator. One variable, nothing else — which narrowed the change-related blast radius to the trace-export path and killed off most of the standard change hypotheses in a single read.

The pattern was an oscillation: applied, reverted, applied, reverted, applied, at roughly ten-to-fifteen-minute intervals. The final application landed about seven minutes before onset and left the endpoint pointing at a loopback address on the pod's own host. The last sampled payment span sits at 19:21:18, seconds before that last application. That adjacency is the hinge of the whole record.

> Evidence `tr_4ee3762a334c`:

```
<tool_result id="tr_4ee3762a334c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-08T19:29:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" radius="seed" hops="0">
service: payment
5 changes, ranked by suspicion
  #1  7m before onset  2026-10-09T19:21:24.868359+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on payment
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  20m before onset  2026-10-09T19:08:38.725626+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on payment
```

## Conclusion

The cause is the trace exporter endpoint value itself, left in the applied state pointing at loopback by the last of five automated edits, roughly seven minutes before onset. Telemetry export was directed at an address nothing serves. The resulting data absence read upward as a critical payment incident, while payment continued charging cards successfully. Confidence is medium. The remedy class is a configuration revert, and the oscillating apply/revert behaviour of the automation should be treated as a second defect in its own right.

> Evidence `tr_4ee3762a334c`:

```
<tool_result id="tr_4ee3762a334c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-08T19:29:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" radius="seed" hops="0">
service: payment
5 changes, ranked by suspicion
  #1  7m before onset  2026-10-09T19:21:24.868359+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on payment
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  20m before onset  2026-10-09T19:08:38.725626+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on payment
```

> Evidence `tr_fb545a7a5108`:

```
<tool_result id="tr_fb545a7a5108" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00">
service: payment
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 1b3e20ba653a01a7  root load-generator/user_checkout_single  53.2ms  started 2026-10-09T19:14:46.122698+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 53.2ms [self 12.0ms]
```

> Evidence `tr_24b2e5ff92f3`:

```
<tool_result id="tr_24b2e5ff92f3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-09T18:59:16.664000+00:00..2026-10-09T19:31:19.460732+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment"}
2026-10-09T18:59:24.730527+00:00  {
2026-10-09T18:59:24.730588+00:00    resource: {
2026-10-09T18:59:24.730592+00:00      attributes: {
2026-10-09T18:59:24.730596+00:00        'process.pid': 1,
```

## Still open

Three things a future responder should resolve before trusting this record completely.

First, the alert predicate is unknown. It is not established whether the 19:29:16 page fired on a customer-facing symptom or on the absence of telemetry. That distinction decides whether this was ever a real outage.

Second, the endpoint is only wrong if nothing is listening. Nobody confirmed whether a collector is bound to loopback port 4317 on payment's host. Check that before the revert is treated as the fix.

Third, the interval from roughly 19:21 to 19:31 is substantially unobserved — logs truncated through it, no sampled traces in it, no span metrics at all — and the other two services in the blast radius were never investigated. The conclusion rests on adjacency in time, not on a measured signal at onset.

