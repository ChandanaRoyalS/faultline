# Checkout orders failing at cart retrieval; cart service in startup crash loop

## What was visible, in order

The page came in on frontend, loadgenerator and checkoutservice together. Frontend's own span error ratio climbed from a floor of zero to roughly a third of all calls across 58 sample points — an onset inside the window, not a carried-in baseline, and not a hard-down service. That metric is aggregated by service name only, with no peer label, so it named the victim and nothing else.

Traces on checkoutservice collapsed the search space. Every sampled trace had the same shape: frontend POST, frontend PlaceOrder client span, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, then an outbound GetCart call. Everything except the prepare span carried error status, and the deepest error-bearing span was that outbound cart call. The failures were fast — roughly 0.4 to 1.1ms — so this was never a latency regression. No cart-service server-side span appeared anywhere, so the failure lived at or beyond that unmeasured edge. Checkout aborted before shipping, payment, currency or email were reached; those services sat inside the blast radius but were never suspects.

> Evidence `tr_85399cf58a71`:

```
<tool_result id="tr_85399cf58a71" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T04:12:00.583000+00:00..2026-08-26T04:27:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3543 n=58
</tool_result:tr_85399cf58a71>
```

> Evidence `tr_35d30c8d5982`:

```
<tool_result id="tr_35d30c8d5982" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T04:12:00.583000+00:00..2026-08-26T04:27:00.583000+00:00">
service: checkoutservice
200 spans
  a2521d33e88eb40f frontend/HTTP POST 1.8ms ERROR
  a2521d33e88eb40f frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.7ms ERROR
  a2521d33e88eb40f checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.9ms ERROR
```

## Two dead ends worth keeping

Asking what changed on frontend, checkoutservice and their downstream dependencies returned completely empty — no deploys, no config edits, no flag flips. That closed deploy, flag flip, downstream change and mid-incident remediation as explanations for those services, but the query covered a later and narrower slice than the interval of interest, leaving the earlier portion unexamined.

The second dead end is more instructive. A ratio query for cart-service error calls over total calls returned no matching series — and the all-status denominator was missing too, not just the error numerator. An empty ratio looks like an answer and is not one. It is consistent with a service that is not serving, but equally with a renamed service label or a broken span-metrics pipeline. It settled nothing and forced a pivot to logs.

> Evidence `tr_dd850a819de0`:

```
<tool_result id="tr_dd850a819de0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T04:12:00.583000+00:00..2026-08-26T04:27:00.583000+00:00">
no changes recorded for frontend,checkoutservice,and downstream dependencies over this window
</tool_result:tr_dd850a819de0>
```

> Evidence `tr_0158ce317070`:

```
<tool_result id="tr_0158ce317070" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T04:12:00.583000+00:00..2026-08-26T04:27:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_0158ce317070>
```

## Cause, fix class, and what remains open

Cart-service logs answered it. At T+0 the service was logging ordinary cart operations cleanly. By roughly T+10m it was in a startup crash loop: attempting a Redis connection, failing after 15-40 seconds, and dying on an unhandled exception in the cart store's connection-establishment routine called from Main — never reaching a serving state. The target logged each cycle was a redis-cart host on port 6380, abortConnect disabled, TLS off, retried identically every 30-60 seconds. That explains the trace evidence: no server-side spans, and sub-millisecond caller failures.

The cart-service change log held exactly one entry: at roughly T+7m, platform-automation updated the environment configuration to set the Redis address to that same endpoint on port 6380. Not a deploy, not a flag flip, not a human edit. Fix class is a configuration revert; confidence is medium.

Still open: nobody queried the Redis backend itself — 6380 may be wrong (6379?), may expect TLS, or redis-cart may simply be down, which would move the failure a layer further out. The change record captured no prior value, so a revert target cannot be named with certainty. The interval preceding the window was never queried by anyone; three findings flag this independently, and if errors predate the edit, the automation may be reacting to the incident rather than causing it. Restart counts and runtime pressure for the cart service were never retrieved, so a resource contributor cannot be formally excluded, and only the checkout-to-cart unmeasured edge was characterised.

> Evidence `tr_6918adff1097`:

```
<tool_result id="tr_6918adff1097" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T04:12:00.583000+00:00..2026-08-26T04:27:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T04:12:01.205156+00:00  GetCartAsync called with userId=
2026-08-26T04:12:01.752223+00:00  AddItemAsync called with userId=49ea5e66-a104-11f1-86d7-1e4ac5f08d0c, productId=0PUK6V6EV0, quantity=3
2026-08-26T04:12:01.754937+00:00  GetCartAsync called with userId=49ea5e66-a104-11f1-86d7-1e4ac5f08d0c
2026-08-26T04:12:01.767833+00:00  GetCartAsync called with userId=49ea5e66-a104-11f1-86d7-1e4ac5f08d0c
```

> Evidence `tr_5b25114cf774`:

```
<tool_result id="tr_5b25114cf774" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T04:12:00.583000+00:00..2026-08-26T04:27:00.583000+00:00">
service: cartservice
1 changes
  2026-08-26T04:19:22.140730+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_5b25114cf774>
```
