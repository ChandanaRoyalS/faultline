# Checkout failures traced to cartservice restart cycle on an unreachable cache endpoint

## What was visible first

Three pages arrived together at T+0: checkoutservice, frontend, and loadgenerator. Triage estimated twelve services and four unmeasured edges, which made the board look worse than the investigation ultimately justified.

Checkoutservice's error ratio over the fifteen minutes around T+0 was a continuous sixty-one-point series that touched zero and peaked near two-thirds. That ruled out a dead process (no scrape gaps, no flat 1.0) and ruled out chronic noise (a clean interval sits in the same window). It could not give an onset minute — only min/max aggregates came back, so the inflection point stayed unlocated for the whole incident.

The trace sample redirected the search almost immediately. Forty checkout traces shared one shape and all failed: frontend POST, frontend PlaceOrder, checkoutservice PlaceOrder, the order-item/shipping-quote prepare step, then an outbound CartService/GetCart call. The deepest erroring span was that cart hop, propagating upward unchanged. Failures were fast — one to four milliseconds end to end, the cart hop itself 0.4–1.2ms — which is refusal, not a deadline. No payment, currency, shipping, email, accounting, or product-catalog spans appear anywhere; checkout aborted before reaching them.

> Evidence `tr_ca11e72b37a1`:

```
<tool_result id="tr_ca11e72b37a1" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_ca11e72b37a1>
```

> Evidence `tr_34e02e3f107e`:

```
<tool_result id="tr_34e02e3f107e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00">
service: checkoutservice
200 spans
  78339330cdaf73b7 frontend/HTTP POST 1.6ms ERROR
  78339330cdaf73b7 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.4ms ERROR
  78339330cdaf73b7 checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.7ms ERROR
```

## Dead ends worth keeping

First, the hunt for something that shipped on the alerting services. Change history for checkoutservice, paymentservice, and currencyservice came back completely empty — no deploys, config edits, flag flips, or scaling events. Two caveats survive unretired: the checkoutservice query actually covered only about T-10m to T+5m, not the full hour intended, and an empty log equals 'nothing happened' only if the pipeline captures every change type, so anything done out of band would be invisible here.

Second, trying to characterise cartservice from metrics. The span-derived error ratio returned no series. The tempting read — zero errors against live traffic — was wrong: the denominator matched nothing either, meaning no cartservice call metrics existed at all in the window. That path is simply not a usable source for this service; two dispatches were spent confirming it, and no restart, memory, CPU, or cache-client metrics were ever retrieved.

Third, checkoutservice's own logs. Every retained line was info severity, no stack traces, no named failing dependency. Early lines show orders completing end to end; from about T+0 only order-received entries remain, with payment, email, and queue-write follow-ups absent, while new orders kept arriving every few seconds through T+4m. Read alone this looks like a hang past order acceptance — misleading. Combined with the traces it is just the path terminating at the cart lookup. Note the coverage hole: roughly ten minutes of the middle were dropped and the query stopped five minutes short.

> Evidence `tr_6d2dbb9f0fa1`:

```
<tool_result id="tr_6d2dbb9f0fa1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_6d2dbb9f0fa1>
```

> Evidence `tr_5cfa77c5594d`:

```
<tool_result id="tr_5cfa77c5594d" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_5cfa77c5594d>
```

> Evidence `tr_d0834463478d`:

```
<tool_result id="tr_d0834463478d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T03:30:27.759067+00:00  {"message":"[PlaceOrder] user_id=\"a5c89298-a1c7-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T03:30:27.758885716Z"}
2026-08-27T03:30:27.777450+00:00  {"message":"payment went through (transaction_id: 8656b267-a5a2-4c5a-a4d9-58bef2ce89f3)","severity":"info","timestamp":"2026-08-27T03:30:27.777386507Z"}
2026-08-27T03:30:27.781929+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-08-27T03:30:27.781825174Z"}
2026-08-27T03:30:27.782484+00:00  {"message":"Successful to write message. offset: 15374","severity":"info","timestamp":"2026-08-27T03:30:27.782420924Z"}
```

## Where it broke, and what is still open

cartservice's logs ended it. Normal cart traffic around T-10m; then from roughly T+2m40s through T+4m50s a repeating cycle — connection attempt to host redis-cart on port 6380, failure, unhandled ApplicationException out of store initialisation called from Main, process exit, restart thirty to sixty seconds later. The failure occurs at startup, not in a handler, so the listener is absent for most of each cycle, which is precisely why checkout's cart call is refused sub-millisecond instead of timing out.

The change history for cartservice was not empty. One entry, roughly T-2m30s: platform-automation rewrote the service's environment configuration so the cache endpoint names redis-cart on port 6380. Automation actor, environment mutation, no deploy or image change, no scaling or flag entry. Hostname unchanged — only the port differs, so this is not a cluster cutover. The port value is the whole failure: the target names a port nothing is listening on. Fix class is a config revert.

Bystanders: product catalog was flat at zero errors across sixty-one points while serving real traffic; payment and currency had clean logs; none appear in any failing trace.

Open items for the next responder. Nobody verified what redis-cart is actually listening on — if the store legitimately moved to 6380, the fix belongs on the Redis side, and the change record carries no prior value. Nobody examined why the automation issued the edit, whether it will re-apply after a manual revert, or whether other services carry the same rewritten endpoint. A gap sits between the change, the page, and the earliest retained crash lines, so the first failed start is unestablished. And checkout's ratio peaking near 0.67 while every sampled trace carries ERROR is not obviously consistent — residual successes may fall between restarts, or the sample may be biased. Unresolved.

> Evidence `tr_37309257e4ed`:

```
<tool_result id="tr_37309257e4ed" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T03:30:16.510283+00:00  GetCartAsync called with userId=
2026-08-27T03:30:23.554050+00:00  GetCartAsync called with userId=
2026-08-27T03:30:27.746534+00:00  AddItemAsync called with userId=a5c89298-a1c7-11f1-86d7-1e4ac5f08d0c, productId=66VCHSJNUP, quantity=2
2026-08-27T03:30:27.749332+00:00  GetCartAsync called with userId=a5c89298-a1c7-11f1-86d7-1e4ac5f08d0c
```

> Evidence `tr_9f124d3d02ef`:

```
<tool_result id="tr_9f124d3d02ef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00">
service: cartservice
1 changes
  2026-08-27T03:37:46.455071+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_9f124d3d02ef>
```

> Evidence `tr_1828e73c3100`:

```
<tool_result id="tr_1828e73c3100" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:30:15.583000+00:00..2026-08-27T03:45:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_1828e73c3100>
```
