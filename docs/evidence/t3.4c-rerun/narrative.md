# Checkout order path halted by a wrong artifact running under the shippingservice label

## What was visible, in order

The page was wide: fourteen services in the blast radius, critical severity, checkoutservice named as origin, eight services alerting. That breadth is misleading — one broken leg of the order path lights up everything on or beside it, plus the load generator driving it.

The first honest signal was checkoutservice's own error ratio: non-zero, bursty, peaking near 29% across 61 sample points and returning to zero in between. Two readings follow. Checkout was not down — most calls succeeded. And the failure was not flat or deterministic, which is the shape you get when a single endpoint is broken and the traffic mix varies.

Traces settled which endpoint. Every failing trace had the same spine: frontend POST, frontend PlaceOrder, checkoutservice PlaceOrder, a clean order-preparation span, then checkoutservice's outbound ShippingService/GetQuote client span carrying the deepest error. No server span ever appeared beneath it. Failing PlaceOrder spans finished in roughly 5–13ms with the erroring GetQuote span under about 2.5ms — a connection-level rejection, not an exceeded deadline. cartservice and its HGET, productcatalogservice GetProduct, and currencyservice Convert were all clean on the same path; payment was never reached.

> Evidence `tr_7d4b93d2d99c`:

```
<tool_result id="tr_7d4b93d2d99c" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2941 n=61
</tool_result:tr_7d4b93d2d99c>
```

> Evidence `tr_1749a639f99a`:

```
<tool_result id="tr_1749a639f99a" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
service: checkoutservice
200 spans
  3272a8c6ad583b8b checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
  3272a8c6ad583b8b productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
  3272a8c6ad583b8b checkoutservice/hipstershop.CurrencyService/Convert 1.2ms
```

## The cause

Change history for checkoutservice over the window was completely empty — no deploys, config edits or flag flips. That closed the most tempting branch and pushed attention downstream.

Change history for shippingservice returned exactly one entry: a platform-automation image-reference update at 02:53:58 UTC, minutes before symptoms. The new reference names an adservice-tagged demo image; the prior reference is recorded as absent/unset. The workload that came up under the shippingservice label was the wrong artifact.

Logs confirm it never served. Through roughly 02:48 the stream shows ordinary INFO-level GetQuote and ShipOrder work. From 02:54:27 it contains only a repeating three-line JVM/OpenTelemetry-agent startup banner — restarts clustering at 02:54:27, 02:54:35, 02:54:46, then spacing to a steady ~65s cadence through 03:01:55. At least eleven cycles, none reaching an application-ready line. There are no ERROR or WARN lines, no exceptions, no stack traces anywhere in the window. Metrics corroborate by absence: the shippingservice error-ratio query returned no series at all, numerator and denominator both missing, so there is no successful-call baseline for errors to rise against. Confidence high; fix class is rollback.

> Evidence `tr_2e7b4cbd2305`:

```
<tool_result id="tr_2e7b4cbd2305" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_2e7b4cbd2305>
```

> Evidence `tr_44a3bc84c6c0`:

```
<tool_result id="tr_44a3bc84c6c0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
service: shippingservice
1 changes
  2026-08-26T02:53:58.124331+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
</tool_result:tr_44a3bc84c6c0>
```

> Evidence `tr_d9493cdf3ac9`:

```
<tool_result id="tr_d9493cdf3ac9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-08-26T02:47:16.978088+00:00  02:47:16 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0893af08336afaa8a6ac773a840d5e23-3ac3c4b4ee51211f-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 5 }] }, extensions: Extensions }
2026-08-26T02:47:16.987407+00:00  02:47:16 [INFO] Sending Quote: 44.50
2026-08-26T02:47:16.991465+00:00  02:47:16 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0893af08336afaa8a6ac773a840d5e23-def5b97a5efa3dbe-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 5 }] }, extensions: Extensions }
2026-08-26T02:47:16.991471+00:00  02:47:16 [INFO] Tracking ID Created: 789cd57a-c7d8-4a88-9b69-960a7dae9362
```

> Evidence `tr_1836bbcbc2e0`:

```
<tool_result id="tr_1836bbcbc2e0" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))' over this window
</tool_result:tr_1836bbcbc2e0>
```

## Dead ends worth keeping

A checkoutservice self-deploy. Nothing landed on checkoutservice in the window, so rolling it back is not an available remedy — there is nothing to roll back.

A timeout or slow dependency. Failing traces complete in single-digit milliseconds. Any framing around deadlines or backpressure is off-target, as is any suspicion of cartservice, Redis, productcatalogservice, currencyservice or paymentservice — all clean on the failing path or never invoked.

Grepping shipping's logs for a named failure, and reading its empty metric series as "quiet but fine." The process dies silently between startup banners, so a keyword search returns nothing and can convince you the logs are healthy. Likewise, absence of a ratio is not a low ratio: the denominator is missing too.

> Evidence `tr_2e7b4cbd2305`:

```
<tool_result id="tr_2e7b4cbd2305" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_2e7b4cbd2305>
```

> Evidence `tr_1749a639f99a`:

```
<tool_result id="tr_1749a639f99a" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
service: checkoutservice
200 spans
  3272a8c6ad583b8b checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
  3272a8c6ad583b8b productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
  3272a8c6ad583b8b checkoutservice/hipstershop.CurrencyService/Convert 1.2ms
```

> Evidence `tr_d9493cdf3ac9`:

```
<tool_result id="tr_d9493cdf3ac9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-08-26T02:47:16.978088+00:00  02:47:16 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0893af08336afaa8a6ac773a840d5e23-3ac3c4b4ee51211f-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 5 }] }, extensions: Extensions }
2026-08-26T02:47:16.987407+00:00  02:47:16 [INFO] Sending Quote: 44.50
2026-08-26T02:47:16.991465+00:00  02:47:16 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0893af08336afaa8a6ac773a840d5e23-def5b97a5efa3dbe-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 5 }] }, extensions: Extensions }
2026-08-26T02:47:16.991471+00:00  02:47:16 [INFO] Tracking ID Created: 789cd57a-c7d8-4a88-9b69-960a7dae9362
```

> Evidence `tr_1836bbcbc2e0`:

```
<tool_result id="tr_1836bbcbc2e0" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))' over this window
</tool_result:tr_1836bbcbc2e0>
```

## Open items for the next responder

The rollback target is not established. The prior image reference is recorded as absent/unset, so the known-good shippingservice digest must be identified before reverting. Separately, why platform-automation applied an adservice-tagged image here is unexplained — the same automation could re-apply it after a revert.

Which workload needs the revert is unsettled. The stream under the shippingservice label mixes Rust-style application output with JVM startup banners, so it is unclear whether the crash-looping Java process is the mis-imaged shipping pod, a co-located quoteservice, or a label-routing artifact. This is held at low confidence and it decides the target of the fix. quoteservice was never queried despite alerting. The kill mechanism per cycle is also unknown — no stack trace or shutdown message, leaving an external kill, a failed probe, or immediate startup failure of a wrong-entrypoint binary all open.

Coverage gaps. All windows end at 03:02, so the 03:02–03:10 tail is unmeasured and it is unknown whether the loop persisted or the incident is still live. currencyservice has no calls_total series under the queried label scheme, which may point at a broader instrumentation or labelling problem also explaining shipping's metric absence. No latency percentiles or per-downstream breakdown were pulled for checkoutservice, no change history was gathered for its other five dependencies or over the full two-hour lookback, and the accounting, email and fraud-detection alerts were assumed to be downstream propagation without being examined directly.

> Evidence `tr_44a3bc84c6c0`:

```
<tool_result id="tr_44a3bc84c6c0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
service: shippingservice
1 changes
  2026-08-26T02:53:58.124331+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
</tool_result:tr_44a3bc84c6c0>
```

> Evidence `tr_d9493cdf3ac9`:

```
<tool_result id="tr_d9493cdf3ac9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-08-26T02:47:16.978088+00:00  02:47:16 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0893af08336afaa8a6ac773a840d5e23-3ac3c4b4ee51211f-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 5 }] }, extensions: Extensions }
2026-08-26T02:47:16.987407+00:00  02:47:16 [INFO] Sending Quote: 44.50
2026-08-26T02:47:16.991465+00:00  02:47:16 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-0893af08336afaa8a6ac773a840d5e23-def5b97a5efa3dbe-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 5 }] }, extensions: Extensions }
2026-08-26T02:47:16.991471+00:00  02:47:16 [INFO] Tracking ID Created: 789cd57a-c7d8-4a88-9b69-960a7dae9362
```

> Evidence `tr_1836bbcbc2e0`:

```
<tool_result id="tr_1836bbcbc2e0" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))' over this window
</tool_result:tr_1836bbcbc2e0>
```

> Evidence `tr_3d5cab00fe9e`:

```
<tool_result id="tr_3d5cab00fe9e" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="currencyservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="currencyservice"}[2m]))' over this window
</tool_result:tr_3d5cab00fe9e>
```

> Evidence `tr_7d4b93d2d99c`:

```
<tool_result id="tr_7d4b93d2d99c" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2941 n=61
</tool_result:tr_7d4b93d2d99c>
```

> Evidence `tr_2e7b4cbd2305`:

```
<tool_result id="tr_2e7b4cbd2305" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T02:47:00.583000+00:00..2026-08-26T03:02:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_2e7b4cbd2305>
```


