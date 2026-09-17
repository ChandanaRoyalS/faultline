# Checkout PlaceOrder requests stop completing mid-flow with no logged errors

## Clock and framing

All offsets in this record are relative to T+0, the moment checkoutservice's error ratio crossed threshold and completed orders stopped appearing. Paging followed at roughly T+2m for checkoutservice, frontend and loadgenerator, with accountingservice, currencyservice, frauddetectionservice, cartservice and emailservice joining shortly after, and shippingservice and quoteservice alerting last at about T+3m30s. Blast radius was assessed at 14 services, severity critical, with checkoutservice as the entry point. Five edges in the affected path had no usable measurement on either side.

> Evidence `tr_5fcac3511390`:

```
<tool_result id="tr_5fcac3511390" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" template="error-ratio" baseline="2026-09-17T16:19:03.239853+00:00..2026-09-17T16:51:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=35 mean=0.00297 min=0 max=0.02083 sd=0.005903
```

## What the responder saw first

The opening signal was checkoutservice's own error ratio: roughly 8.9% mean across the incident window against about 0.3% at rest, a change of around thirtyfold, peaking near 67%. A single change point sits at T+0. The series is volatile rather than a flat elevated floor, so the first instinct was to look for intermittent bursts. Two intervals inside the window carry no defined ratio at all, meaning checkoutservice recorded no calls whatsoever during them - genuine gaps in span-derived traffic, not scrape artifacts. Request rate and tail latency were never pulled for checkoutservice, so the usual comparison against the known noisy p95 baseline was never made.

> Evidence `tr_5fcac3511390`:

```
<tool_result id="tr_5fcac3511390" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" template="error-ratio" baseline="2026-09-17T16:19:03.239853+00:00..2026-09-17T16:51:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=35 mean=0.00297 min=0 max=0.02083 sd=0.005903
```

## The logs changed the shape of the problem

Checkout's logs contain no error or warning lines anywhere in the window - every returned line is informational. That killed the assumption that checkout would name its failing dependency in an exception. What the logs do show is a clean break in the order flow. Before roughly T-2m each order-start line is followed within tens of milliseconds by payment confirmation, confirmation email, and an order-publish write. From T-10s through the last line at about T+4m, only order-start lines appear. No payment, no email, no publish. Order-start lines keep arriving at a steady cadence right to the end of the window, across multiple currencies and distinct user ids, so the process is alive, accepting work, and simply not finishing it. The failure mode is silent hanging, not loud failing. There is a roughly two-and-a-half minute gap in returned lines bracketing onset.

> Evidence `tr_9fea75aec3e6`:

```
<tool_result id="tr_9fea75aec3e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T16:51:23.499943+00:00  {"message":"[PlaceOrder] user_id=\"03e6747a-b2b8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T16:51:23.499856009Z"}
2026-09-17T16:51:23.518258+00:00  {"message":"payment went through (transaction_id: 3b031b5d-c953-4c6f-b9b0-53f673c914a1)","severity":"info","timestamp":"2026-09-17T16:51:23.518145926Z"}
2026-09-17T16:51:23.522996+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-17T16:51:23.522922926Z"}
2026-09-17T16:51:23.524562+00:00  {"message":"Successful to write message. offset: 65395","severity":"info","timestamp":"2026-09-17T16:51:23.524464634Z"}
```

## Narrowing to a pre-charge hop

Because the flow never reaches payment confirmation after onset, everything downstream of the charge - email delivery, the order publish to accounting and fraud detection - is out of the causal path and was set aside. paymentservice logs confirmed the boundary from the other side: every charge receipt in the kept range has a matching completion within about a millisecond, sub-millisecond deltas hold right up to the last line at about T-2m, and then nothing at all for the remaining six-plus minutes of the window. Process identity (host and pid) is unchanged throughout, with no startup, shutdown or fatal entries. Charges stopped arriving; they were not being processed slowly, queued, or lost to contention. The block therefore sits somewhere between checkout accepting the order and checkout issuing the charge.

> Evidence `tr_3391d631f80b`:

```
<tool_result id="tr_3391d631f80b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T16:51:23.517133+00:00  {"level":30,"time":1789663883517,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"ebb4b88b22c19d3cf10dba7094685a8f","span_id":"07b507b8d1da80d9","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7632,"high":0,"unsigned":false},"nanos":349999997},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-17T16:51:23.518223+00:00  {"level":30,"time":1789663883517,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"ebb4b88b22c19d3cf10dba7094685a8f","span_id":"07b507b8d1da80d9","trace_flags":"01","transactionId":"3b031b5d-c953-4c6f-b9b0-53f673c914a1","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":7632,"high":0,"unsigned":false},"nanos":349999997,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T16:51:23.747876+00:00  {"level":30,"time":1789663883747,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"31daf110e14dc2c1125dd9858035fae6","span_id":"383477254a10a5ad","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-17T16:51:23.748313+00:00  {"level":30,"time":1789663883747,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"31daf110e14dc2c1125dd9858035fae6","span_id":"383477254a10a5ad","trace_flags":"01","transactionId":"4edb0c46-3bb9-42cc-8152-d77b689fff7f","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_9fea75aec3e6`:

```
<tool_result id="tr_9fea75aec3e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T16:51:23.499943+00:00  {"message":"[PlaceOrder] user_id=\"03e6747a-b2b8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T16:51:23.499856009Z"}
2026-09-17T16:51:23.518258+00:00  {"message":"payment went through (transaction_id: 3b031b5d-c953-4c6f-b9b0-53f673c914a1)","severity":"info","timestamp":"2026-09-17T16:51:23.518145926Z"}
2026-09-17T16:51:23.522996+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-17T16:51:23.522922926Z"}
2026-09-17T16:51:23.524562+00:00  {"message":"Successful to write message. offset: 65395","severity":"info","timestamp":"2026-09-17T16:51:23.524464634Z"}
```

## Traces: useful for elimination, useless for the stall itself

Thirty-five checkout traces matched the window but the returned sample was truncated to five, and the latest sampled root starts around T-7m. Nothing in the trace evidence covers the stall period, so the open span that is actually blocking PlaceOrder was never identified. What the pre-onset traces do give is elimination. Every sampled PlaceOrder completes end to end in 23-33ms with all outbound spans closed: cartservice GetCart and EmptyCart at a fraction of a millisecond, currencyservice Convert at effectively zero, productcatalogservice GetProduct around a millisecond, paymentservice Charge well under a millisecond, shippingservice ShipOrder at effectively zero. Root durations stay flat across the sampled span, so there is no gradual ramp visible before onset - the transition looks abrupt. The one hop flagged as degrading in all five traces is shippingservice/GetQuote and its internal HTTP call out to quoteservice, at roughly 5-8ms and 20-25% of trace self-time. Elevated relative to its peers, but nowhere near stall magnitude on its own.

> Evidence `tr_85d28d498e0b`:

```
<tool_result id="tr_85d28d498e0b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00">
service: checkoutservice
5 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 8369122036e83a6a  root frontend/HTTP POST  33.1ms  started 2026-09-17T17:06:13.944020+00:00  36 spans
  +0.0ms frontend/HTTP POST 33.1ms [self 0.4ms]
```

## Dead ends worth keeping

Three lines of enquiry consumed effort and produced nothing usable.

First, change history on checkoutservice was queried twice, and both times came back empty. That much is real: no deploy, config push or flag flip landed on checkoutservice during the incident or in the 24 hours following, which rules out a concurrent change prolonging it and also rules out a quiet human remediation explaining any recovery. But both query windows *start* at the alert timestamp and run forward. Neither covers the hours before onset. The question a responder actually wanted answered - did something change shortly before this started, on this or any other service - was never asked. Do not read these results as clearing pre-incident changes.

Second, cartservice error-ratio metrics returned no samples in either the incident window or the baseline. Because both windows are equally empty, the absence predates onset and is a labelling or population problem with the span-derived call metrics for that service, not a collection outage caused by the incident. The tool's 'no departure from baseline' verdict here is arithmetic on two empty sets and is not evidence of health. The checkout-to-cart edge remains unmeasured by this path.

Third, adservice and recommendationservice were considered and dropped: neither appears anywhere under the PlaceOrder subtree in any sampled trace, so neither can be the blocking outbound call.

> Evidence `tr_3e15998386f0`:

```
<tool_result id="tr_3e15998386f0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:21:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_3e15998386f0>
```

> Evidence `tr_517bb1d1f417`:

```
<tool_result id="tr_517bb1d1f417" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:21:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_517bb1d1f417>
```

> Evidence `tr_52e65f3d3eca`:

```
<tool_result id="tr_52e65f3d3eca" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" template="error-ratio" baseline="2026-09-17T16:19:03.239853+00:00..2026-09-17T16:51:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_85d28d498e0b`:

```
<tool_result id="tr_85d28d498e0b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00">
service: checkoutservice
5 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 8369122036e83a6a  root frontend/HTTP POST  33.1ms  started 2026-09-17T17:06:13.944020+00:00  36 spans
  +0.0ms frontend/HTTP POST 33.1ms [self 0.4ms]
```

## Best available reading

Confidence is low. The reading that survives elimination is that the quote hop reached from shippingservice became unresponsive around T+0, leaving checkoutservice blocked on an in-flight call with spans that never close. That would account for order-start lines with no completions, for the span-derived traffic gaps (no spans close, so no calls are counted), for the error ratio climbing in volatile bursts as waits eventually time out, and for quoteservice and shippingservice alerting last rather than first - their symptoms surface only once the caller gives up. The suggested fix class is a restart of the stalled hop.

> Evidence `tr_9fea75aec3e6`:

```
<tool_result id="tr_9fea75aec3e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T16:51:23.499943+00:00  {"message":"[PlaceOrder] user_id=\"03e6747a-b2b8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T16:51:23.499856009Z"}
2026-09-17T16:51:23.518258+00:00  {"message":"payment went through (transaction_id: 3b031b5d-c953-4c6f-b9b0-53f673c914a1)","severity":"info","timestamp":"2026-09-17T16:51:23.518145926Z"}
2026-09-17T16:51:23.522996+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-17T16:51:23.522922926Z"}
2026-09-17T16:51:23.524562+00:00  {"message":"Successful to write message. offset: 65395","severity":"info","timestamp":"2026-09-17T16:51:23.524464634Z"}
```

> Evidence `tr_5fcac3511390`:

```
<tool_result id="tr_5fcac3511390" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" template="error-ratio" baseline="2026-09-17T16:19:03.239853+00:00..2026-09-17T16:51:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=35 mean=0.00297 min=0 max=0.02083 sd=0.005903
```

> Evidence `tr_85d28d498e0b`:

```
<tool_result id="tr_85d28d498e0b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00">
service: checkoutservice
5 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 8369122036e83a6a  root frontend/HTTP POST  33.1ms  started 2026-09-17T17:06:13.944020+00:00  36 spans
  +0.0ms frontend/HTTP POST 33.1ms [self 0.4ms]
```

> Evidence `tr_3391d631f80b`:

```
<tool_result id="tr_3391d631f80b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T16:51:23.517133+00:00  {"level":30,"time":1789663883517,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"ebb4b88b22c19d3cf10dba7094685a8f","span_id":"07b507b8d1da80d9","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7632,"high":0,"unsigned":false},"nanos":349999997},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-17T16:51:23.518223+00:00  {"level":30,"time":1789663883517,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"ebb4b88b22c19d3cf10dba7094685a8f","span_id":"07b507b8d1da80d9","trace_flags":"01","transactionId":"3b031b5d-c953-4c6f-b9b0-53f673c914a1","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":7632,"high":0,"unsigned":false},"nanos":349999997,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T16:51:23.747876+00:00  {"level":30,"time":1789663883747,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"31daf110e14dc2c1125dd9858035fae6","span_id":"383477254a10a5ad","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-17T16:51:23.748313+00:00  {"level":30,"time":1789663883747,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"31daf110e14dc2c1125dd9858035fae6","span_id":"383477254a10a5ad","trace_flags":"01","transactionId":"4edb0c46-3bb9-42cc-8152-d77b689fff7f","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":7215,"high":0,"unsigned":false},"nanos":800000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## What is still open

The attribution rests on elimination plus one pre-onset latency signal. No dispatch ever queried quoteservice or shippingservice directly - not logs, not metrics, not traces - so the named hop was never observed during the stall itself. No trace evidence covers T+0 onward, so the open span blocking PlaceOrder is still unidentified. Both change-history windows run forward from onset, leaving every pre-incident change on every service unchecked. cartservice has no usable metrics in either window. A responder revisiting this should start by pulling quoteservice and shippingservice logs and traces across the stall window, and by re-running change history over the hours *preceding* onset across the full service set.

> Evidence `tr_85d28d498e0b`:

```
<tool_result id="tr_85d28d498e0b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00">
service: checkoutservice
5 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 8369122036e83a6a  root frontend/HTTP POST  33.1ms  started 2026-09-17T17:06:13.944020+00:00  36 spans
  +0.0ms frontend/HTTP POST 33.1ms [self 0.4ms]
```

> Evidence `tr_517bb1d1f417`:

```
<tool_result id="tr_517bb1d1f417" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:21:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_517bb1d1f417>
```

> Evidence `tr_52e65f3d3eca`:

```
<tool_result id="tr_52e65f3d3eca" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T16:51:15.583000+00:00..2026-09-17T17:23:27.926147+00:00" template="error-ratio" baseline="2026-09-17T16:19:03.239853+00:00..2026-09-17T16:51:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

