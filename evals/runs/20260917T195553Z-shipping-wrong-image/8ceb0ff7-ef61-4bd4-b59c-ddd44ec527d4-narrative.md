# Checkout order failures traced to unanswered shipping-quote calls

## What was visible, in order

The page came from checkoutservice and loadgenerator together, which reads as "orders are failing and the synthetic caller noticed." That is what it was. Severity critical, blast radius ten services, seed checkoutservice, four edges crossed without measurement.

First hard number: checkoutservice error ratio averaged about 11% in the incident window with a peak near 29%, against a baseline well under 1% — a sixteen-fold regression, but not a total outage. Variance was high with troughs at zero, so errors arrived in bursts. Two change points appeared, one around 19:36:30 and a second around 19:57:00. The first sits more than twenty minutes before the onset timestamp we were handed, and it quietly undermined the framing of later time-boxed queries.

The logs then said "alive, but not finishing." Everything was info level — no exceptions, no stack traces, no restarts. At the head of the window each PlaceOrder line was followed by the full chain: payment authorization, confirmation email, successful message write with increasing offset. From ~19:57 only the PlaceOrder intake lines remained; the completions were gone. Intake continued steadily through 20:01:34, so the process was serving throughout. Both USD and CAD orders stalled alike, which ruled out a currency-specific path early.

> Evidence `tr_67c82c6818b1`:

```
<tool_result id="tr_67c82c6818b1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T19:28:45.583000+00:00..2026-09-17T20:01:36.353378+00:00" template="error-ratio" baseline="2026-09-17T18:55:54.812622+00:00..2026-09-17T19:28:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=132 mean=0.1107 min=0 max=0.2931 sd=0.1223
  baseline window: n=132 mean=0.006881 min=0 max=0.05263 sd=0.0131
```

> Evidence `tr_764881231624`:

```
<tool_result id="tr_764881231624" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:28:45.583000+00:00..2026-09-17T20:01:36.353378+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T19:28:48.489790+00:00  {"message":"[PlaceOrder] user_id=\"01909dd4-b2ce-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T19:28:48.489546256Z"}
2026-09-17T19:28:48.510168+00:00  {"message":"payment went through (transaction_id: e98d3742-ddc7-42eb-9557-c5ff0360b21b)","severity":"info","timestamp":"2026-09-17T19:28:48.510003714Z"}
2026-09-17T19:28:48.517503+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T19:28:48.517434047Z"}
2026-09-17T19:28:48.518253+00:00  {"message":"Successful to write message. offset: 66618","severity":"info","timestamp":"2026-09-17T19:28:48.518193714Z"}
```

## Traces reframed it; the dead ends

Traces inverted the picture. Every PlaceOrder trace at and after 19:57:06 completed in six to ten milliseconds with ERROR propagated from checkoutservice up through frontend. Nothing hung. The "silent stall" read off the logs was just the absence of completion lines for orders that had already aborted.

In ten of eleven post-19:57 traces the failing hop was identical: checkoutservice's client call to hipstershop.ShippingService/GetQuote inside prepareOrderItemsAndShippingQuoteFromCart. ERROR status, ~2ms self time, and no shippingservice server-side child span at all — the call failed at or before reaching shippingservice. It was the last child attempted, so checkout aborted there: no Charge, no email, no EmptyCart, no ShipOrder. The eleventh trace (20:01:34) failed with no GetQuote span at all and 5.1ms of self time in the same function, consistent with the step failing before a client span was emitted. Dependencies that did answer were healthy: cartservice GetCart/HGET 0.2–1.9ms, currencyservice Convert under 1.6ms, productcatalogservice GetProduct under 1.4ms.

Keep these dead ends. cartservice error-ratio metrics returned zero samples in both the incident and baseline windows — emptiness, not flatness; it neither cleared cartservice nor marked onset, and the series simply is not present under that service name. cartservice logs came back truncated to the oldest eight and newest thirty-two lines, dropping the entire 19:30–20:00 interval we cared about; what returned was routine and fast. And the only latency-heavy trace in the set was a *successful* pre-onset one at 19:52:29, 86% in emailservice/send_email. Tempting, unrelated: post-onset checkout never reaches the email call.

> Evidence `tr_2cfe1ebbc275`:

```
<tool_result id="tr_2cfe1ebbc275" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T18:58:45.583000+00:00..2026-09-17T20:01:36.353378+00:00">
service: checkoutservice
12 trace(s) shown of 29 found, 200 spans; offsets are from each trace's root

trace 297b6515ba20b059  root frontend/HTTP POST  187.2ms  started 2026-09-17T19:52:29.825013+00:00  44 spans
  +0.0ms frontend/HTTP POST 187.2ms [self 0.0ms]
```

> Evidence `tr_9f26c3d3d7e4`:

```
<tool_result id="tr_9f26c3d3d7e4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T19:28:45.583000+00:00..2026-09-17T20:01:36.353378+00:00" template="error-ratio" baseline="2026-09-17T18:55:54.812622+00:00..2026-09-17T19:28:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_5be9102d2787`:

```
<tool_result id="tr_5be9102d2787" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T18:58:45.583000+00:00..2026-09-17T20:01:36.353378+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T18:58:45.907786+00:00  AddItemAsync called with userId=cf2749aa-b2c9-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=4
2026-09-17T18:58:45.910975+00:00  GetCartAsync called with userId=cf2749aa-b2c9-11f1-b359-b6ed2071a170
2026-09-17T18:58:46.569113+00:00  AddItemAsync called with userId=cf8bed60-b2c9-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=1
2026-09-17T18:58:46.572427+00:00  GetCartAsync called with userId=cf8bed60-b2c9-11f1-b359-b6ed2071a170
```

## Conclusion and what is still open

checkoutservice fails roughly 11% of PlaceOrder calls because its outbound GetQuote call fails fast at or before reaching shippingservice; checkout aborts the order there, so payment, email, EmptyCart and ShipOrder never run, and frontend and loadgenerator alert as callers. checkoutservice keeps serving, logs nothing abnormal, does not restart. Confidence medium; expected fix class restart.

Change history for checkoutservice was empty — no deploys, config edits or flag flips — which excludes a checkout rollout, a flag flip either way, and ongoing change churn, and also means there is no artifact to revert. But both change queries began at 19:58:45 and ran forward, while the first change point was at 19:36:30, outside the interval; both covered only the seed at zero hops. So "nothing changed" cannot bear much weight.

Still open: no query was ever dispatched to shippingservice — its logs, metrics, restart and memory-kill history and change record are all unexamined, so the mechanism behind the unanswered calls is not identified. Re-run change history starting well before 19:36:30 and widen it past zero hops. And the partial, bursty shape (~11% with zero-floor troughs) does not distinguish partial replica loss from intermittent connection failure; per-dependency failure rates and latency percentiles for checkoutservice were never returned.

> Evidence `tr_2cfe1ebbc275`:

```
<tool_result id="tr_2cfe1ebbc275" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T18:58:45.583000+00:00..2026-09-17T20:01:36.353378+00:00">
service: checkoutservice
12 trace(s) shown of 29 found, 200 spans; offsets are from each trace's root

trace 297b6515ba20b059  root frontend/HTTP POST  187.2ms  started 2026-09-17T19:52:29.825013+00:00  44 spans
  +0.0ms frontend/HTTP POST 187.2ms [self 0.0ms]
```

> Evidence `tr_509231b777b0`:

```
<tool_result id="tr_509231b777b0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T19:58:45.583000+00:00..2026-09-17T20:01:36.353378+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_509231b777b0>
```

> Evidence `tr_3ec607a3891f`:

```
<tool_result id="tr_3ec607a3891f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T19:58:45.583000+00:00..2026-09-17T20:01:36.353378+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_3ec607a3891f>
```

