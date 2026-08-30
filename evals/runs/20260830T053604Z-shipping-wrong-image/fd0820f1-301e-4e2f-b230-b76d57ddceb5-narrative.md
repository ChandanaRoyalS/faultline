# Checkout orders abort at shipping quote after wrong artifact lands on shippingservice

## What was visible first, and the dead ends

The page arrived as a three-service fan-out — checkoutservice, frontend, loadgenerator — with a blast radius drawn at twelve services, which made the first minutes feel far larger than the incident turned out to be. Take T+0 as the checkout alert.

The first instinct was that checkoutservice itself was broken, and that consumed several dispatches for no return. Its span-level error ratio was genuinely non-zero, peaking near 28% and dropping back to zero at other points in the same window. That partial, intermittent shape reads like a problem inside checkout. It was not, and it was never fully explained (see open threads). It should have been weighted less.

The checkout logs were the second dead end, and an instructive one. Every returned line was info severity: no errors, no exceptions, no panics, and — critically — no line naming a downstream callee, an RPC status code, or a timeout. What the logs did give was a shape change. Early on, each order-placement entry was followed by payment, confirmation-email, and message-write entries. From about T+1m onward only the order-placement entries appear; the completion side is gone entirely, while intake continues steadily through T+4m. That closed out three stories at once: checkout had not crashed or restarted, upstream traffic had not stopped, and this was not latency with orders quietly completing late. Note the log result was truncated and never returned the stretch containing onset.

The checkout change log came back completely empty — no deploys, config edits, or flag flips — which also ruled out a mid-incident operator change muddying the timeline. Two caveats worth carrying: the window covered only about ten minutes before the alert, not the hour requested, and the query was scoped by service name with no dependency coverage.

> Evidence `tr_4eeea7e06d09`:

```
<tool_result id="tr_4eeea7e06d09" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2836 n=61
</tool_result:tr_4eeea7e06d09>
```

> Evidence `tr_d0a8db91e7c3`:

```
<tool_result id="tr_d0a8db91e7c3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-30T05:28:48.406919+00:00  {"message":"[PlaceOrder] user_id=\"ad57a076-a433-11f1-8c4e-9e12df7a2593\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-30T05:28:48.406812169Z"}
2026-08-30T05:28:48.423330+00:00  {"message":"payment went through (transaction_id: 7aa7df71-6d40-469d-bc9c-2000f1dc162a)","severity":"info","timestamp":"2026-08-30T05:28:48.423219502Z"}
2026-08-30T05:28:48.427761+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-08-30T05:28:48.427664127Z"}
2026-08-30T05:28:48.428374+00:00  {"message":"Successful to write message. offset: 25528","severity":"info","timestamp":"2026-08-30T05:28:48.428311586Z"}
```

> Evidence `tr_21c77bd08c88`:

```
<tool_result id="tr_21c77bd08c88" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_21c77bd08c88>
```

## Traces localized it in one step

The trace evidence is where the investigation turned, and in hindsight it should have been the second dispatch rather than the fourth. In every failing checkout trace, exactly one child span of checkoutservice carries ERROR: the outbound call to ShippingService/GetQuote. The status originates on that dependency-call span and is inherited upward through PlaceOrder to the frontend HTTP POST, which explains the whole alert fan-out without any independent failure in frontend or loadgenerator.

Two details were decisive. The errored GetQuote spans complete in roughly 1.8–2.5ms with parents finishing in 5–11ms, so nothing is consuming a latency budget — this is an immediate rejection, not a deadline. And no server-side shippingservice span appears beneath those client spans, whereas cartservice, productcatalogservice and currencyservice all show matching server-side children in the same traces. The call dies at the connection boundary before anything on the shipping side runs.

That single dispatch eliminated cartservice and its Redis backend, productcatalogservice, currencyservice and the featureflagservice lookups, all non-error and sub-2.5ms. Payment, email and ShipOrder never appear at all; failing traces terminate inside prepareOrderItemsAndShippingQuoteFromCart.

> Evidence `tr_83d5dc9c4c5f`:

```
<tool_result id="tr_83d5dc9c4c5f" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00">
service: checkoutservice
200 spans
  59960b212d440d59 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 10.6ms ERROR
  59960b212d440d59 checkoutservice/hipstershop.CheckoutService/PlaceOrder 9.1ms ERROR
  59960b212d440d59 checkoutservice/prepareOrderItemsAndShippingQuoteFromCart 9.0ms
```

## The shipping side, and what closed it

A shippingservice error-ratio query returned no series at all. Because the denominator was unfiltered by status, the absence covers total request volume, not just errors — and a degraded-but-up service would still produce a non-empty denominator. The metric was useless for triage; it could not distinguish 'emitted nothing' from 'labelled differently', and no per-RPC breakdown was obtainable.

The logs settled it. Around T-10m shippingservice is plainly healthy, handling GetQuote and returning ShipOrder tracking IDs in Rust-style application logs. From about T-2m the entire tail is JVM/agent startup output — a three-line boot triad repeating at least ten times over roughly seven minutes, the later repetitions on a near-constant ~65s cadence. No panic or stack traces, no listener-bind lines, no TLS or handshake output, no connection-refused or resource-exhausted lines. That closed out a port conflict, a handshake failure, load shedding, a healthy-but-idle process, and a single one-off restart.

The change record held exactly one entry for shippingservice: an automated image-reference update at T-2m38s pointing at a demo image tag whose name suffix refers to adservice, not shippingservice. The prior value is unrecorded. Together: a Java artifact sits where the real Rust binary belonged, the container boots and dies before serving, and checkout — healthy and unchanged — gets an instant rejection on every quote. Nothing is exhausted, nothing is slow. Fix class is rollback.

Still open: the shipping log stream is heterogeneous under one label, so the boot lines should be confirmed against the pod identity and image digest; the rollback target must be recovered from deployment history; the ~2.5 minute gap between the change and the alert is unexplained; the partial 28% error ratio is unreconciled with the expectation of near-total failure; no restart-count or exit-code data was ever retrieved; and nobody has explained why an adservice-named tag was applied to shippingservice, which means other services may be carrying wrong artifacts that have not surfaced.

> Evidence `tr_218fafc5435a`:

```
<tool_result id="tr_218fafc5435a" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))' over this window
</tool_result:tr_218fafc5435a>
```

> Evidence `tr_ca4098866497`:

```
<tool_result id="tr_ca4098866497" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-08-30T05:28:48.411764+00:00  05:28:48 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-08f22770378a1362fefd538379e28161-f16883c5e10afd42-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "2200 Mission College Blvd", city: "Santa Clara", state: "CA", country: "United States", zip_code: "95054" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 10 }] }, extensions: Extensions }
2026-08-30T05:28:48.420157+00:00  05:28:48 [INFO] Sending Quote: 89.0
2026-08-30T05:28:48.424024+00:00  05:28:48 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-08f22770378a1362fefd538379e28161-83cd3bce0a6ca538-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "2200 Mission College Blvd", city: "Santa Clara", state: "CA", country: "United States", zip_code: "95054" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 10 }] }, extensions: Extensions }
2026-08-30T05:28:48.424029+00:00  05:28:48 [INFO] Tracking ID Created: 065724bd-e36b-4f65-a94d-bcdc074fd133
```

> Evidence `tr_df66fa544485`:

```
<tool_result id="tr_df66fa544485" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T05:28:45.583000+00:00..2026-08-30T05:43:45.583000+00:00">
service: shippingservice
1 changes
  2026-08-30T05:36:07.862091+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
</tool_result:tr_df66fa544485>
```
