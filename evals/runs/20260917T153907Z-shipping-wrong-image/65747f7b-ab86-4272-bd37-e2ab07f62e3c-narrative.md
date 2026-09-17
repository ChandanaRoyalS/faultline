# Checkout cart failures traced to shippingservice running a foreign image and restart-looping

## What was visible, in order

The page came in on checkoutservice at T+0, severity critical, and within about three minutes had spread to frontend, loadgenerator, quoteservice, accounting, email, fraud detection and shippingservice. Eight alerting services read like a substrate problem; it turned out seven were downstream of one broken hop.

Metrics confirmed the failure was real and older than the page: checkoutservice error ratio went from roughly 0.4% baseline to about 11% mean with peaks near 29%, a ~28-fold rise well outside baseline spread. The earliest change point sat about 23 minutes before the alert, with a second crossing at T-2m. The ratio dipped to zero within the window, so this was bursty partial degradation, not a hard outage.

Checkout's own logs contained no error, warning or timeout lines at all, but the result was truncated and the moment of interest fell inside the elided middle. What the retained tail did show mattered: early orders had a full sequence (placement, payment with transaction id, confirmation email, message write with increasing offset), while the last couple of minutes had order-placement lines only. Orders started and never finished, arrival cadence held steady, and both USD and CAD orders stalled.

Traces were the turn. Every post-onset checkout trace carried ERROR from the frontend POST down into prepareOrderItemsAndShippingQuoteFromCart, and the erroring leaf was always checkoutservice's client span for ShippingService/GetQuote — with no shippingservice server child and self-time equal to total at 0.3-2.3ms. A connect-level failure, not a slow response. Failing roots ran 5.2-11.0ms against 23.9ms for a healthy trace ten minutes earlier, so the symptom was fast errors.

shippingservice change history then supplied the cause: an image reference update at T-3m pointing the service at a tag belonging to a different service. Its logs from T-2m43s onward contain only JVM/OTel-agent startup banners, about ten cycles with gaps lengthening from ~6s to ~64s, bracketing the page at T-26s and T+38s, with no request-handling line after T-3m. The banners are Java; the earlier lines that served quotes were Rust-formatted. The thing restarting is not the binary that served quotes. Fix class: rollback.

> Evidence `tr_14ffebb2ecab`:

```
<tool_result id="tr_14ffebb2ecab" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T15:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" template="error-ratio" baseline="2026-09-17T14:38:41.023386+00:00..2026-09-17T15:12:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=135 mean=0.114 min=0 max=0.2875 sd=0.1206
  baseline window: n=135 mean=0.004007 min=0 max=0.04167 sd=0.008525
```

> Evidence `tr_92b46127de99`:

```
<tool_result id="tr_92b46127de99" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T15:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T15:12:33.975149+00:00  {"message":"[PlaceOrder] user_id=\"35a621b2-b2aa-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T15:12:33.97500071Z"}
2026-09-17T15:12:33.992353+00:00  {"message":"payment went through (transaction_id: ec7075da-0dc8-4645-86b1-3aeb29b302a5)","severity":"info","timestamp":"2026-09-17T15:12:33.992271585Z"}
2026-09-17T15:12:33.997522+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-17T15:12:33.99746971Z"}
2026-09-17T15:12:33.998399+00:00  {"message":"Successful to write message. offset: 65156","severity":"info","timestamp":"2026-09-17T15:12:33.998326501Z"}
```

> Evidence `tr_788cdbb6dc15`:

```
<tool_result id="tr_788cdbb6dc15" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T15:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00">
service: checkoutservice
11 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace ccdb283b45946697  root frontend/HTTP POST  23.9ms  started 2026-09-17T15:32:04.396011+00:00  42 spans
  +0.0ms frontend/HTTP POST 23.9ms [self 0.0ms]
```

> Evidence `tr_0621fcda4b47`:

```
<tool_result id="tr_0621fcda4b47" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T15:42:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" radius="seed" hops="0">
service: shippingservice
11 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T15:39:15.798022+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-17T15:28:39.773514+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_10cbee2bb0cb`:

```
<tool_result id="tr_10cbee2bb0cb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T14:12:18.818544+00:00  14:12:18 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-df4b383757e92c25831f9017f656a445-0ab8dabe7eb5fc99-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "0PUK6V6EV0", quantity: 5 }] }, extensions: Extensions }
2026-09-17T14:12:18.825807+00:00  14:12:18 [INFO] Sending Quote: 124.60
2026-09-17T14:12:18.829005+00:00  14:12:18 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-df4b383757e92c25831f9017f656a445-4d9ac7074c8c2283-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "0PUK6V6EV0", quantity: 5 }] }, extensions: Extensions }
2026-09-17T14:12:18.829010+00:00  14:12:18 [INFO] Tracking ID Created: 79e73ef5-010a-44f1-a94c-588fa955c85f
```

## Dead ends worth keeping

The first move was to ask what changed on checkoutservice. The log came back empty, which read as reassuring until the window was checked — it started at the alert timestamp and ran forward a day, so it never covered the minutes before onset. It does legitimately rule out an in-flight deploy, a flag flip, or a quiet remediation on checkoutservice sustaining the failure, but it answered a question nobody asked. Anchor that window to end at onset.

Every other checkout dependency was cleared by the traces, and these are the ones a responder will reach for first. currencyservice Convert spans: present, error-free, 0.8-1.6ms. cartservice GetCart and its Redis child: present, error-free, 0.2-2.7ms. productcatalogservice GetProduct: error-free, sub-1.1ms. paymentservice never appears in a failing trace at all — the request aborts before the charge stage, so absence there means innocence, not guilt. adservice and recommendationservice are not children of checkoutservice in any trace, healthy or failing.

A decoy in the change history cost real time: a config change repointing shippingservice's quote-service address at a host that reads as nonexistent, applied at T-23m, about 23 seconds before the first error-ratio change point. It is almost certainly why that change point exists — but it was reverted at T-13m40s, thirteen minutes before the page, so it cannot be the ongoing cause. Compounding this, the tool's relative-time labels disagreed with its absolute timestamps (describing T-23m as T-23s), which briefly led to the image update being written off as irrelevant. Trust the absolute timestamps.

Span metrics were useless for both shippingservice and quoteservice: the error-ratio series returned nothing in the incident window and nothing in the baseline either, so the silence predates the incident and points at an instrumentation or label gap rather than traffic stopping. Do not spend time reading that emptiness as a signal.

Inside the restart loop, several tidy explanations went unsupported. No panic, stack trace or error-level line was retained — each cycle ends silently after the banners, which disfavours a logged application crash and leans toward an external kill or a failure before logging initialises, though truncation weakens that. No bind or address-in-use message appears in any cycle, so a listener conflict is not the evidenced mode. And nothing in the logs supports shipping failing because of its calls to quoteservice: the healthy lines show quotes computed in-process, and the tail shows the process dying before serving anything.

> Evidence `tr_c7f9c7ab201b`:

```
<tool_result id="tr_c7f9c7ab201b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T15:42:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_c7f9c7ab201b>
```

> Evidence `tr_788cdbb6dc15`:

```
<tool_result id="tr_788cdbb6dc15" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T15:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00">
service: checkoutservice
11 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace ccdb283b45946697  root frontend/HTTP POST  23.9ms  started 2026-09-17T15:32:04.396011+00:00  42 spans
  +0.0ms frontend/HTTP POST 23.9ms [self 0.0ms]
```

> Evidence `tr_0621fcda4b47`:

```
<tool_result id="tr_0621fcda4b47" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T15:42:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" radius="seed" hops="0">
service: shippingservice
11 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T15:39:15.798022+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-17T15:28:39.773514+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_2dbf9c31c083`:

```
<tool_result id="tr_2dbf9c31c083" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T14:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" template="error-ratio" baseline="2026-09-17T12:38:41.023386+00:00..2026-09-17T14:12:15.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_10cbee2bb0cb`:

```
<tool_result id="tr_10cbee2bb0cb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T14:12:18.818544+00:00  14:12:18 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-df4b383757e92c25831f9017f656a445-0ab8dabe7eb5fc99-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "0PUK6V6EV0", quantity: 5 }] }, extensions: Extensions }
2026-09-17T14:12:18.825807+00:00  14:12:18 [INFO] Sending Quote: 124.60
2026-09-17T14:12:18.829005+00:00  14:12:18 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-df4b383757e92c25831f9017f656a445-4d9ac7074c8c2283-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "0PUK6V6EV0", quantity: 5 }] }, extensions: Extensions }
2026-09-17T14:12:18.829010+00:00  14:12:18 [INFO] Tracking ID Created: 79e73ef5-010a-44f1-a94c-588fa955c85f
```

## Still open

One cause or two is unsettled. The early error-ratio change point fits the reverted address config, but nobody measured whether errors recovered between that revert and the image update twenty minutes later. A single query over that gap would settle it and should be the first thing run next time.

Why each startup cycle dies is unevidenced. No panic, trace or bind error was retained, and no memory, CPU or restart-count metrics were collected, so an external kill cannot be distinguished from an immediate crash.

There is no metric-side corroboration for the shipping path at all. Span metrics are empty for shippingservice and quoteservice in both windows, and quoteservice was never examined by logs or traces — the whole shipping-side conclusion rests on logs and checkout's client spans.

> Evidence `tr_14ffebb2ecab`:

```
<tool_result id="tr_14ffebb2ecab" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T15:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" template="error-ratio" baseline="2026-09-17T14:38:41.023386+00:00..2026-09-17T15:12:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=135 mean=0.114 min=0 max=0.2875 sd=0.1206
  baseline window: n=135 mean=0.004007 min=0 max=0.04167 sd=0.008525
```

> Evidence `tr_10cbee2bb0cb`:

```
<tool_result id="tr_10cbee2bb0cb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T14:12:18.818544+00:00  14:12:18 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-df4b383757e92c25831f9017f656a445-0ab8dabe7eb5fc99-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "0PUK6V6EV0", quantity: 5 }] }, extensions: Extensions }
2026-09-17T14:12:18.825807+00:00  14:12:18 [INFO] Sending Quote: 124.60
2026-09-17T14:12:18.829005+00:00  14:12:18 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-df4b383757e92c25831f9017f656a445-4d9ac7074c8c2283-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 5 }, CartItem { product_id: "0PUK6V6EV0", quantity: 5 }] }, extensions: Extensions }
2026-09-17T14:12:18.829010+00:00  14:12:18 [INFO] Tracking ID Created: 79e73ef5-010a-44f1-a94c-588fa955c85f
```

> Evidence `tr_2dbf9c31c083`:

```
<tool_result id="tr_2dbf9c31c083" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T14:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" template="error-ratio" baseline="2026-09-17T12:38:41.023386+00:00..2026-09-17T14:12:15.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1bbe818245bd`:

```
<tool_result id="tr_1bbe818245bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T15:12:15.583000+00:00..2026-09-17T15:45:50.142614+00:00" template="error-ratio" baseline="2026-09-17T14:38:41.023386+00:00..2026-09-17T15:12:15.583000+00:00">
service: quoteservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="quoteservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="quoteservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

