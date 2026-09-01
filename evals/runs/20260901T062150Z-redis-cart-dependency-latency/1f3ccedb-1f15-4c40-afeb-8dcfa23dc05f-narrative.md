# Cart path latency traced to slow cache calls inside cartservice

## What the responder saw first

The page named four services at once: cartservice, frontend, loadgenerator, and checkoutservice. Severity was warning, not critical, and the declared blast radius was twelve services with cartservice as the origin point. Four edges in the path were unmeasured, which is worth holding in mind: the shape of the graph the alert drew was partly inferred, not observed.

The first instinct — four services alerting together means something is broken — turned out to be wrong in an important way. Nothing was broken. Everything was answering. Everything was answering slowly, and the slowness was flowing uphill through the call graph into the services that depend on cart.

## The first two queries were both dead ends

The opening move was the standard one: pull error-rate metrics for cartservice over the fifteen minutes bracketing onset. The query came back completely empty — not zero errors, but no series at all. Both the numerator (error-status spans) and the denominator (all calls) were absent. That is a genuinely confusing result, because a service under load should emit call counters continuously, and their total absence normally means either the service stopped handling requests or its telemetry export broke.

A responder reading this months later should know: neither of those was true. The span-derived call metric for cartservice simply was not available for this window. Do not spend time here. Go to traces.

The second dead end was logs. Two separate log queries were run against cartservice, and both came back truncated in the same unhelpful way: the oldest eight lines and the newest thirty-two lines were kept, and everything in between was discarded. Onset sat squarely inside the discarded middle. The second attempt tried to narrow to a three-minute band around onset with a severity filter, and the query as executed applied neither constraint — it returned the same full-window, unfiltered, truncated slice. Both attempts produced only routine informational request tracing for cart reads, adds, and empties.

Those logs did establish two useful negatives. cartservice was up and busily serving many distinct user ids both at the very start of the window and again in the tail, several minutes after onset. So there was no crash loop, no restart, and no failure to recover. But the specific question — what, if anything, cartservice logged at onset — was never answered. The absence of error text in those results is a sampling artifact, not evidence.

> Evidence `tr_006d4ad454d0`:

```
<tool_result id="tr_006d4ad454d0" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_006d4ad454d0>
```

> Evidence `tr_f2f149819e65`:

```
<tool_result id="tr_f2f149819e65" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T06:15:30.965909+00:00  GetCartAsync called with userId=
2026-09-01T06:15:31.012812+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=1YMWWN1N4O, quantity=5
2026-09-01T06:15:31.014864+00:00  GetCartAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb
2026-09-01T06:15:31.028898+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=6E92ZMYYFZ, quantity=1
```

> Evidence `tr_e1ff0d09fc2d`:

```
<tool_result id="tr_e1ff0d09fc2d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T06:15:30.965909+00:00  GetCartAsync called with userId=
2026-09-01T06:15:31.012812+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=1YMWWN1N4O, quantity=5
2026-09-01T06:15:31.014864+00:00  GetCartAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb
2026-09-01T06:15:31.028898+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=6E92ZMYYFZ, quantity=1
```

## Traces gave the answer

The trace query is what broke the case open, and it should be the first stop next time. Two hundred spans came back, spread across many trace ids and covering GetCart, AddItem, and EmptyCart. Not one of them carried an error status. Every cart operation ran to completion.

The durations were the signal. GetCart and EmptyCart server spans sat at roughly 300ms each. AddItem sat at roughly 600ms, and its cost decomposed cleanly into two sequential ~300ms segments. Opening those spans showed cartservice's own cache client spans — HGET and HMSET — each consuming 300 to 309ms and accounting for essentially the entire duration of the enclosing span. One representative AddItem: 605ms total, of which ~301ms was HGET and ~304ms was HMSET. Almost no self-time was left for application work, which rules out cartservice being CPU-bound or blocked on anything other than its cache.

The propagation is straightforward arithmetic. Frontend cart GET requests measured ~306ms and cart POST requests ~910ms — the frontend adds only a handful of milliseconds over its cart child. Checkout PlaceOrder measured ~660–680ms, dominated by two cartservice calls (GetCart ~310ms, EmptyCart ~301ms).

> Evidence `tr_8a248dc689c1`:

```
<tool_result id="tr_8a248dc689c1" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
service: cartservice
200 spans
  acada018ad1ce1ec frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.7ms
  acada018ad1ce1ec frauddetectionservice/orders process 0.2ms
  acada018ad1ce1ec frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.1ms
```

## Downstreams the traces cleared

The same trace pull was enough to eliminate every other plausible culprit in the path, and this is the part worth reading if you find yourself tempted to chase them again.

productcatalogservice GetProduct server spans measured ~0.0ms, with caller-side spans between 0.6 and 2.7ms — three orders of magnitude below the cart spans. shippingservice GetQuote, including its quoteservice call, ran ~17–21ms; ShipOrder ran ~0.0–1.6ms. emailservice order-confirmation calls ranged ~3.9–30.7ms, a small slice of a 660ms PlaceOrder. Currency Convert came in at ~0.0–3.8ms, Payment Charge at ~0.1–3.2ms, and fraud/accounting message processing at ~0.0–0.2ms. adservice and recommendationservice appeared nowhere in these traces at all — the cart and checkout paths never touch them.

A separate change-log query against productcatalogservice returned nothing for the window, closing that thread from a second angle, though it only covered that one service and only the last fifteen minutes of the broader period of interest.

> Evidence `tr_8a248dc689c1`:

```
<tool_result id="tr_8a248dc689c1" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
service: cartservice
200 spans
  acada018ad1ce1ec frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.7ms
  acada018ad1ce1ec frauddetectionservice/orders process 0.2ms
  acada018ad1ce1ec frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.1ms
```

> Evidence `tr_3c982f5d9127`:

```
<tool_result id="tr_3c982f5d9127" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_3c982f5d9127>
```

## Frontend errors: flat zero, and why that mattered

A frontend error-ratio query returned a defined value at all sixty-one sample points, and every one of them was zero. This matters for two reasons.

First, it confirms the incident is not an error-rate event. No downstream failure was surfacing as failed spans on frontend — any cart-side problem was being absorbed or was manifesting purely as latency. Second, the fact that all sixty-one points were defined rather than missing means the denominator was populated throughout, so frontend was genuinely serving traffic. A total outage would have produced gaps, not zeros.

The limitation: that series was aggregated by service name only, with no per-downstream breakdown, so it says nothing about request rate, latency percentiles, or the specific cart call path.

> Evidence `tr_1c6bbccf1bb9`:

```
<tool_result id="tr_1c6bbccf1bb9" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_1c6bbccf1bb9>
```

## Looking for the change

With the mechanism identified, the obvious next question was what altered cartservice's cache behaviour. The change log for cartservice — covering deployments, config edits, and feature-flag flips, and scoped to include cache and datastore backing components — returned nothing at all.

That empty result does real work. It excludes a deploy landing immediately before onset, a flag or config toggle coinciding with onset, an in-flight rollout still progressing during the incident, and a backing-store change landing alongside a service change. All four are closed for the interval queried.

The caveat is the interval itself. The query spanned roughly fifteen minutes, from about ten minutes before onset to five minutes after. The preceding fifty minutes were never examined. An edit made earlier that only began to manifest at onset is not excluded by this evidence.

> Evidence `tr_644656977e91`:

```
<tool_result id="tr_644656977e91" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_644656977e91>
```

## Where it landed

cartservice is slow, not failing. Every cartservice server span is consumed almost entirely by its own cache client operations, at a near-constant ~300ms per HGET or HMSET. That cost is deterministic enough per operation to look configured rather than organic — real contention or saturation tends to produce a spread of durations, not a repeated flat value. The remedy class is therefore a config revert on the cache path.

Confidence is medium, and the reason for the hedge is that the change record needed to confirm this was never found within the window queried.

> Evidence `tr_8a248dc689c1`:

```
<tool_result id="tr_8a248dc689c1" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
service: cartservice
200 spans
  acada018ad1ce1ec frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.7ms
  acada018ad1ce1ec frauddetectionservice/orders process 0.2ms
  acada018ad1ce1ec frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.1ms
```

> Evidence `tr_644656977e91`:

```
<tool_result id="tr_644656977e91" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_644656977e91>
```

## Left open for the next responder

Three things were never resolved and are worth picking up first if this recurs.

The cache backend itself was never queried directly. Nobody dispatched on the Redis-side metrics, so saturation, network path between cartservice and the cache, and a deliberately configured delay are all still live possibilities. The trace evidence points at the cache but does not distinguish between them.

Change coverage stops short. Nothing before the ten-minute pre-onset mark was examined. An earlier edit with a delayed effect remains a viable explanation.

The onset region itself was never sampled in logs. Both log attempts truncated it away, and the cartservice saturation and call metrics returned no series. If you can get level-filtered logs for the three minutes around onset, that is the single highest-value missing piece.

> Evidence `tr_006d4ad454d0`:

```
<tool_result id="tr_006d4ad454d0" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_006d4ad454d0>
```

> Evidence `tr_f2f149819e65`:

```
<tool_result id="tr_f2f149819e65" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T06:15:30.965909+00:00  GetCartAsync called with userId=
2026-09-01T06:15:31.012812+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=1YMWWN1N4O, quantity=5
2026-09-01T06:15:31.014864+00:00  GetCartAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb
2026-09-01T06:15:31.028898+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=6E92ZMYYFZ, quantity=1
```

> Evidence `tr_e1ff0d09fc2d`:

```
<tool_result id="tr_e1ff0d09fc2d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-01T06:15:30.965909+00:00  GetCartAsync called with userId=
2026-09-01T06:15:31.012812+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=1YMWWN1N4O, quantity=5
2026-09-01T06:15:31.014864+00:00  GetCartAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb
2026-09-01T06:15:31.028898+00:00  AddItemAsync called with userId=88a97458-a5cc-11f1-ae7b-9eef0fcf8acb, productId=6E92ZMYYFZ, quantity=1
```

> Evidence `tr_644656977e91`:

```
<tool_result id="tr_644656977e91" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T06:15:30.583000+00:00..2026-09-01T06:30:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_644656977e91>
```
