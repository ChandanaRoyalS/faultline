# Checkout order flow halts at the shipping quote hop

## What we saw first

The page arrived from three places at once — checkoutservice, frontend, and loadgenerator — with checkoutservice named as the origin and a blast radius of twelve services. The presenting symptom was orders that started and never finished. From the responder's chair the first useful observation was that nothing looked dead: checkout was still accepting requests and writing an order-placement line for each one right through the end of the observation window at roughly T+3m. What had vanished was everything that normally follows: the payment line, the confirmation-email line, the message-write line. In the pre-onset sample those four lines travel together; after onset the first one arrives alone, ~32 times in a row.

> Evidence `tr_728eaeaa1680`:

```
<tool_result id="tr_728eaeaa1680" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T14:51:33.049306+00:00  {"message":"[PlaceOrder] user_id=\"460e1a58-b2a7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T14:51:33.049151209Z"}
2026-09-17T14:51:33.066621+00:00  {"message":"payment went through (transaction_id: c84650bf-be9f-4245-a928-3ba4d81ce7fe)","severity":"info","timestamp":"2026-09-17T14:51:33.066529001Z"}
2026-09-17T14:51:33.072811+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-17T14:51:33.072680959Z"}
2026-09-17T14:51:33.073615+00:00  {"message":"Successful to write message. offset: 64973","severity":"info","timestamp":"2026-09-17T14:51:33.073555543Z"}
```

## The first dead end: checkoutservice's own change history

The instinct was to look for something shipped to checkoutservice. The change log for the service across the full preceding day came back completely empty — no rollouts, no config edits, no flag flips. That closed four theories in one query: there was no deploy to blame, no flag to unflip, no version to roll back to (a rollback here would have had no target), and any eventual recovery would not have been the result of a corrective change to this service. Worth noting for the next responder: that query was scoped to the seed service only, zero hops. It said nothing about its immediate dependencies, and the answer was sitting one hop away the whole time.

> Evidence `tr_ee62daef3e7d`:

```
<tool_result id="tr_ee62daef3e7d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T15:21:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_ee62daef3e7d>
```

## The second dead end: the error-ratio baseline

The checkoutservice error ratio did roughly double against the prior six hours — mean 0.032 to 0.072 — which looked promising for about five minutes and then actively misled. The elevation was episodic, not a step: six separate threshold crossings scattered across six hours with clean recovery between them, which is the wrong shape for a single discrete event and the wrong shape for progressive resource starvation too. Peak values landed on suspiciously exact fractions (2/3, 1/2, 1/5), consistent with very small request counts per interval, so individual spikes carried little weight as severity signals. Several intervals had no requests recorded at all — in the baseline window as well as the incident one. The one durable takeaway is that failing checkouts predate the incident; only the rate changed. This series is not where the onset moment lives.

> Evidence `tr_75c73d19dc55`:

```
<tool_result id="tr_75c73d19dc55" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T03:21:30.583000+00:00..2026-09-17T09:21:30.583000+00:00" template="error-ratio" baseline="2026-09-16T21:21:30.583000+00:00..2026-09-17T03:21:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=1179 mean=0.07197 min=0 max=0.6667 sd=0.1811
  baseline window: n=349 mean=0.0324 min=0 max=0.5 sd=0.04976
```

## The third dead end: cart and Redis

Trace sampling surfaced a slow request at roughly T-13m: 670ms end to end, dominated by two cartservice Redis operations at about 301ms of self-time each, no errors anywhere in it. It is a genuine latency signature and it is unrelated. In every failing trace after onset the CartService/GetCart child and its Redis read complete in well under a millisecond and carry no error status — the cart hop is healthy in exactly the requests that fail. Same story for product catalog and currency conversion: GetProduct and Convert children are present, all sub-4ms, all clean. Payment, email, ad, and recommendation never appear at all in the failing traces, so none of them could be the origin.

> Evidence `tr_5a04b0440243`:

```
<tool_result id="tr_5a04b0440243" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00">
service: checkoutservice
9 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 6f1d97fec80eca9a  root frontend/HTTP POST  670.9ms  started 2026-09-17T15:08:48.769017+00:00  48 spans
  +0.0ms frontend/HTTP POST 670.9ms [self 0.0ms]
```

## The hop that actually failed

Eight failing traces between T+2m and T+3m all carried the error on the same child span: checkoutservice's client span for ShippingService/GetQuote, flagged as the degrading hop every time. The failure mode was error status, not delay — failing roots finished in 8–20ms and the erroring quote spans were 2.5–4.3ms, indistinguishable in duration from healthy ones. The root PlaceOrder terminates inside prepareOrderItemsAndShippingQuoteFromCart with no payment, email, EmptyCart, ShipOrder, or order-publish children emitted, which matches the truncated log shape exactly. checkoutservice's own self-time across the failing spans was 0.1–0.8ms; it was not burning time or generating the failure itself.

> Evidence `tr_5a04b0440243`:

```
<tool_result id="tr_5a04b0440243" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00">
service: checkoutservice
9 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 6f1d97fec80eca9a  root frontend/HTTP POST  670.9ms  started 2026-09-17T15:08:48.769017+00:00  48 spans
  +0.0ms frontend/HTTP POST 670.9ms [self 0.0ms]
```

> Evidence `tr_728eaeaa1680`:

```
<tool_result id="tr_728eaeaa1680" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T14:51:33.049306+00:00  {"message":"[PlaceOrder] user_id=\"460e1a58-b2a7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T14:51:33.049151209Z"}
2026-09-17T14:51:33.066621+00:00  {"message":"payment went through (transaction_id: c84650bf-be9f-4245-a928-3ba4d81ce7fe)","severity":"info","timestamp":"2026-09-17T14:51:33.066529001Z"}
2026-09-17T14:51:33.072811+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-17T14:51:33.072680959Z"}
2026-09-17T14:51:33.073615+00:00  {"message":"Successful to write message. offset: 64973","severity":"info","timestamp":"2026-09-17T14:51:33.073555543Z"}
```

## Upstream: shippingservice is alive and silently incomplete

shippingservice logs told the clearest story in the record. Before onset, each inbound GetQuote is followed within milliseconds by a quote-sent line, and ship-order calls are followed by tracking-ID creation. After onset, every inbound GetQuote is logged and none of them are followed by anything — no quote-sent line, no ship-order activity, no tracking IDs. Severity across the whole tail is INFO only: no errors, no warnings, no panic or stack trace, no startup or config-load failure banner, no restart. Requests keep arriving every few seconds through the end of the window. That rules out a crash loop, a rejected-payload theory (post-onset requests carry well-formed addresses and cart items, shaped identically to the ones that succeeded earlier), a startup failure, and upstream traffic loss. The service can accept a quote request and can no longer produce a quote, quietly.

> Evidence `tr_253b1eca761e`:

```
<tool_result id="tr_253b1eca761e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T14:51:33.054609+00:00  14:51:33 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-988f7da37a3322ef21437d875998c205-4161515b65b87720-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "L9ECAV7KIM", quantity: 12 }] }, extensions: Extensions }
2026-09-17T14:51:33.063672+00:00  14:51:33 [INFO] Sending Quote: 133.50
2026-09-17T14:51:33.067479+00:00  14:51:33 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-988f7da37a3322ef21437d875998c205-09b1145862291f16-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "L9ECAV7KIM", quantity: 12 }] }, extensions: Extensions }
2026-09-17T14:51:33.067494+00:00  14:51:33 [INFO] Tracking ID Created: 99b44302-881e-4077-be3c-2c119a126d53
```

## The change

shippingservice's change history, unlike checkout's, was populated: nine entries in the preceding day, all attributed to platform-automation and none to a human. The one nearest onset is an environment edit landing about T-2m that set QUOTE_SERVICE_ADDR to an address naming a quote host that the value itself signals is absent. It has no paired revert inside the window, so it was still in effect at onset. The same value had been applied and reverted twice before in the same day — roughly T-8h36m and T-3h48m, each backed out within about an hour — so this is a recurring automation loop rather than a one-off. Two image-reference changes to an adservice-tagged demo image also appear, but both were reverted and the last revert landed about T-3h18m, so no image change was in effect at onset and the image path does not correlate with the timing.

> Evidence `tr_4891b42b3bd9`:

```
<tool_result id="tr_4891b42b3bd9" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T15:21:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" radius="candidate_cause" hops="1">
service: shippingservice
9 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T15:19:07.989505+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
  #2  3.3h before onset  2026-09-17T12:05:11.498783+00:00  platform-automation  image reverted: image reference reverted on shippingservice
```

## What is still not proven

Three gaps a future responder should not inherit as settled. First, nothing in the evidence directly observes shippingservice failing to reach the configured host: there is no connection or DNS error line, and the reqwest-http-client child span beneath the shipping server span is not marked ERROR in any failing trace. The error status attaches at the checkoutservice-to-shipping boundary rather than propagating up from a failed shipping server span, so the link from the changed value to the missing quote is inferred from timing and log shape, not observed. Second, shippingservice has no call-count or error-ratio samples in either the incident or baseline window — the series is simply absent, which means its request rate, restart count and readiness are unmeasured, and the metric pipeline for that service may itself be broken. Metric-only triage on shippingservice is blocked until someone checks whether the exporter is emitting. Third, the checkout log query truncated across the onset minute itself (oldest 8 lines and newest 32 retained, middle discarded), so no line at or near onset was ever read; a severity-filtered or narrowly bounded query would have done better than the broad service selector.

> Evidence `tr_5a04b0440243`:

```
<tool_result id="tr_5a04b0440243" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00">
service: checkoutservice
9 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 6f1d97fec80eca9a  root frontend/HTTP POST  670.9ms  started 2026-09-17T15:08:48.769017+00:00  48 spans
  +0.0ms frontend/HTTP POST 670.9ms [self 0.0ms]
```

> Evidence `tr_479f55d42c39`:

```
<tool_result id="tr_479f55d42c39" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" template="error-ratio" baseline="2026-09-17T14:18:18.726140+00:00..2026-09-17T14:51:30.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_728eaeaa1680`:

```
<tool_result id="tr_728eaeaa1680" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T14:51:33.049306+00:00  {"message":"[PlaceOrder] user_id=\"460e1a58-b2a7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T14:51:33.049151209Z"}
2026-09-17T14:51:33.066621+00:00  {"message":"payment went through (transaction_id: c84650bf-be9f-4245-a928-3ba4d81ce7fe)","severity":"info","timestamp":"2026-09-17T14:51:33.066529001Z"}
2026-09-17T14:51:33.072811+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-17T14:51:33.072680959Z"}
2026-09-17T14:51:33.073615+00:00  {"message":"Successful to write message. offset: 64973","severity":"info","timestamp":"2026-09-17T14:51:33.073555543Z"}
```

## Remediation and the trap in it

Fix class is a config revert: restore QUOTE_SERVICE_ADDR on shippingservice to its prior value. The trap is that the automation loop has re-applied this same value twice before after it was backed out, so a revert may be undone without anyone touching it — and because shippingservice emits no error output and has no metric series, the re-application would be nearly invisible. Whoever reverts should also disable or pin the automation path that keeps writing the value, and should confirm recovery by watching for the quote-sent completion lines returning in shippingservice logs rather than by watching any dashboard.

> Evidence `tr_4891b42b3bd9`:

```
<tool_result id="tr_4891b42b3bd9" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T15:21:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" radius="candidate_cause" hops="1">
service: shippingservice
9 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T15:19:07.989505+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
  #2  3.3h before onset  2026-09-17T12:05:11.498783+00:00  platform-automation  image reverted: image reference reverted on shippingservice
```

> Evidence `tr_253b1eca761e`:

```
<tool_result id="tr_253b1eca761e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T14:51:33.054609+00:00  14:51:33 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-988f7da37a3322ef21437d875998c205-4161515b65b87720-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "L9ECAV7KIM", quantity: 12 }] }, extensions: Extensions }
2026-09-17T14:51:33.063672+00:00  14:51:33 [INFO] Sending Quote: 133.50
2026-09-17T14:51:33.067479+00:00  14:51:33 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-988f7da37a3322ef21437d875998c205-09b1145862291f16-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1355 Market St", city: "San Francisco", state: "CA", country: "United States", zip_code: "94103" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "L9ECAV7KIM", quantity: 12 }] }, extensions: Extensions }
2026-09-17T14:51:33.067494+00:00  14:51:33 [INFO] Tracking ID Created: 99b44302-881e-4077-be3c-2c119a126d53
```

> Evidence `tr_479f55d42c39`:

```
<tool_result id="tr_479f55d42c39" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T14:51:30.583000+00:00..2026-09-17T15:24:42.439860+00:00" template="error-ratio" baseline="2026-09-17T14:18:18.726140+00:00..2026-09-17T14:51:30.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

