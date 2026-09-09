# Checkout order failures traced to shippingservice quote-address configuration

## What was visible, and the two dead ends

The page fired on checkoutservice, with parallel alerts from accountingservice, emailservice, frauddetectionservice, quoteservice and loadgenerator; twelve services in the blast radius, severity critical. quoteservice appearing in that list pulled early attention toward it, wrongly.

The first hard measurement was checkoutservice's error ratio: baseline mean ~0.0014 against ~0.048 in the incident window, roughly 34x, with a clean change point at T+0. Onset was abrupt, killing any slow-degradation theory. It was also bursty - peak ~0.28, standard deviation above the mean, some two-minute buckets entirely clean - so checkoutservice was not hard-down and "everything fails" was not available as a shortcut.

First dead end: checkoutservice's own change log came back completely empty. That looked stronger than it was. The query was seed-only with zero dependency hops, so cartservice, productcatalogservice, currencyservice and paymentservice were never covered, and the window opened *at* onset, so anything landing minutes prior fell outside it. Recognising that gap is what forced the search outward.

Second dead end: checkoutservice's logs name nobody. Every line was info severity - no errors, no status codes, no dependency named. What they did show was truncation: early in the window each order ran start, payment with transaction id, email, queue write with increasing offset; from about T+4m only the order-start line appeared. That ruled out a crash, a traffic stop, an upstream/ingress break (checkout logged every entry), a currency-specific problem (USD and CAD both truncated), and a publish-only failure (payment and email lines were missing too, placing the break at or before payment).

> Evidence `tr_b57a1efb2e83`:

```
<tool_result id="tr_b57a1efb2e83" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T19:22:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" template="error-ratio" baseline="2026-09-08T18:47:33.704217+00:00..2026-09-08T19:22:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=140 mean=0.04792 min=0 max=0.2826 sd=0.09904
  baseline window: n=140 mean=0.001413 min=0 max=0.1053 sd=0.01033
```

> Evidence `tr_e02cf4febc25`:

```
<tool_result id="tr_e02cf4febc25" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T19:52:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_e02cf4febc25>
```

> Evidence `tr_89b911dc756c`:

```
<tool_result id="tr_89b911dc756c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:22:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T19:22:38.464077+00:00  {"message":"[PlaceOrder] user_id=\"a74dcef6-abba-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T19:22:38.463951336Z"}
2026-09-08T19:22:38.480078+00:00  {"message":"payment went through (transaction_id: 398e896d-b01e-4565-9ee7-14d0687d3a63)","severity":"info","timestamp":"2026-09-08T19:22:38.480004086Z"}
2026-09-08T19:22:38.484561+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-08T19:22:38.484469586Z"}
2026-09-08T19:22:38.485406+00:00  {"message":"Successful to write message. offset: 15626","severity":"info","timestamp":"2026-09-08T19:22:38.485338211Z"}
```

## Traces and shipping logs localise the hop

Traces named the edge. In both failing checkout traces the first ERROR span below the checkout root was checkoutservice's client call to ShippingService/GetQuote, propagating up through PlaceOrder to the frontend root. GetCart, GetProduct and Convert all started earlier and completed clean, eliminating cartservice, productcatalogservice and currencyservice in one pass. paymentservice went too: failing traces held only ~13-14 spans with no Charge, ShipOrder, EmptyCart or email spans at all. The failure was in quoting, not the ShipOrder path.

One detail misleads. The shippingservice *server* span was not marked ERROR - the error sat on checkout's client span, while shipping's work truncated at its outbound HTTP client hop instead of reaching its downstream quote call. Anyone expecting the error stamped on the failing server would look straight past this. In the same window's non-error traces, that same quote hop was already the dominant latency contributor at ~20-25% of trace self-time.

shippingservice's logs mirrored checkout's: info only, no errors, no timeouts, and critically no connection-failure line from its HTTP client. If you go looking for shipping to name its own broken dependency you will find nothing. Early in the window each inbound quote request produced a quote-sent line within ~10ms then a ship-order line with a tracking id; from T+4m inbound quote requests kept arriving every few seconds with not one quote-sent line. Requests were well-formed with valid traceparents, so ingress and parsing were intact and the process never restarted.

> Evidence `tr_f1ed1bc7307c`:

```
<tool_result id="tr_f1ed1bc7307c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T19:22:30.583000+00:00..2026-09-08T19:57:27.461783+00:00">
service: checkoutservice
6 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 9951d43b512dc100  root frontend/HTTP POST  24.2ms  started 2026-09-08T19:43:27.203010+00:00  50 spans
  +0.0ms frontend/HTTP POST 24.2ms [self 0.0ms]
```

> Evidence `tr_0c78921f0445`:

```
<tool_result id="tr_0c78921f0445" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:22:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-08T19:22:38.468748+00:00  19:22:38 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-bdcd8f885324bf6f5c380f653ecd7263-4ecdf7946c88e9c7-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "100 Winchester Circle", city: "Los Gatos", state: "CA", country: "United States", zip_code: "95032" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 4 }] }, extensions: Extensions }
2026-09-08T19:22:38.477032+00:00  19:22:38 [INFO] Sending Quote: 35.60
2026-09-08T19:22:38.480847+00:00  19:22:38 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-bdcd8f885324bf6f5c380f653ecd7263-a9009b9949f002b2-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "100 Winchester Circle", city: "Los Gatos", state: "CA", country: "United States", zip_code: "95032" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 4 }] }, extensions: Extensions }
2026-09-08T19:22:38.480852+00:00  19:22:38 [INFO] Tracking ID Created: 50118049-0cf0-4ee4-bec4-aa547e1d2e8d
```

## The cause, and what remains unmeasured

shippingservice's change history was not empty. Platform-automation set QUOTE_SERVICE_ADDR to a host named as though the quote service no longer existed, roughly two minutes before onset - the closest change to onset and the only one in the final hour. The same edit had been applied and reverted three times earlier that day, each revert within 10-20 minutes; this final application had no matching revert, so the bad address was live at onset. That disposed of both the hope that it had already been rolled back and the theory of latent long-standing state.

The image reference changes in the same log were a distraction: three of them, each pointing at a demo tag for a different service, each reverted, the most recent ending ~12.2 hours before onset. The running image had been stable for over half a day, so no code rollout explains this. All thirteen changes came from the same automated actor, which also rules out an unreviewed manual human change. quoteservice's change log was empty, removing it as trigger, active rollout, or source of recovery.

Mechanism: a configuration value naming a destination that does not exist, so the quote call never completes, so checkout aborts before payment and the payment, email and queue consumers go quiet. Fix class is a configuration revert. Confidence high.

Still open for the next responder. quoteservice was never probed directly for health - its innocence rests on an empty change log, not a positive signal. The burstiness with a ~0.28 peak rather than near-total failure is unexplained; partial replica rollout or retries are plausible but no per-replica breakdown exists. And shippingservice span-metrics returned nothing in *both* windows, so shipping-side error rate and GetQuote latency are simply unmeasured. Note the baseline was equally empty, which points at a missing or mislabelled series rather than traffic stopping - do not read that absence as evidence of anything. It also means we do not know whether a reverted value takes effect without a restart.

> Evidence `tr_be915e3e37f1`:

```
<tool_result id="tr_be915e3e37f1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T19:52:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" radius="also_affected" hops="1">
service: shippingservice
13 changes, ranked by suspicion
  #1  2m before onset  2026-09-08T19:49:32.098926+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
  #2  12.2h before onset  2026-09-08T07:40:53.572919+00:00  platform-automation  image reverted: image reference reverted on shippingservice
```

> Evidence `tr_be1a0f4b5fdf`:

```
<tool_result id="tr_be1a0f4b5fdf" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T19:52:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" radius="seed" hops="0">
no changes recorded for quoteservice over this window
</tool_result:tr_be1a0f4b5fdf>
```

> Evidence `tr_a3ea319834fe`:

```
<tool_result id="tr_a3ea319834fe" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T19:22:30.583000+00:00..2026-09-08T19:57:27.461783+00:00" template="error-ratio" baseline="2026-09-08T18:47:33.704217+00:00..2026-09-08T19:22:30.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

