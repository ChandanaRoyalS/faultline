# Checkout failures traced to cartservice startup crash loop after a cache address change

## What was visible first, and what it hid

Paging started from checkoutservice, with frontend and loadgenerator alongside. The seed service was the loudest thing, not the broken thing.

Checkoutservice's error ratio sat at a flat, zero-variance zero across the whole baseline and then stepped up at a single detected change point at T+0, about 105 seconds before the reference time the investigation anchored on. Mean error share was around 6.7%, peaking near two-thirds of requests. No chronic background errors to disentangle, and every incident-side sample had a real denominator, so the spike was not an artifact of a traffic gap — the undefined samples fell on the baseline side.

Ten sampled checkout traces all had the same five-span shape: frontend POST errors, PlaceOrder gRPC errors, checkoutservice/PlaceOrder errors, and CartService/GetCart — invoked from prepareOrderItemsAndShippingQuoteFromCart — carrying the error status as the leaf and 28-42% of each trace's duration. Parent self time was 0.1-0.3ms, so checkoutservice's own logic was not at issue, and the frontend was propagating rather than originating. End-to-end durations were 1.4-3.6ms: fast failures, not timeouts.

> Evidence `tr_b3910e6d922e`:

```
<tool_result id="tr_b3910e6d922e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" template="error-ratio" baseline="2026-09-08T17:38:30.784262+00:00..2026-09-08T18:10:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.06738 min=0 max=0.6667 sd=0.1909
  baseline window: n=11 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_38fa477ad955`:

```
<tool_result id="tr_38fa477ad955" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace 3d75b8a61b4b8529  root frontend/HTTP POST  2.9ms  started 2026-09-08T18:38:45.753020+00:00  5 spans
  +0.0ms frontend/HTTP POST 2.9ms [self 0.3ms]  ERROR
```

## Dead ends worth keeping

The four unmeasured edges pull attention toward paymentservice, currencyservice and accountingservice. Skip it. None of them produce a span in any of the ten traces; checkout aborts inside prepareOrderItemsAndShippingQuoteFromCart before those calls are attempted.

Change history on checkoutservice came back empty — but the query ran at hop depth zero, covering only the seed and none of its dependencies, and its window began at the reference time and ran forward about a day, so it examined the aftermath rather than the lead-up. An empty result from a window aimed the wrong way nearly closed off the productive line.

Checkoutservice's own logs contain no error or warning lines and name no failed RPC target; order entries continue steadily past the reference time with no restart markers. The only usable signal is a shape change: early entries carry full downstream completion lines (payment, email, queue write), while entries from T+55s to T+3m30s are the order line alone. The result was truncated to the oldest eight and newest thirty-two lines, so roughly T-28m to T+55s was never returned — the absence of errors covers two short segments, not the window.

Cartservice metrics returned zero samples in both windows. Because the baseline is equally empty, this reads as series that were never reported rather than collection dying at onset, and it must not be read as evidence the process stopped serving. Onset timing has no independent metric corroboration.

> Evidence `tr_38fa477ad955`:

```
<tool_result id="tr_38fa477ad955" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace 3d75b8a61b4b8529  root frontend/HTTP POST  2.9ms  started 2026-09-08T18:38:45.753020+00:00  5 spans
  +0.0ms frontend/HTTP POST 2.9ms [self 0.3ms]  ERROR
```

> Evidence `tr_fdfef69d1dae`:

```
<tool_result id="tr_fdfef69d1dae" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T18:40:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_fdfef69d1dae>
```

> Evidence `tr_a3115dfb62d3`:

```
<tool_result id="tr_a3115dfb62d3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T18:10:33.404541+00:00  {"message":"[PlaceOrder] user_id=\"955c0816-abb0-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T18:10:33.404379709Z"}
2026-09-08T18:10:33.425358+00:00  {"message":"payment went through (transaction_id: 0fed0f11-ed78-4ce0-b79a-e3e9f3ed5456)","severity":"info","timestamp":"2026-09-08T18:10:33.42527175Z"}
2026-09-08T18:10:33.431621+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-08T18:10:33.431523667Z"}
2026-09-08T18:10:33.432570+00:00  {"message":"Successful to write message. offset: 15090","severity":"info","timestamp":"2026-09-08T18:10:33.432499Z"}
```

> Evidence `tr_584aeb4b9afb`:

```
<tool_result id="tr_584aeb4b9afb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" template="error-ratio" baseline="2026-09-08T17:38:30.784262+00:00..2026-09-08T18:10:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where the answer was, and what stays open

Cartservice logs at T-28m show ordinary cart operations with no errors. In the T+1m21s to T+3m30s tail the service is in a repeated startup-crash cycle: connection attempt to the cache, failure, unhandled ApplicationException, restart — at least six cycles in two minutes. The stack frames sit in RedisCartStore.EnsureRedisConnected, called from InitializeAsync, called from Main. That chain is the point: the throw happens during process initialization, so the process never reaches a state where it can serve gRPC cart calls at all. Not a degraded service — a process exiting before it serves anything. The target named is the redis-cart host on port 6380. The loop was still running at window close, with no successful-connection line.

Cartservice's change history closes it: REDIS_ADDR was set to that 6380 endpoint at T-50s, where no explicit value had been set before. The nearest image change was a revert off a hotfix tag 5.1 hours earlier, so no roll-forward; no flag toggles are recorded; all thirteen changes in the day are attributed to platform-automation. A traffic-shaping sidecar had been attached to the cart-service network namespace about 19 minutes before onset and removed about 9 minutes before, so it was gone by the time symptoms began. Fix class: revert the configuration value.

Three things stay open. Nobody probed redis-cart itself — if the cache legitimately moved to 6380 and the instance is down or not listening, the cause is the store's availability rather than the address value. Checkoutservice's error ratio peaks near 0.67, not 1.0, while cartservice appears fully down; what carried the successful checkouts is unexplained. And both log results were truncated across roughly T-28m to T+55s, so the interval containing onset itself is largely unobserved.

> Evidence `tr_8cc792d6a61f`:

```
<tool_result id="tr_8cc792d6a61f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-08T18:10:33.391857+00:00  AddItemAsync called with userId=955c0816-abb0-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=5
2026-09-08T18:10:33.394416+00:00  GetCartAsync called with userId=955c0816-abb0-11f1-b359-b6ed2071a170
2026-09-08T18:10:33.406141+00:00  GetCartAsync called with userId=955c0816-abb0-11f1-b359-b6ed2071a170
2026-09-08T18:10:33.427903+00:00  EmptyCartAsync called with userId=955c0816-abb0-11f1-b359-b6ed2071a170
```

> Evidence `tr_357d9c0d9bd1`:

```
<tool_result id="tr_357d9c0d9bd1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T18:40:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" radius="candidate_cause" hops="1">
service: cartservice
13 changes, ranked by suspicion
  #1  2m before onset  2026-09-08T18:37:55.862118+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  9m before onset  2026-09-08T18:30:38.055180+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

> Evidence `tr_b3910e6d922e`:

```
<tool_result id="tr_b3910e6d922e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" template="error-ratio" baseline="2026-09-08T17:38:30.784262+00:00..2026-09-08T18:10:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.06738 min=0 max=0.6667 sd=0.1909
  baseline window: n=11 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_a3115dfb62d3`:

```
<tool_result id="tr_a3115dfb62d3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T18:10:30.583000+00:00..2026-09-08T18:42:30.381738+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T18:10:33.404541+00:00  {"message":"[PlaceOrder] user_id=\"955c0816-abb0-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T18:10:33.404379709Z"}
2026-09-08T18:10:33.425358+00:00  {"message":"payment went through (transaction_id: 0fed0f11-ed78-4ce0-b79a-e3e9f3ed5456)","severity":"info","timestamp":"2026-09-08T18:10:33.42527175Z"}
2026-09-08T18:10:33.431621+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-08T18:10:33.431523667Z"}
2026-09-08T18:10:33.432570+00:00  {"message":"Successful to write message. offset: 15090","severity":"info","timestamp":"2026-09-08T18:10:33.432499Z"}
```

