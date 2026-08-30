# Checkout aborts at the shipping quote boundary after an automated config update

## What was visible, in order

Alerts land on checkoutservice, frontend, and loadgenerator — the outer two because they are what notice, not because they are broken. The first real signal is checkoutservice's span error ratio: an intermittent band from zero to roughly three failures in ten calls across 61 sample points. That partial ratio shaped the first stretch of triage and invited a search for something flaky. It did usefully exclude both a healthy checkoutservice and a hard-down one. Requested latency percentiles and per-downstream breakdown never came back.

Checkoutservice logs were all INFO — no exceptions, no named downstream error — and truncated by design to the oldest 8 and newest 32 lines, discarding roughly T-10m to T+0. What survived was still decisive if read structurally: early in the window each order-placement start line is followed within tens of milliseconds by payment confirmation, confirmation email, and a successful message write. From T+0 to T+3m only the start lines remain, at a steady few per minute. The process is up and receiving work; the completions are simply absent rather than logged as failures. That excluded a crash, excluded upstream traffic collapse, and excluded any single-user or single-currency theory — distinct users, both USD and CAD, none completing.

> Evidence `tr_62e1cffccb80`:

```
<tool_result id="tr_62e1cffccb80" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.3 n=61
</tool_result:tr_62e1cffccb80>
```

> Evidence `tr_02e778da6175`:

```
<tool_result id="tr_02e778da6175" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-29T20:22:06.582804+00:00  {"message":"[PlaceOrder] user_id=\"4def1e6c-a3e7-11f1-8c4e-9e12df7a2593\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-29T20:22:06.582668513Z"}
2026-08-29T20:22:06.601144+00:00  {"message":"payment went through (transaction_id: 085ed30d-4603-47cf-b34f-29e397f2f73c)","severity":"info","timestamp":"2026-08-29T20:22:06.601037805Z"}
2026-08-29T20:22:06.608301+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-08-29T20:22:06.608188013Z"}
2026-08-29T20:22:06.608774+00:00  {"message":"Successful to write message. offset: 21389","severity":"info","timestamp":"2026-08-29T20:22:06.608701097Z"}
```

## Dead ends worth keeping

Change history on checkoutservice returned empty. Read the second finding before trusting the first: the query covered only about fifteen minutes around onset, not the two-hour lookback requested. A re-dispatch executed against the identical window and returned the identical empty result — confirming the first query was not mis-scoped by accident, but extending nothing. Roughly 18:32 to 20:22 is still dark. Within the covered band the negatives hold: nothing deployed to checkoutservice before onset, nothing flipped at the onset minute, no post-onset remediation to explain the tail.

A parallel change query on productcatalogservice also came back empty, and covered only that one service. Cartservice and the other synchronous dependencies were never checked for change history at all.

Traces then closed several doors permanently. Cartservice GetCart and its Redis HGET, productcatalogservice GetProduct with its feature-flag child, and currencyservice Convert are all sub-millisecond to about a millisecond with no error flags. Payment, email, and fulfilment are not broken — they are never reached. Frontend's error status is inherited, its spans being strict ancestors of the erroring checkout span. And this is not a timing problem: failing requests finish in single-digit to low-teens milliseconds with no span over ~4ms, so no deadline had room to expire.

> Evidence `tr_0fc36111a604`:

```
<tool_result id="tr_0fc36111a604" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_0fc36111a604>
```

> Evidence `tr_f25e4e507bbf`:

```
<tool_result id="tr_f25e4e507bbf" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_f25e4e507bbf>
```

> Evidence `tr_79f505a13285`:

```
<tool_result id="tr_79f505a13285" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_79f505a13285>
```

> Evidence `tr_a391b01a5a02`:

```
<tool_result id="tr_a391b01a5a02" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
service: checkoutservice
200 spans
  a7f7a80ed3dfc1dd cartservice/hipstershop.CartService/GetCart 0.3ms
  a7f7a80ed3dfc1dd cartservice/HGET 0.2ms
  a7f7a80ed3dfc1dd checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.8ms
```

## The cause, and what remains unproven

In every failing trace the error is stamped on exactly one span: checkoutservice's client span for ShippingService GetQuote. The trace stops there, containing no spans for any later checkout stage — which explains the missing completion log lines precisely. Shippingservice's own server span and its nested outbound client span both return success in roughly 2ms.

Change history on shippingservice held one record for the window: an environment/config update applied by platform-automation at T-3m, setting QUOTE_SERVICE_ADDR — previously unset — to an address naming a decommissioned backend. No image, version, proto, or flag change anywhere. Shippingservice logs corroborate: early lines pair each GetQuote request with a quote-response line carrying an amount, then ship-order and tracking-ID lines; from about T+1m onward only inbound request lines remain, all INFO, requests still well-formed with valid trace context. The reading is that shippingservice, pointed at a backend that does not exist, returns an empty or invalid quote as a nominal success, and checkoutservice rejects it at its client boundary. Fix class: revert the config value.

Still open. First, the mechanism inside shippingservice is inferred, not observed — a successful 2ms outbound span is not what a call to an unresolvable host normally looks like, and whether that span belongs to this call at all was never settled. Second, the metrics' intermittent 0–30% ratio contradicts the deterministic single shape seen in every sampled trace; whether the surviving majority take a cached or retried path is unresolved and decides whether a revert alone suffices. Third, it is unverified whether the variable takes effect without restarting shippingservice pods, since environment values are typically read at process start. Also unexplained: the three-minute gap between apply and onset, and the untested middle interval — an error-filtered query over the truncated window is the cheapest next step.

> Evidence `tr_a391b01a5a02`:

```
<tool_result id="tr_a391b01a5a02" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
service: checkoutservice
200 spans
  a7f7a80ed3dfc1dd cartservice/hipstershop.CartService/GetCart 0.3ms
  a7f7a80ed3dfc1dd cartservice/HGET 0.2ms
  a7f7a80ed3dfc1dd checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.8ms
```

> Evidence `tr_8eb4ad4bdd98`:

```
<tool_result id="tr_8eb4ad4bdd98" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00">
service: shippingservice
1 changes
  2026-08-29T20:29:14.838170+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
</tool_result:tr_8eb4ad4bdd98>
```

> Evidence `tr_c10985a9dc78`:

```
<tool_result id="tr_c10985a9dc78" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-29T20:22:00.583000+00:00..2026-08-29T20:37:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-08-29T20:22:06.588916+00:00  20:22:06 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0f1183f4957f52642d78d96efe25088c-511478609fd5afff-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "6E92ZMYYFZ", quantity: 2 }, CartItem { product_id: "1YMWWN1N4O", quantity: 1 }] }, extensions: Extensions }
2026-08-29T20:22:06.598225+00:00  20:22:06 [INFO] Sending Quote: 26.70
2026-08-29T20:22:06.601685+00:00  20:22:06 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "baggage": "synthetic_request=true", "traceparent": "00-0f1183f4957f52642d78d96efe25088c-95c3ca440bcdf1ba-01"} }, message: ShipOrderRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "6E92ZMYYFZ", quantity: 2 }, CartItem { product_id: "1YMWWN1N4O", quantity: 1 }] }, extensions: Extensions }
2026-08-29T20:22:06.601691+00:00  20:22:06 [INFO] Tracking ID Created: 43467e73-ad86-4d6c-b2b2-01781d2bf590
```
