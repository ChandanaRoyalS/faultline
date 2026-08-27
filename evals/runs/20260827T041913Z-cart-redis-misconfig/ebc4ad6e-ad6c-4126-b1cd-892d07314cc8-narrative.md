# Checkout failures traced to a cart backend address pointing at a dead port

## What was visible, in order

The page arrived from three places at once: frontend and loadgenerator at T+0 (04:22), checkoutservice about fifteen seconds later. The shape was a partial break, not an outage. Frontend's error ratio climbed from a clean zero baseline to a peak near 31%; roughly two thirds of traffic still completed. checkoutservice's own ratio moved harder, topping out around 0.67. Both series were densely populated, so the theory that telemetry had simply gone missing died immediately, as did the idea that this was a pure slowdown with no error component.

Note for the next responder: the metric queries as executed covered only 04:12-04:27. The wider hour that was asked for, plus latency percentiles and saturation signals, were never actually returned. Nothing in the conclusion rests on them, but do not read the record as if they were checked.

> Evidence `tr_01c987ecc565`:

```
<tool_result id="tr_01c987ecc565" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3088 n=57
</tool_result:tr_01c987ecc565>
```

> Evidence `tr_39c88823fcba`:

```
<tool_result id="tr_39c88823fcba" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=58
</tool_result:tr_39c88823fcba>
```

## Two dead ends worth keeping

The obvious opening move was to check whether checkoutservice had just been touched. It had not: the change log across 04:12-04:27 came back completely empty, with ten minutes of margin on either side of onset. That cost a few minutes and produced nothing to roll back, but it closed off the comfortable "bad release on the owning service" path and forced the search outward.

checkoutservice's own logs were close to useless for attribution. Every line returned carried info severity: no error or warning lines, no exception type names, no downstream service named. A service failing on an outbound call was saying nothing about it. That gap is worth a follow-up ticket on its own. The logs did set boundaries: around 04:12 orders completed the full pipeline (payment with transaction id, confirmation email, message write with incrementing offset), while from roughly 04:20:43 to 04:24:53 only order-start lines appeared at a steady cadence. So the process was alive and accepting work, orders were beginning but not finishing, and the break did not predate the window. The middle of the log window was truncated, so the exact transition cannot be dated from logs.

> Evidence `tr_3812dbe219c3`:

```
<tool_result id="tr_3812dbe219c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_3812dbe219c3>
```

> Evidence `tr_d62763c38653`:

```
<tool_result id="tr_d62763c38653" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T04:12:41.652996+00:00  {"message":"[PlaceOrder] user_id=\"8c1ac798-a1cd-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T04:12:41.652858097Z"}
2026-08-27T04:12:41.672114+00:00  {"message":"payment went through (transaction_id: adf2fde9-04a5-46cd-8e7d-1015131dfcc1)","severity":"info","timestamp":"2026-08-27T04:12:41.672029972Z"}
2026-08-27T04:12:41.677628+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-27T04:12:41.677455291Z"}
2026-08-27T04:12:41.678248+00:00  {"message":"Successful to write message. offset: 15577","severity":"info","timestamp":"2026-08-27T04:12:41.678156083Z"}
```

## Where it actually was, and what is still open

Traces cut the space. Every failing checkout trace had the same chain: frontend HTTP POST, frontend gRPC PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, ending at checkoutservice's outbound CartService/GetCart client span, the deepest span in error. The enclosing assembly span was not in error and frontend spans were strictly ancestors, so both were propagating. No cartservice server span and no Redis span appeared beneath the failing calls, unlike the one successful trace which shows both. Failing traces ran 1-3ms end to end with sub-millisecond leaf spans, so this was fast-fail at connection establishment, not a timeout in the fan-out, and payment, shipping, currency, email and product catalog were never reached.

cartservice metrics returned no series at all: both numerator and denominator empty, the ratio undefined rather than elevated, which also excludes partial replica degradation. Logs settled it. Normal cart reads and writes through about 04:12:10; by 04:23:20 a tight crash-restart loop, each cycle logging a Redis connect attempt, a failure after 25-40s, an unhandled ApplicationException and a stack trace ending at the process entrypoint. The failure is in startup initialization of the Redis-backed cart store called from Main, before any request is served, and it repeats at least six times between 04:23 and 04:26. The target logged every time is redis-cart on port 6380; the conventional port is 6379. That also disposed of TLS/auth (TLS disabled, failure at connect), bad-input panics, any non-Redis dependency, and any transient blip.

The cause: at 04:19:13 UTC a platform-automation principal ran an environment update on cartservice setting the Redis backend address to port 6380. It is the only cartservice entry in the window, a configuration mutation rather than a deploy, image rollout or flag flip, pushed by a pipeline rather than a human console edit. The value takes effect on restart and the service cannot start. Fix class: revert the configuration.

Still open, and important. Nobody queried the Redis side at all, so we cannot say whether 6380 is a typo for 6379 or whether this was a real migration whose listener never landed. The change record shows no prior value, so the exact state to revert to must be read from the deployment manifest or the pipeline. The three-minute gap between the 04:19:13 write and the 04:22 alert is unexplained; no pod or replica event data was gathered. Twelve services were in the blast radius but only frontend, checkoutservice and cartservice were examined, so other cart-dependent surfaces and any unrelated degradation went unchecked. Finally, whether the same automation pushed this variable to other services or environments was never queried.

> Evidence `tr_c2ed8108ce8a`:

```
<tool_result id="tr_c2ed8108ce8a" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00">
service: checkoutservice
200 spans
  b6f90e5c8ab41371 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
  b6f90e5c8ab41371 checkoutservice/hipstershop.CurrencyService/Convert 1.3ms
  b6f90e5c8ab41371 currencyservice/CurrencyService/Convert 0.0ms
```

> Evidence `tr_ef8759fc9086`:

```
<tool_result id="tr_ef8759fc9086" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T04:12:00.600580+00:00  GetCartAsync called with userId=
2026-08-27T04:12:02.988317+00:00  GetCartAsync called with userId=
2026-08-27T04:12:05.515734+00:00  GetCartAsync called with userId=
2026-08-27T04:12:06.828398+00:00  GetCartAsync called with userId=
```

> Evidence `tr_d1cc26cefb81`:

```
<tool_result id="tr_d1cc26cefb81" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T04:12:00.583000+00:00..2026-08-27T04:27:00.583000+00:00">
service: cartservice
1 changes
  2026-08-27T04:19:13.900377+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_d1cc26cefb81>
```
