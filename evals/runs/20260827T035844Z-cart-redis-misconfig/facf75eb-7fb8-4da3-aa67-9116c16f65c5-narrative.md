# Checkout failures traced to a cart store endpoint rewrite

## What was visible, in order

Three alerts arrived together: checkoutservice, frontend, loadgenerator. Take the incident marker as T+0.

First readings were the two alerting services' error ratios. Frontend peaked near a third of calls errored, checkoutservice near two thirds; both series also touched zero inside the same fifteen-minute slice. That suggested a bursty, partial degradation. It was wrong, and it cost time — both queries aggregated by service only, with no route or downstream dimension, so they mixed checkout traffic with everything else. Telemetry itself was fine: 61 sample points each, so a collector gap was excluded early.

Traces corrected the picture. Forty checkout traces were structurally identical: frontend POST, frontend PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, then an outbound CartService/GetCart. GetCart was the deepest span and the deepest errored span; its parent was not marked errored, so the error was introduced at the outbound cart call and inherited upward. Every sampled trace failed — uniform, not intermittent. Whole traces finished in single-digit milliseconds, so a latency or deadline cascade was ruled out; these are immediate rejections. No trace reached currencyservice, paymentservice, accountingservice, shippingservice or productcatalogservice — execution short-circuited at the cart fetch, so anyone chasing those was chasing services never called.

> Evidence `tr_4b6f80a2745f`:

```
<tool_result id="tr_4b6f80a2745f" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_4b6f80a2745f>
```

> Evidence `tr_e965cf620377`:

```
<tool_result id="tr_e965cf620377" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3307 n=61
</tool_result:tr_e965cf620377>
```

> Evidence `tr_1cff58eba55c`:

```
<tool_result id="tr_1cff58eba55c" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
service: checkoutservice
200 spans
  78d6e84333329d91 frontend/HTTP POST 1.5ms ERROR
  78d6e84333329d91 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.4ms ERROR
  78d6e84333329d91 checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.7ms ERROR
```

## Cart itself, and the change that lines up

Cart logs were decisive. Early in the window cartservice was serving normal AddItem and GetCart traffic cleanly, so it entered healthy. Later the window shows a repeating cycle: connect attempt to Redis at redis-cart:6380, failure after fifteen to thirty-six seconds, then an unhandled exception out of RedisCartStore.EnsureRedisConnected via InitializeAsync in Program Main, killing the process. At least five identical cycles — sustained, not a blip. The endpoint is consistent across restarts, so this is not drift or DNS flapping. Redis conventionally listens on 6379; the process keeps dialling 6380.

An attempt to anchor onset from cartservice call metrics returned nothing — and the total-call denominator was empty too, not just the error counter. That is not "zero errors"; a process dying during startup never reaches a serving state and emits no call counters. Any dashboard built on that expression was blank for the window.

Exactly one change landed on cartservice in the covered window, roughly T-2m30s: an automated platform actor rewrote the service environment so the Redis endpoint variable points at redis-cart:6380. No prior value recorded. Environment mutation only — no image, no rollout, no flag — so a code deploy and a flag toggle are both excluded, and there is no competing change to disentangle.

> Evidence `tr_36aff0184df5`:

```
<tool_result id="tr_36aff0184df5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T03:51:18.974184+00:00  AddItemAsync called with userId=8f92cf18-a1ca-11f1-86d7-1e4ac5f08d0c, productId=OLJCESPC7Z, quantity=1
2026-08-27T03:51:18.978203+00:00  GetCartAsync called with userId=8f92cf18-a1ca-11f1-86d7-1e4ac5f08d0c
2026-08-27T03:51:20.331942+00:00  GetCartAsync called with userId=
2026-08-27T03:51:23.759888+00:00  AddItemAsync called with userId=926d0d2a-a1ca-11f1-86d7-1e4ac5f08d0c, productId=1YMWWN1N4O, quantity=1
```

> Evidence `tr_4394866ca91a`:

```
<tool_result id="tr_4394866ca91a" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_4394866ca91a>
```

> Evidence `tr_c0d42f396713`:

```
<tool_result id="tr_c0d42f396713" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
service: cartservice
1 changes
  2026-08-27T03:58:45.548549+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_c0d42f396713>
```

## Dead ends, conclusion, and what is still open

Change queries on checkoutservice, productcatalogservice, currencyservice and paymentservice all came back completely empty. For each, three explanations closed: a deploy just before onset, a flag or config push coinciding with onset, and an in-flight remediation edit muddying the signal. For checkoutservice this also means there is nothing to roll back on the alerting service itself, which is where instinct sends you first.

One caveat spans all five change queries including cart's: each actually covered only about T-10m to T+5m, not the ninety-minute lookback requested. Roughly eighty earlier minutes are unexamined everywhere.

Conclusion: the endpoint value in cartservice's environment names a port with no listener. cartservice dies in startup, restarts, never serves; checkoutservice's GetCart is rejected immediately and the error propagates to frontend. Fix class is a configuration revert to the correct port. Confidence high.

Still open. Nobody confirmed what port redis-cart is actually listening on, and no prior value is recorded — if redis-cart had moved or gone down, the edit could be coincidental or a failed remediation; check the listener first. The edit came from platform automation, so a manual revert may be reconciled back if that automation runs continuously. Cart's exact onset minute is unestablished: the log result dropped the middle of the window and no cart call metrics exist to anchor it. Finally, twelve services were in blast radius but only five were examined, and the upstream error attribution rests on trace sampling rather than dimensioned metrics.

> Evidence `tr_e76969138297`:

```
<tool_result id="tr_e76969138297" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_e76969138297>
```

> Evidence `tr_8abb7e77159e`:

```
<tool_result id="tr_8abb7e77159e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8abb7e77159e>
```

> Evidence `tr_276e740a9dcb`:

```
<tool_result id="tr_276e740a9dcb" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:51:15.583000+00:00..2026-08-27T04:06:15.583000+00:00">
no changes recorded for paymentservice over this window
</tool_result:tr_276e740a9dcb>
```
