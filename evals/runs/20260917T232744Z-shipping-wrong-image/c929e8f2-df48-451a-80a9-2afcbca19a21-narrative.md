# Checkout aborts at the shipping quote hop after an unreverted image swap

## What was visible, and the dead ends

The page named checkoutservice as the origin: twelve services in the blast radius, seven alerting, five unmeasured edges between them. Treating checkoutservice as the broken thing is the expensive mistake here.

Its change history came back empty - no deploys, config edits, or flag flips - though note the queried window began at onset and ran forward, never sampling the hours before it. Its error-ratio metric moved only from about 6.5% baseline to 7.9%, inside one standard deviation, with identical peaks in both windows and change points only two-plus hours before onset; no request-rate, latency, or saturation series came back at all. cartservice also looked alarming and was not relevant: 32 automated entries showing a repeating four-hourly cycle of image swap, an egress-delay sidecar, and a Redis address override - every one of them reverted, the last activity ending roughly 1.9 hours before onset.

> Evidence `tr_83d62c4c189e`:

```
<tool_result id="tr_83d62c4c189e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T23:30:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_83d62c4c189e>
```

> Evidence `tr_ec16a83cabf8`:

```
<tool_result id="tr_ec16a83cabf8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:30:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" template="error-ratio" baseline="2026-09-17T17:25:32.588047+00:00..2026-09-17T20:30:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=740 mean=0.07854 min=0 max=0.6667 sd=0.1824
  baseline window: n=740 mean=0.06513 min=0 max=0.6667 sd=0.157
```

> Evidence `tr_a5de874d209c`:

```
<tool_result id="tr_a5de874d209c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T23:30:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" radius="candidate_cause" hops="1">
service: cartservice
32 changes, ranked by suspicion
  #1  1.9h before onset  2026-09-17T21:34:54.124304+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  2.1h before onset  2026-09-17T21:26:54.144037+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## What localized it

Ten sampled failing traces, spanning roughly T+4m to T+5m, all had one shape: frontend POST, frontend PlaceOrder, and checkoutservice PlaceOrder marked in error, with the only erroring leaf being checkout's client span for ShippingService GetQuote. No shippingservice server span existed on the other end in any trace - the client span was all self-time. Whole traces ran 6.4-11.4ms and the erroring hop 0.5-2.7ms, so this fails fast; drop any timeout or slow-dependency theory. cartservice, currencyservice, and productcatalogservice all completed cleanly, and paymentservice never appears at all because checkout aborts before reaching it.

Checkout's own logs agree but name nobody: all info severity, early orders showing placement plus payment, email, and broker write within ~25ms, late orders showing placement alone. The process stayed alive and logging throughout. The result was truncated, so onset itself was never directly read.

> Evidence `tr_89bcb0420124`:

```
<tool_result id="tr_89bcb0420124" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T23:00:30.583000+00:00..2026-09-17T23:35:28.577953+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 147 spans; offsets are from each trace's root

trace 39547a0b41dee5e8  root frontend/HTTP POST  7.4ms  started 2026-09-17T23:34:36.028009+00:00  16 spans
  +0.0ms frontend/HTTP POST 7.4ms [self 0.1ms]  ERROR
```

> Evidence `tr_642597894060`:

```
<tool_result id="tr_642597894060" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T23:00:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T23:00:36.207564+00:00  {"message":"[PlaceOrder] user_id=\"97eddb8a-b2eb-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T23:00:36.207471013Z"}
2026-09-17T23:00:36.225253+00:00  {"message":"payment went through (transaction_id: d38df5c6-47a9-4668-8d3e-5afcbcff8b14)","severity":"info","timestamp":"2026-09-17T23:00:36.225174597Z"}
2026-09-17T23:00:36.229794+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-17T23:00:36.229688097Z"}
2026-09-17T23:00:36.230531+00:00  {"message":"Successful to write message. offset: 68110","severity":"info","timestamp":"2026-09-17T23:00:36.230453263Z"}
```

## The cause and what stays open

About 2m37s before onset, platform-automation repointed shippingservice's image reference at an unrelated adservice-tagged demo artifact. Nineteen automated changes sit in that log, cycling between a bogus quote-service address and this image swap; the cycle completed and reverted four times earlier the same day, but this final pass was never reverted. The address variable was reverted ~13m before onset and was not in effect. Shipping's logs match: Rust-style gRPC quote handling until about T-3m, then only a repeating JVM/agent startup preamble, ten times through T+4m24s, never reaching a serving state. Fix class: rollback.

Open items for the next responder. Nobody inspected the running image digest or pod events, so the wrong-artifact claim rests on the change record plus the runtime shift in logs. The pre-onset lines are Rust and the post-onset lines are JVM, so the restart loop may belong to a different workload inheriting the label. And nothing explains why it restarts - no panic, bind failure, or memory evidence was gathered, and shippingservice has no call-count series in either window, so there is no metric-side confirmation of the cutoff.

> Evidence `tr_8df2455f0e0e`:

```
<tool_result id="tr_8df2455f0e0e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T23:30:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" radius="seed" hops="0">
service: shippingservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T23:27:53.748676+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-17T23:17:17.252452+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_0dd84f9d81f9`:

```
<tool_result id="tr_0dd84f9d81f9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T21:30:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-17T21:35:03.047546+00:00  21:35:03 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-15be5fa76a8d831181102dfc01435bd5-7229cb8ac9604636-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [] }, extensions: Extensions }
2026-09-17T21:35:03.061515+00:00  21:35:03 [INFO] Sending Quote: 0.0
2026-09-17T21:35:03.067898+00:00  21:35:03 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-15be5fa76a8d831181102dfc01435bd5-7a4d3c5f66b7f7fd-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [] }, extensions: Extensions }
2026-09-17T21:35:03.067907+00:00  21:35:03 [INFO] Tracking ID Created: d2e8e1e4-3b17-47af-a689-d45c813f48c3
```

> Evidence `tr_cb285e8828ab`:

```
<tool_result id="tr_cb285e8828ab" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T20:30:30.583000+00:00..2026-09-17T23:35:28.577953+00:00" template="error-ratio" baseline="2026-09-17T17:25:32.588047+00:00..2026-09-17T20:30:30.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

