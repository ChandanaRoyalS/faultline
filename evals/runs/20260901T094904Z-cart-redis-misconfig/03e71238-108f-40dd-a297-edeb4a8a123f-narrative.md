# Checkout failures traced to cart backing-store endpoint

## What was visible, in order

Pages arrived together from checkoutservice, frontend, and loadgenerator; twelve services sat inside the blast radius and four edges out of checkout were unmeasured. checkoutservice's own errored-span ratio was clearly non-zero, peaking near two-thirds, but returned to zero at points in the window — which read as partial degradation and cost time.

Its logs were quietly misleading. Every returned line was informational, with no error or warning anywhere. Early samples around T-7m showed complete orders: request received, payment succeeded, email sent, message written. From roughly T+2m to T+5m only order-entry lines appeared, with no completion of any kind. The natural reading was a stall or hung downstream call. That reading was wrong and is the most useful dead end here. Two caveats explain it: the result kept only the oldest eight and newest thirty-two lines, so a nine-minute middle was never returned, and checkout emits no terminal line at all when the call fails early. What the logs did settle is that the process was alive and taking traffic throughout, retiring the crash and out-of-memory theories for this service.

> Evidence `tr_96fdfcc4f20e`:

```
<tool_result id="tr_96fdfcc4f20e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=57
</tool_result:tr_96fdfcc4f20e>
```

> Evidence `tr_6a5141eb5726`:

```
<tool_result id="tr_6a5141eb5726" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-01T09:41:47.222769+00:00  {"message":"[PlaceOrder] user_id=\"596c4770-a5e9-11f1-ae7b-9eef0fcf8acb\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-01T09:41:47.222677506Z"}
2026-09-01T09:41:47.239779+00:00  {"message":"payment went through (transaction_id: c6158eea-c078-4dc5-98a3-c41b8caf57fc)","severity":"info","timestamp":"2026-09-01T09:41:47.239668547Z"}
2026-09-01T09:41:47.244229+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-09-01T09:41:47.244166589Z"}
2026-09-01T09:41:47.244842+00:00  {"message":"Successful to write message. offset: 2033","severity":"info","timestamp":"2026-09-01T09:41:47.244767881Z"}
```

## Traces corrected the stall theory, and a metric path closed

Around forty sampled failing checkouts shared one five-span shape: frontend POST, frontend PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, and a CartService GetCart child. GetCart was always the deepest span in error; its parent, checkout's local order assembly, was consistently clean. Traces finished in one to four milliseconds and GetCart was sub-millisecond, so these were fast failures, not timeouts. No spans for payment, currency, accounting, or email appeared anywhere — all four unmeasured edges sit past the abort point and were never reached. Every sampled trace failed identically, contradicting the intermittency the ratio metric implied.

change history for checkoutservice was empty across roughly ten minutes before and five after onset, clearing it as originator. The obvious next step — cartservice's request and error rates — was unavailable: the span-metrics query returned nothing, including the unfiltered call denominator. That emptiness is a series-level gap, not proof the service was idle or down; a renamed label or unconfigured exporter looks identical. No saturation data came back either.

> Evidence `tr_df9a68fd96ac`:

```
<tool_result id="tr_df9a68fd96ac" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00">
service: checkoutservice
200 spans
  f61d8c95bb90a2e6 frontend/HTTP POST 2.0ms ERROR
  f61d8c95bb90a2e6 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.8ms ERROR
  f61d8c95bb90a2e6 checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.8ms ERROR
```

> Evidence `tr_5d1f4532b2a4`:

```
<tool_result id="tr_5d1f4532b2a4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_5d1f4532b2a4>
```

> Evidence `tr_97b723431be4`:

```
<tool_result id="tr_97b723431be4" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_97b723431be4>
```

## The cause, and what is still open

cartservice's logs closed it. The errors are startup-path failures out of RedisCartStore.InitializeAsync and EnsureRedisConnected, raised as unhandled exceptions from Program.Main — the process died during initialization and never served a cart RPC. Each attempt connected to the redis-cart host on port 6380 with TLS disabled and failed twenty to forty seconds later, looping from about T+3.5m to T+6m. The same service was healthy at T-7m. Exactly one change is recorded: at T+0 an automated actor set the Redis backing address to that host and port. A wrong endpoint in a configuration string is the whole mechanism. Confidence medium; fix class is a configuration revert.

Also ruled out on the cart side: no auth or ACL error (failure is at connect, no credentials present), no capacity or pool-exhaustion signals, no code rollout, secret rotation, flag flip, or competing change.

Open: whether 6380 is genuinely wrong or is a TLS port being reached with TLS disabled — reverting the port and enabling TLS are different fixes and the evidence does not separate them. No prior value is recorded, so the correct address must come from a known-good manifest or peer environment. The two-thirds error peak against uniformly failing traces is unexplained; call volume was never retrieved. Onset is unpinned between T-7m and T+3.5m. Only cartservice's change history was queried, so whether the same edit landed on other services is unverified.

> Evidence `tr_4ebe4ee16310`:

```
<tool_result id="tr_4ebe4ee16310" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T09:41:47.172784+00:00  AddItemAsync called with userId=596c4770-a5e9-11f1-ae7b-9eef0fcf8acb, productId=1YMWWN1N4O, quantity=1
2026-09-01T09:41:47.175096+00:00  GetCartAsync called with userId=596c4770-a5e9-11f1-ae7b-9eef0fcf8acb
2026-09-01T09:41:47.191185+00:00  AddItemAsync called with userId=596c4770-a5e9-11f1-ae7b-9eef0fcf8acb, productId=66VCHSJNUP, quantity=4
2026-09-01T09:41:47.192926+00:00  GetCartAsync called with userId=596c4770-a5e9-11f1-ae7b-9eef0fcf8acb
```

> Evidence `tr_afbf7ec16980`:

```
<tool_result id="tr_afbf7ec16980" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00">
service: cartservice
1 changes
  2026-09-01T09:49:07.969932+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_afbf7ec16980>
```

> Evidence `tr_96fdfcc4f20e`:

```
<tool_result id="tr_96fdfcc4f20e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T09:41:45.583000+00:00..2026-09-01T09:56:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=57
</tool_result:tr_96fdfcc4f20e>
```
