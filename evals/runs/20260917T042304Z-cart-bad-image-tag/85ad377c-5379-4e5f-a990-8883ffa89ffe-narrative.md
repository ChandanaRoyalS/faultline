# PlaceOrder aborts at the first cart lookup while checkout stays healthy

## What was visible, in order

The page arrived broad: fourteen services in the blast radius, nine alerting, severity critical, seed checkoutservice, five unmeasured edges in the graph. The natural first read was a shared dependency or a wide degradation. That read was wrong, and most of the effort went into proving it wrong.

Checkout's own error ratio came back first and argued nothing was happening: the incident-window mean sat at roughly 45% of baseline, lower than normal. Two details rescued it. A single change point at 04:25:30 peaked near two-thirds, above the baseline maximum — a short late burst, not a trend. And several intervals had no defined ratio at all, meaning stretches with no checkout traffic. A ratio can look calm because the denominator collapsed.

Logs then showed a live process: nothing but info-severity PlaceOrder request-start lines from 04:26:49 through 04:29:23, steady cadence, no restart banner, no error or timeout, no dependency named. The tell was absence — at 03:57 every PlaceOrder was followed by payment success, confirmation email and a queue write with an offset. After 04:26:49 that sequence is gone entirely.

Traces settled it. Four traces between 04:28:41 and 04:28:49 are three to five spans, 2.7–4.4ms end to end, ending at checkoutservice's client span for CartService/GetCart: ERROR, all duration as self-time, no cartservice server child span anywhere. One trace stops a level earlier with no cart call emitted at all. Healthy traces from 04:13–04:15 ran 42–54 spans through the full fan-out.

> Evidence `tr_93ad4c6210c1`:

```
<tool_result id="tr_93ad4c6210c1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" template="error-ratio" baseline="2026-09-16T22:25:37.000525+00:00..2026-09-17T01:27:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=563 mean=0.03379 min=0 max=0.6667 sd=0.1171
  baseline window: n=36 mean=0.07423 min=0 max=0.5 sd=0.08032
```

> Evidence `tr_aa6212e2c3aa`:

```
<tool_result id="tr_aa6212e2c3aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:57:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T03:57:36.814614+00:00  {"message":"[PlaceOrder] user_id=\"eb73b6e4-b24b-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T03:57:36.814473259Z"}
2026-09-17T03:57:36.833281+00:00  {"message":"payment went through (transaction_id: 2a67e5f1-4071-46fb-8899-fec7f03e0e26)","severity":"info","timestamp":"2026-09-17T03:57:36.833219426Z"}
2026-09-17T03:57:36.838193+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-17T03:57:36.838126259Z"}
2026-09-17T03:57:36.843647+00:00  {"message":"Successful to write message. offset: 60904","severity":"info","timestamp":"2026-09-17T03:57:36.843460009Z"}
```

> Evidence `tr_8d0fbe9b8a12`:

```
<tool_result id="tr_8d0fbe9b8a12" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T03:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00">
service: checkoutservice
8 trace(s) shown of 40 found, 200 spans; offsets are from each trace's root

trace 2625ae934f1c7a6a  root frontend/HTTP POST  25.9ms  started 2026-09-17T04:13:04.468016+00:00  42 spans
  +0.0ms frontend/HTTP POST 25.9ms [self 0.9ms]
```

## Dead ends worth keeping

Payment was chased hard and yielded nothing usable. Its error-ratio query returned no samples in either the incident or the baseline window. Both windows equally empty points at a series that was never populated — a naming or instrumentation mismatch — not telemetry going dark at onset. Watch the trap: the tooling reported the mean as unmoved, which reads like a clean bill of health but is absence of data. Payment is cleared only because the failing traces never reach it.

The one recorded change on paymentservice in 24h was an automated environment-variable revert 19.1 hours before onset, unsetting a tracing exporter endpoint. Telemetry config only, poor temporal fit, explains nothing.

The checkoutservice change log was empty — but two caveats a future responder should not repeat: the query was scoped to the seed at zero hops, and the window ran forward from 04:27:30 rather than backward, so anything landing before onset was never searched.

A shipping-to-quote hop at ~4.7–6.1ms had been flagged as a degrading edge; it appears only in the successful traces. Same for a 3.2ms cart HMSET and a 9.9ms payment charge.

The eight non-seed alerts were consequences. Currency, shipping, quote, email and accounting fired roughly 90 seconds later because the abort starved them of traffic; their spans never appear in the failing traces.

> Evidence `tr_cd3000fd86e8`:

```
<tool_result id="tr_cd3000fd86e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" template="error-ratio" baseline="2026-09-16T22:25:37.000525+00:00..2026-09-17T01:27:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_227bea3f8f97`:

```
<tool_result id="tr_227bea3f8f97" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T04:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" radius="candidate_cause" hops="1">
service: paymentservice
1 changes, ranked by suspicion
  #1  19.1h before onset  2026-09-16T09:21:04.136085+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317  ->  None
</tool_result:tr_227bea3f8f97>
```

> Evidence `tr_a69bfa12916a`:

```
<tool_result id="tr_a69bfa12916a" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T04:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_a69bfa12916a>
```

> Evidence `tr_8d0fbe9b8a12`:

```
<tool_result id="tr_8d0fbe9b8a12" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T03:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00">
service: checkoutservice
8 trace(s) shown of 40 found, 200 spans; offsets are from each trace's root

trace 2625ae934f1c7a6a  root frontend/HTTP POST  25.9ms  started 2026-09-17T04:13:04.468016+00:00  42 spans
  +0.0ms frontend/HTTP POST 25.9ms [self 0.9ms]
```

## Where it landed and what is still open

Best reading: cartservice stopped serving from roughly 04:25 to 04:28, refusing or resetting connections, while checkoutservice — healthy, accepting requests, logging no errors — returned fast errors at its first downstream hop. A fast client-side error with no server span and no accumulated latency is the shape of a refused RPC, not a slow one. Fix class: restart.

Confidence is low for one reason: no query was ever run against cartservice. Its logs, memory and connection-pool figures, restart history and change record are entirely unexamined. The mechanism inside cart is inferred from the shape of an upstream trace.

Three threads for whoever picks this up. Dispatch against cartservice directly. Get the exact gRPC status on the failing GetCart client span — UNAVAILABLE, DEADLINE_EXCEEDED and INTERNAL point three different ways and it was never reported. Check cart's Redis backend, since a Redis outage would give an identical upstream signature if cart failed fast or crash-looped. Separately, checkout's request rate, p95 and saturation were never returned and its logs are truncated between ~03:58 and 04:26:49, so true onset remains unpinned.

> Evidence `tr_8d0fbe9b8a12`:

```
<tool_result id="tr_8d0fbe9b8a12" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T03:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00">
service: checkoutservice
8 trace(s) shown of 40 found, 200 spans; offsets are from each trace's root

trace 2625ae934f1c7a6a  root frontend/HTTP POST  25.9ms  started 2026-09-17T04:13:04.468016+00:00  42 spans
  +0.0ms frontend/HTTP POST 25.9ms [self 0.9ms]
```

> Evidence `tr_aa6212e2c3aa`:

```
<tool_result id="tr_aa6212e2c3aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:57:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T03:57:36.814614+00:00  {"message":"[PlaceOrder] user_id=\"eb73b6e4-b24b-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T03:57:36.814473259Z"}
2026-09-17T03:57:36.833281+00:00  {"message":"payment went through (transaction_id: 2a67e5f1-4071-46fb-8899-fec7f03e0e26)","severity":"info","timestamp":"2026-09-17T03:57:36.833219426Z"}
2026-09-17T03:57:36.838193+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-17T03:57:36.838126259Z"}
2026-09-17T03:57:36.843647+00:00  {"message":"Successful to write message. offset: 60904","severity":"info","timestamp":"2026-09-17T03:57:36.843460009Z"}
```

> Evidence `tr_93ad4c6210c1`:

```
<tool_result id="tr_93ad4c6210c1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T04:29:24.165475+00:00" template="error-ratio" baseline="2026-09-16T22:25:37.000525+00:00..2026-09-17T01:27:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=563 mean=0.03379 min=0 max=0.6667 sd=0.1171
  baseline window: n=36 mean=0.07423 min=0 max=0.5 sd=0.08032
```

