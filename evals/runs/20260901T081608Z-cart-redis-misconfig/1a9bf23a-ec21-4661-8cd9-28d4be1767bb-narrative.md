# Checkout outage traced to a cart-store endpoint change

## What was visible first, and why checkout was a dead end

Alerts fired on checkoutservice, frontend and loadgenerator at the same moment; call it T+0. Severity critical, blast radius twelve services, four unmeasured edges crossed. The handed-over starting point was checkoutservice, which is where the investigation began and where it should not have stayed.

Checkout's own signals were ambiguous or actively misleading. Its span error ratio was elevated, peaking near two thirds of calls, but it also touched zero within the same window and reported continuously across fifty-seven points — bursty, not a hard outage, and not a one-off blip. Its change history was completely empty: no deploy, no config edit, no flag flip, no dependency bump. That empties the self-inflicted-trigger hypothesis, with the caveat that the query only spanned roughly T-10m to T+5m, so an older change remains unqueried.

The logs were the worst artifact. Zero error- or exception-severity lines; everything informational. Early orders showed complete sequences — start, payment success with transaction id, confirmation email, message write with incrementing offset. From about T-0m25s onward only order-start lines remained, at steady cadence through T+2m23s. So the process was alive and taking work the whole time, and the break was upstream of payment, not at the broker publish step — if publishing alone had failed, the payment and email lines would still be present. The result was truncated (oldest eight, newest thirty-two lines), leaving the window's middle and everything after T+2m23s uncovered.

> Evidence `tr_f9f0e604de0d`:

```
<tool_result id="tr_f9f0e604de0d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=57
</tool_result:tr_f9f0e604de0d>
```

> Evidence `tr_5540124a46bb`:

```
<tool_result id="tr_5540124a46bb" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_5540124a46bb>
```

> Evidence `tr_1e273413ff83`:

```
<tool_result id="tr_1e273413ff83" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-01T08:09:10.591466+00:00  {"message":"[PlaceOrder] user_id=\"69712a80-a5dc-11f1-ae7b-9eef0fcf8acb\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-01T08:09:10.591341461Z"}
2026-09-01T08:09:10.622098+00:00  {"message":"payment went through (transaction_id: bdcfcd00-036c-4aee-9ea4-0a8f47b9240c)","severity":"info","timestamp":"2026-09-01T08:09:10.622022211Z"}
2026-09-01T08:09:10.626327+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-01T08:09:10.626257795Z"}
2026-09-01T08:09:10.626853+00:00  {"message":"Successful to write message. offset: 1398","severity":"info","timestamp":"2026-09-01T08:09:10.626794586Z"}
```

## Traces pointed the way; cart logs held the mechanism

Traces resolved it. Every failing trace shared one shape: frontend POST, frontend PlaceOrder, checkout PlaceOrder, order-preparation span, and inside it a cart-fetch call. The deepest ERROR span was always the cart fetch, and that status propagated unchanged to the frontend entry span. Root spans ran one to three milliseconds with the erroring child under about 1.2 ms — an immediate rejection, not a timeout or saturation. Across two hundred spans there were no payment, currency or accounting spans at all; checkout aborted before those calls were attempted. The preparation span itself was not marked ERROR and no shipping-quote span appeared. Checkout was a propagator.

cartservice's metrics were empty end to end — no error numerator and, tellingly, no total-call denominator either. That is blindness, not health, and it extends back to the window's healthy opening when cartservice was demonstrably serving traffic.

Its logs carried the answer: an unhandled ApplicationException from the Redis cart-store initialization path, unwinding out of the process entry point, so the process terminates. Connect, fail, throw, exit, restart — every twenty to forty-five seconds from about T+0m51s onward. Each attempt burned tens of seconds before failing, consistent with a connect timeout against no listener rather than a refusal. Recorded parameters name the redis-cart host on port 6380 with TLS disabled. Around T-10m the same service was serving add-item, get-cart and empty-cart cleanly.

One change existed on cartservice in the window: platform-automation set REDIS_ADDR to that 6380 endpoint at T-3m, replacing a previously unset value. Machine-originated, from a pipeline or config-sync. Endpoint change at T-3m, crash loop from T+0m51s, checkout's cart fetch failing instantly, error propagating to frontend, alerts. High confidence; fix class is reverting the configuration value.

> Evidence `tr_1bcec88a89b7`:

```
<tool_result id="tr_1bcec88a89b7" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
service: checkoutservice
200 spans
  323b6c040170263f frontend/HTTP POST 1.5ms ERROR
  323b6c040170263f frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.3ms ERROR
  323b6c040170263f checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.6ms ERROR
```

> Evidence `tr_c215ed2babd1`:

```
<tool_result id="tr_c215ed2babd1" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_c215ed2babd1>
```

> Evidence `tr_4170a4bb8bb9`:

```
<tool_result id="tr_4170a4bb8bb9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T08:09:07.184159+00:00  AddItemAsync called with userId=6769670c-a5dc-11f1-ae7b-9eef0fcf8acb, productId=9SIQT8TOJO, quantity=2
2026-09-01T08:09:07.187181+00:00  GetCartAsync called with userId=6769670c-a5dc-11f1-ae7b-9eef0fcf8acb
2026-09-01T08:09:10.582763+00:00  AddItemAsync called with userId=69712a80-a5dc-11f1-ae7b-9eef0fcf8acb, productId=6E92ZMYYFZ, quantity=2
2026-09-01T08:09:10.584437+00:00  GetCartAsync called with userId=69712a80-a5dc-11f1-ae7b-9eef0fcf8acb
```

> Evidence `tr_c59d58a6dd97`:

```
<tool_result id="tr_c59d58a6dd97" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
service: cartservice
1 changes
  2026-09-01T08:16:11.688396+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_c59d58a6dd97>
```

## Ruled out, and what remains open

Ruled out and not worth repeating: a checkout deploy, flag flip or dependency bump at onset; paymentservice, currencyservice, accountingservice and the shipping-quote path, none of which were ever reached — the absence of their spans is evidence, not a gap; a broker-publish break; a slow or saturated dependency; an out-of-memory kill on cartservice, since every termination carries an explicit managed exception; a cart request-handling or bad-data bug, since the throw precedes request handling; Redis returning errors or evicting, since no session is ever established; a TLS handshake problem, since TLS is off; and load-dependent intermittency, since startup never completes at all.

Still open. Whether redis-cart genuinely does not listen on 6380, or whether a server-side port move was applied to the client only — the fix differs, and no redis-side telemetry was gathered. The prior REDIS_ADDR value was recorded as absent, so a revert target must come from the deployment manifest rather than inference. The timing gap is unexplained: change at T-3m, alerts at T+0, first crash-loop line at T+0m51s; whether cartservice ran on the old connection until a pod restart, and what triggered that restart, was never established. Why cartservice emitted no span metrics at all, including during the healthy opening, may be an independent labelling or scrape problem. Checkout's error ratio dips to zero and its logs stop at T+2m23s, so behaviour in the final stretch is uncovered. Only two of twelve affected services were examined, so an independent failure elsewhere was not excluded. And nobody checked whether the automation that wrote 6380 will simply re-apply it after a revert.

> Evidence `tr_1bcec88a89b7`:

```
<tool_result id="tr_1bcec88a89b7" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
service: checkoutservice
200 spans
  323b6c040170263f frontend/HTTP POST 1.5ms ERROR
  323b6c040170263f frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.3ms ERROR
  323b6c040170263f checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.6ms ERROR
```

> Evidence `tr_4170a4bb8bb9`:

```
<tool_result id="tr_4170a4bb8bb9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T08:09:07.184159+00:00  AddItemAsync called with userId=6769670c-a5dc-11f1-ae7b-9eef0fcf8acb, productId=9SIQT8TOJO, quantity=2
2026-09-01T08:09:07.187181+00:00  GetCartAsync called with userId=6769670c-a5dc-11f1-ae7b-9eef0fcf8acb
2026-09-01T08:09:10.582763+00:00  AddItemAsync called with userId=69712a80-a5dc-11f1-ae7b-9eef0fcf8acb, productId=6E92ZMYYFZ, quantity=2
2026-09-01T08:09:10.584437+00:00  GetCartAsync called with userId=69712a80-a5dc-11f1-ae7b-9eef0fcf8acb
```

> Evidence `tr_c215ed2babd1`:

```
<tool_result id="tr_c215ed2babd1" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T08:09:00.583000+00:00..2026-09-01T08:24:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_c215ed2babd1>
```
