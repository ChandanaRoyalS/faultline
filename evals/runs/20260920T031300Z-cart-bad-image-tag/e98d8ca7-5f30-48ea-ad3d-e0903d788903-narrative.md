# Frontend-reported shipping-quote failures traced to an unresolvable upstream hostname

## What was visible, in order

The page opened on frontend, with alerts across fourteen services. That breadth shaped the first hour badly — it looked like a shared-dependency collapse, and several dispatches went hunting for one.

The first concrete signal arrived in frontend's logs, about thirty minutes before the declared onset: a gRPC INTERNAL (code 13) out of a shipping-quote lookup, whose body was not a gRPC error at all but a Rust HTTP client error against http://quoteservice-gone:8090/getquote, failing DNS name resolution. That hostname was the single most informative artifact of the incident and it was present in the very first pull. Two details in the same result mattered: every error line was a client-side frame from frontend's Node gRPC client — outbound calls, not inbound handling — and the tail of the window carried a different signature entirely, repeated gRPC UNAVAILABLE (code 14) with no target hostname attached.

Frontend was then cleared as origin. Its change log held nothing for a full preceding day, so there was no revision to roll back. Its error ratio during the incident averaged ~9% against a ~10% baseline — a ratio of about 0.94, no step change to align anything against. Frontend was never clean; it carries roughly a tenth of its calls as bursty errors chronically. Request rate and p95 were never retrieved.

> Evidence `tr_a8ab86418f50`:

```
<tool_result id="tr_a8ab86418f50" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-20T02:55:23.586896+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-20T02:55:23.586911+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-20T02:55:23.586912+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-20T02:55:23.586913+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_051d9be580b1`:

```
<tool_result id="tr_051d9be580b1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T03:24:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_051d9be580b1>
```

> Evidence `tr_8edf0ca58eac`:

```
<tool_result id="tr_8edf0ca58eac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" template="error-ratio" baseline="2026-09-20T02:22:54.327692+00:00..2026-09-20T02:54:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=113 mean=0.09039 min=0 max=0.5091 sd=0.1249
  baseline window: n=114 mean=0.0964 min=0 max=0.3016 sd=0.117
```

## Dead ends worth keeping

productcatalogservice drew two dispatches on the shared-dependency theory. The error-ratio query returned no samples in either window — which reads as a missing series (no export, or a label mismatch), not as confirmed zero errors, since a live service would at least produce a denominator. Its change history was empty too, but note the defect: that window began at onset and ran forward, so it never covered the period just before. It was the traces that actually retired this line — five clean frontend→productcatalogservice GetProduct traces with server spans and sub-3ms durations, plus a clean GetAds through adservice.

Hunting the rename was the second dead end. A full-day change query on quoteservice returned nothing at all — no deploy, no config edit, no flag, no rename. The bad endpoint value appears to have been sitting in configuration rather than introduced by a tracked change, which means there is no revision to revert to.

The traces also cleared loadgenerator (negligible self-time on the erroring POST; duration and error both sit on the frontend server span) and ruled out generalised frontend saturation. They did surface one thing that does not fit: a frontend→cartservice GetCart client span with no callee span at all, failing in well under a millisecond — a fast rejection, not a timeout.

> Evidence `tr_74c58c45e378`:

```
<tool_result id="tr_74c58c45e378" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" template="error-ratio" baseline="2026-09-20T02:22:54.327692+00:00..2026-09-20T02:54:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_6ef53586d749`:

```
<tool_result id="tr_6ef53586d749" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T03:24:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_6ef53586d749>
```

> Evidence `tr_3516e4585ed6`:

```
<tool_result id="tr_3516e4585ed6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T03:24:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" radius="seed" hops="0">
no changes recorded for quoteservice over this window
</tool_result:tr_3516e4585ed6>
```

> Evidence `tr_5dbc5020ba24`:

```
<tool_result id="tr_5dbc5020ba24" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00">
service: frontend
10 trace(s) shown of 10 found, 30 spans; offsets are from each trace's root

trace 9642418007267be6  root loadgenerator/HTTP GET  17.7ms  started 2026-09-20T03:25:28.333229+00:00  3 spans
  +0.0ms loadgenerator/HTTP GET 17.7ms [self 2.1ms]
```

## Conclusion, contradiction, and what is still open

Stated conclusion: the shipping-quote path points at a hostname that does not exist, so every quote request fails before a connection is attempted. Not a slow or 5xx upstream — resolution fails, no server is reached. Not auth or TLS. Not internal to frontend. Fix class is config revert, though in practice a forward correction, since no tracked change exists to roll back to.

Confidence is low, for three reasons a responder should weigh before acting.

First, the chain from the Rust client error to shippingservice was inferred by language, never confirmed. Shippingservice's own logs show INFO only — quote requests answered milliseconds later, tracking IDs created, quote-then-ship completing end to end. No DNS errors, no connection failures, and no upstream host or port anywhere in the output. Something is calling quoteservice-gone; the evidence does not show that it is shippingservice. Neither quoteservice nor shippingservice configuration was ever queried directly.

Second, the frontend→cartservice UNAVAILABLE edge is unexplained. cartservice was never dispatched on. That may be a second independent failure, or the dominant one.

Third, nothing covers the declared onset. Both log pulls kept only the oldest eight and newest thirty-two lines and dropped the middle; the traces cluster from roughly T+43s onward; frontend's errors predate the window entirely. What changed at onset is unknown.

> Evidence `tr_6d491b0f03be`:

```
<tool_result id="tr_6d491b0f03be" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-20T02:55:23.583756+00:00  02:55:23 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-e7ef5c571ea359c12a1b11a64543cae3-045cd10d9d3d8d84-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "410 Terry Ave N", city: "Seattle", state: "WA", country: "United States", zip_code: "98109" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 4 }, CartItem { product_id: "OLJCESPC7Z", quantity: 1 }, CartItem { product_id: "1YMWWN1N4O", quantity: 10 }] }, extensions: Extensions }
2026-09-20T02:55:25.994675+00:00  02:55:25 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-397be722937ddd71cd76bacea34e71fa-fa13cc6806c687c8-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "1YMWWN1N4O", quantity: 5 }] }, extensions: Extensions }
2026-09-20T02:55:30.483107+00:00  02:55:30 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-ef8429678675aa9c1a9034e6ee874ee4-c16f3987a122f949-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "150 Elgin St", city: "Ottawa", state: "ON", country: "Canada", zip_code: "K2P1L4" }), items: [CartItem { product_id: "L9ECAV7KIM", quantity: 10 }] }, extensions: Extensions }
2026-09-20T02:55:31.963197+00:00  02:55:31 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "baggage": "synthetic_request=true", "traceparent": "00-19395b4eb92a80a02212090441f7abb5-9ee231ef157c0adb-01"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "2ZYFJ3GM2N", quantity: 6 }, CartItem { product_id: "1YMWWN1N4O", quantity: 10 }, CartItem { product_id: "OLJCESPC7Z", quantity: 1 }] }, extensions: Extensions }
```

> Evidence `tr_5dbc5020ba24`:

```
<tool_result id="tr_5dbc5020ba24" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00">
service: frontend
10 trace(s) shown of 10 found, 30 spans; offsets are from each trace's root

trace 9642418007267be6  root loadgenerator/HTTP GET  17.7ms  started 2026-09-20T03:25:28.333229+00:00  3 spans
  +0.0ms loadgenerator/HTTP GET 17.7ms [self 2.1ms]
```

> Evidence `tr_a8ab86418f50`:

```
<tool_result id="tr_a8ab86418f50" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T02:54:45.583000+00:00..2026-09-20T03:26:36.838308+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-20T02:55:23.586896+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-20T02:55:23.586911+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-20T02:55:23.586912+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-20T02:55:23.586913+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

