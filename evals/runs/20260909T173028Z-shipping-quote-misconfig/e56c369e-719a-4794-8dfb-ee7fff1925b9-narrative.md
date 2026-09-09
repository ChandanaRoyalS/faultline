# Checkout order placement aborting at the shipping quote call

## What was visible first

The page named checkoutservice as the seed, with accountingservice, emailservice, frauddetectionservice, quoteservice and loadgenerator alerting alongside. Twelve services in the radius, severity critical. The alert set reads as a broad multi-service event, but four of those companions sit downstream of a completed order, so they were symptom candidates from the start.

The first useful measurement was checkoutservice's own span error ratio against the preceding 35 minutes. Baseline near 0.7 percent; during the event a mean around 4.9 percent with a peak near 29 percent. A single change point placed onset at T+0, about two minutes before the timestamp the alert had drawn attention to — a discrepancy that matters, because anchoring the search at the alert time puts you on the wrong side of the transition. The series is bursty: window minimum still zero, standard deviation roughly twice the mean. That excluded a hard-down state and excluded a slow ramp, so gradual creep in some resource was off the table early.

Two obvious follow-ups came back thin. The change log for checkoutservice was empty, excluding a checkout-side deploy, config edit, or recorded rollback — but note the query covered only the seed service and ran forward from the alert timestamp, not backward before onset and not across dependencies. Checkoutservice logs showed, from about T+3m onward, only info-level order-intake lines: no error severity, no status code, no downstream target named. Early in the window two orders completed a full four-step pipeline (intake, payment, confirmation email, broker write). After onset the intake line appears for every request and the three follow-ups never do. Intake cadence held steady to the end of the window, so the process was alive. That killed crash, restart, entry-side rejection, and any currency-specific pattern — but also killed the hope that checkout's own logs would name the blocked dependency.

> Evidence `tr_0a0cf7b61d67`:

```
<tool_result id="tr_0a0cf7b61d67" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T17:03:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" template="error-ratio" baseline="2026-09-09T16:28:18.813181+00:00..2026-09-09T17:03:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=140 mean=0.0492 min=0 max=0.2909 sd=0.1011
  baseline window: n=140 mean=0.006791 min=0 max=0.05769 sd=0.0118
```

> Evidence `tr_8356a0199a05`:

```
<tool_result id="tr_8356a0199a05" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T17:33:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_8356a0199a05>
```

> Evidence `tr_7531ce607edf`:

```
<tool_result id="tr_7531ce607edf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T17:03:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T17:03:22.721713+00:00  {"message":"[PlaceOrder] user_id=\"5d4c66a8-ac70-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T17:03:22.721615218Z"}
2026-09-09T17:03:22.739305+00:00  {"message":"payment went through (transaction_id: 6cb7986e-2e0b-4847-b7fb-39601b9d6b87)","severity":"info","timestamp":"2026-09-09T17:03:22.739234051Z"}
2026-09-09T17:03:22.743572+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-09-09T17:03:22.743438051Z"}
2026-09-09T17:03:22.744389+00:00  {"message":"Successful to write message. offset: 24564","severity":"info","timestamp":"2026-09-09T17:03:22.744300801Z"}
```

## The cartservice detour, which did not matter

Cartservice absorbed real effort and turned out to be irrelevant. Recording it because the change log will look attractive again to anyone reading it cold.

The error-ratio metric for cartservice returned no samples at all — in the event window and in the baseline window equally. Because the emptiness is symmetric, it points at the service not emitting those counters rather than at anything changing at onset. It is not evidence of cartservice going quiet, and it leaves the baseline-versus-event comparison simply undefined. Cartservice logs showed only routine AddItem and GetCart handling at a steady multi-request-per-second rate through the end of the window: no panics, no startup lines, no backend connection or auth errors. Some GetCart calls carry an empty userId both before and during the period of interest, which reads as normal. Caveat: that log result was truncated to the oldest few and newest thirty-odd lines, so the stretch covering onset was never returned.

The change log is the seductive part. Thirty-four entries, all cartservice-scoped, all attributed to platform automation, forming a cycle recurring every four to six hours: a hotfix image tag set then reverted, a traffic-shaping sidecar with fixed egress delay attached to the cart-service network namespace then removed, and a REDIS_ADDR override to a non-default port applied then reverted. Six near-identical cycles. Every mutation has a matching revert, so net state at onset was baseline. Last event of any kind was the REDIS_ADDR revert about 1.6 hours before onset; shaping removal 1.9 hours before; image revert 2.2 hours before. Nothing in the final 1.6 hours. All three tempting readings are excluded by their own reverts. Also: zero change entries for productcatalogservice, currencyservice, or paymentservice anywhere in the window.

> Evidence `tr_3cadfa778661`:

```
<tool_result id="tr_3cadfa778661" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T17:03:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" template="error-ratio" baseline="2026-09-09T16:28:18.813181+00:00..2026-09-09T17:03:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_a8dba74f8e25`:

```
<tool_result id="tr_a8dba74f8e25" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T17:03:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T17:03:18.534867+00:00  AddItemAsync called with userId=5acf7938-ac70-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=4
2026-09-09T17:03:18.537437+00:00  GetCartAsync called with userId=5acf7938-ac70-11f1-b359-b6ed2071a170
2026-09-09T17:03:22.477802+00:00  GetCartAsync called with userId=
2026-09-09T17:03:22.523407+00:00  AddItemAsync called with userId=5d31c69a-ac70-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=4
```

> Evidence `tr_ed1f48b28f48`:

```
<tool_result id="tr_ed1f48b28f48" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T17:33:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" radius="candidate_cause" hops="1">
service: cartservice
34 changes, ranked by suspicion
  #1  1.6h before onset  2026-09-09T15:57:59.265915+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.7h before onset  2026-09-09T15:49:25.709034+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Where the traces put the boundary, and what stayed open

Traces located the break. Across sampled checkoutservice PlaceOrder traces, the single erroring downstream call is the checkoutservice client span for hipstershop.ShippingService/GetQuote, marked ERROR in eleven of twelve traces shown out of fifty-five found, propagating up through PlaceOrder, frontend PlaceOrder, and the frontend HTTP POST root. The failing calls are fast — roughly 2.6 to 4.4 milliseconds inside traces totalling 7 to 18 milliseconds — so this is a prompt error return, not a hung or expired call, which removes any deadline or slow-backend reading. The shippingservice server span for the same operation, and its own outbound HTTP child, complete without error status in every affected trace. The failure is visible at the calling boundary, not as a reported server-side failure. It sits inside prepareOrderItemsAndShippingQuoteFromCart, with no payment, email, or shipping-order-placement spans present at all, matching the log picture. Sibling calls to cart, currency, and product catalog complete cleanly in sub-millisecond to roughly 2 millisecond times. Checkoutservice's PlaceOrder span shows about 0.1 millisecond of self time, so a local bug is a poor fit. One minority variant: a five-span trace with no GetQuote span at all and large self time before the ERROR — unresolved, possibly a recording gap.

The reading that stood: from T+0 the shipping quote path returns errors for a subset of requests, aborting PlaceOrder before payment, and the downstream alerts follow because no order ever reaches those stages. Confidence low, no fix class identified. Five edges in the radius were crossed unmeasured.

For whoever picks this up: the gRPC status code and error message on the failing span were never exposed, so UNAVAILABLE, INTERNAL, and a business-logic rejection all remain live with very different remediations — get the code first. No specialist examined shippingservice or quoteservice directly, despite quoteservice alerting; there are no logs, metrics, or change history for either. And the reason a server span succeeds while the client span errors — connection-level, response-validation, or an instrumentation gap — is entirely open. Change history for those two services, and for the hours before onset, was never queried.

> Evidence `tr_d06a5501028c`:

```
<tool_result id="tr_d06a5501028c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-09T16:33:15.583000+00:00..2026-09-09T17:38:12.352819+00:00">
service: checkoutservice
12 trace(s) shown of 55 found, 200 spans; offsets are from each trace's root

trace 5211a80484dd2375  root frontend/HTTP POST  11.0ms  started 2026-09-09T17:31:30.512010+00:00  26 spans
  +0.0ms frontend/HTTP POST 11.0ms [self 0.1ms]  ERROR
```

> Evidence `tr_7531ce607edf`:

```
<tool_result id="tr_7531ce607edf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T17:03:15.583000+00:00..2026-09-09T17:38:12.352819+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T17:03:22.721713+00:00  {"message":"[PlaceOrder] user_id=\"5d4c66a8-ac70-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T17:03:22.721615218Z"}
2026-09-09T17:03:22.739305+00:00  {"message":"payment went through (transaction_id: 6cb7986e-2e0b-4847-b7fb-39601b9d6b87)","severity":"info","timestamp":"2026-09-09T17:03:22.739234051Z"}
2026-09-09T17:03:22.743572+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-09-09T17:03:22.743438051Z"}
2026-09-09T17:03:22.744389+00:00  {"message":"Successful to write message. offset: 24564","severity":"info","timestamp":"2026-09-09T17:03:22.744300801Z"}
```

