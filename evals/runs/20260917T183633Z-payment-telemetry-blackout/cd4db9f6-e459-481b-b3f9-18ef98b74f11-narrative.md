# paymentservice critical alert with no telemetry behind it

## What we saw first

The page came from paymentservice, critical, at the onset moment we will call T+0 (18:42:45). Blast radius was recorded as three services starting from paymentservice, with two edges we never got measurements across. The first thing a responder should know is that the alert did not arrive with the usual supporting picture: there was no error-rate curve to look at, no latency shape, no exemplar trace. That absence is itself the story, but it took several dead ends before anyone treated it that way rather than as a tooling hiccup.

## The metrics dead end

The natural first move was the span-derived error ratio for paymentservice over the incident window plus a 32-minute baseline. It returned nothing — not zeros, nothing. Both numerator and denominator series were absent, so the result cannot be read as 'healthy'; there was simply no series to read. Critically, the baseline window was just as empty as the incident window, which kills the tempting reading that collection broke at T+0. Whatever the gap is, it predates the alert. This query also told us nothing about request rate or latency; those were never measured and remain unmeasured.

> Evidence `tr_d9a6dceca055`:

```
<tool_result id="tr_d9a6dceca055" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T18:12:45.583000+00:00..2026-09-17T18:44:33.771651+00:00" template="error-ratio" baseline="2026-09-17T17:40:57.394349+00:00..2026-09-17T18:12:45.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The trace dead end

Next we widened to traces, an hour before onset through the end of the window. Zero spans for paymentservice, end to end. No stop, no gap, no thinning — which rules out both an onset-aligned export failure and a partial degradation such as sampling loss or collector backpressure, since either would have left spans earlier in the window. Traces therefore contributed nothing to timing the onset or scoping the radius, and the onset time had to stand on the alert and the change log alone.

> Evidence `tr_70fc53ef9511`:

```
<tool_result id="tr_70fc53ef9511" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T17:42:45.583000+00:00..2026-09-17T18:44:33.771651+00:00">
no traces for paymentservice over this window
</tool_result:tr_70fc53ef9511>
```

## The service was fine

Logs were the first signal that actually contained data, and they showed a working service: continuous info-level charge request/completion pairs, each completion within a millisecond of its request, running steadily from roughly T+0 through T+2m. No warn, error or fatal lines anywhere. That rules out charges failing, and rules out an ongoing restart cycle at the end of the window. Two caveats a future responder should keep. First, the log stream was found under the service label 'payment-service' while metrics and traces were queried under 'paymentservice' — a label mismatch is not excluded as a contributor to the emptiness above. Second, retention had already dropped the middle of the window, so the moments immediately at and just before onset are unobserved, and the container host id differs between the early and late retained lines. Something replaced the instance mid-window; whether that was a rollout or a kill, and whether it mattered, was never established.

> Evidence `tr_ba00d73b4854`:

```
<tool_result id="tr_ba00d73b4854" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T18:12:45.583000+00:00..2026-09-17T18:44:33.771651+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T18:12:55.092712+00:00  {"level":30,"time":1789668775092,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"8a58166690eef267067a7e39d4921084","span_id":"a4ab539798dec9be","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":266,"high":0,"unsigned":false},"nanos":799999996},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-17T18:12:55.093168+00:00  {"level":30,"time":1789668775092,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"8a58166690eef267067a7e39d4921084","span_id":"a4ab539798dec9be","trace_flags":"01","transactionId":"aec957e1-a8b9-456a-bc3a-f5dd49990010","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":266,"high":0,"unsigned":false},"nanos":799999996,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T18:12:57.753789+00:00  {"level":30,"time":1789668777753,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"859d74dc3e29fe3a38e8950644825484","span_id":"41827d4a64ee6537","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":437,"high":0,"unsigned":false},"nanos":699999998},"creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardCvv":397,"creditCardExpirationYear":2039,"creditCardExpirationMonth":5}},"msg":"Charge request received."}
2026-09-17T18:12:57.754302+00:00  {"level":30,"time":1789668777753,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"859d74dc3e29fe3a38e8950644825484","span_id":"41827d4a64ee6537","trace_flags":"01","transactionId":"e8f97f96-bcc7-4604-b44d-8d79a2642d09","cardType":"visa","lastFourDigits":"7968","amount":{"units":{"low":437,"high":0,"unsigned":false},"nanos":699999998,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## The caller was quieter, not noisier

We checked the upstream caller, checkoutservice, expecting propagated failures. The opposite: its error ratio was exactly zero for all 128 samples of the incident window, while the pre-incident baseline had averaged around 0.16 with excursions near 0.67. Errors went away going into the incident, not up. Note the query was unscoped by peer — it aggregates all checkoutservice spans — so 'no payment-call errors' is an inference from the absence of any errors at all. Either way, checkoutservice is not the origin and had nothing to propagate.

> Evidence `tr_bdc93f9465dd`:

```
<tool_result id="tr_bdc93f9465dd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T18:12:45.583000+00:00..2026-09-17T18:44:33.771651+00:00" template="error-ratio" baseline="2026-09-17T17:40:57.394349+00:00..2026-09-17T18:12:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1619 min=0 max=0.6667 sd=0.2713
```

## Where it actually landed

The change log for paymentservice held seven records in the window, all by platform-automation, all touching one environment variable: the OTLP traces endpoint. Four times over about thirteen hours it was set to a loopback address and then reverted. The instance roughly six minutes before onset was the exception — it was still in effect at T+0. No deploys, no releases, no flag flips, no dependency bumps, no credential rotations, and no human actor appears anywhere in the history. With the exporter pointed at an address where nothing listens, the service goes dark to the telemetry stack while continuing to serve charges normally, which is precisely the combination the logs and the empty metric/trace queries describe. Confidence is medium; the fix class is a config revert. Note the honest tension: the three earlier identical set events were each reverted without an attributed incident, so the change may be necessary but not sufficient, and the pending unreverted state is what distinguishes this occurrence.

> Evidence `tr_56b09c695d58`:

```
<tool_result id="tr_56b09c695d58" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T18:42:45.583000+00:00..2026-09-17T18:44:33.771651+00:00" radius="seed" hops="0">
service: paymentservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T18:36:39.517440+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  4.2h before onset  2026-09-17T14:31:24.799205+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Left open

Nobody established any user-visible impact, and nobody established what the critical rule actually evaluated. If it was a no-data condition, this was an observability-only event and no customer was affected — but that was never confirmed. The emptiness in traces and metrics predates the change by more than an hour, which the loopback endpoint alone does not explain; a label mismatch or a separate instrumentation gap is still live. The mid-window instance replacement and its cause are unobserved because of the log retention hole. The third service in the triage set and both unmeasured edges were never dispatched at all.

> Evidence `tr_70fc53ef9511`:

```
<tool_result id="tr_70fc53ef9511" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T17:42:45.583000+00:00..2026-09-17T18:44:33.771651+00:00">
no traces for paymentservice over this window
</tool_result:tr_70fc53ef9511>
```

> Evidence `tr_d9a6dceca055`:

```
<tool_result id="tr_d9a6dceca055" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T18:12:45.583000+00:00..2026-09-17T18:44:33.771651+00:00" template="error-ratio" baseline="2026-09-17T17:40:57.394349+00:00..2026-09-17T18:12:45.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ba00d73b4854`:

```
<tool_result id="tr_ba00d73b4854" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T18:12:45.583000+00:00..2026-09-17T18:44:33.771651+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T18:12:55.092712+00:00  {"level":30,"time":1789668775092,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"8a58166690eef267067a7e39d4921084","span_id":"a4ab539798dec9be","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":266,"high":0,"unsigned":false},"nanos":799999996},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-17T18:12:55.093168+00:00  {"level":30,"time":1789668775092,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"8a58166690eef267067a7e39d4921084","span_id":"a4ab539798dec9be","trace_flags":"01","transactionId":"aec957e1-a8b9-456a-bc3a-f5dd49990010","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":266,"high":0,"unsigned":false},"nanos":799999996,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T18:12:57.753789+00:00  {"level":30,"time":1789668777753,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"859d74dc3e29fe3a38e8950644825484","span_id":"41827d4a64ee6537","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":437,"high":0,"unsigned":false},"nanos":699999998},"creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardCvv":397,"creditCardExpirationYear":2039,"creditCardExpirationMonth":5}},"msg":"Charge request received."}
2026-09-17T18:12:57.754302+00:00  {"level":30,"time":1789668777753,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"859d74dc3e29fe3a38e8950644825484","span_id":"41827d4a64ee6537","trace_flags":"01","transactionId":"e8f97f96-bcc7-4604-b44d-8d79a2642d09","cardType":"visa","lastFourDigits":"7968","amount":{"units":{"low":437,"high":0,"unsigned":false},"nanos":699999998,"currencyCode":"USD"},"msg":"Transaction complete."}
```

