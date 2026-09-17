# Checkout orders terminate at the shipping-quote step

## What was visible, in order

Two pages arrived together: checkoutservice and the load generator. Orders were not completing. The first useful measurement was that checkout's error ratio did not ramp, it stepped: baseline over the preceding half hour sat near 0.6% with brief excursions to ~5%, and a single change point landed at 19:36:30, after which the mean ran about 3.6% with bursts reaching a quarter of calls. That step also rules out two early readings — checkout was not chronically broken (the elevation is real against baseline) and it was not hard down (most requests kept succeeding throughout).

At roughly T+2m we pulled checkout's own logs expecting the service to say why it was failing. It did not. Every retained line was info severity — no warnings, no errors, no timeout or deadline text, no dependency name, no RPC status. What the logs gave instead was shape: early in the window each order-request line was followed within ~50ms by payment confirmation with a transaction id, a confirmation email, and a successful message write. From about 19:37 only the order-initiation lines appear; the completion lines stop. Initiations continued steadily to the end of the window, so the process was alive and serving.

At that point we read this as requests stalling in flight. That reading was wrong, and the traces corrected it.

> Evidence `tr_cd8afa3b416f`:

```
<tool_result id="tr_cd8afa3b416f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T19:08:15.583000+00:00..2026-09-17T19:41:18.909082+00:00" template="error-ratio" baseline="2026-09-17T18:35:12.256918+00:00..2026-09-17T19:08:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=133 mean=0.036 min=0 max=0.2667 sd=0.08467
  baseline window: n=133 mean=0.006403 min=0 max=0.05263 sd=0.01277
```

> Evidence `tr_a129308b4eee`:

```
<tool_result id="tr_a129308b4eee" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:08:15.583000+00:00..2026-09-17T19:41:18.909082+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T19:08:20.625625+00:00  {"message":"[PlaceOrder] user_id=\"25b3ad62-b2cb-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T19:08:20.625506257Z"}
2026-09-17T19:08:20.645822+00:00  {"message":"payment went through (transaction_id: 74c01251-529a-408e-8604-636a7f188546)","severity":"info","timestamp":"2026-09-17T19:08:20.645689424Z"}
2026-09-17T19:08:20.666904+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T19:08:20.666734424Z"}
2026-09-17T19:08:20.667680+00:00  {"message":"Successful to write message. offset: 66444","severity":"info","timestamp":"2026-09-17T19:08:20.667610007Z"}
```

## The traces, which settled the shape

At about T+6m, ten checkout traces captured after 19:39 all showed an identical path. Cart GetCart with its nested Redis HGET completes in well under a millisecond. Product catalog GetProduct completes, sometimes with a feature-flag subcall. Currency Convert completes. All clean. Then the checkoutservice-side client span for ShippingService/GetQuote carries an error status that propagates up through PlaceOrder to the frontend root. No payment span, no email span — execution never reaches those stages.

The shippingservice server span is present in the same traces, along with its own outbound HTTP call, and both finish in about 2-2.5ms with no error. Shipping is answering; the error sits only on the caller's side of that hop.

The traces also killed the stall theory. Root spans complete in 7-12ms end to end and the shipping hop is 2.7-3.7ms. This is a fast failure, not a timeout. The hop was flagged as degrading mostly because it is the error-bearing span and consumes 27-38% of an already very short trace — do not let that percentage pull you into a latency story. Across ~80 seconds of sampling every trace failed identically, so this is uniform rather than a subset of traffic.

> Evidence `tr_4d9660bc87d3`:

```
<tool_result id="tr_4d9660bc87d3" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T18:08:15.583000+00:00..2026-09-17T19:41:18.909082+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 166 spans; offsets are from each trace's root

trace a9edb165d4dcb7b7  root frontend/HTTP POST  10.4ms  started 2026-09-17T19:39:53.072013+00:00  22 spans
  +0.0ms frontend/HTTP POST 10.4ms [self 0.6ms]  ERROR
```

## Dead ends, gaps, and what remains open

The missing payment completions pulled us toward paymentservice around T+9m and produced nothing conclusive. Through 19:35:16 it logged paired charge-received and transaction-complete entries sharing trace ids, closing within about a millisecond, with no orphaned received-only lines and no error or capacity wording anywhere. Then six minutes of complete silence. The obvious reading is that payment went quiet because checkout stopped calling it, but the arithmetic does not close: payment's last line precedes checkout's error step by roughly three minutes, and the evidence does not reconcile that.

We queried the change log for checkoutservice twice; both came back empty over a window starting at onset and running about a day forward. That legitimately rules out a self-inflicted change at or after onset and any in-progress rollout or later remediation on checkoutservice. But both queries ran at zero hops — dependencies were never inspected — and both windows begin at onset rather than before it. Given that the traces point at the checkout-to-shipping boundary, a change landing on shippingservice or the flag service in the preceding hours is exactly what this scoping missed. Re-run with a pre-onset window and at least one hop of radius.

cartservice error ratio returned no samples in either the incident or the baseline window. Identical emptiness across both means the series was never collected, not that cart was healthy — treat it as a coverage gap. Latency metrics and the error ratios for productcatalog, shipping and email were never measured at all.

Conclusion, held at low confidence: orders abort at the shipping-quote step, with the failure on checkout's side of a response that shipping served successfully. The honest reason for low confidence is that we never captured the status code or exception text on that client span — only the error flag. No fix class was identified.

> Evidence `tr_76d4f0d7b975`:

```
<tool_result id="tr_76d4f0d7b975" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T18:08:15.583000+00:00..2026-09-17T19:41:18.909082+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T18:08:37.306177+00:00  {"level":30,"time":1789668517306,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"cbd32fbabfe5dee18c3cc5f046040eeb","span_id":"f3aeea5c131d69e8","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":18132,"high":0,"unsigned":false},"nanos":49999997},"creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardCvv":397,"creditCardExpirationYear":2039,"creditCardExpirationMonth":5}},"msg":"Charge request received."}
2026-09-17T18:08:37.306515+00:00  {"level":30,"time":1789668517306,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"cbd32fbabfe5dee18c3cc5f046040eeb","span_id":"f3aeea5c131d69e8","trace_flags":"01","transactionId":"b931766a-9bdc-4152-819f-7fe46c1f3e2c","cardType":"visa","lastFourDigits":"7968","amount":{"units":{"low":18132,"high":0,"unsigned":false},"nanos":49999997,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T18:08:49.943978+00:00  {"level":30,"time":1789668529943,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"19f1df5b3d462f7c1112806b99fc476b","span_id":"e7efb9e9c9720882","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":1055,"high":0,"unsigned":false},"nanos":146218479},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-17T18:08:49.944457+00:00  {"level":30,"time":1789668529943,"pid":17,"hostname":"8518c4ae5f7f","trace_id":"19f1df5b3d462f7c1112806b99fc476b","span_id":"e7efb9e9c9720882","trace_flags":"01","transactionId":"b6bbcbb3-2e0f-4c48-955b-4f70ff38390e","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":1055,"high":0,"unsigned":false},"nanos":146218479,"currencyCode":"CAD"},"msg":"Transaction complete."}
```

> Evidence `tr_0989f9e34431`:

```
<tool_result id="tr_0989f9e34431" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T19:38:15.583000+00:00..2026-09-17T19:41:18.909082+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_0989f9e34431>
```

> Evidence `tr_a1c6fee8a8bb`:

```
<tool_result id="tr_a1c6fee8a8bb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T19:08:15.583000+00:00..2026-09-17T19:41:18.909082+00:00" template="error-ratio" baseline="2026-09-17T18:35:12.256918+00:00..2026-09-17T19:08:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

