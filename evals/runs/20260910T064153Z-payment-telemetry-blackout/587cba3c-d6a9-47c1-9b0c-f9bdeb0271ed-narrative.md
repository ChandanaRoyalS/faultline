# Payment service alert with no matching payment failure: trace export pointed at a dead loopback port

## What the responder saw first

The page named paymentservice and carried critical severity, with a triage blast radius of three services. That framing set the initial expectation: a payment outage, probably with checkout bleeding errors behind it. Almost none of that expectation survived first contact.

The first thing worth knowing, and the thing that took longest to accept, is that the alert's own supporting signal was never recovered. No error-ratio, latency, request-volume or saturation series for paymentservice could be produced for the period leading into or following onset. The error-ratio query came back empty — not zero, empty — and stayed empty in the three-hour baseline window that preceded it as well. Because both windows are equally blank, the emptiness cannot be read as a symptom that began at onset; the series appears simply not to exist under the label set that was queried, which points at a naming, label or instrumentation mismatch rather than at service behaviour. An empty series is also not a clean bill of health, so it could not be used in either direction.

> Evidence `tr_a32af0265a24`:

```
<tool_result id="tr_a32af0265a24" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T03:48:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" template="error-ratio" baseline="2026-09-10T00:46:06.976865+00:00..2026-09-10T03:48:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The change record, and the cycle that mattered

With metrics unusable, the change log was the next stop, and it was the one place that produced a clear shape. In the full twenty-four-hour window paymentservice had exactly nine changes. All nine came from the same automated actor, platform-automation, and every one touched a single environment variable: the OTLP traces exporter endpoint. No deploys, no version rollouts, no flag flips, no credential rotations, no dependency bumps, no named human operator anywhere in the window. Each of those hypotheses was checked against the same record and discarded on the same grounds — they are absent, not merely unproven.

The interesting structure is the rhythm. Four prior set-then-revert pairs occurred at roughly three-and-a-half-hour intervals, each setting the traces endpoint to a loopback address and removing it eleven or twelve minutes later. The ninth entry, about six minutes before onset (call it T-6m), set the loopback endpoint again and has no matching revert recorded before onset. The service therefore entered the incident window with trace export addressed to a local port that has no collector behind it. That is the only change with plausible timing proximity, and its content is not a trigger for a downstream failure — the wrong value is the failure. Spans stop leaving the service.

> Evidence `tr_9a64d95e4027`:

```
<tool_result id="tr_9a64d95e4027" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T06:48:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T06:41:59.548640+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  7.6h before onset  2026-09-09T23:10:37.940565+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Checking whether payments were actually broken

Logs were the deciding evidence against a payment outage. Every payment-service line returned in the roughly thirty-two-minute window is informational, and consists of paired charge-received and transaction-complete records. From T+0 (06:48:53) through the window boundary at about T+1m (06:49:54), charges kept completing with transaction IDs, card types and amounts, several per minute. There is no error, exception, warning or rejection text anywhere in what was returned.

That let several plausible stories be closed. An error burst dominating logs from onset: the newest lines are continuous across onset and contain none. A named downstream dependency unreachable or erroring: no line names any RPC target or connection failure, and charges resolve inline within roughly half a millisecond of receipt. Expired credential or token causing rejections: no auth-related message at all, and charges are accepted. Input-validation rejections: varied currencies and amounts all completed. Process crash: output continues to the window edge.

One oddity is worth flagging without over-reading it. The reporting hostname differs between the early lines and the lines around onset, which is consistent with the pod having been replaced or rescheduled somewhere in the middle of the window. Nothing was built on that observation.

> Evidence `tr_1aeca8c4ed2c`:

```
<tool_result id="tr_1aeca8c4ed2c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:18:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T06:18:06.220252+00:00  {"level":30,"time":1789021086220,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"fb059e219e750727aa2f299e4ada14fd","span_id":"1bfe65b9ef211a0f","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":277,"high":0,"unsigned":false},"nanos":699999998},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-10T06:18:06.220695+00:00  {"level":30,"time":1789021086220,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"fb059e219e750727aa2f299e4ada14fd","span_id":"1bfe65b9ef211a0f","trace_flags":"01","transactionId":"572a2c51-43bb-4599-8e74-ed1faa5b51ed","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":277,"high":0,"unsigned":false},"nanos":699999998,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-10T06:18:11.384298+00:00  {"level":30,"time":1789021091384,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"3585f873bb52761449f0ad8e3f2efd9b","span_id":"a47d783c4d4e0b81","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":593,"high":0,"unsigned":false},"nanos":397639979},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T06:18:11.384711+00:00  {"level":30,"time":1789021091384,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"3585f873bb52761449f0ad8e3f2efd9b","span_id":"a47d783c4d4e0b81","trace_flags":"01","transactionId":"29b41470-965a-4b26-8a72-b8ab174fdf17","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":593,"high":0,"unsigned":false},"nanos":397639979,"currencyCode":"CAD"},"msg":"Transaction complete."}
```

## The caller, and a baseline that misled

checkoutservice was the obvious place to look for the missing error signal, and it produced a result that reads backwards on first glance. Error ratio in the incident window averaged effectively zero, peaking near 1.4%, roughly two hundred times below the preceding baseline mean of about 17%. No sustained departure was flagged.

That 'two hundred times better' figure is a dead end, and a seductive one. The baseline window itself was erratic, with a wide spread and a maximum where nearly two-thirds of calls errored. The apparent improvement is far more likely an artefact of comparing against an already-unstable or already-degraded stretch than evidence of anything happening at onset. What it does support is narrower and still useful: checkout-attributed error spans are essentially absent in the incident window, so no payment-path failure was surfacing through the caller, and onset cannot be placed at the alert time from this series. Only error ratio was returned — checkout latency, volume and payment-call coverage were never retrieved.

> Evidence `tr_712a833fa9e8`:

```
<tool_result id="tr_712a833fa9e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T06:18:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" template="error-ratio" baseline="2026-09-10T05:46:06.976865+00:00..2026-09-10T06:18:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.000798 min=0 max=0.0137 sd=0.003105
  baseline window: n=128 mean=0.174 min=0 max=0.6667 sd=0.2803
```

## Conclusion

The failure is telemetry visibility, not payments. Six minutes before onset the traces-export endpoint on paymentservice was set to a loopback address and, unlike the four preceding cycles, was never reverted, so the service ran with spans going nowhere. That is consistent with the empty span-derived error-ratio series, and it is consistent with a healthy payment path: charges continued completing successfully through the end of the observed window, and the caller showed near-zero error ratio. The fix class is a config revert — restore the prior exporter endpoint value and, separately, fix whatever in the automation left the fifth cycle half-completed.

Confidence is medium, and the reason for the hedge is in the next section.

> Evidence `tr_9a64d95e4027`:

```
<tool_result id="tr_9a64d95e4027" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T06:48:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T06:41:59.548640+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  7.6h before onset  2026-09-09T23:10:37.940565+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_a32af0265a24`:

```
<tool_result id="tr_a32af0265a24" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T03:48:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" template="error-ratio" baseline="2026-09-10T00:46:06.976865+00:00..2026-09-10T03:48:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1aeca8c4ed2c`:

```
<tool_result id="tr_1aeca8c4ed2c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:18:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T06:18:06.220252+00:00  {"level":30,"time":1789021086220,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"fb059e219e750727aa2f299e4ada14fd","span_id":"1bfe65b9ef211a0f","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":277,"high":0,"unsigned":false},"nanos":699999998},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-10T06:18:06.220695+00:00  {"level":30,"time":1789021086220,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"fb059e219e750727aa2f299e4ada14fd","span_id":"1bfe65b9ef211a0f","trace_flags":"01","transactionId":"572a2c51-43bb-4599-8e74-ed1faa5b51ed","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":277,"high":0,"unsigned":false},"nanos":699999998,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-10T06:18:11.384298+00:00  {"level":30,"time":1789021091384,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"3585f873bb52761449f0ad8e3f2efd9b","span_id":"a47d783c4d4e0b81","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":593,"high":0,"unsigned":false},"nanos":397639979},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T06:18:11.384711+00:00  {"level":30,"time":1789021091384,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"3585f873bb52761449f0ad8e3f2efd9b","span_id":"a47d783c4d4e0b81","trace_flags":"01","transactionId":"29b41470-965a-4b26-8a72-b8ab174fdf17","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":593,"high":0,"unsigned":false},"nanos":397639979,"currencyCode":"CAD"},"msg":"Transaction complete."}
```

> Evidence `tr_712a833fa9e8`:

```
<tool_result id="tr_712a833fa9e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T06:18:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" template="error-ratio" baseline="2026-09-10T05:46:06.976865+00:00..2026-09-10T06:18:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.000798 min=0 max=0.0137 sd=0.003105
  baseline window: n=128 mean=0.174 min=0 max=0.6667 sd=0.2803
```

## Open questions for the next responder

First and largest: what signal actually fired the paymentservice alert? No error, latency or saturation series for the service was ever recovered, so the alert's basis is unverified. Anyone reopening this should start by finding the alert rule and the series it evaluates.

Second, and it undercuts the causal chain: it is not established that the paymentservice call-count series ever existed under the queried labels. The pre-onset baseline is equally empty. If that series never existed, the emptiness has nothing to do with the change six minutes before onset, and the link between the config value and the observed blank telemetry becomes circumstantial rather than demonstrated. Confirming or refuting the existence of that series before the change is the single highest-value follow-up.

Third, coverage gaps. The log query was truncated to the oldest eight and newest thirty-two lines, leaving roughly the thirty minutes before onset unobserved; an error burst confined to that stretch would not appear. The third triaged service was never dispatched, and the two unmeasured edges in the blast radius were never measured.

> Evidence `tr_a32af0265a24`:

```
<tool_result id="tr_a32af0265a24" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T03:48:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" template="error-ratio" baseline="2026-09-10T00:46:06.976865+00:00..2026-09-10T03:48:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1aeca8c4ed2c`:

```
<tool_result id="tr_1aeca8c4ed2c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:18:00.583000+00:00..2026-09-10T06:49:54.189135+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T06:18:06.220252+00:00  {"level":30,"time":1789021086220,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"fb059e219e750727aa2f299e4ada14fd","span_id":"1bfe65b9ef211a0f","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":277,"high":0,"unsigned":false},"nanos":699999998},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-10T06:18:06.220695+00:00  {"level":30,"time":1789021086220,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"fb059e219e750727aa2f299e4ada14fd","span_id":"1bfe65b9ef211a0f","trace_flags":"01","transactionId":"572a2c51-43bb-4599-8e74-ed1faa5b51ed","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":277,"high":0,"unsigned":false},"nanos":699999998,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-10T06:18:11.384298+00:00  {"level":30,"time":1789021091384,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"3585f873bb52761449f0ad8e3f2efd9b","span_id":"a47d783c4d4e0b81","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":593,"high":0,"unsigned":false},"nanos":397639979},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T06:18:11.384711+00:00  {"level":30,"time":1789021091384,"pid":17,"hostname":"d08c3cd20bb8","trace_id":"3585f873bb52761449f0ad8e3f2efd9b","span_id":"a47d783c4d4e0b81","trace_flags":"01","transactionId":"29b41470-965a-4b26-8a72-b8ab174fdf17","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":593,"high":0,"unsigned":false},"nanos":397639979,"currencyCode":"CAD"},"msg":"Transaction complete."}
```

