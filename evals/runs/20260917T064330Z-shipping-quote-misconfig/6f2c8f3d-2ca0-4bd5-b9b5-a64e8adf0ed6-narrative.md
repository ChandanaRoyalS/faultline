# Checkout PlaceOrder failures traced to a shipping quote address pointing at a non-existent host

## What was visible, in order

Offsets are relative to T+0, the moment platform-automation applied an environment change to shippingservice.

The entry point was checkoutservice's error ratio. It stepped up abruptly at about T+38s, rising roughly six-fold against the preceding baseline (mean ~0.9% to ~5.2%, peak near 32%). The change-point detection found a single step, not a ramp, which immediately killed the slow-resource-consumption story. The window minimum stayed at zero and the standard deviation was twice the mean, so checkout kept serving successful requests throughout — not a crash, not a total outage. No latency, request-rate, CPU, memory or pool series came back at all, so the question of whether checkout got slower was left open here.

Checkout's logs showed the shape. Early in the window every order produced a complete chain: order-placement entry, payment confirmation with a transaction id, confirmation email, successful message write. Late in the window only the order-placement entries survive; payment, email and message-write lines are gone, while entry lines keep arriving at a steady cadence to the end. Process alive, requests entering, nothing completing. Note that the retrieval returned only the oldest 8 and newest 32 lines, so the minutes around onset are simply absent — read nothing into that gap. Every returned line was info severity and none named a downstream call; checkout failed silently from its own logs' point of view.

Ten sampled traces from ~T+6m onward fail identically: the root frontend POST, the frontend-to-checkout PlaceOrder call, the checkout PlaceOrder span, and checkout's client span for ShippingService/GetQuote are all ERROR, with GetQuote flagged as the degrading hop every time. The shippingservice server span is not marked ERROR and completes in ~2ms, nearly all of it inside its outbound HTTP client child. End-to-end roots run under 14ms, so this is a failure signature and not a latency regression.

> Evidence `tr_89b826922c52`:

```
<tool_result id="tr_89b826922c52" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T06:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" template="error-ratio" baseline="2026-09-17T05:40:28.777094+00:00..2026-09-17T06:16:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=143 mean=0.05236 min=0 max=0.3158 sd=0.1045
  baseline window: n=143 mean=0.008847 min=0 max=0.0597 sd=0.01616
```

> Evidence `tr_2fc1e2471d5a`:

```
<tool_result id="tr_2fc1e2471d5a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T06:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T06:16:03.870583+00:00  {"message":"[PlaceOrder] user_id=\"42d81584-b25f-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T06:16:03.870405466Z"}
2026-09-17T06:16:03.889494+00:00  {"message":"payment went through (transaction_id: a6b085d8-cfa8-4d4a-b1be-e3bd7f15c71d)","severity":"info","timestamp":"2026-09-17T06:16:03.889400632Z"}
2026-09-17T06:16:03.894701+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T06:16:03.894555799Z"}
2026-09-17T06:16:03.895629+00:00  {"message":"Successful to write message. offset: 61966","severity":"info","timestamp":"2026-09-17T06:16:03.895541091Z"}
```

> Evidence `tr_3baf6f0e3276`:

```
<tool_result id="tr_3baf6f0e3276" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T06:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace 24efede126282ac3  root frontend/HTTP POST  10.5ms  started 2026-09-17T06:50:08.070018+00:00  14 spans
  +0.0ms frontend/HTTP POST 10.5ms [self 0.2ms]  ERROR
```

## Dead ends worth keeping

Looking for a change on checkoutservice returned an empty set, and the emptiness was nearly useless. The query covered only the seed service at zero hops, so checkout's dependencies were never searched, and its window began at the alert timestamp and ran forward a day — never touching the minutes before onset, which is exactly where the answer was. Treat this as a scoping lesson, not a finding.

The traces retired five candidates permanently. paymentservice appears in no trace at all — checkout aborts before reaching it. cartservice and its Redis lookup run in fractions of a millisecond, clean. currencyservice Convert spans register effectively zero. productcatalogservice including its flag lookup is sub-millisecond and clean. adservice and recommendationservice appear nowhere in the 162 spans examined. Do not re-walk these.

Shipping's error-ratio metric returned no samples in the incident window — and none in the preceding baseline hour either. That symmetry is the point: the series is absent on both sides, so this is missing or differently-labelled instrumentation, not telemetry that died at onset. It cannot time shipping's onset in either direction. Shipping's logs likewise name no outbound call, no target host, no status code and no timeout; the service fails mute. Its logs did rule out a crashed pod, malformed inbound requests, and wrong-value quotes: inbound gRPC keeps landing with ordinary payloads, and the quote-computed completion lines simply stop appearing after the healthy stretch.

> Evidence `tr_8962b4d9d9e5`:

```
<tool_result id="tr_8962b4d9d9e5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T06:46:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_8962b4d9d9e5>
```

> Evidence `tr_3baf6f0e3276`:

```
<tool_result id="tr_3baf6f0e3276" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T06:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace 24efede126282ac3  root frontend/HTTP POST  10.5ms  started 2026-09-17T06:50:08.070018+00:00  14 spans
  +0.0ms frontend/HTTP POST 10.5ms [self 0.2ms]  ERROR
```

> Evidence `tr_afa4f9e81b06`:

```
<tool_result id="tr_afa4f9e81b06" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T05:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" template="error-ratio" baseline="2026-09-17T03:40:28.777094+00:00..2026-09-17T05:16:00.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_857b37d1d57b`:

```
<tool_result id="tr_857b37d1d57b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T05:16:09.469702+00:00  05:16:09 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-6a52463f1b7dab11bc35159ab5b60425-a2debf913c644b27-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "2200 Mission College Blvd", city: "Santa Clara", state: "CA", country: "United States", zip_code: "95054" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "66VCHSJNUP", quantity: 10 }, CartItem { product_id: "1YMWWN1N4O", quantity: 4 }] }, extensions: Extensions }
2026-09-17T05:16:09.476921+00:00  05:16:09 [INFO] Sending Quote: 151.30
2026-09-17T05:16:09.480223+00:00  05:16:09 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-6a52463f1b7dab11bc35159ab5b60425-2fee7c58537c86b8-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "2200 Mission College Blvd", city: "Santa Clara", state: "CA", country: "United States", zip_code: "95054" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "66VCHSJNUP", quantity: 10 }, CartItem { product_id: "1YMWWN1N4O", quantity: 4 }] }, extensions: Extensions }
2026-09-17T05:16:09.480228+00:00  05:16:09 [INFO] Tracking ID Created: 598b0b20-7b6e-45a0-bc06-0333e0d101b4
```

## What closed it, and what is still open

quoteservice logged steady HTTP 200s for POST /getquote from a single upstream client every few seconds, then nothing after T-7s. Because the retrieval preserved the newest lines, that silence is a genuine gap rather than a truncation artifact — verify that reasoning before leaning on it, as it is load-bearing. The silence ruled out quoteservice rejecting calls, serving them normally, degrading gradually, or throwing internally: the failure is absence of request handling.

The change history for shippingservice held exactly one entry in the window: platform-automation set QUOTE_SERVICE_ADDR to an address naming a host that does not exist, where the variable had previously been unset and shipping resolved a working default. Machine-applied, not a deploy, not a flag flip, and no adjacent-service change on record. From that point shipping aimed its quote lookup at nothing; checkout calls GetQuote inside prepareOrderItemsAndShippingQuoteFromCart, so PlaceOrder aborts there and payment, email and message-write are never reached. Confidence high; fix class is reverting the configuration value.

Three things remain unresolved. Checkout's error ratio averages ~5% with a 32% peak while every sampled trace fails identically — partial rollout, a fallback path, or sampling bias, unknown. No shipping log or metric names the outbound call, target host, resolution failure or status code, so the link from the variable to the failure is inferential. And the change search on checkout never covered pre-onset time or dependencies, so that ground is genuinely unexamined rather than clean.

> Evidence `tr_c3765ab8ae2c`:

```
<tool_result id="tr_c3765ab8ae2c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" oldest_kept="8" newest_kept="32">
selector: {service="quoteservice"}
2026-09-17T05:16:09.476794+00:00  172.18.0.7 - - [17/Sep/2026:05:16:09 +0000] "POST /getquote HTTP/1.1" 200 170 "-" "-"
2026-09-17T05:16:10.586379+00:00  172.18.0.7 - - [17/Sep/2026:05:16:10 +0000] "POST /getquote HTTP/1.1" 200 170 "-" "-"
2026-09-17T05:16:12.039934+00:00  172.18.0.7 - - [17/Sep/2026:05:16:12 +0000] "POST /getquote HTTP/1.1" 200 183 "-" "-"
2026-09-17T05:16:25.554935+00:00  172.18.0.7 - - [17/Sep/2026:05:16:25 +0000] "POST /getquote HTTP/1.1" 200 184 "-" "-"
```

> Evidence `tr_4ca845522927`:

```
<tool_result id="tr_4ca845522927" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T06:46:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" radius="also_affected" hops="1">
service: shippingservice
1 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T06:43:37.316183+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
</tool_result:tr_4ca845522927>
```

> Evidence `tr_afa4f9e81b06`:

```
<tool_result id="tr_afa4f9e81b06" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T05:16:00.583000+00:00..2026-09-17T06:51:32.388906+00:00" template="error-ratio" baseline="2026-09-17T03:40:28.777094+00:00..2026-09-17T05:16:00.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

