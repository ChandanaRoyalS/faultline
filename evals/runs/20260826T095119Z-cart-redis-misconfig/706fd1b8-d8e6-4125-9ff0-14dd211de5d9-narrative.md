# Checkout failures traced to a cart Redis endpoint value

## What we saw first

Three alerts arrived close together: frontend, loadgenerator, and checkoutservice. From the responder's chair the visible symptom was user-facing checkout failures, not a total outage. Frontend's error ratio moved from a clean zero inside the observation window up to roughly 35% of calls at its worst, while checkoutservice peaked near 67%. Frontend never stopped emitting metrics — 61 contiguous samples, no gaps — so nothing had died at the edge; it was passing along something coming from deeper in. The ratio split between the two (a third versus two thirds) was itself informative: checkout is only a fraction of frontend traffic, so a total loss of checkout would look like exactly this at the frontend.

One thing to note up front for anyone re-reading these metrics: only min/max aggregates came back, not the per-timestamp series. That means the onset moment was never directly observed on either service, and the ordering later in this record is inferred from alert times rather than read off a curve. No latency percentiles were retrieved for frontend, checkoutservice, or cartservice at any point.

> Evidence `tr_a75ec76afef0`:

```
<tool_result id="tr_a75ec76afef0" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3457 n=61
</tool_result:tr_a75ec76afef0>
```

> Evidence `tr_663cc5422f32`:

```
<tool_result id="tr_663cc5422f32" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_663cc5422f32>
```

## Following the traces down

Traces were the turn in the investigation. Around forty sampled checkout traces all failed in the same place and in the same way: checkoutservice's outbound call to hipstershop.CartService/GetCart, made from prepareOrderItemsAndShippingQuoteFromCart, carried the ERROR status, and that status propagated up through checkoutservice PlaceOrder into frontend PlaceOrder and the frontend HTTP POST. There were no successful PlaceOrder traces in the sample at all — this was a hard fail-fast, not a partial or canary-scoped impact.

Two things fell out of this immediately. First, whole swathes of the checkout path were never reached: no spans at all for accountingservice, currencyservice, paymentservice, shippingservice, productcatalogservice, or emailservice. Every theory naming one of those as the cause was closed by absence. Second, this was not a timing problem. End-to-end durations sat between 1 and 7 milliseconds. Nothing hung, nothing timed out; requests returned errors instantly. The parent prepareOrderItems span was not itself marked ERROR while its GetCart child was, which pinned the origin precisely at the cart dependency boundary rather than inside checkoutservice's own logic.

> Evidence `tr_84ff3bfd8f4d`:

```
<tool_result id="tr_84ff3bfd8f4d" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
service: checkoutservice
200 spans
  266772d22d10b0db checkoutservice/prepareOrderItemsAndShippingQuoteFromCart 0.5ms
  266772d22d10b0db checkoutservice/hipstershop.CartService/GetCart 0.4ms ERROR
  1842dc44303f438c frontend/HTTP POST 4.6ms ERROR
```

## The dead ends, in the order we walked them

Change history was queried on four services and consumed the whole tool budget. Frontend: nothing recorded. Checkoutservice: nothing recorded. Productcatalogservice: nothing recorded. Three empty results in a row, which is genuinely useful — it closed the deploy-triggered and flag-flip theories for those services, and it also confirmed no in-flight rollback or remediation was muddying the picture while we looked.

Productcatalogservice was checked on the metrics side too, and its error ratio was flat zero across all 61 samples — a measured zero with a live denominator, not missing data. That service was fully exonerated.

The cartservice metric query was the one real trap. It returned nothing at all — no error-filtered numerator and no unfiltered total-calls denominator. The tempting misread is "empty means zero errors, so cartservice is fine." It does not. An absent denominator is absence of telemetry, and no health conclusion can be drawn from it. That gap is still unresolved and is flagged again below.

Worth recording explicitly: the change queries all covered roughly 09:44–09:59, while the period of interest started around 09:30. The first fourteen minutes were never examined by any change query, and all four results say so.

> Evidence `tr_9373afe09afe`:

```
<tool_result id="tr_9373afe09afe" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_9373afe09afe>
```

> Evidence `tr_e8cbbe4269bd`:

```
<tool_result id="tr_e8cbbe4269bd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_e8cbbe4269bd>
```

> Evidence `tr_c6b98ef7dd43`:

```
<tool_result id="tr_c6b98ef7dd43" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_c6b98ef7dd43>
```

> Evidence `tr_5238aec71711`:

```
<tool_result id="tr_5238aec71711" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_5238aec71711>
```

> Evidence `tr_8f33eb8fc66f`:

```
<tool_result id="tr_8f33eb8fc66f" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_8f33eb8fc66f>
```

## Where it landed

Cartservice was the fourth change query and the only one that returned anything. A single entry: platform-automation updated the service environment at 09:51:20 UTC, setting a Redis address variable that had previously been unset to point at host redis-cart on port 6380. No image, no version, no code artifact — a configuration mutation only, and machine-originated rather than an operator's emergency edit. Because the prior value was absent, the service had until that moment been running on its baked-in default endpoint.

Cartservice's own logs closed the loop. The earliest lines in the window show the service healthy, serving AddItem, GetCart, and EmptyCart with no errors. Later in the window it is in a continuous loop: a connect attempt to redis-cart on 6380, a failure some twenty to thirty-five seconds later, and an unhandled ApplicationException thrown from RedisCartStore.InitializeAsync / EnsureRedisConnected as called from Main. Because the exception is unhandled and thrown during startup initialization, the process never finishes starting — it crash-loops rather than serving with degraded cart access. The connection string in use names port 6380 with ssl=false and abortConnect=false.

So the failing mechanism is the configuration value itself. The endpoint it names is not one a Redis server answers on, cartservice therefore never completes startup, checkoutservice's GetCart has nothing to talk to, and the ERROR walks up the call chain to the user. Confidence is high. Fix class is a configuration revert.

> Evidence `tr_4f54ca0da4a7`:

```
<tool_result id="tr_4f54ca0da4a7" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
service: cartservice
1 changes
  2026-08-26T09:51:20.222869+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_4f54ca0da4a7>
```

> Evidence `tr_287da123d1d8`:

```
<tool_result id="tr_287da123d1d8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T09:44:00.990236+00:00  AddItemAsync called with userId=aab442ba-a132-11f1-86d7-1e4ac5f08d0c, productId=9SIQT8TOJO, quantity=1
2026-08-26T09:44:00.992477+00:00  GetCartAsync called with userId=aab442ba-a132-11f1-86d7-1e4ac5f08d0c
2026-08-26T09:44:01.133243+00:00  AddItemAsync called with userId=aac873f2-a132-11f1-86d7-1e4ac5f08d0c, productId=0PUK6V6EV0, quantity=3
2026-08-26T09:44:01.134840+00:00  GetCartAsync called with userId=aac873f2-a132-11f1-86d7-1e4ac5f08d0c
```

## What a future responder should not assume we settled

The single most important open item: nothing in this investigation confirmed what port redis-cart actually listens on. No dispatch touched redis-cart directly. If the platform was mid-migration to 6380 and the server side never landed — or landed and is itself down — then the cartservice value is early rather than wrong, and the correct fix is finishing or repairing the Redis side, not reverting the client. Check this before reverting.

Second: the change-tool budget was exhausted before any query reached 09:30–09:44. A change on any service in that earlier interval, including redis-cart itself, is entirely unverified.

Third: exact onset is unpinned on both sides. The metric results gave only aggregates, and the log query returned only the oldest eight and newest thirty-two lines, omitting the transition from healthy to failing. The 09:51:20 → ~09:54 ordering is an inference from alert times.

Fourth: cartservice emits no calls_total series for the window at all. This is consistent with a crash loop, but it could equally be a pre-existing label mismatch or scrape problem. It was never resolved, which means cartservice's own error and latency behaviour before the change rests entirely on eight early log lines.

Fifth: why the automation wrote this value is unknown — pipeline template, policy rollout, partially-applied migration. Without that answer, a revert may simply be re-applied by the same automation.

Finally, scope. The blast radius was twelve services with four unmeasured edges crossed; four services were examined. Whether the impact outside the checkout path shares this cause or is independent was never tested.

> Evidence `tr_4f54ca0da4a7`:

```
<tool_result id="tr_4f54ca0da4a7" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
service: cartservice
1 changes
  2026-08-26T09:51:20.222869+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_4f54ca0da4a7>
```

> Evidence `tr_287da123d1d8`:

```
<tool_result id="tr_287da123d1d8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T09:44:00.990236+00:00  AddItemAsync called with userId=aab442ba-a132-11f1-86d7-1e4ac5f08d0c, productId=9SIQT8TOJO, quantity=1
2026-08-26T09:44:00.992477+00:00  GetCartAsync called with userId=aab442ba-a132-11f1-86d7-1e4ac5f08d0c
2026-08-26T09:44:01.133243+00:00  AddItemAsync called with userId=aac873f2-a132-11f1-86d7-1e4ac5f08d0c, productId=0PUK6V6EV0, quantity=3
2026-08-26T09:44:01.134840+00:00  GetCartAsync called with userId=aac873f2-a132-11f1-86d7-1e4ac5f08d0c
```

> Evidence `tr_8f33eb8fc66f`:

```
<tool_result id="tr_8f33eb8fc66f" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T09:44:00.583000+00:00..2026-08-26T09:59:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_8f33eb8fc66f>
```
