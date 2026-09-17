# Checkout order placement failing at the shipping quote hop

## What was visible, and the dead ends

Pages arrived together from checkoutservice, loadgenerator and frontend, which read as one failure seen from three vantage points on the order path. The first instinct was that checkoutservice was broken, and that cost time. A baseline comparison of its error ratio was close to useless: the mean moved only about 1.5x (roughly 6.3% to 9.4%), both windows peaked at the same 50% maximum, minima stayed at baseline, and the result was characterised as no sustained departure. Rate, p95/p99, CPU, memory and restart counts returned nothing. It did close two readings: the service was neither fully down nor suffering a sustained hard error regression. Its logs then returned no error, timeout or rejection severities at all — every line was info — so checkoutservice never named a failing dependency. What the logs did show was shape: at T-30m each order-placement entry was followed within tens of milliseconds by payment, email and message-write lines; from T+0 onward only the entry lines appeared, every few seconds, for thirty-plus consecutive requests with no completion or failure. The process was alive, ingress intact, no crash, no validation rejection (both USD and CAD entries present). The reading at the time was that orders hung in flight. A later attempt at shippingservice error ratio was a second dead end: no samples in the incident window and none in the baseline either, meaning that series is simply never emitted here rather than telemetry breaking at onset.

> Evidence `tr_20f0e76a43f6`:

```
<tool_result id="tr_20f0e76a43f6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-16T19:09:15.583000+00:00..2026-09-17T01:09:15.583000+00:00" template="error-ratio" baseline="2026-09-16T13:09:15.583000+00:00..2026-09-16T19:09:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=75 mean=0.09437 min=0 max=0.5 sd=0.1048
  baseline window: n=80 mean=0.06336 min=0 max=0.5 sd=0.148
```

> Evidence `tr_05c347741022`:

```
<tool_result id="tr_05c347741022" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T06:39:15.583000+00:00..2026-09-17T07:12:41.487765+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T06:39:22.041725+00:00  {"message":"[PlaceOrder] user_id=\"84380efa-b262-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T06:39:22.041521627Z"}
2026-09-17T06:39:22.061723+00:00  {"message":"payment went through (transaction_id: b08a6efc-46ed-4804-b4d6-d47c2aeb9e1a)","severity":"info","timestamp":"2026-09-17T06:39:22.061452668Z"}
2026-09-17T06:39:22.066449+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-09-17T06:39:22.066316043Z"}
2026-09-17T06:39:22.067276+00:00  {"message":"Successful to write message. offset: 62172","severity":"info","timestamp":"2026-09-17T06:39:22.067180043Z"}
```

> Evidence `tr_c013a4dc96d3`:

```
<tool_result id="tr_c013a4dc96d3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T06:39:15.583000+00:00..2026-09-17T07:12:41.487765+00:00" template="error-ratio" baseline="2026-09-17T06:05:49.678235+00:00..2026-09-17T06:39:15.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The hop that mattered

Ten sampled traces from just after T+2m gave the clean answer. In every trace exactly one child of prepareOrderItemsAndShippingQuoteFromCart carried ERROR status: the client span for ShippingService/GetQuote, propagating up through checkoutservice/PlaceOrder, frontend/PlaceOrder and the HTTP POST root. That span was a leaf in all ten traces — duration equal to self-time, around 2-3ms, with no shippingservice server child — so the call failed at or before shipping. Checkoutservice's own self-time was negligible (0.1ms on PlaceOrder), removing local computation, GC and CPU starvation from suspicion. Cartservice with its Redis HGET, currencyservice/Convert, and productcatalogservice/GetProduct with its nested flag lookup all completed OK sub-3ms in every trace. Frontend was cleared because the error originates at the deepest errored span. Root durations of 6-12ms confirm an error incident, not a latency one.

> Evidence `tr_a5836b015606`:

```
<tool_result id="tr_a5836b015606" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T06:09:15.583000+00:00..2026-09-17T07:12:41.487765+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 146 spans; offsets are from each trace's root

trace 941e7d4546f06a94  root frontend/HTTP POST  9.3ms  started 2026-09-17T07:11:52.276011+00:00  21 spans
  +0.0ms frontend/HTTP POST 9.3ms [self 0.1ms]  ERROR
```

## Cause and what stays open

Shippingservice logs closed it. At T-30m the service logged normal GetQuote and ShipOrder handling with quote amounts and tracking IDs from a Rust-style logger. From about T-3m to T+3m the only output under that label was repeated JVM and OpenTelemetry-javaagent startup banners every 30-60s, with no inbound GetQuote lines and no error, panic or rejection lines. Log delivery was clearly working, so the missing request lines are an absence of handling, not an observability gap. The change record explains it: at roughly T-3m an automated actor updated the image reference to a tag naming a different service's artifact. The pod is running the wrong application, so there is no GetQuote listener and checkoutservice's client call fails as a leaf. Fix class is rollback of that image reference. A QUOTE_SERVICE_ADDR variable pointing at a non-existent host was added at T-25m and reverted at T-13m — a red herring for the live failure, though runtime confirmation of the revert was never obtained. Checkoutservice had no recorded changes, but that query window began at onset and never covered the preceding hours, so a pre-onset change there is unexamined rather than absent. Also unsettled: whether the wrong image is crash-looping or starting cleanly as the other service and merely not exposing the shipping gRPC endpoint (no restart-count or resource metrics retrieved); whether the shipping label aggregates two workloads, given the runtime change in the log stream; and why checkoutservice logs suggested hanging requests while traces show fast-failing roots.

> Evidence `tr_d34629c643fb`:

```
<tool_result id="tr_d34629c643fb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T06:39:15.583000+00:00..2026-09-17T07:12:41.487765+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T06:39:22.048730+00:00  06:39:22 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-d9ab4d1d49c4ed5658fe1991124ba206-95582c5c78c7bf0b-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1600 Amphitheatre Parkway", city: "Mountain View", state: "CA", country: "United States", zip_code: "94043" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 3 }] }, extensions: Extensions }
2026-09-17T06:39:22.058259+00:00  06:39:22 [INFO] Sending Quote: 26.70
2026-09-17T06:39:22.062347+00:00  06:39:22 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-d9ab4d1d49c4ed5658fe1991124ba206-bcd5bd4b628d2c67-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1600 Amphitheatre Parkway", city: "Mountain View", state: "CA", country: "United States", zip_code: "94043" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 3 }] }, extensions: Extensions }
2026-09-17T06:39:22.062353+00:00  06:39:22 [INFO] Tracking ID Created: 7fee94a3-ec96-42bd-aaf0-d77768cef4a1
```

> Evidence `tr_e10b02239329`:

```
<tool_result id="tr_e10b02239329" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T07:09:15.583000+00:00..2026-09-17T07:12:41.487765+00:00" radius="candidate_cause" hops="1">
service: shippingservice
3 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T07:06:26.505480+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-17T06:55:51.732533+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_de3b09d5ab74`:

```
<tool_result id="tr_de3b09d5ab74" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T07:09:15.583000+00:00..2026-09-17T07:12:41.487765+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_de3b09d5ab74>
```

