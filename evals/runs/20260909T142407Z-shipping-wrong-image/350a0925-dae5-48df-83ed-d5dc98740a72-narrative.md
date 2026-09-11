# Checkout order failures traced to the shipping quote hop

## What was visible, in order

The page came from checkoutservice and the loadgenerator; nothing else in a ten-service radius alerted. The error ratio told an awkward story: roughly 11.8% during the window against about 1.0% baseline, peaking near 28% — an order-of-magnitude jump, but not an outage, and the baseline was never clean (it already showed excursions to ~8.6%). More important was the timing: the alert timestamp was not the onset. The earliest threshold crossing sat about 23 minutes earlier, a second crossing came later, and between them the ratio fell back under threshold. Two crossings, not one clean step. That shape is what made this a two-phase incident, and it is where a responder anchoring on the paging time will lose an hour.

Checkoutservice logs came back truncated by design — oldest few lines, newest few dozen, middle discarded — so they could not speak to the alert minute at all. What they gave was shape: early orders produced a full four-step sequence (order start, payment, confirmation email, message write), while every retained late line was an order-start with nothing after it. Orders kept arriving steadily and the process stayed alive and logging, so 'traffic stopped upstream' and 'the pod died' were both out. No error line, no downstream name, no status code, no config value appeared anywhere — checkoutservice never names its own failing dependency here. A currency-specific theory died too: stalled orders spanned USD and CAD.

> Evidence `tr_c23b2d629e51`:

```
<tool_result id="tr_c23b2d629e51" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T13:56:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" template="error-ratio" baseline="2026-09-09T13:23:20.114264+00:00..2026-09-09T13:56:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=134 mean=0.1177 min=0 max=0.28 sd=0.1212
  baseline window: n=134 mean=0.01005 min=0 max=0.08602 sd=0.0201
```

> Evidence `tr_119f459f6067`:

```
<tool_result id="tr_119f459f6067" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T13:56:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T13:56:46.871642+00:00  {"message":"[PlaceOrder] user_id=\"4c095802-ac56-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T13:56:46.87155105Z"}
2026-09-09T13:56:46.889155+00:00  {"message":"payment went through (transaction_id: cd0070c9-d8a5-4d3e-b9f7-2c58a7e013b9)","severity":"info","timestamp":"2026-09-09T13:56:46.889083967Z"}
2026-09-09T13:56:46.893736+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-09T13:56:46.893655758Z"}
2026-09-09T13:56:46.894607+00:00  {"message":"Successful to write message. offset: 23317","severity":"info","timestamp":"2026-09-09T13:56:46.894510467Z"}
```

## Dead ends worth keeping

Change history on checkoutservice returned nothing at all — no deploys, config edits, or flag flips. Narrowly useful: nothing was landing on checkoutservice to sustain or re-trigger the incident, and no unlogged revert explained any recovery. The service is tracked (well-formed empty answer, not an unknown-service error). The trap: the window began at the alert timestamp and ran forward 24 hours, so the hours *before* the alert were never covered and the original question was never actually answered.

The cartservice error-ratio query returned no samples in either the incident or the baseline window. Because both were equally empty, the gap predates the incident and is almost certainly a label or scrape-coverage problem, not a signal. It was briefly read as 'the dependencies are flat, so the problem is internal to checkoutservice' — it supports neither claim. An empty series cannot show flatness, and the query only ever covered cartservice; productcatalog, email, and shipping were untouched by it.

The biggest dead end was in the change log. At 14:02:13 an environment variable pointed the quote dependency at a host name that reads as non-existent, about 77 seconds before the 14:03:30 onset — excellent correlation. But it was reverted at 14:13:37, bounding exposure to roughly 14:02–14:14, while traces were still failing at 14:29–14:30. It explains the first crossing and nothing after it.

> Evidence `tr_2d896171db16`:

```
<tool_result id="tr_2d896171db16" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T14:26:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_2d896171db16>
```

> Evidence `tr_81279db57104`:

```
<tool_result id="tr_81279db57104" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T13:56:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" template="error-ratio" baseline="2026-09-09T13:23:20.114264+00:00..2026-09-09T13:56:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_625b05302b69`:

```
<tool_result id="tr_625b05302b69" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T14:26:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" radius="candidate_cause" hops="1">
service: shippingservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-09T14:24:15.309722+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-09T14:13:37.036240+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

## What resolved it, and confidence

Traces settled the question. Ten sampled PlaceOrder traces all failed, and in every one the only erroring downstream call was the checkoutservice client span for ShippingService/GetQuote from prepareOrderItemsAndShippingQuoteFromCart; the error propagated up through the frontend root, which is why checkoutservice paged. Two details narrowed the mechanism: the failing spans were fast (0.4–2.5ms inside 6–11ms requests), ruling out a hang or deadline; and no server-side shippingservice span appeared beneath them, while cart, productcatalog, and currency siblings all showed their callee spans and returned OK. Fast error plus absent callee span is a call rejected at connect. Payment and email spans were absent entirely — never reached, because the order aborts in the prepare/quote phase. Checkoutservice self-times were 0.1–0.9ms, so it was not the culprit.

Shipping's own logs showed a healthy server early (paired quote and ship-order calls, prices, tracking IDs), then in the newest portion only JVM and OpenTelemetry Java agent startup lines repeating every 30–60 seconds, with no request handling. The change log supplies the join: an image reference update at 14:24:15 moved shippingservice to a demo tag whose name denotes adservice. The wrong artifact runs under the shippingservice identity, so its gRPC port never serves GetQuote — matching the 14:25:30 re-crossing and the startup loop. Fix class: rollback.

Confidence medium. Still open: the error ratio between 14:13:37 and 14:24:15 (recovery there confirms two phases; none admits one sustained cause); both log queries were truncated, leaving 14:03–14:24 unobserved and no gRPC status code retrieved; whether the late JVM lines truly belong to shippingservice, rated low confidence and the weakest link; and whether the automation's 4–5 hour cycle (19:49, 23:37, 05:14, 10:29, 14:02) will revert the image on its own — a manual rollback may simply be undone.

> Evidence `tr_07ea98356fa4`:

```
<tool_result id="tr_07ea98356fa4" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T12:56:45.583000+00:00..2026-09-09T14:30:11.051736+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 138 spans; offsets are from each trace's root

trace c812f57c6871f769  root frontend/HTTP POST  7.9ms  started 2026-09-09T14:29:35.155016+00:00  12 spans
  +0.0ms frontend/HTTP POST 7.9ms [self 0.2ms]  ERROR
```

> Evidence `tr_e151438f74bf`:

```
<tool_result id="tr_e151438f74bf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T13:56:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-09T13:56:46.879348+00:00  13:56:46 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-2ef2dc50c84483c008d9a7dc046f1189-2323f314a9d8e9fa-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "410 Terry Ave N", city: "Seattle", state: "WA", country: "United States", zip_code: "98109" }), items: [CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "L9ECAV7KIM", quantity: 3 }, CartItem { product_id: "1YMWWN1N4O", quantity: 1 }, CartItem { product_id: "OLJCESPC7Z", quantity: 4 }] }, extensions: Extensions }
2026-09-09T13:56:46.886517+00:00  13:56:46 [INFO] Sending Quote: 115.70
2026-09-09T13:56:46.889817+00:00  13:56:46 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-2ef2dc50c84483c008d9a7dc046f1189-cb609781e884f95a-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "410 Terry Ave N", city: "Seattle", state: "WA", country: "United States", zip_code: "98109" }), items: [CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "L9ECAV7KIM", quantity: 3 }, CartItem { product_id: "1YMWWN1N4O", quantity: 1 }, CartItem { product_id: "OLJCESPC7Z", quantity: 4 }] }, extensions: Extensions }
2026-09-09T13:56:46.889824+00:00  13:56:46 [INFO] Tracking ID Created: 25677209-deaf-4850-93d8-66770a140a8e
```

> Evidence `tr_625b05302b69`:

```
<tool_result id="tr_625b05302b69" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T14:26:45.583000+00:00..2026-09-09T14:30:11.051736+00:00" radius="candidate_cause" hops="1">
service: shippingservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-09T14:24:15.309722+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-09T14:13:37.036240+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

