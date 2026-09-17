# Checkout failures traced to a shipping quote address change

## What we saw first

The page came from two places at once: checkoutservice and the loadgenerator. From the responder's chair that combination reads as customer-visible checkout breakage rather than a background job problem, and the blast radius as drawn covered ten services with checkoutservice as the entry point. Four of the edges crossed during the walk had no measurement behind them, which mattered later — several of the exonerations below rest on traces rather than metrics because the metrics simply were not there.

The first instinct was to treat checkoutservice as the origin. That instinct was wrong, but it took three queries to establish that.

## Ruling out checkoutservice itself

At about T+3m we pulled the change history for checkoutservice across a full day. It came back empty — not filtered, genuinely empty. No deploys, no config edits, no flag flips, no image-reference bumps, no rollbacks. That single empty answer killed four hypotheses at once and is worth remembering: an empty change log for the alerting service is a cheap, high-value result.

Next we looked at checkoutservice's error ratio over a three-hour span. This is the dead end that cost the most time. The mean rose from roughly 0.05 to 0.07 — a real but unimpressive 1.4x — with wide variance in both windows and excursions as high as 0.67 on isolated samples. Crucially, change-point detection found steps at two earlier points in the morning and nothing at all near the time of interest. Intermittent checkout errors predated the incident, so the metric could neither confirm onset nor tell us which outbound call degraded first. Anyone re-reading this should not expect the error-ratio series to mark the start; the onset timing in this record comes from the alert and the change log, not from Prometheus.

The checkoutservice logs were more useful, though obliquely. The returned tail showed only info-level order-start entries — no errors, no warnings, no panics, nothing naming a dependency or a credential. But the shape had changed: early in the window each order produced four lines (order start, payment, confirmation email, message-write offset), while late orders produced only the first line. Orders were still arriving steadily with distinct user ids, so the process was alive, traffic was flowing, and log shipping was intact. The conclusion was that orders were stalling after PlaceOrder began, inside the item-and-quote preparation step, before payment or email were ever reached. Note the coverage limit: the result kept only the oldest few and newest few dozen lines, so the middle of the window, including the onset itself, was never observed.

> Evidence `tr_233bf12317e1`:

```
<tool_result id="tr_233bf12317e1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T11:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_233bf12317e1>
```

> Evidence `tr_c992ab65bf62`:

```
<tool_result id="tr_c992ab65bf62" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T08:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00" template="error-ratio" baseline="2026-09-17T05:35:18.496931+00:00..2026-09-17T08:38:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=720 mean=0.07037 min=0 max=0.6667 sd=0.1907
  baseline window: n=483 mean=0.05103 min=0 max=0.3158 sd=0.1006
```

> Evidence `tr_d98de2cef145`:

```
<tool_result id="tr_d98de2cef145" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T10:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T10:38:02.931481+00:00  {"message":"[PlaceOrder] user_id=\"dc1f2ae2-b283-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T10:38:02.931385Z"}
2026-09-17T10:38:02.947366+00:00  {"message":"payment went through (transaction_id: 5677fd93-6b22-4321-a8ad-80cd1e1c033d)","severity":"info","timestamp":"2026-09-17T10:38:02.947254292Z"}
2026-09-17T10:38:02.951248+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-17T10:38:02.951124917Z"}
2026-09-17T10:38:02.951943+00:00  {"message":"Successful to write message. offset: 63284","severity":"info","timestamp":"2026-09-17T10:38:02.951888292Z"}
```

## Traces name the hop

The traces were the turning point. Across eleven shown failing checkout traces, ten carried the error on a single span: the checkoutservice client span for the shipping GetQuote call. It was the only errored child under the item-and-quote preparation step, and the error flowed straight up through PlaceOrder, the frontend gRPC span, and the frontend HTTP root.

Just as valuable is what the traces exonerated. Cart and its redis HGET completed cleanly every time. Product catalog, including its flag lookup fan-out, stayed under about a millisecond with no error flag. Currency conversion returned effectively instantly. No email or payment child spans appeared at all — consistent with the log shape, since checkout never got that far. And this was not a latency problem: root durations sat between eight and eleven milliseconds, with the shipping hop contributing only a few milliseconds. Whoever arrives expecting timeouts and second-long hangs should discard that model early.

Two caveats we deliberately left in. First, the shippingservice server span and its own downstream HTTP client span carried no error flag in any shown trace, so the failure surfaces at the caller's boundary and not inside shipping's recorded work. Second, one failing trace had no shipping call in it whatsoever and still errored, with almost all the time spent in the frontend-to-checkout edge and self time in the preparation step. So shipping does not fully explain the failure population. Coverage was eleven of forty traces; the pattern is established for the sample, not proven for all of it.

> Evidence `tr_00cb71419679`:

```
<tool_result id="tr_00cb71419679" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T10:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00">
service: checkoutservice
11 trace(s) shown of 40 found, 200 spans; offsets are from each trace's root

trace 14ebb5796dd6e32d  root frontend/HTTP POST  10.2ms  started 2026-09-17T11:38:18.470015+00:00  19 spans
  +0.0ms frontend/HTTP POST 10.2ms [self 0.1ms]  ERROR
```

## The change that explains it

With shipping named, we pulled its change history. Five records, all attributed to the same automated actor. The most recent sat roughly two minutes before onset: an environment variable update repointing the quote-service address at a host whose very name says it is no longer a live backend. That is the cause as we understand it.

The history around it is instructive. The same value had been set earlier that morning and then withdrawn a few hours before onset, which rules out any story about delayed impact from the earlier edit — it was not in effect until it was re-applied. An image-reference change was also applied and reverted hours before onset, leaving the running image unchanged at the time of failure, so this is not a code rollout. No flag toggles appear. No human operator appears.

The honest gap: the change log records the edit, not its runtime effect. Nothing in shipping's logs, metrics, or spans directly records a call failing against that address. Causation here is inferred from proximity plus the trace evidence, which is why confidence is medium rather than high.

> Evidence `tr_df91c2ae7515`:

```
<tool_result id="tr_df91c2ae7515" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T11:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00" radius="candidate_cause" hops="1">
service: shippingservice
5 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T11:35:08.422818+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
  #2  4.4h before onset  2026-09-17T07:16:35.437212+00:00  platform-automation  image reverted: image reference reverted on shippingservice
```

## Dead ends on the shipping side

Two shipping-side queries produced results that look like exonerations and are not.

The shipping log query was run against a window starting roughly a day before onset and covering six hours. Within it, every retained line was info-level: quote requests, quote amounts issued, ship orders, tracking IDs created, all healthy at both ends of the window, all carrying synthetic load-generator baggage. On that basis we ruled out a crash or restart at the window boundary, ruled out unimplemented gRPC methods, and ruled out shipping as an error source. All of that is true — of the wrong day. These findings do not describe the incident window and should not be cited as evidence that shipping was healthy during the incident. The same result was also truncated to its oldest and newest lines, so most of its own six hours went unobserved.

The shipping error-ratio metric returned no samples at all, in either the incident window or its baseline. Because both windows were empty, the right reading is that the underlying call-count series does not exist for this service — a label or instrumentation mismatch, or the service not reporting — rather than telemetry collapsing at onset. Request rate, restart count, and per-method failure rate were never measured. Do not read the empty result as a flat, healthy line; it exonerates nothing.

> Evidence `tr_e2347fd30d25`:

```
<tool_result id="tr_e2347fd30d25" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-16T11:38:00.583000+00:00..2026-09-16T17:38:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="shipping-service"}
2026-09-16T11:40:46.755692+00:00  11:40:46 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-7c180a4050eb37181129d67bd8472533-dc5aebf0c4c94dea-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 4 }, CartItem { product_id: "LS4PSXUNUM", quantity: 2 }, CartItem { product_id: "66VCHSJNUP", quantity: 5 }] }, extensions: Extensions }
2026-09-16T11:40:46.768533+00:00  11:40:46 [INFO] Sending Quote: 97.90
2026-09-16T11:40:46.774771+00:00  11:40:46 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-7c180a4050eb37181129d67bd8472533-50cce27c556ee223-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 4 }, CartItem { product_id: "LS4PSXUNUM", quantity: 2 }, CartItem { product_id: "66VCHSJNUP", quantity: 5 }] }, extensions: Extensions }
2026-09-16T11:40:46.774786+00:00  11:40:46 [INFO] Tracking ID Created: 2227ef09-608f-4ff8-8bee-6e6c8d17cf9b
```

> Evidence `tr_137f717fbf1e`:

```
<tool_result id="tr_137f717fbf1e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T11:08:00.583000+00:00..2026-09-17T11:40:42.669069+00:00" template="error-ratio" baseline="2026-09-17T10:35:18.496931+00:00..2026-09-17T11:08:00.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where it stands and what to do

The remedy is a config revert: restore the shipping quote-service address environment variable to the value it held before the pre-onset edit. The wrong value is itself the failure, so no code change or rollback is required.

Open items for whoever picks this up. Nothing directly observes a request failing against the dead address; if that path can be instrumented, the inference chain closes. Onset timing rests on the alert and the change record, not on any metric change point. Trace coverage was partial, and at least one failing checkout had no shipping involvement, so there may be a second, smaller failure path in the preparation step worth a look. Finally, the repeated apply-revert-reapply pattern from the automated change pipeline is a finding in its own right — the same bad value reached production twice in one morning.

> Evidence `tr_df91c2ae7515`:

```
<tool_result id="tr_df91c2ae7515" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T11:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00" radius="candidate_cause" hops="1">
service: shippingservice
5 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T11:35:08.422818+00:00  platform-automation  environment updated: QUOTE_SERVICE_ADDR updated on shippingservice
      None  ->  QUOTE_SERVICE_ADDR=http://quoteservice-gone:8090
  #2  4.4h before onset  2026-09-17T07:16:35.437212+00:00  platform-automation  image reverted: image reference reverted on shippingservice
```

> Evidence `tr_00cb71419679`:

```
<tool_result id="tr_00cb71419679" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T10:38:00.583000+00:00..2026-09-17T11:40:42.669069+00:00">
service: checkoutservice
11 trace(s) shown of 40 found, 200 spans; offsets are from each trace's root

trace 14ebb5796dd6e32d  root frontend/HTTP POST  10.2ms  started 2026-09-17T11:38:18.470015+00:00  19 spans
  +0.0ms frontend/HTTP POST 10.2ms [self 0.1ms]  ERROR
```

