# Critical alert on paymentservice, measured failure only on checkoutservice

## What the responder saw first

The page named paymentservice, severity critical, blast radius of three services. Everything in this record is offset from that alert: T+0. The first instinct was the obvious one — go look at paymentservice and find out why it was failing. That instinct consumed most of the investigation and produced nothing, and the reason it produced nothing is the useful part of this record.

## Dead end one: paymentservice metrics do not exist

The first dispatch asked for an error ratio on paymentservice against a 32-minute baseline ending at T-30m. The query returned zero samples — not zeros, no samples at all — in both the incident window and the baseline. Because the baseline was equally empty, the gap cannot be read as a symptom of the event; the series was already absent long before T+0. Nothing about a crash, a dead exporter, or a scrape failure at onset can be supported by this. Nor can silence be read as health: the label selector simply matches nothing for this service. No request rate, no latency percentiles, no saturation signal of any kind was ever available for paymentservice. Anyone returning to this incident should treat that as an instrumentation gap to fix, not a clue to chase.

> Evidence `tr_95a053e1c0b1`:

```
<tool_result id="tr_95a053e1c0b1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T12:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" template="error-ratio" baseline="2026-09-10T12:22:13.889226+00:00..2026-09-10T12:54:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Dead end two: paymentservice logs are clean through the alert

Logs for the payment service across T-30m to T+2m came back entirely info-level: paired charge-received and transaction-complete records, each completion carrying a transaction id and card type. The kept tail covers T-8s onward contiguously, bracketing the alert timestamp itself, and contains no error severity, no exception text, no downstream timeout or failure message. Charges were still completing at a steady cadence at the window edge, roughly T+2m. So: paymentservice had not crashed, was not failing a downstream call, and was not declining charges at the moment it was paged for. One incidental observation worth noting — the reporting hostname differs between the oldest and newest kept lines, so the serving process changed somewhere in the unreturned middle. That middle, roughly T-30m to T-8s, was never observed; the result was truncated to the oldest 8 and newest 32 lines.

> Evidence `tr_5129518395da`:

```
<tool_result id="tr_5129518395da" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T12:54:18.472724+00:00  {"level":30,"time":1789044858472,"pid":17,"hostname":"f04808eae69d","trace_id":"b787d3e2f62d722f662d9e4f0a2d4934","span_id":"a29a2df4dcbd2f34","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":138,"high":0,"unsigned":false},"nanos":849999999},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-10T12:54:18.473262+00:00  {"level":30,"time":1789044858472,"pid":17,"hostname":"f04808eae69d","trace_id":"b787d3e2f62d722f662d9e4f0a2d4934","span_id":"a29a2df4dcbd2f34","trace_flags":"01","transactionId":"8c5f74cb-2511-47d5-8f9a-e70705c2dfec","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":138,"high":0,"unsigned":false},"nanos":849999999,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-10T12:54:18.897219+00:00  {"level":30,"time":1789044858897,"pid":17,"hostname":"f04808eae69d","trace_id":"e2492781bdcb33b5853063b5801f4771","span_id":"315f9284dbe0e9bb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":2041,"high":0,"unsigned":false},"nanos":119999991},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-10T12:54:18.897603+00:00  {"level":30,"time":1789044858897,"pid":17,"hostname":"f04808eae69d","trace_id":"e2492781bdcb33b5853063b5801f4771","span_id":"315f9284dbe0e9bb","trace_flags":"01","transactionId":"09600c1f-2d6e-41d2-90be-252b837581c0","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":2041,"high":0,"unsigned":false},"nanos":119999991,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Dead end three: the configuration change five minutes before onset

The change record for paymentservice looked promising at first read. Seven recorded changes in a 24-hour window, all of them the same single environment-variable toggle: an OTLP traces endpoint being pointed at a loopback address, then reverted. The most recent set landed about five minutes before T+0 and, unlike the three earlier pairs, had no revert following it — it was still in effect at alert time. That is a tempting shape.

It does not hold up. The identical set-then-revert cycle had already run three times earlier the same day (roughly 21h, 14h, and 7h prior), each set reverted 11-12 minutes later, all by the platform-automation actor. If the toggle alone were sufficient to cause this failure, the earlier applications should have produced comparable onsets. Its distinguishing feature here is duration, not novelty. And its plausible reach is trace export behaviour — an exporter blocking or retrying against an unreachable local collector — not payment processing logic. Most decisively, as the next section shows, the actual measured failure had already been running for over an hour by the time this change landed.

The same record rules out several other candidates cleanly: no deployment or image rollout entries, no feature flag flips, no credential or secret rotation, no dependency or library bumps, and no ad-hoc human action — every entry is attributed to platform automation.

> Evidence `tr_43a6e07ebaf1`:

```
<tool_result id="tr_43a6e07ebaf1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T13:24:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" radius="seed" hops="0">
service: paymentservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-10T13:18:22.500257+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  6.5h before onset  2026-09-10T06:53:18.190056+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Where the failure actually was

The only measured failure in this incident is on checkoutservice. Its own span error ratio rose from a ~0.04% baseline mean (max under 2% across the preceding 92 minutes) to an ~11% mean in the incident window, with peaks near 67% — roughly a 254x shift, well outside baseline range and not explicable as metric noise.

The timing is the part that reframes everything above. The first threshold breach was at T-82m, with a second change point at T-46m. The alert at T+0 sits deep inside a long-running condition rather than marking its onset. Any story built around a single event at alert time is therefore wrong on arrival.

The shape of the elevation matters too. High standard deviation relative to the mean, and a window minimum of zero, mean the error ratio swung between clean and heavily failing intervals. That is inconsistent with a total dependency outage and points at a partial or intermittent condition. The errors are recorded as span status errors on checkoutservice's own call series, so the failure is visible at the checkoutservice layer regardless of which downstream is implicated.

> Evidence `tr_50d18f22666d`:

```
<tool_result id="tr_50d18f22666d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" template="error-ratio" baseline="2026-09-10T10:22:13.889226+00:00..2026-09-10T11:54:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=369 mean=0.1116 min=0 max=0.6667 sd=0.2396
  baseline window: n=369 mean=0.0004403 min=0 max=0.01935 sd=0.002282
```

## Dead end four: checkoutservice logs also came back clean

Having located the failure, the natural next step was to read checkout's logs for the error lines. This did not work either, for a mechanical reason: the query was truncated to the oldest 8 and newest 32 lines, and the region around T+0 fell in the dropped middle. Every kept line is info severity. In the tail (T+54s through T+2m) checkout completes the full PlaceOrder sequence — payment charge, confirmation email, Kafka write — with monotonically increasing offsets, so end-to-end orders were succeeding after the alert. The oldest kept lines at T-30m show the same clean pattern, so the traffic shape is unchanged between the two ends of the window.

What this does establish, negatively: checkout was not still degraded at T+2m; it never crashed or restarted (continuous logging, no startup banner, Kafka offsets advance without reset); and paymentservice was not hard-down or unreachable from checkout, since authorizations with distinct transaction ids succeed at both window ends. Throughput in the tail is sparse and irregular — single orders every 5-30s, with a ~27s gap — but nothing is logged in those gaps.

What it does not establish: the actual error lines at onset were never seen. Both log queries dropped the same middle span.

> Evidence `tr_fc84f1f5a321`:

```
<tool_result id="tr_fc84f1f5a321" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T12:54:18.454166+00:00  {"message":"[PlaceOrder] user_id=\"bc3ba74a-ad16-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:54:18.454044467Z"}
2026-09-10T12:54:18.473294+00:00  {"message":"payment went through (transaction_id: 8c5f74cb-2511-47d5-8f9a-e70705c2dfec)","severity":"info","timestamp":"2026-09-10T12:54:18.473190425Z"}
2026-09-10T12:54:18.479213+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-09-10T12:54:18.479066134Z"}
2026-09-10T12:54:18.479992+00:00  {"message":"Successful to write message. offset: 31680","severity":"info","timestamp":"2026-09-10T12:54:18.479891717Z"}
```

## Conclusion, and how far to trust it

The failing mechanism is an intermittent partial error condition on checkoutservice's outbound path, beginning around T-82m. paymentservice, the service that paged, shows no failure of its own in any evidence gathered. It is the alerting surface, not the source.

Confidence is medium, and the limit is coverage rather than contradiction. No fix class is identified because the specific failing call was never localized. Three concrete gaps remain open for whoever picks this up:

First, which downstream call inside checkoutservice's PlaceOrder path carries the error spans is unknown. Two edges in the blast radius were never measured, and the third service in the radius was never queried at all.

Second, no change record was ever pulled for checkoutservice or its dependencies. The two change points at T-82m and T-46m are unexplained; the only change history examined belongs to the wrong service.

Third, both log queries lost the same middle span, so the error lines at onset remain unobserved, and there are no saturation or latency metrics for either service to fall back on.

> Evidence `tr_50d18f22666d`:

```
<tool_result id="tr_50d18f22666d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" template="error-ratio" baseline="2026-09-10T10:22:13.889226+00:00..2026-09-10T11:54:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=369 mean=0.1116 min=0 max=0.6667 sd=0.2396
  baseline window: n=369 mean=0.0004403 min=0 max=0.01935 sd=0.002282
```

> Evidence `tr_5129518395da`:

```
<tool_result id="tr_5129518395da" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T12:54:18.472724+00:00  {"level":30,"time":1789044858472,"pid":17,"hostname":"f04808eae69d","trace_id":"b787d3e2f62d722f662d9e4f0a2d4934","span_id":"a29a2df4dcbd2f34","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":138,"high":0,"unsigned":false},"nanos":849999999},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-10T12:54:18.473262+00:00  {"level":30,"time":1789044858472,"pid":17,"hostname":"f04808eae69d","trace_id":"b787d3e2f62d722f662d9e4f0a2d4934","span_id":"a29a2df4dcbd2f34","trace_flags":"01","transactionId":"8c5f74cb-2511-47d5-8f9a-e70705c2dfec","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":138,"high":0,"unsigned":false},"nanos":849999999,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-10T12:54:18.897219+00:00  {"level":30,"time":1789044858897,"pid":17,"hostname":"f04808eae69d","trace_id":"e2492781bdcb33b5853063b5801f4771","span_id":"315f9284dbe0e9bb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":2041,"high":0,"unsigned":false},"nanos":119999991},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-10T12:54:18.897603+00:00  {"level":30,"time":1789044858897,"pid":17,"hostname":"f04808eae69d","trace_id":"e2492781bdcb33b5853063b5801f4771","span_id":"315f9284dbe0e9bb","trace_flags":"01","transactionId":"09600c1f-2d6e-41d2-90be-252b837581c0","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":2041,"high":0,"unsigned":false},"nanos":119999991,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_fc84f1f5a321`:

```
<tool_result id="tr_fc84f1f5a321" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:54:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T12:54:18.454166+00:00  {"message":"[PlaceOrder] user_id=\"bc3ba74a-ad16-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:54:18.454044467Z"}
2026-09-10T12:54:18.473294+00:00  {"message":"payment went through (transaction_id: 8c5f74cb-2511-47d5-8f9a-e70705c2dfec)","severity":"info","timestamp":"2026-09-10T12:54:18.473190425Z"}
2026-09-10T12:54:18.479213+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-09-10T12:54:18.479066134Z"}
2026-09-10T12:54:18.479992+00:00  {"message":"Successful to write message. offset: 31680","severity":"info","timestamp":"2026-09-10T12:54:18.479891717Z"}
```

> Evidence `tr_43a6e07ebaf1`:

```
<tool_result id="tr_43a6e07ebaf1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T13:24:15.583000+00:00..2026-09-10T13:26:17.276774+00:00" radius="seed" hops="0">
service: paymentservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-10T13:18:22.500257+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  6.5h before onset  2026-09-10T06:53:18.190056+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

