# Checkout order placement broken by a stale shipping quote-backend address

## What was visible first

The page arrived as critical and wide: fourteen services touched, alerts on checkout, loadgenerator, frontend, accounting, email, frauddetection and quoteservice, with five uninstrumented edges in the path. Seed was checkoutservice, so it looked like a checkout regression rippling outward.

Checkout's logs gave the first real shape. Early in the window every order produced a full pipeline: order start, payment authorization, confirmation email, message write with advancing offset. In the final minutes only order-start lines remained, while requests kept arriving every few seconds. Orders entered and never completed, and checkout logged no error of its own at any severity. Both USD and CAD orders stalled, so it was not currency-scoped. The break sat at or before payment, since even the payment-success line was gone.

> Evidence `tr_5e4527a04081`:

```
<tool_result id="tr_5e4527a04081" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T09:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T09:32:36.125900+00:00  {"message":"[PlaceOrder] user_id=\"64469fc6-ac31-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T09:32:36.125815128Z"}
2026-09-09T09:32:36.144637+00:00  {"message":"payment went through (transaction_id: 13ef8ddb-c06a-4eac-af03-7d2f3589191b)","severity":"info","timestamp":"2026-09-09T09:32:36.144567795Z"}
2026-09-09T09:32:36.148834+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-09T09:32:36.148757337Z"}
2026-09-09T09:32:36.150097+00:00  {"message":"Successful to write message. offset: 21377","severity":"info","timestamp":"2026-09-09T09:32:36.149942587Z"}
```

## Two dead ends worth keeping

Checkout as origin. Its 24h change log was empty — no deploys, config edits or flag flips — which also removed the convenient remedy of rolling back the last release. That query was scoped to the seed service only, zero hops, so its emptiness said nothing about neighbours; reading it as "nothing changed anywhere" would have cost hours. Checkout's error ratio was actively misleading: mean roughly 2.5x *below* the preceding hour, no sustained departure, populated denominator throughout. That excluded checkout as an error-emitting culprit and excluded an outage, but not a dependency problem absorbed as latency or a non-propagating error. No latency series and no per-dependency breakdown were returned at all.

Cartservice's noisy log. One hop out, cart showed 24 automated entries in 24h as repeated set-then-revert cycles: hotfix image, a traffic-shaping sidecar with fixed egress delay, a Redis address override. Loud, recurring, and irrelevant — the nearest change was ~1.6h before onset and every override in the last cycle was already reverted. At onset cart was baseline everything.

> Evidence `tr_2af50a49a8d3`:

```
<tool_result id="tr_2af50a49a8d3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T10:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_2af50a49a8d3>
```

> Evidence `tr_da783d30949b`:

```
<tool_result id="tr_da783d30949b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T09:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00" template="error-ratio" baseline="2026-09-09T08:27:39.540109+00:00..2026-09-09T09:32:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=260 mean=0.02873 min=0 max=0.2667 sd=0.07144
  baseline window: n=260 mean=0.07191 min=0 max=0.6667 sd=0.1986
```

> Evidence `tr_fa6b3dffc9d2`:

```
<tool_result id="tr_fa6b3dffc9d2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T10:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00" radius="candidate_cause" hops="1">
service: cartservice
24 changes, ranked by suspicion
  #1  1.6h before onset  2026-09-09T08:55:27.921065+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.8h before onset  2026-09-09T08:47:28.922734+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Where it actually was, and what stayed open

Ten sampled failing traces were structurally identical: frontend POST, frontend PlaceOrder and checkout PlaceOrder all ERROR, with the sole erroring child being checkout's client span for the shipping GetQuote call from prepareOrderItemsAndShippingQuoteFromCart. That cleared currencyservice (present, sub-millisecond, error-free), cart/Redis, catalogue and flags, and payment (no payment span anywhere in 162 spans). Shipping meanwhile kept accepting quote requests at baseline rate from the same generator, logging only INFO, but the quote-value, ship-order and tracking-ID lines that followed every baseline request never appeared. Shipping's error-ratio series returned no samples across both baseline and incident windows — an absence pre-dating onset by hours, so a collection gap, not a symptom, and not a flat zero.

The cause: about two minutes before onset, platform-automation set shipping's quote-backend address to a non-existent host. The same edit had been applied and reverted three times earlier in the same 24h window; this one was never reverted. Shipping cannot reach the backend it is told to call, so no quote is produced and checkout's client call fails during order preparation. Fix class: config revert. Confidence high.

Open items. Traces show a ~3ms fast failure with no deadline signature while shipping's logs suggest a hung outbound call — the same hop read two incompatible ways, unreconciled. Shipping's server span is non-error while checkout's client span errors, so a checkout-side response-handling or validation failure is not directly excluded, and there is no server-side call series to settle it. Both log queries were truncated around onset (oldest 8, newest 32 lines), so the transition itself was inferred; and the set-then-revert automation may re-apply the bad value unless paused.

> Evidence `tr_699e2f62b4f8`:

```
<tool_result id="tr_699e2f62b4f8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T09:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace f10e934369a73b8e  root frontend/HTTP POST  11.1ms  started 2026-09-09T10:35:49.127013+00:00  18 spans
  +0.0ms frontend/HTTP POST 11.1ms [self 0.7ms]  ERROR
```

> Evidence `tr_0cba20e388e0`:

```
<tool_result id="tr_0cba20e388e0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-09T08:32:34.005924+00:00  08:32:34 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-198f0fd7251f82c7d77059d7ee19a438-7e2ae541fe40dc2c-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }] }, extensions: Extensions }
2026-09-09T08:32:34.026740+00:00  08:32:34 [INFO] Sending Quote: 44.50
2026-09-09T08:32:34.034346+00:00  08:32:34 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-198f0fd7251f82c7d77059d7ee19a438-f8d498ef8e828440-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }] }, extensions: Extensions }
2026-09-09T08:32:34.034358+00:00  08:32:34 [INFO] Tracking ID Created: 521669ae-8f73-458a-ae8d-c29b69f992bd
```

> Evidence `tr_741f1f235fbb`:

```
<tool_result id="tr_741f1f235fbb" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T10:32:30.583000+00:00..2026-09-09T10:37:21.625891+00:00" radius="also_affected" hops="1">
service: shippingservice
13 changes, ranked by suspicion
  #1  2m before onset  2026-09-09T10:29:46.326449+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
  #2  4.9h before onset  2026-09-09T05:37:36.479019+00:00  platform-automation  image reverted: image reference reverted on shippingservice
```

