# paymentservice alert with no corresponding symptom: telemetry export pointed at a dead loopback address

## What we saw first

The page named paymentservice and nothing else. Severity was set critical, and the blast radius as drawn covered three services, with two edges in the graph that carry no measurement at all — worth remembering, because those unmeasured edges are exactly where a confident-sounding story can hide.

The responder's first move was the obvious one: pull the error ratio for paymentservice around onset and see how bad it was. That query came back empty. Not zero — empty. No samples in the incident window at all. The same query over the three hours preceding onset was also empty, which is the detail that reframed the whole investigation: there was never a series here to lose. Whatever the alert was reacting to, the span-derived call counters for this service name were not producing data before the incident either.

At that point the working question stopped being "why is paymentservice failing" and became "why can we not see paymentservice."

> Evidence `tr_327aa30e6511`:

```
<tool_result id="tr_327aa30e6511" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Checking whether payments were actually broken

Before chasing the observability angle we needed to know if customers were losing money. The service's own logs answered that cleanly. Across roughly T-1m to T+2m the log stream is a continuous run of INFO-level pairs: charge received, transaction complete, typically about a millisecond apart, each completion carrying a transaction id. No errors, no warnings, no stack traces, no timeout or connection messages from any downstream. Traffic in that block spans several distinct cards and both USD and CAD, so this is not a narrow failure surviving behind a mostly-healthy aggregate.

One oddity in the logs that we chased and then set down: the container hostname on the newest lines differs from the hostname on the lines an hour earlier, while the process id is unchanged. That is consistent with the service having been moved or restarted onto a new container somewhere in the middle of the window we did not retrieve. It could have mattered. It did not turn out to explain anything — the charge/completion pattern is identical on both sides of the gap.

> Evidence `tr_fc89f8e7fd07`:

```
<tool_result id="tr_fc89f8e7fd07" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T22:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-09T22:05:11.780982+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-09T22:05:11.781531+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","transactionId":"beab4c30-718e-409b-95df-8780448130fe","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-09T22:05:31.935510+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":788,"high":0,"unsigned":false},"nanos":500000000},"creditCard":{"creditCardNumber":"4539-1103-5661-7083","creditCardCvv":784,"creditCardExpirationYear":2039,"creditCardExpirationMonth":4}},"msg":"Charge request received."}
2026-09-09T22:05:31.936062+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","transactionId":"717a6e68-1c1c-48a4-8452-d1fdcdd7f3ab","cardType":"visa","lastFourDigits":"7083","amount":{"units":{"low":788,"high":0,"unsigned":false},"nanos":500000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Ruling out the caller

With paymentservice looking healthy from the inside, the next candidate was the caller. If checkoutservice were failing its calls into payments, that would explain a page even with clean payment logs.

It was not. checkoutservice's error ratio over the incident window ran at roughly 62% of its baseline mean — better than normal, not worse. There is no change point at or near onset; the series is flat there. The one change point the analysis does surface sits about 33 minutes earlier and is a single high-ratio sample against a wide standard deviation, the signature of a spike on a small denominator rather than a level shift. We also confirmed checkoutservice kept serving: more defined samples in the incident window than in baseline, and the same number of no-traffic intervals in each, so the occasional gaps in that series are a standing property, not something that started at onset.

Caveat we recorded rather than resolved: this result measured error ratio only. Latency and request rate for checkoutservice were never pulled, so "the payment call path is unchanged" is supported on the error dimension alone.

> Evidence `tr_ec4f6e6c8903`:

```
<tool_result id="tr_ec4f6e6c8903" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=457 mean=0.04204 min=0 max=0.6667 sd=0.1562
  baseline window: n=354 mean=0.06817 min=0 max=0.3016 sd=0.1117
```

## The change history

The change log for paymentservice over the preceding 24 hours holds exactly nine entries. All nine come from the same actor, platform-automation, and all nine touch one thing: the OTLP traces exporter endpoint environment variable.

About five minutes before onset, that variable was set to a loopback address — 127.0.0.1 on the OTLP port — with no collector listening behind it. Unlike the four earlier set/revert pairs in the same window, this one has no matching revert. It was still in effect when the incident began.

The earlier pairs are informative. Roughly 18.7h, 13.6h, 10.1h and 6.6h before onset, the same variable was set the same way and reverted about eleven or twelve minutes later each time. That is an automation loop flapping, not a one-off operator error.

What the change history also let us discard: there is no deploy, image rollout, or version bump in the window — all nine entries are environment-variable updates, so a code change is out. There is no feature-flag entry either, so a business-logic flip (provider, retry policy, currency handling) is out. Every entry is attributed to automation; no human made an ad-hoc change during the incident. And the "nothing changed here, it must be external" hypothesis is off the table, because something did change and stayed changed.

> Evidence `tr_3fc206e3cba2`:

```
<tool_result id="tr_3fc206e3cba2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T23:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T22:59:00.850606+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  6.4h before onset  2026-09-09T16:41:58.800019+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Where that leaves the cause

The reading we settled on: paymentservice is not failing to serve payments, it is failing to be observed. Its traces were being shipped to an address with nothing behind it, which is why the span-derived counters that feed the error-ratio dashboards have no samples, while the service's own logs show it charging cards normally and its caller shows no degradation. The wrong endpoint value is itself the failure.

Fix class is a configuration revert: point the exporter back at the real collector, then stop the automation loop that keeps re-applying the loopback value. Confidence medium, for the reasons below.

> Evidence `tr_3fc206e3cba2`:

```
<tool_result id="tr_3fc206e3cba2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T23:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T22:59:00.850606+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  6.4h before onset  2026-09-09T16:41:58.800019+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_327aa30e6511`:

```
<tool_result id="tr_327aa30e6511" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_fc89f8e7fd07`:

```
<tool_result id="tr_fc89f8e7fd07" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T22:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-09T22:05:11.780982+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-09T22:05:11.781531+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","transactionId":"beab4c30-718e-409b-95df-8780448130fe","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-09T22:05:31.935510+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":788,"high":0,"unsigned":false},"nanos":500000000},"creditCard":{"creditCardNumber":"4539-1103-5661-7083","creditCardCvv":784,"creditCardExpirationYear":2039,"creditCardExpirationMonth":4}},"msg":"Charge request received."}
2026-09-09T22:05:31.936062+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","transactionId":"717a6e68-1c1c-48a4-8452-d1fdcdd7f3ab","cardType":"visa","lastFourDigits":"7083","amount":{"units":{"low":788,"high":0,"unsigned":false},"nanos":500000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_ec4f6e6c8903`:

```
<tool_result id="tr_ec4f6e6c8903" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=457 mean=0.04204 min=0 max=0.6667 sd=0.1562
  baseline window: n=354 mean=0.06817 min=0 max=0.3016 sd=0.1117
```

## Open questions the next responder inherits

Three things are genuinely unresolved, and the first two are load-bearing.

First: what fired the alert? Neither metrics nor logs show anything at the onset timestamp. There is no user-facing impact evidence anywhere in this record. We never identified the signal behind the page.

Second: the timing does not fully close. The metrics baseline covering the three hours before onset is also empty, but the loopback value was only re-applied about five minutes before onset. So the missing series predates this change. Either the earlier flap cycles left the exporter broken for longer than the change log suggests, or the counters were never produced for this service name for an unrelated reason. The change explains the state at onset; it does not explain the baseline.

Third, and the one to check before acting: label mismatch. The logs are keyed service="payment-service", the metric query selects service_name="paymentservice". If that selector is simply wrong, the empty metric result is a query artifact rather than evidence of anything, and the whole verdict weakens considerably. Re-run the counter query with the label the logs actually use before you touch the configuration.

> Evidence `tr_327aa30e6511`:

```
<tool_result id="tr_327aa30e6511" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_fc89f8e7fd07`:

```
<tool_result id="tr_fc89f8e7fd07" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T22:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-09T22:05:11.780982+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-09T22:05:11.781531+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","transactionId":"beab4c30-718e-409b-95df-8780448130fe","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-09T22:05:31.935510+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":788,"high":0,"unsigned":false},"nanos":500000000},"creditCard":{"creditCardNumber":"4539-1103-5661-7083","creditCardCvv":784,"creditCardExpirationYear":2039,"creditCardExpirationMonth":4}},"msg":"Charge request received."}
2026-09-09T22:05:31.936062+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","transactionId":"717a6e68-1c1c-48a4-8452-d1fdcdd7f3ab","cardType":"visa","lastFourDigits":"7083","amount":{"units":{"low":788,"high":0,"unsigned":false},"nanos":500000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_3fc206e3cba2`:

```
<tool_result id="tr_3fc206e3cba2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T23:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T22:59:00.850606+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  6.4h before onset  2026-09-09T16:41:58.800019+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Dead ends worth keeping

Recorded so nobody re-walks them: paymentservice as the origin of an exception storm (all INFO, clean pairs). A downstream card processor or ledger failing behind paymentservice (no dependency or timeout messages, sub-millisecond completions). paymentservice crash-looping (continuous requests handled by one live process). Failure confined to a currency or card (CAD and multiple distinct cards all complete). checkoutservice as originator or propagator (error ratio below baseline, no change point at onset). A code deploy or feature flag as the change (neither exists in the window). Telemetry stopping at onset as a symptom of the incident (the baseline is equally empty, so there was nothing to stop). And the container hostname change in the logs, which looked like a restart worth explaining and explained nothing.

> Evidence `tr_fc89f8e7fd07`:

```
<tool_result id="tr_fc89f8e7fd07" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T22:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-09T22:05:11.780982+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-09T22:05:11.781531+00:00  {"level":30,"time":1788991511780,"pid":17,"hostname":"8c5384d4f153","trace_id":"acbf66c5dbbdcf1e6905bc3caec8e238","span_id":"1a0823f4a654e490","trace_flags":"01","transactionId":"beab4c30-718e-409b-95df-8780448130fe","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-09T22:05:31.935510+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":788,"high":0,"unsigned":false},"nanos":500000000},"creditCard":{"creditCardNumber":"4539-1103-5661-7083","creditCardCvv":784,"creditCardExpirationYear":2039,"creditCardExpirationMonth":4}},"msg":"Charge request received."}
2026-09-09T22:05:31.936062+00:00  {"level":30,"time":1788991531935,"pid":17,"hostname":"8c5384d4f153","trace_id":"71d43af9225c3a05ee0ea17b6a372d4c","span_id":"ab1aca28a097c23b","trace_flags":"01","transactionId":"717a6e68-1c1c-48a4-8452-d1fdcdd7f3ab","cardType":"visa","lastFourDigits":"7083","amount":{"units":{"low":788,"high":0,"unsigned":false},"nanos":500000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_ec4f6e6c8903`:

```
<tool_result id="tr_ec4f6e6c8903" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=457 mean=0.04204 min=0 max=0.6667 sd=0.1562
  baseline window: n=354 mean=0.06817 min=0 max=0.3016 sd=0.1117
```

> Evidence `tr_327aa30e6511`:

```
<tool_result id="tr_327aa30e6511" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T20:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" template="error-ratio" baseline="2026-09-09T17:03:05.942966+00:00..2026-09-09T20:05:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3fc206e3cba2`:

```
<tool_result id="tr_3fc206e3cba2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T23:05:00.583000+00:00..2026-09-09T23:06:55.223034+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T22:59:00.850606+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  6.4h before onset  2026-09-09T16:41:58.800019+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

