# Checkout order placement fails at the shipping-quote hop

## What was visible, and the dead ends

The page named checkoutservice as the seed, critical, fourteen services in the blast radius. Alerting came in two waves: around T+3m accountingservice, emailservice, frauddetectionservice and quoteservice; around T+4m frontend and loadgenerator. That shape looks like a broad multi-service event and is in fact one break with consumers starving behind it.

The first instinct was that checkoutservice was failing. Its span error ratio said otherwise: no movement against the preceding hour, mean marginally lower (~0.94x), no sustained departure, no step at onset. Errors were bursty in both windows, and the larger single peak sat in the baseline. Carry the caveat forward: only the aggregate error-ratio template was evaluated, so latency and per-dependency outbound breakdown were never measured.

The second dead end was the change log for checkoutservice, which returned empty — no deploy, config edit, or flag update. It rules out an in-window checkout change, a still-landing release, and a remediation edit. But the scoping was bad and that is the useful part: the query was pinned to the seed only, zero hops, so none of the six dependencies were examined, and the window began *at* onset and ran forward a day, placing the pre-incident interval outside the range. This empty answer says almost nothing.

A third detour was paymentservice, drawn in because payment confirmations stopped appearing in logs. Its change log holds only four platform-automation edits to an OTLP traces exporter endpoint, in two set/revert pairs, net zero, the most recent ~13.6h before onset. Its error-ratio query returned no samples in either the incident window or the baseline before it — a missing series, not a stall at onset, and useless as a timing control. The traces had already shown PlaceOrder failing before payment is reached, so the absent confirmations are a consequence.

> Evidence `tr_5e157bd09087`:

```
<tool_result id="tr_5e157bd09087" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T19:15:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" template="error-ratio" baseline="2026-09-08T18:10:33.237583+00:00..2026-09-08T19:15:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=260 mean=0.07479 min=0 max=0.3091 sd=0.1152
  baseline window: n=260 mean=0.07991 min=0 max=0.6667 sd=0.2083
```

> Evidence `tr_df308219e272`:

```
<tool_result id="tr_df308219e272" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T20:15:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_df308219e272>
```

> Evidence `tr_9157b2c8f8cd`:

```
<tool_result id="tr_9157b2c8f8cd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T20:15:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" radius="candidate_cause" hops="1">
service: paymentservice
4 changes, ranked by suspicion
  #1  13.6h before onset  2026-09-08T06:40:27.688792+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317  ->  None
  #2  13.8h before onset  2026-09-08T06:29:10.994591+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
```

> Evidence `tr_f76a71bf6e67`:

```
<tool_result id="tr_f76a71bf6e67" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T19:45:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" template="error-ratio" baseline="2026-09-08T19:10:33.237583+00:00..2026-09-08T19:45:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Logs and traces: where the picture resolved

checkoutservice logs showed complete order flows early in the window — placement, then payment success, confirmation email, and a successful message write with incrementing offset. From roughly T+1m onward only the placement entries remain. Requests enter PlaceOrder and never reach completion logging. Placement entries continue to the tail, so the process was alive and serving; the path was not already broken at window start. Currency looks irrelevant — the incomplete tail orders are overwhelmingly USD, the same as the successful early ones. The cost of this query: only the oldest eight and newest thirty-two lines returned, with onset entirely inside the omitted middle. Every readable line was info severity, no stack trace, and nothing naming a host, port, endpoint or config key. A severity-filtered re-query is needed.

The traces settled it. In twelve of thirteen sampled PlaceOrder traces the checkoutservice outbound client span for hipstershop.ShippingService/GetQuote is ERROR and is the degrading hop, propagating up through frontend/PlaceOrder to the frontend HTTP root. Two details matter: the spans complete in 0.5–2.7ms inside 6.9–12.9ms roots, far too short for a client deadline, so this returns an error promptly rather than hanging; and no shippingservice server span appears beneath any of them, while the peer dependencies all produce matching server spans. checkoutservice self time stays at 0.1–0.2ms, so it is propagating, not blocking. One trace near T+5m fails with no quote span at all, attributed to large self time in the prepare step.

Ruled out along the way: cartservice GetCart (clean, 1.2–2.7ms, matching server span and successful Redis HGET), currencyservice Convert (non-error, sub-2ms), productcatalogservice GetProduct (non-error, sub-1.5ms). No payment span appears anywhere — failure occurs inside prepareOrderItemsAndShippingQuoteFromCart. No ad or recommendation spans. The frontend is not an independent source: its ERROR spans are parents of the erroring checkout span every time.

> Evidence `tr_759a815ca833`:

```
<tool_result id="tr_759a815ca833" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:45:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T19:45:32.615874+00:00  {"message":"[PlaceOrder] user_id=\"da551cfc-abbd-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T19:45:32.615773708Z"}
2026-09-08T19:45:32.633224+00:00  {"message":"payment went through (transaction_id: f8622b55-314f-40aa-a79e-2fa8a0c45d07)","severity":"info","timestamp":"2026-09-08T19:45:32.633173375Z"}
2026-09-08T19:45:32.637186+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-08T19:45:32.637084875Z"}
2026-09-08T19:45:32.638084+00:00  {"message":"Successful to write message. offset: 15841","severity":"info","timestamp":"2026-09-08T19:45:32.638030916Z"}
```

> Evidence `tr_4a2e78a4b574`:

```
<tool_result id="tr_4a2e78a4b574" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T19:15:30.583000+00:00..2026-09-08T20:20:27.928417+00:00">
service: checkoutservice
13 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 86eca1b54a1a3d9a  root frontend/HTTP POST  9.6ms  started 2026-09-08T20:13:17.060010+00:00  24 spans
  +0.0ms frontend/HTTP POST 9.6ms [self 0.1ms]  ERROR
```

## Conclusion and open threads

checkoutservice is the reporter, not the culprit. The break sits at the shipping quote endpoint: an immediate error with no server-side span means the call is rejected or never accepted, not slow. The fan-out follows mechanically — post-checkout consumers starve, quoteservice goes idle because shippingservice never calls it, frontend surfaces the propagated error.

Confidence is low and no fix class is proposed, because no dispatch ever examined shippingservice itself. The refusal is inferred purely from the client side; the fast-reject-with-no-server-span pattern suggests shippingservice not serving the endpoint as addressed — a wrong or unreachable target or port, or a process unable to serve — rather than saturation.

Three threads to pick up. First, run change, log and metric queries against shippingservice with a window that starts well *before* onset; nothing there is measured. Second, get the gRPC status code on the failing GetQuote spans — UNAVAILABLE versus UNIMPLEMENTED versus RESOURCE_EXHAUSTED would discriminate between the candidate causes and was never reported. Third, re-query checkoutservice logs filtered to warning and above across the onset region to recover the first error text and any named endpoint.

> Evidence `tr_4a2e78a4b574`:

```
<tool_result id="tr_4a2e78a4b574" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T19:15:30.583000+00:00..2026-09-08T20:20:27.928417+00:00">
service: checkoutservice
13 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 86eca1b54a1a3d9a  root frontend/HTTP POST  9.6ms  started 2026-09-08T20:13:17.060010+00:00  24 spans
  +0.0ms frontend/HTTP POST 9.6ms [self 0.1ms]  ERROR
```

> Evidence `tr_759a815ca833`:

```
<tool_result id="tr_759a815ca833" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:45:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T19:45:32.615874+00:00  {"message":"[PlaceOrder] user_id=\"da551cfc-abbd-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T19:45:32.615773708Z"}
2026-09-08T19:45:32.633224+00:00  {"message":"payment went through (transaction_id: f8622b55-314f-40aa-a79e-2fa8a0c45d07)","severity":"info","timestamp":"2026-09-08T19:45:32.633173375Z"}
2026-09-08T19:45:32.637186+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-08T19:45:32.637084875Z"}
2026-09-08T19:45:32.638084+00:00  {"message":"Successful to write message. offset: 15841","severity":"info","timestamp":"2026-09-08T19:45:32.638030916Z"}
```

> Evidence `tr_f76a71bf6e67`:

```
<tool_result id="tr_f76a71bf6e67" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T19:45:30.583000+00:00..2026-09-08T20:20:27.928417+00:00" template="error-ratio" baseline="2026-09-08T19:10:33.237583+00:00..2026-09-08T19:45:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

