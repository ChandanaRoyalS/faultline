# Payment path alert that turned out to be a telemetry blind spot

## What the responder saw first

The page named paymentservice and carried critical severity, with a blast radius drawn across three services. That framing sets an expectation: charges are failing or slow, and checkout is bleeding. Nothing in the first few minutes of looking confirmed that expectation, and the rest of this record is mostly the story of that gap between the alert's implication and the evidence.

The first instinct was to reach for paymentservice error rate. That reach came back empty in a way that was easy to misread — see the dead ends below.

## The service was healthy the whole time

Application logs are the clearest thing in the record. Across the window every payment-service line is info level and every charge request has a matching completion. No error, warn, or fatal lines. No shutdown or drain notices, no panics, no startup or bind failures.

A charge arriving right at the alert instant completed in roughly four tenths of a millisecond, and successful pairs continued without a break for the next two minutes to the edge of the window. All of those lines carry the same pid and container hostname, so the process serving at the alert was the same process serving two minutes later — no restart, no replacement, no eviction.

Handling time is sub-millisecond throughout. Traffic is intermittent rather than dense, with quiet spells of twenty to twenty-five seconds; those spells contain no output at all rather than failed attempts, which is worth noting because a sparse log can look like an outage if you squint.

One loose thread: the oldest lines in the window (around three hours before the alert) carry a different pid and hostname than the newest. Something replaced the instance somewhere in the truncated middle. Nothing here dates or explains that, and it does not bear on the alert window.

> Evidence `tr_f60a43a23791`:

```
<tool_result id="tr_f60a43a23791" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T11:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T11:25:52.320703+00:00  {"level":30,"time":1789644352320,"pid":16,"hostname":"09d81a8e6b92","trace_id":"d3de108b2282d964bf181c9cc1e226b8","span_id":"f41f44925a7688a3","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":554,"high":0,"unsigned":false},"nanos":299999995},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-17T11:25:52.321500+00:00  {"level":30,"time":1789644352320,"pid":16,"hostname":"09d81a8e6b92","trace_id":"d3de108b2282d964bf181c9cc1e226b8","span_id":"f41f44925a7688a3","trace_flags":"01","transactionId":"aa226b75-b8c7-4657-9a14-9bfa115f2192","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":554,"high":0,"unsigned":false},"nanos":299999995,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T11:25:53.961884+00:00  {"level":30,"time":1789644353961,"pid":16,"hostname":"09d81a8e6b92","trace_id":"c2572178ecd2bc430b5b324be22aa80b","span_id":"64a3a3aff8fa1d5e","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":23302,"high":0,"unsigned":false},"nanos":699999986},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-17T11:25:53.962624+00:00  {"level":30,"time":1789644353961,"pid":16,"hostname":"09d81a8e6b92","trace_id":"c2572178ecd2bc430b5b324be22aa80b","span_id":"64a3a3aff8fa1d5e","trace_flags":"01","transactionId":"586bf0af-a6d3-4824-9d39-b6952c86f10c","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":23302,"high":0,"unsigned":false},"nanos":699999986,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## The caller agreed

If paymentservice were failing, checkoutservice would show it. Its span error ratio is flat zero across the whole window — 128 samples, mean, min, max and standard deviation all zero. No trend, no intermittent spikes.

The interesting wrinkle is the baseline immediately before the window, which carried a real error ratio averaging around 0.17 and peaking near two thirds. So the window is not a continuation of calm; it is a drop into calm. Whatever was erroring in checkout ended before or at the window's start. That argues against any active, still-running error condition at the time of the page.

Caveat the reader should keep: this metric is service-wide and not broken out by downstream peer, so it does not isolate payment-directed calls. It still bounds them — a zero total means no subset can be non-zero.

> Evidence `tr_f7a92b0eca17`:

```
<tool_result id="tr_f7a92b0eca17" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" template="error-ratio" baseline="2026-09-17T13:23:54.094935+00:00..2026-09-17T13:55:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1697 min=0 max=0.6667 sd=0.2767
```

## Where the signal actually stopped

Traces are where the shape of the incident finally appeared. paymentservice is not dark: 34 traces matched, and sampled ones show Charge spans nested under checkoutservice at several points earlier in the window. While exporting, the work is unremarkable — the server-side span sits around 0.2ms with an effectively free child. The hops flagged as degrading in those traces are frontend to checkout and shipping to quote, never payment. The service even emitted its own telemetry-export client span as a trace root, proving the pipeline was alive earlier.

Then it stops. The latest sampled trace begins around 14:17, while the query window ran through 14:27. Roughly eight minutes of silence ending at the alert.

Importantly, the silence is not payment-only. The surviving traces are whole checkout traces carrying frontend, cart, currency, shipping, email and accounting spans, and they end at the same time. So this is not a case of one service's spans being dropped out of otherwise intact traces.

> Evidence `tr_79febd00f80b`:

```
<tool_result id="tr_79febd00f80b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00">
service: paymentservice
6 trace(s) shown of 34 found, 200 spans; offsets are from each trace's root

trace 33a998657ec84fd7  root frontend/HTTP POST  30.0ms  started 2026-09-17T14:09:57.352012+00:00  48 spans
  +0.0ms frontend/HTTP POST 30.0ms [self 0.0ms]
```

## The change

Change history for paymentservice in the window holds five entries. All five are by platform-automation, and all five touch exactly one environment variable: the OTLP traces endpoint. Each time it is set to a loopback address, and each time it is reverted.

The most recent entry re-applies that loopback value roughly six minutes before the alert, making it the nearest change in time. The variable was absent immediately beforehand, so this was unset-to-set rather than a value tweak. The set-and-revert pattern repeats three times across roughly nine hours — about 8.7h, 3.8h, and 6m before onset — which reads as an automation loop flapping rather than a deliberate one-off edit.

The mechanism is small and mundane: a config value naming an address with nothing listening behind it. Exports go nowhere. The process keeps serving. Observability of paymentservice failed; paymentservice did not.

> Evidence `tr_7970c9cda487`:

```
<tool_result id="tr_7970c9cda487" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T14:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" radius="seed" hops="0">
service: paymentservice
5 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T14:19:42.590765+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.7h before onset  2026-09-17T10:46:30.144142+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Dead ends worth keeping

Error ratio for paymentservice. The query returned no samples in the incident window — which for about a minute looked like proof that telemetry was severed at onset. It is not. The three-hour baseline window is equally empty. The underlying call-count series simply does not exist under that service label, most likely an instrumentation, label-naming, or scrape-coverage matter that predates everything here. It also means no request rate, latency percentile, restart count, or saturation evidence came from this source at all. Do not read this emptiness as either a spike or a clean bill of health.

A code deploy or release. Ruled out — no deploy or release events appear in the window; every entry is an environment edit.

An image or artifact roll. Ruled out — no image or digest changes recorded.

A human operator. Ruled out — every change is attributed to platform-automation.

A broad config audit. Ruled out — one key, touched five times. The surface is tiny.

A feature flag toggle. Ruled out — no flag edits present.

A long-standing stable setting. Ruled out — the same value was applied and reverted three times in nine hours.

Crash, OOM kill, SIGTERM, or failed restart at onset. All ruled out by the logs: same process identity, continuous successful service, no signal or lifecycle output.

Card declines, validation errors, or gateway errors reaching callers. Ruled out — every charge has a matching completion at info level.

paymentservice as the latency source. Ruled out twice over: sub-millisecond in-handler time in the logs, ~0.2ms server spans in traces.

An active checkout error condition. Ruled out — errors sit in the baseline, not the window.

A clean cut at the moment of the change. This one I wanted to be true and it is not. The last observed span predates the edit by two or three minutes. The boundary is earlier and imprecise, and the record should not pretend otherwise.

> Evidence `tr_bf5326f86bad`:

```
<tool_result id="tr_bf5326f86bad" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T11:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" template="error-ratio" baseline="2026-09-17T08:23:54.094935+00:00..2026-09-17T11:25:45.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_7970c9cda487`:

```
<tool_result id="tr_7970c9cda487" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T14:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" radius="seed" hops="0">
service: paymentservice
5 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T14:19:42.590765+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.7h before onset  2026-09-17T10:46:30.144142+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_f60a43a23791`:

```
<tool_result id="tr_f60a43a23791" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T11:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T11:25:52.320703+00:00  {"level":30,"time":1789644352320,"pid":16,"hostname":"09d81a8e6b92","trace_id":"d3de108b2282d964bf181c9cc1e226b8","span_id":"f41f44925a7688a3","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":554,"high":0,"unsigned":false},"nanos":299999995},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-17T11:25:52.321500+00:00  {"level":30,"time":1789644352320,"pid":16,"hostname":"09d81a8e6b92","trace_id":"d3de108b2282d964bf181c9cc1e226b8","span_id":"f41f44925a7688a3","trace_flags":"01","transactionId":"aa226b75-b8c7-4657-9a14-9bfa115f2192","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":554,"high":0,"unsigned":false},"nanos":299999995,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T11:25:53.961884+00:00  {"level":30,"time":1789644353961,"pid":16,"hostname":"09d81a8e6b92","trace_id":"c2572178ecd2bc430b5b324be22aa80b","span_id":"64a3a3aff8fa1d5e","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":23302,"high":0,"unsigned":false},"nanos":699999986},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-17T11:25:53.962624+00:00  {"level":30,"time":1789644353961,"pid":16,"hostname":"09d81a8e6b92","trace_id":"c2572178ecd2bc430b5b324be22aa80b","span_id":"64a3a3aff8fa1d5e","trace_flags":"01","transactionId":"586bf0af-a6d3-4824-9d39-b6952c86f10c","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":23302,"high":0,"unsigned":false},"nanos":699999986,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_79febd00f80b`:

```
<tool_result id="tr_79febd00f80b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00">
service: paymentservice
6 trace(s) shown of 34 found, 200 spans; offsets are from each trace's root

trace 33a998657ec84fd7  root frontend/HTTP POST  30.0ms  started 2026-09-17T14:09:57.352012+00:00  48 spans
  +0.0ms frontend/HTTP POST 30.0ms [self 0.0ms]
```

> Evidence `tr_f7a92b0eca17`:

```
<tool_result id="tr_f7a92b0eca17" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" template="error-ratio" baseline="2026-09-17T13:23:54.094935+00:00..2026-09-17T13:55:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1697 min=0 max=0.6667 sd=0.2767
```

## Conclusion and confidence

The payment path never broke. The cause is the loopback traces-endpoint value re-applied by platform-automation about six minutes before the page, the third application in a roughly nine-hour flap, touching no other key and no artifact. The fix class is a config revert, plus whatever stops the automation from re-applying it.

Confidence is medium, not high, and the reasons are below.

> Evidence `tr_7970c9cda487`:

```
<tool_result id="tr_7970c9cda487" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T14:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" radius="seed" hops="0">
service: paymentservice
5 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T14:19:42.590765+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.7h before onset  2026-09-17T10:46:30.144142+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_f60a43a23791`:

```
<tool_result id="tr_f60a43a23791" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T11:25:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T11:25:52.320703+00:00  {"level":30,"time":1789644352320,"pid":16,"hostname":"09d81a8e6b92","trace_id":"d3de108b2282d964bf181c9cc1e226b8","span_id":"f41f44925a7688a3","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":554,"high":0,"unsigned":false},"nanos":299999995},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-17T11:25:52.321500+00:00  {"level":30,"time":1789644352320,"pid":16,"hostname":"09d81a8e6b92","trace_id":"d3de108b2282d964bf181c9cc1e226b8","span_id":"f41f44925a7688a3","trace_flags":"01","transactionId":"aa226b75-b8c7-4657-9a14-9bfa115f2192","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":554,"high":0,"unsigned":false},"nanos":299999995,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T11:25:53.961884+00:00  {"level":30,"time":1789644353961,"pid":16,"hostname":"09d81a8e6b92","trace_id":"c2572178ecd2bc430b5b324be22aa80b","span_id":"64a3a3aff8fa1d5e","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":23302,"high":0,"unsigned":false},"nanos":699999986},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-17T11:25:53.962624+00:00  {"level":30,"time":1789644353961,"pid":16,"hostname":"09d81a8e6b92","trace_id":"c2572178ecd2bc430b5b324be22aa80b","span_id":"64a3a3aff8fa1d5e","trace_flags":"01","transactionId":"586bf0af-a6d3-4824-9d39-b6952c86f10c","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":23302,"high":0,"unsigned":false},"nanos":699999986,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_79febd00f80b`:

```
<tool_result id="tr_79febd00f80b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00">
service: paymentservice
6 trace(s) shown of 34 found, 200 spans; offsets are from each trace's root

trace 33a998657ec84fd7  root frontend/HTTP POST  30.0ms  started 2026-09-17T14:09:57.352012+00:00  48 spans
  +0.0ms frontend/HTTP POST 30.0ms [self 0.0ms]
```

> Evidence `tr_f7a92b0eca17`:

```
<tool_result id="tr_f7a92b0eca17" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00" template="error-ratio" baseline="2026-09-17T13:23:54.094935+00:00..2026-09-17T13:55:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1697 min=0 max=0.6667 sd=0.2767
```

## Still open

The timing does not line up cleanly. The last observed span precedes the edit by two to three minutes, and only 6 of 34 traces were sampled, so the apparent boundary may be an artifact of sampling. A per-minute span count over the window would settle whether export ceased at the change or earlier. Until then the causal link is inferred, not demonstrated.

The alert rule that fired was never retrieved. Whether it is an absence-of-telemetry rule — which would close the loop neatly — is unconfirmed. Worth pulling first if this recurs.

Two hops flagged as degrading in the traces, shipping to quote and frontend to checkout, were never investigated. Neither service was dispatched, and triage reports two unmeasured edges crossed. A concurrent latency problem in that region is not excluded by anything in this record. If users reported slowness, that is where to look, not at payments.

> Evidence `tr_79febd00f80b`:

```
<tool_result id="tr_79febd00f80b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T13:55:45.583000+00:00..2026-09-17T14:27:37.071065+00:00">
service: paymentservice
6 trace(s) shown of 34 found, 200 spans; offsets are from each trace's root

trace 33a998657ec84fd7  root frontend/HTTP POST  30.0ms  started 2026-09-17T14:09:57.352012+00:00  48 spans
  +0.0ms frontend/HTTP POST 30.0ms [self 0.0ms]
```

