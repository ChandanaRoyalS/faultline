# Checkout order flow broken by a mismatched shippingservice image

## What was visible, and why checkoutservice was the wrong lead

Six services alerted at once and the seed handed to the responder was checkoutservice — the loudest alert and the one closest to the customer-visible symptom, but a bystander. Three lines of evidence against it all came back clean. Its change history was empty across the queried interval, ruling out any deploy or config edit on the service itself; note the query was scoped to the seed with zero hops, so its dependencies were never examined, and the window ran forward from onset, so a pre-onset change elsewhere would not have shown. Its error ratio was statistically indistinguishable from the prior hour — about a 1.03x mean shift, with the incident-window maximum actually below baseline — meaning a real downstream failure was in progress and this metric registered nothing. Its logs were the most deceptive artifact: every line info severity, no error, no exception, no dependency named. The tell is structural, not textual. Early on, each order placement is followed by payment confirmation with a transaction id, a confirmation email, and a queue write with an offset. In the final contiguous minutes only the placement lines remain. Orders are still accepted every few seconds, so the process is alive; USD and CAD are affected alike, so it is not a currency path. This is a caller blocked at an upstream step, silently.

> Evidence `tr_8b49d40eb91d`:

```
<tool_result id="tr_8b49d40eb91d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T10:54:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_8b49d40eb91d>
```

> Evidence `tr_0cb74cf61e9e`:

```
<tool_result id="tr_0cb74cf61e9e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T09:54:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" template="error-ratio" baseline="2026-09-09T08:49:02.088897+00:00..2026-09-09T09:54:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=262 mean=0.07324 min=0 max=0.2857 sd=0.1074
  baseline window: n=262 mean=0.07093 min=0 max=0.6667 sd=0.1987
```

> Evidence `tr_55c59e9f5ddd`:

```
<tool_result id="tr_55c59e9f5ddd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T09:54:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T09:54:31.484028+00:00  {"message":"[PlaceOrder] user_id=\"74430344-ac34-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T09:54:31.483935501Z"}
2026-09-09T09:54:31.500722+00:00  {"message":"payment went through (transaction_id: 9f68514c-9efc-41fc-9671-7286744b558d)","severity":"info","timestamp":"2026-09-09T09:54:31.500657668Z"}
2026-09-09T09:54:31.505422+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-09T09:54:31.505324459Z"}
2026-09-09T09:54:31.506270+00:00  {"message":"Successful to write message. offset: 21585","severity":"info","timestamp":"2026-09-09T09:54:31.506183668Z"}
```

## Traces named the boundary; the change log named the cause

Traces broke it open. Across ten sampled failing checkouts, exactly one child under checkoutservice errors: the client call to hipstershop.ShippingService/GetQuote from prepareOrderItemsAndShippingQuoteFromCart. That error terminates PlaceOrder and is inherited up to the frontend root, which is why the frontend looked implicated. The span lasts 0.4–2.4ms inside traces completing in 7–12ms — far too fast for any deadline — and no server-side shippingservice span appears beneath it, unlike cartservice, currencyservice and productcatalogservice, which all show healthy server children. One trap: the erroring span is often not the first child to start, but it is always the only child to error; ordering by start time points at the wrong span. The shippingservice change log then supplied the cause. Fifteen entries in the window, all from platform-automation, none from a human, none a flag toggle. At roughly T-2m30s the container image reference was set to an artifact belonging to a different service. Four earlier update-and-revert rounds over the preceding hours each ended in a revert; this one did not, and the mismatched reference was still in place at onset. Shipping-service logs confirm it: healthy GetQuote and ShipOrder handling around T-30m, then from about T-2m onward nothing but JVM and OpenTelemetry-javaagent startup sequences repeating at short intervals, with the earlier Rust-style request logger gone. The wrong artifact is starting under the shippingservice identity and never opens the shipping surface — hence the missing server spans. Fix class is rollback.

> Evidence `tr_9ad90e426eb5`:

```
<tool_result id="tr_9ad90e426eb5" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T10:24:30.583000+00:00..2026-09-09T10:59:59.077103+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 180 spans; offsets are from each trace's root

trace ba3cf32b84e0f539  root frontend/HTTP POST  10.4ms  started 2026-09-09T10:58:12.456012+00:00  25 spans
  +0.0ms frontend/HTTP POST 10.4ms [self 0.1ms]  ERROR
```

> Evidence `tr_1cb128a4a1c2`:

```
<tool_result id="tr_1cb128a4a1c2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T10:54:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" radius="seed" hops="0">
service: shippingservice
15 changes, ranked by suspicion
  #1  2m before onset  2026-09-09T10:52:03.283649+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-09T10:41:27.684803+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_805b5a83eb83`:

```
<tool_result id="tr_805b5a83eb83" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T10:24:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-09T10:24:36.108603+00:00  10:24:36 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-5a2ce6c8aa078fe2ac21aab8985528e2-d28aeeadcffee052-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "6E92ZMYYFZ", quantity: 4 }] }, extensions: Extensions }
2026-09-09T10:24:36.117638+00:00  10:24:36 [INFO] Sending Quote: 35.60
2026-09-09T10:24:36.122758+00:00  10:24:36 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-5a2ce6c8aa078fe2ac21aab8985528e2-65ec4d3bb5edce4d-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "6E92ZMYYFZ", quantity: 4 }] }, extensions: Extensions }
2026-09-09T10:24:36.122764+00:00  10:24:36 [INFO] Tracking ID Created: b181b90d-9d07-4914-859d-be437dc092ea
```

## Dead ends, gaps, and what is still open

Kept because each cost time. The QUOTE_SERVICE_ADDR edits on shippingservice are the best decoy in the record: the address was pointed at an unresolvable-looking quote host about 25 minutes before onset and removed about 13 minutes before onset. It names the exact path that was failing and was not in effect at onset. The shippingservice error-ratio metric returned no samples at all — but the baseline window is equally empty, so this is a collection or labelling gap, not a signal loss aligned with onset; it supports nothing either way. The checkoutservice error ratio is likewise useless for excluding dependencies. Cartservice and its Redis HGET, currencyservice Convert, and productcatalogservice GetProduct with its nested flag lookup all complete sub-millisecond without error. A latency or timeout reading is incompatible with sub-3ms erroring spans. A checkoutservice crash is excluded by continuous order placements and no restart banner. Still open: the correct prior image reference was never confirmed, so the rollback target must come from deployment config rather than this evidence; why the process restarts is unestablished, since each startup sequence completes with no exception or parse error — crash loop versus a probe killing a process that never opens the port is unresolved; log coverage has holes on both services around the transition, so the healthy-to-failing moment was never directly observed; checkoutservice's other declared dependencies were never checked for changes, so a concurrent change elsewhere is unnecessary as an explanation but not excluded; the four downstream alerts are inferred consequences, never verified; and whether the automation will re-apply or self-revert the image — and must therefore be paused before a rollback holds — is unknown.

> Evidence `tr_1cb128a4a1c2`:

```
<tool_result id="tr_1cb128a4a1c2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T10:54:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" radius="seed" hops="0">
service: shippingservice
15 changes, ranked by suspicion
  #1  2m before onset  2026-09-09T10:52:03.283649+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-09T10:41:27.684803+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_a8b5ce8362bc`:

```
<tool_result id="tr_a8b5ce8362bc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T10:24:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" template="error-ratio" baseline="2026-09-09T09:49:02.088897+00:00..2026-09-09T10:24:30.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_805b5a83eb83`:

```
<tool_result id="tr_805b5a83eb83" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T10:24:30.583000+00:00..2026-09-09T10:59:59.077103+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-09T10:24:36.108603+00:00  10:24:36 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-5a2ce6c8aa078fe2ac21aab8985528e2-d28aeeadcffee052-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "6E92ZMYYFZ", quantity: 4 }] }, extensions: Extensions }
2026-09-09T10:24:36.117638+00:00  10:24:36 [INFO] Sending Quote: 35.60
2026-09-09T10:24:36.122758+00:00  10:24:36 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-5a2ce6c8aa078fe2ac21aab8985528e2-65ec4d3bb5edce4d-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "6E92ZMYYFZ", quantity: 4 }] }, extensions: Extensions }
2026-09-09T10:24:36.122764+00:00  10:24:36 [INFO] Tracking ID Created: b181b90d-9d07-4914-859d-be437dc092ea
```

