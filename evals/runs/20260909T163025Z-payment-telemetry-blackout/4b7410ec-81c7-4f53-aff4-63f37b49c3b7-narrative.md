# Payment alert with a healthy request path: telemetry export stopped at the source

## What we were paged for

The page named paymentservice and the blast radius was drawn as three services with critical severity, with two edges in the graph never having been measured at all. Sitting down at T+0 the natural expectation was a payment outage: charges failing, checkout backing up behind them, users unable to complete orders. That expectation is worth writing down because almost every dispatch that followed contradicted it, and the contradiction is the finding.

## First look: the request path was fine

The paymentservice log stream over the half hour before the page and through the page itself contains no error or warning lines whatsoever. Every returned record is info severity and every one is half of a matched pair: charge request received, transaction complete, roughly a millisecond apart, with a transaction id. That continues right to the end of the window, which means the service was up, serving, and succeeding at T+0 and after. So four early hypotheses died here at once: paymentservice down or crash-looping, charges timing out, a failing downstream named in an exception, and a rejected configuration value being logged. None of those leave a log stream that looks like this.

One caveat that mattered later: the result was truncated to the oldest eight and newest thirty-two lines, so roughly T-30m to T+0 of the log stream is simply unobserved. An error burst confined to that interval would not appear. A second, softer observation: the reporting hostname differs between the oldest and newest lines, consistent with a restart or instance replacement somewhere in the unobserved middle.

> Evidence `tr_8a0b0bdb0cd0`:

```
<tool_result id="tr_8a0b0bdb0cd0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-09T16:06:17.828067+00:00  {"level":30,"time":1788969977827,"pid":17,"hostname":"97921f75f4fe","trace_id":"662fb506703409f9849665256d970132","span_id":"11c322b61cdb1c6a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":8304,"high":0,"unsigned":false},"nanos":999999997},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-09T16:06:17.828574+00:00  {"level":30,"time":1788969977828,"pid":17,"hostname":"97921f75f4fe","trace_id":"662fb506703409f9849665256d970132","span_id":"11c322b61cdb1c6a","trace_flags":"01","transactionId":"543731c3-5e46-47bd-86c1-3a2afe312188","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":8304,"high":0,"unsigned":false},"nanos":999999997,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-09T16:06:18.032310+00:00  {"level":30,"time":1788969978032,"pid":17,"hostname":"97921f75f4fe","trace_id":"eb715a1466362bced4c09cb391cb1046","span_id":"65fbd5ba8ca3fd64","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":12358,"high":0,"unsigned":false},"nanos":519999992},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-09T16:06:18.033213+00:00  {"level":30,"time":1788969978032,"pid":17,"hostname":"97921f75f4fe","trace_id":"eb715a1466362bced4c09cb391cb1046","span_id":"65fbd5ba8ca3fd64","trace_flags":"01","transactionId":"b6384400-53fc-4cc3-b29a-b49433315cc1","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":12358,"high":0,"unsigned":false},"nanos":519999992,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Traces: the step change

Traces told the same story about latency and a different story about visibility. Every paymentservice Charge span in the returned data is sub-millisecond — server span around 0.2-0.3ms, inner charge span at or near zero — with no error status anywhere. The tool's own degrading-hop attribution never points at paymentservice; in all five complete checkout traces it points at the shippingservice HTTP client call into quoteservice, at roughly 17-24% of trace self-time, with root latencies a modest 22-36ms. That hop is a standing characteristic of this system, not the incident; chasing it would have been a dead end and it is recorded here so the next responder does not.

The useful signal is the shape of the stream itself. Full 36-42 span traces run through T-6m. Then one trace at T-6m that is structurally incomplete: eight spans, ending after an early ProductCatalog call, with no Charge, no ShipOrder, no EmptyCart, no email spans, and self-time oddly concentrated in checkoutservice. Then nothing at all for the remaining eight to nine minutes of the window. Not a ramp — full traces, one truncated trace, silence. We checked whether that gap could be a query artifact; the result was non-empty and unfiltered within the window, so the absence is real. Worth noting a nearby data point that cuts the other way: a standalone single-span paymentservice trace for an OTLP metrics Export RPC appears at T-9m and completes in about 1.1ms, so the export path was still working then.

> Evidence `tr_db859f4b8caf`:

```
<tool_result id="tr_db859f4b8caf" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00">
service: paymentservice
7 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 1fbf49442fa31612  root frontend/HTTP POST  29.3ms  started 2026-09-09T16:24:44.561021+00:00  36 spans
  +0.0ms frontend/HTTP POST 29.3ms [self 0.4ms]
```

## Metrics: two empty answers and one inverted one

The paymentservice error-ratio query returned no samples in the incident window — and no samples in the baseline window before it either. That symmetry is the point: the series is absent in both, so the gap predates the page and is not an onset marker. Most likely a collection or label mismatch, i.e. this service does not emit calls_total under that service_name. Either way, no error spike is observable for paymentservice and no claim about one can rest on this evidence. Latency percentiles, saturation and restart counts were not returned by this query at all; nothing is known about them.

The checkoutservice error ratio is the sharpest piece of evidence in the record, and it reads backwards from what you would expect. In the incident window it is flat zero — 129 samples, mean zero, standard deviation zero. In the preceding baseline it was noisy: mean around 0.16 with peaks near 0.67 and high variance. Errors were happening before the window and stopped when it opened. A system does not become perfect; a metric derived from spans goes to zero-variance zero when spans stop arriving. That reading also rules out the tidy escalation story — paymentservice failures propagating upward as checkoutservice errors — because any such propagation would have raised the aggregate ratio, and it did not. Note the query aggregates all checkoutservice calls and does not filter on a downstream peer, so it never isolated the checkout-to-payment edge specifically. Latency percentiles for checkoutservice were requested and not returned.

> Evidence `tr_5058419370b8`:

```
<tool_result id="tr_5058419370b8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" template="error-ratio" baseline="2026-09-09T15:34:06.041616+00:00..2026-09-09T16:06:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_41fae3883547`:

```
<tool_result id="tr_41fae3883547" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" template="error-ratio" baseline="2026-09-09T15:34:06.041616+00:00..2026-09-09T16:06:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0.1623 min=0 max=0.6667 sd=0.2737
```

## The change that lines up

The change log for paymentservice over the preceding 24 hours contains exactly nine entries, all of them environment-variable toggles of a single tracing-exporter endpoint variable, all attributed to platform-automation. No deploys, no image rollouts, no feature flags, no human actor, and nothing touching credentials, timeouts, upstream endpoints or resource limits. The entry closest to the page landed about five minutes before it — T-5m — setting OTEL_EXPORTER_OTLP_TRACES_ENDPOINT to http://127.0.0.1:4317, a loopback address where no collector listens.

Two things temper this. First, the set/revert pair repeats on a cadence of roughly every five to six hours across the window, which reads as an automated flapping loop rather than a deliberate action. Second, prior identical set operations at roughly T-18h, T-12h, T-7h and T-3.6h were each reverted without an incident being attributed to them — so the change alone is not obviously sufficient to produce what we saw here. The change log query for checkoutservice and its one-hop neighbours came back completely empty, which retires the in-window deploy, flag-flip and partial-rollout theories; but note that query's interval ran forward from T+0 rather than backward, so it does not speak to the period before the page.

> Evidence `tr_3a9d2f12f403`:

```
<tool_result id="tr_3a9d2f12f403" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:36:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T16:30:31.364625+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.4h before onset  2026-09-09T13:13:37.300770+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_c8f537ccb806`:

```
<tool_result id="tr_c8f537ccb806" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T16:36:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" radius="also_affected" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_c8f537ccb806>
```

## Where this lands

Reading the pieces together: the payment request path never broke. What broke was telemetry export from paymentservice, five minutes after its trace exporter endpoint was pointed at loopback. The evidence for that is the step change in the trace stream and the collapse of checkoutservice's error ratio to zero-variance zero — both signatures of spans no longer arriving rather than of a system improving. Call it an observability blackout, caused by a config value that is itself wrong: an exporter endpoint naming an address with no receiver. Fix class is a config revert, which is also what the automation loop does on its own every few hours. Confidence is medium, not high, for the reasons in the next section.

> Evidence `tr_db859f4b8caf`:

```
<tool_result id="tr_db859f4b8caf" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00">
service: paymentservice
7 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 1fbf49442fa31612  root frontend/HTTP POST  29.3ms  started 2026-09-09T16:24:44.561021+00:00  36 spans
  +0.0ms frontend/HTTP POST 29.3ms [self 0.4ms]
```

> Evidence `tr_41fae3883547`:

```
<tool_result id="tr_41fae3883547" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" template="error-ratio" baseline="2026-09-09T15:34:06.041616+00:00..2026-09-09T16:06:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0.1623 min=0 max=0.6667 sd=0.2737
```

> Evidence `tr_3a9d2f12f403`:

```
<tool_result id="tr_3a9d2f12f403" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:36:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T16:30:31.364625+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.4h before onset  2026-09-09T13:13:37.300770+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Still open

Three gaps a future responder should close rather than assume. One: whether any user-facing failure occurred at all. Every dispatch found the request path healthy, and no frontend success-rate evidence was ever gathered — that is the single most valuable missing query. Two: whether the export loss is confined to paymentservice or is collector-wide. No collector health was queried, and a collector outage would produce exactly the same shape in the data we have; this is the main competing explanation and it was never tested. Three: roughly T-30m to T+0 of the paymentservice log stream is unobserved due to result truncation, and no latency percentiles or saturation figures were returned for either paymentservice or checkoutservice.

> Evidence `tr_8a0b0bdb0cd0`:

```
<tool_result id="tr_8a0b0bdb0cd0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-09T16:06:17.828067+00:00  {"level":30,"time":1788969977827,"pid":17,"hostname":"97921f75f4fe","trace_id":"662fb506703409f9849665256d970132","span_id":"11c322b61cdb1c6a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":8304,"high":0,"unsigned":false},"nanos":999999997},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-09T16:06:17.828574+00:00  {"level":30,"time":1788969977828,"pid":17,"hostname":"97921f75f4fe","trace_id":"662fb506703409f9849665256d970132","span_id":"11c322b61cdb1c6a","trace_flags":"01","transactionId":"543731c3-5e46-47bd-86c1-3a2afe312188","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":8304,"high":0,"unsigned":false},"nanos":999999997,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-09T16:06:18.032310+00:00  {"level":30,"time":1788969978032,"pid":17,"hostname":"97921f75f4fe","trace_id":"eb715a1466362bced4c09cb391cb1046","span_id":"65fbd5ba8ca3fd64","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":12358,"high":0,"unsigned":false},"nanos":519999992},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-09T16:06:18.033213+00:00  {"level":30,"time":1788969978032,"pid":17,"hostname":"97921f75f4fe","trace_id":"eb715a1466362bced4c09cb391cb1046","span_id":"65fbd5ba8ca3fd64","trace_flags":"01","transactionId":"b6384400-53fc-4cc3-b29a-b49433315cc1","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":12358,"high":0,"unsigned":false},"nanos":519999992,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_5058419370b8`:

```
<tool_result id="tr_5058419370b8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" template="error-ratio" baseline="2026-09-09T15:34:06.041616+00:00..2026-09-09T16:06:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_41fae3883547`:

```
<tool_result id="tr_41fae3883547" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T16:06:15.583000+00:00..2026-09-09T16:38:25.124384+00:00" template="error-ratio" baseline="2026-09-09T15:34:06.041616+00:00..2026-09-09T16:06:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0.1623 min=0 max=0.6667 sd=0.2737
```

