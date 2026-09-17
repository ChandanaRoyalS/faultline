# paymentservice critical alert with a healthy charge path: a telemetry-export config edit

## What the responder saw first

The page named paymentservice, severity critical, and the blast radius was drawn as three services starting from payments. That framing sets an expectation — checkouts failing, charges erroring — and the first half hour was spent discovering that the expectation was wrong in every direction it was tested.

The first useful move was the change log for paymentservice covering the full 24h leading to the page. It held exactly two entries, both from platform-automation, both touching the same environment variable: the OTLP traces export endpoint. The most recent one landed roughly five minutes before the alert (call it T-5m) and set that endpoint to a loopback address on port 4317. The other entry, about 20.5 hours earlier, had set the same variable back to unset. So this was not a first-time rollout; it was a re-application of a value that somebody had deliberately backed out the day before. That flip-flop shape is the single most load-bearing observation in this record.

> Evidence `tr_6794690e86df`:

```
<tool_result id="tr_6794690e86df" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:49:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" radius="seed" hops="0">
service: paymentservice
2 changes, ranked by suspicion
  #1  5m before onset  2026-09-17T05:43:12.122072+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  20.5h before onset  2026-09-16T09:21:04.136085+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Ruling out the obvious causes on the alerting service

With a config edit in hand it is tempting to stop, so the change log was read for what was *not* there. No deploy or image rollout for paymentservice in the whole window. No feature flag toggles. No credential, secret, or dependency-auth rotation — which matters because an expiring gateway credential is the classic explanation for a payments page and it simply is not in the record. No individual human actor either; both edits are attributed to automation, so the "someone was hand-editing under pressure" story does not apply.

The edit is telemetry-plane only. It changes where traces are shipped. It does not touch payment logic, gateway addresses, or any dependency endpoint.

> Evidence `tr_6794690e86df`:

```
<tool_result id="tr_6794690e86df" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:49:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" radius="seed" hops="0">
service: paymentservice
2 changes, ranked by suspicion
  #1  5m before onset  2026-09-17T05:43:12.122072+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  20.5h before onset  2026-09-16T09:21:04.136085+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## The request path was healthy the whole time

Logs for paymentservice across roughly T-30m to T+2m are unbroken info-level charge-request / transaction-complete pairs. Every charge request has a matching completion with a transaction id, charges resolve in around half a millisecond, and there is no panic, no stack trace, no startup banner, no auth or validation error text, and no mention of any dependency by name. Critically, the newest lines cover T-1m through T+2m continuously — the service was serving and succeeding straight through the alert.

Two caveats a future responder should carry: the result was truncated (oldest 8 lines and newest 32 retained), so roughly T-30m to T-1m is unobserved; and the container hostname differs between the oldest and newest retained lines while the process id does not, which suggests a pod or container replacement happened somewhere in that unobserved middle. That replacement is never explained and remains open.

> Evidence `tr_3f1d3e055e48`:

```
<tool_result id="tr_3f1d3e055e48" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:19:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T05:19:02.443244+00:00  {"level":30,"time":1789622342443,"pid":17,"hostname":"8f6b7face2a8","trace_id":"217be6e648c1a503e82b05030805f351","span_id":"a8f29946dce80810","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":295,"high":0,"unsigned":false},"nanos":668429893},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-17T05:19:02.443633+00:00  {"level":30,"time":1789622342443,"pid":17,"hostname":"8f6b7face2a8","trace_id":"217be6e648c1a503e82b05030805f351","span_id":"a8f29946dce80810","trace_flags":"01","transactionId":"b7751e92-5544-473d-9d5a-1a11069d5c44","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":295,"high":0,"unsigned":false},"nanos":668429893,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-17T05:19:10.020157+00:00  {"level":30,"time":1789622350020,"pid":17,"hostname":"8f6b7face2a8","trace_id":"14d4d4434cd3697e29c958e3a1f12389","span_id":"ddce764600040132","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3718,"high":0,"unsigned":false},"nanos":759999999},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-17T05:19:10.020787+00:00  {"level":30,"time":1789622350020,"pid":17,"hostname":"8f6b7face2a8","trace_id":"14d4d4434cd3697e29c958e3a1f12389","span_id":"ddce764600040132","trace_flags":"01","transactionId":"eca0c961-624e-4f2b-b815-db33bffc64e7","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":3718,"high":0,"unsigned":false},"nanos":759999999,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Traces agreed, but from the wrong six hours

A trace query returned 45 traces / 200 spans with paymentservice present throughout as a callee of checkoutservice. Every Charge span completes clean — no error status, durations of 0.2ms to 3.1ms with the nested charge child under 1ms. The service was neither down nor slow nor erroring. The only degrading hop flagged in any checkout trace was shippingservice to quoteservice at 18–24% of trace self-time, entirely unrelated to payments. There was even a single-span root trace showing paymentservice making its own OTLP export call, which at the time read as proof that export had not stopped.

This is the dead end worth remembering. The query window ran approximately T-7h to T-1h — it ends *before* the config edit at T-5m. So "export did not stop" was concluded from a period in which the endpoint had not yet been changed. The trace evidence establishes a healthy baseline and nothing about the post-change state. Anyone picking this up should re-run the same query anchored after T-5m; whether paymentservice telemetry still arrives after the edit is the decisive fact and it was never checked.

> Evidence `tr_9298c776bea9`:

```
<tool_result id="tr_9298c776bea9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-16T22:49:00.583000+00:00..2026-09-17T04:49:00.583000+00:00">
service: paymentservice
6 trace(s) shown of 45 found, 200 spans; offsets are from each trace's root

trace 161b0757715e6336  root frontend/HTTP POST  30.0ms  started 2026-09-17T04:14:39.526014+00:00  44 spans
  +0.0ms frontend/HTTP POST 30.0ms [self 0.0ms]
```

## The metric that returned nothing

The paymentservice span-derived error-ratio query came back with no samples at all — not a gap, not a zero, an empty series. The instinct is to read that as "collection broke at onset," and that instinct was tested and rejected: the six-hour baseline window is equally empty. A series that never existed before the alert cannot have been broken by the alert. The likelier explanations are a label mismatch, missing span-metrics instrumentation, or a different metric name.

The important discipline here is not to launder emptiness into health. Several readings of this result — "flat and healthy," "no sustained departure," "no pre-onset ramp" — are artifacts of there being nothing to plot. None of them are findings. And because no request-rate, latency, or alert-definition query was ever retrieved, what the page actually fired on is unknown. That gap is the second thing left open.

> Evidence `tr_9c126d3555e8`:

```
<tool_result id="tr_9c126d3555e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-16T23:49:00.583000+00:00..2026-09-17T05:49:00.583000+00:00" template="error-ratio" baseline="2026-09-16T17:49:00.583000+00:00..2026-09-16T23:49:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Downstream: checkoutservice was fine, and was getting better

checkoutservice error ratio is identically zero across the incident window — 129 samples, zero variance, no step, no ramp, nothing at the alert moment. The preceding baseline carried a real error ratio (mean around 0.17, peaks near 0.67), so the direction of travel is errors *clearing* before the window opened, not appearing during it. Whatever was wrong at checkout earlier had already recovered.

One scoping caveat: the query aggregates all checkoutservice spans by status code and is not narrowed to the outbound payment call. It is evidence about the service as a whole. But since the total is zero, any payment-edge errors would have to be a subset of zero, so the conclusion holds for the edge too.

> Evidence `tr_074bebd38483`:

```
<tool_result id="tr_074bebd38483" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T05:19:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" template="error-ratio" baseline="2026-09-17T04:46:54.727381+00:00..2026-09-17T05:19:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0.1724 min=0 max=0.6667 sd=0.2823
```

## Where this landed

The reading, at medium confidence, is a telemetry-plane failure rather than a customer-facing one. The only near-onset change on the path repointed trace export to a loopback address five minutes before the page, re-applying a value previously reverted on purpose. Payments continued succeeding throughout, checkout emitted no errors, and the metric that would have shown otherwise was empty for reasons predating the incident. The alert appears to reflect missing observability, not failing traffic.

Fix class is a config revert: put the export endpoint back to the state it was in after the earlier revert.

> Evidence `tr_6794690e86df`:

```
<tool_result id="tr_6794690e86df" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:49:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" radius="seed" hops="0">
service: paymentservice
2 changes, ranked by suspicion
  #1  5m before onset  2026-09-17T05:43:12.122072+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  20.5h before onset  2026-09-16T09:21:04.136085+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_3f1d3e055e48`:

```
<tool_result id="tr_3f1d3e055e48" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:19:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T05:19:02.443244+00:00  {"level":30,"time":1789622342443,"pid":17,"hostname":"8f6b7face2a8","trace_id":"217be6e648c1a503e82b05030805f351","span_id":"a8f29946dce80810","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":295,"high":0,"unsigned":false},"nanos":668429893},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-17T05:19:02.443633+00:00  {"level":30,"time":1789622342443,"pid":17,"hostname":"8f6b7face2a8","trace_id":"217be6e648c1a503e82b05030805f351","span_id":"a8f29946dce80810","trace_flags":"01","transactionId":"b7751e92-5544-473d-9d5a-1a11069d5c44","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":295,"high":0,"unsigned":false},"nanos":668429893,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-17T05:19:10.020157+00:00  {"level":30,"time":1789622350020,"pid":17,"hostname":"8f6b7face2a8","trace_id":"14d4d4434cd3697e29c958e3a1f12389","span_id":"ddce764600040132","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3718,"high":0,"unsigned":false},"nanos":759999999},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-17T05:19:10.020787+00:00  {"level":30,"time":1789622350020,"pid":17,"hostname":"8f6b7face2a8","trace_id":"14d4d4434cd3697e29c958e3a1f12389","span_id":"ddce764600040132","trace_flags":"01","transactionId":"eca0c961-624e-4f2b-b815-db33bffc64e7","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":3718,"high":0,"unsigned":false},"nanos":759999999,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_074bebd38483`:

```
<tool_result id="tr_074bebd38483" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T05:19:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" template="error-ratio" baseline="2026-09-17T04:46:54.727381+00:00..2026-09-17T05:19:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0.1724 min=0 max=0.6667 sd=0.2823
```

## Open items for whoever reads this next

Three things were not resolved and should be checked before this record is treated as closed.

First, re-run the paymentservice trace query for the period *after* T-5m. The existing trace evidence predates the change entirely and cannot speak to whether export survived it.

Second, retrieve the alert definition and the request-rate and latency series. Nobody established what the page fired on, which means nobody established that the page and the config edit are actually about the same thing.

Third, check whether a collector sidecar is listening on 127.0.0.1:4317 inside the paymentservice pod. If one is, the loopback value is benign and this whole line of reasoning collapses — in which case the unexplained pod replacement visible in the log hostnames becomes the more interesting thread.

> Evidence `tr_9298c776bea9`:

```
<tool_result id="tr_9298c776bea9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-16T22:49:00.583000+00:00..2026-09-17T04:49:00.583000+00:00">
service: paymentservice
6 trace(s) shown of 45 found, 200 spans; offsets are from each trace's root

trace 161b0757715e6336  root frontend/HTTP POST  30.0ms  started 2026-09-17T04:14:39.526014+00:00  44 spans
  +0.0ms frontend/HTTP POST 30.0ms [self 0.0ms]
```

> Evidence `tr_9c126d3555e8`:

```
<tool_result id="tr_9c126d3555e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-16T23:49:00.583000+00:00..2026-09-17T05:49:00.583000+00:00" template="error-ratio" baseline="2026-09-16T17:49:00.583000+00:00..2026-09-16T23:49:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3f1d3e055e48`:

```
<tool_result id="tr_3f1d3e055e48" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:19:00.583000+00:00..2026-09-17T05:51:06.438619+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T05:19:02.443244+00:00  {"level":30,"time":1789622342443,"pid":17,"hostname":"8f6b7face2a8","trace_id":"217be6e648c1a503e82b05030805f351","span_id":"a8f29946dce80810","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":295,"high":0,"unsigned":false},"nanos":668429893},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-17T05:19:02.443633+00:00  {"level":30,"time":1789622342443,"pid":17,"hostname":"8f6b7face2a8","trace_id":"217be6e648c1a503e82b05030805f351","span_id":"a8f29946dce80810","trace_flags":"01","transactionId":"b7751e92-5544-473d-9d5a-1a11069d5c44","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":295,"high":0,"unsigned":false},"nanos":668429893,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-17T05:19:10.020157+00:00  {"level":30,"time":1789622350020,"pid":17,"hostname":"8f6b7face2a8","trace_id":"14d4d4434cd3697e29c958e3a1f12389","span_id":"ddce764600040132","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3718,"high":0,"unsigned":false},"nanos":759999999},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-17T05:19:10.020787+00:00  {"level":30,"time":1789622350020,"pid":17,"hostname":"8f6b7face2a8","trace_id":"14d4d4434cd3697e29c958e3a1f12389","span_id":"ddce764600040132","trace_flags":"01","transactionId":"eca0c961-624e-4f2b-b815-db33bffc64e7","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":3718,"high":0,"unsigned":false},"nanos":759999999,"currencyCode":"USD"},"msg":"Transaction complete."}
```

