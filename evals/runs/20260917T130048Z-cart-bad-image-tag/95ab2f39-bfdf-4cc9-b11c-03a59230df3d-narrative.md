# Checkout failures traced to a cart service that never came back after a hotfix image swap

## What was visible, in order

Three alerts landed in the same second: checkoutservice, frontend, loadgenerator. Checkout looked like the sick service because it was the seed and the one whose error ratio moved. Its error ratio over the surrounding half hour averaged essentially at baseline (~0.93x), which initially argued against any regression — a trap of averaging. A single change point at T-1m pushed roughly two thirds of calls into error, far above the baseline maximum of 0.28, with variance nearly double. A sharp burst, not a drift. The same series had a defined ratio in every incident-window interval, so checkout was taking traffic throughout and had not stopped serving.

Checkout's own logs said almost nothing at onset: only info-level order-placement start lines, no errors, no named dependency. One detail was worth keeping — those starts had no matching payment or confirmation follow-ups, whereas lines from T-30m ran through to completion. Requests were entering checkout and dying quietly.

Traces settled it. Ten sampled failing traces were identical, five spans deep: frontend POST, frontend PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, and a checkoutservice client call to CartService/GetCart. That cart call is the only leaf and is ERROR in every trace, propagating unchanged to the frontend root — which explains the simultaneous alerts. It held essentially all downstream time while checkout's own spans carried 0.1-0.3ms of self-time. Durations were tiny (traces 3.1-12.3ms, the cart call 2.0-4.5ms): immediate refusals, not timeouts.

On the cart side, logs run as ordinary cart-operation traffic and then stop, with the last two lines at about T-3m being a hosting-lifetime shutdown notice. Nothing after that, including the whole failure interval. The cart change log shows a container image reference update to a hotfix tag applied roughly two minutes before onset — the only change in the preceding hour.

> Evidence `tr_26bc1cd98727`:

```
<tool_result id="tr_26bc1cd98727" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" template="error-ratio" baseline="2026-09-17T12:01:42.463917+00:00..2026-09-17T12:33:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.07218 min=0 max=0.6667 sd=0.1965
  baseline window: n=57 mean=0.07726 min=0 max=0.28 sd=0.1142
```

> Evidence `tr_a4609a571d39`:

```
<tool_result id="tr_a4609a571d39" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T12:33:46.183010+00:00  {"message":"[PlaceOrder] user_id=\"06a17490-b294-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T12:33:46.182921299Z"}
2026-09-17T12:33:46.201918+00:00  {"message":"payment went through (transaction_id: b363bbb4-dfea-44f5-8e11-a2adaad58ce1)","severity":"info","timestamp":"2026-09-17T12:33:46.201814508Z"}
2026-09-17T12:33:46.207132+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T12:33:46.207069466Z"}
2026-09-17T12:33:46.960675+00:00  {"message":"Failed to write message: kafka: Failed to produce message to topic orders: kafka: client has run out of available brokers to talk to: dial tcp 172.18.0.8:9092: connect: connection refused","severity":"error","timestamp":"2026-09-17T12:33:46.960569258Z"}
```

> Evidence `tr_31b188036a49`:

```
<tool_result id="tr_31b188036a49" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace a5c036958759b79f  root frontend/HTTP POST  3.3ms  started 2026-09-17T13:03:57.531014+00:00  5 spans
  +0.0ms frontend/HTTP POST 3.3ms [self 0.1ms]  ERROR
```

> Evidence `tr_f39555a31a12`:

```
<tool_result id="tr_f39555a31a12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T12:33:46.144583+00:00  AddItemAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=1
2026-09-17T12:33:46.146031+00:00  GetCartAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170
2026-09-17T12:33:46.155794+00:00  AddItemAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=3
2026-09-17T12:33:46.157093+00:00  GetCartAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170
```

> Evidence `tr_60f0309fc3f8`:

```
<tool_result id="tr_60f0309fc3f8" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:03:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" radius="candidate_cause" hops="1">
service: cartservice
15 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T13:00:54.142790+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
  #2  3.0h before onset  2026-09-17T10:03:07.534610+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

## Dead ends worth keeping

Kafka. Checkout's logs do contain real error lines naming a downstream: a TCP connection refusal to a broker address and port for the order-topic producer, then a tripped circuit breaker on the same path. Wrong twice over — they appear only near T-30m, none in the block spanning onset, and they followed successful payment and confirmation, so that call was a post-commit asynchronous publish, not a blocking step.

The four unmeasured edges. The instinct was to suspect payment, currency and accounting. No spans for those, nor shipping, product catalog or email, appear in any failing trace; checkout aborts during cart preparation, upstream of all of them. Caveat retained: their absence is inferred from where the request dies, not observed.

Cart backing store and network. The cart change log shows an environment override pointing the store at a non-default port, reverted about three hours before onset, and a traffic-shaping container carrying a 300ms egress delay, detached about 3.3 hours before onset with no reattachment. Neither was in effect, and a 2-4ms refusal is the opposite signature of added delay. Cart's logs also name no cache or datastore dependency and show no connection or timeout errors.

> Evidence `tr_a4609a571d39`:

```
<tool_result id="tr_a4609a571d39" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T12:33:46.183010+00:00  {"message":"[PlaceOrder] user_id=\"06a17490-b294-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T12:33:46.182921299Z"}
2026-09-17T12:33:46.201918+00:00  {"message":"payment went through (transaction_id: b363bbb4-dfea-44f5-8e11-a2adaad58ce1)","severity":"info","timestamp":"2026-09-17T12:33:46.201814508Z"}
2026-09-17T12:33:46.207132+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T12:33:46.207069466Z"}
2026-09-17T12:33:46.960675+00:00  {"message":"Failed to write message: kafka: Failed to produce message to topic orders: kafka: client has run out of available brokers to talk to: dial tcp 172.18.0.8:9092: connect: connection refused","severity":"error","timestamp":"2026-09-17T12:33:46.960569258Z"}
```

> Evidence `tr_31b188036a49`:

```
<tool_result id="tr_31b188036a49" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace a5c036958759b79f  root frontend/HTTP POST  3.3ms  started 2026-09-17T13:03:57.531014+00:00  5 spans
  +0.0ms frontend/HTTP POST 3.3ms [self 0.1ms]  ERROR
```

> Evidence `tr_60f0309fc3f8`:

```
<tool_result id="tr_60f0309fc3f8" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:03:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" radius="candidate_cause" hops="1">
service: cartservice
15 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T13:00:54.142790+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
  #2  3.0h before onset  2026-09-17T10:03:07.534610+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_f39555a31a12`:

```
<tool_result id="tr_f39555a31a12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T12:33:46.144583+00:00  AddItemAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=1
2026-09-17T12:33:46.146031+00:00  GetCartAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170
2026-09-17T12:33:46.155794+00:00  AddItemAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=3
2026-09-17T12:33:46.157093+00:00  GetCartAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170
```

## Conclusion, fix, and what is still open

cartservice was replaced about three minutes before onset with a hotfix image tag (v1.2.1-cartservice-hotfix.2). The prior process shut down gracefully and nothing took its place. With no cart process answering, checkout's outbound GetCart call fails immediately and that ERROR leaf propagates to the frontend root. checkoutservice has no registered changes in the window queried, near-zero span self-time, and no error lines at onset: it is a victim. Fix class: rollback of the cart image reference to the preceding known-serving tag.

Confidence medium. The same hotfix tag was applied and reverted at least four times earlier in the day by the same automation actor, which weakens the inference that the artifact content is at fault rather than the swap procedure.

Still open. Nobody checked cart pod or container state, restart counts, or image-pull status — the container failing to start is inferred from log silence alone, and that is the highest-value next check. Cart emits no call counters in either incident or baseline windows, so its unavailability and recovery cannot be timed from metrics at all; note the baseline is equally empty, so this is not an exporter that died at onset. Checkout's error ratio shows only one change point, at T-1m, with a window mean at baseline, which sits awkwardly against a cart outage apparently beginning at T-3m; true duration is unresolved. Finally, the checkoutservice change query began at onset and ran forward a day at zero hops, so a checkout-side change in the minutes before onset was never searched.

> Evidence `tr_60f0309fc3f8`:

```
<tool_result id="tr_60f0309fc3f8" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:03:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" radius="candidate_cause" hops="1">
service: cartservice
15 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T13:00:54.142790+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
  #2  3.0h before onset  2026-09-17T10:03:07.534610+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_f39555a31a12`:

```
<tool_result id="tr_f39555a31a12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T12:33:46.144583+00:00  AddItemAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=1
2026-09-17T12:33:46.146031+00:00  GetCartAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170
2026-09-17T12:33:46.155794+00:00  AddItemAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=3
2026-09-17T12:33:46.157093+00:00  GetCartAsync called with userId=06a17490-b294-11f1-b359-b6ed2071a170
```

> Evidence `tr_31b188036a49`:

```
<tool_result id="tr_31b188036a49" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace a5c036958759b79f  root frontend/HTTP POST  3.3ms  started 2026-09-17T13:03:57.531014+00:00  5 spans
  +0.0ms frontend/HTTP POST 3.3ms [self 0.1ms]  ERROR
```

> Evidence `tr_0c5239388bf4`:

```
<tool_result id="tr_0c5239388bf4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T10:03:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" template="error-ratio" baseline="2026-09-17T07:01:42.463917+00:00..2026-09-17T10:03:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_26bc1cd98727`:

```
<tool_result id="tr_26bc1cd98727" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T12:33:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" template="error-ratio" baseline="2026-09-17T12:01:42.463917+00:00..2026-09-17T12:33:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.07218 min=0 max=0.6667 sd=0.1965
  baseline window: n=57 mean=0.07726 min=0 max=0.28 sd=0.1142
```

> Evidence `tr_07d86ece2fd1`:

```
<tool_result id="tr_07d86ece2fd1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T13:03:45.583000+00:00..2026-09-17T13:05:48.702083+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_07d86ece2fd1>
```

