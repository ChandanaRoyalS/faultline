# Checkout order flow aborts at shipping quote step; shipping-side state never established

## What we saw first

The page arrived as a critical, wide-blast-radius event: eleven services in the radius, six of them alerting within the same second — checkoutservice, accountingservice, emailservice, frauddetectionservice, quoteservice and shippingservice. The declared starting point was checkoutservice, which is where the responder (me) began and, as it turned out, where nearly all of the investigation stayed.

The surface symptom from the business side was simple: orders were being started and not finished. Nothing in the alert set pointed at a single owner, and six simultaneous alerts read at first glance like several independent problems rather than one. That reading cost time and is worth flagging early for the next reader: the alert fan-out was almost certainly a consequence, not a set of causes.

## First pass: was checkout broken on its own?

The first two lines of inquiry were the obvious ones for a service named as the origin, and both were dead ends in the useful sense — they closed doors.

Change history for checkoutservice came back completely empty for the interval queried. No deploys, no config edits, no flag flips. That excluded the three most attractive early hypotheses at once: a rollout landing at onset, a mid-incident flag flip, and the tempting remediation of "just roll back the last checkout change." There was nothing to roll back. Note the caveat that mattered later: the query covered only checkoutservice, and only a roughly fifteen-minute window ending at T+0-ish relative to the alert. The half hour before that, and every dependency, were never asked about.

Checkout's own error-ratio metric confirmed the incident was real but immediately muddied the picture. The ratio was materially non-zero, peaking around 0.30 across the sampled window, with at least one interval sitting at zero. That ruled out both "false alarm" and "hard down / crash loop" — most requests on this service were still returning non-error status. It also ruled out a flat step change predating the window. What it did not do was match what traces later showed, and that discrepancy is still unreconciled (see Loose ends). The metric query also failed to deliver what was actually asked for: it filtered to checkoutservice alone, so no dependency comparison, no latency percentiles and no request-volume series were ever obtained.

> Evidence `tr_188ed47f27e7`:

```
<tool_result id="tr_188ed47f27e7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_188ed47f27e7>
```

> Evidence `tr_8208b7da1b41`:

```
<tool_result id="tr_8208b7da1b41" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2979 n=55
</tool_result:tr_8208b7da1b41>
```

## The log signature: orders start, orders never finish

Checkout's logs were the first evidence that reframed the incident. Nothing in the returned data was error or warning severity — every line was info. That was itself a finding: checkout names no failing dependency anywhere we could see.

The shape of the info lines was the signal. Early in the window each request logged a full lifecycle: order start, payment success with a transaction id, confirmation email sent, and a successful queue write with an increasing offset. In the contiguous later segment, only the order-start lines remained. Payment, email and queue-write lines vanished together — not one stage erroring loudly, all post-start stages simply absent. Order-start lines continued at a steady one-every-five-to-fifteen-seconds cadence right through the end of the window.

That combination ruled out several things cleanly. Checkout had not crashed or been restarted, and it had not stopped receiving traffic — it was alive and logging to the last second. This was not a telemetry outage either; logs were flowing densely, only their content had changed. And it was not a single loud stage failure such as payment declining, because all downstream stages disappeared as a block, implying a blocking call upstream of payment.

One gap here that never got closed: the result was truncated to the oldest handful and newest few dozen lines, leaving roughly a ten-minute interval in the middle unobserved. If an error or warning line naming the failing dependency exists, that is where it is.

> Evidence `tr_d66c8ab1f361`:

```
<tool_result id="tr_d66c8ab1f361" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T09:00:52.983515+00:00  {"message":"[PlaceOrder] user_id=\"ce8d6efa-a1f5-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T09:00:52.983416708Z"}
2026-08-27T09:00:53.000754+00:00  {"message":"payment went through (transaction_id: fdb19865-d25d-486f-ae7e-eff375fc1792)","severity":"info","timestamp":"2026-08-27T09:00:53.000433917Z"}
2026-08-27T09:00:53.006113+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-08-27T09:00:53.006013917Z"}
2026-08-27T09:00:53.006624+00:00  {"message":"Successful to write message. offset: 17633","severity":"info","timestamp":"2026-08-27T09:00:53.006568083Z"}
```

## Traces: the exact abort point

Traces are what turned a shape into a location. Every sampled PlaceOrder trace in the window told the same story, and it was unambiguous.

The chain up to a point was healthy: cartservice GetCart with its Redis HGET, productcatalogservice GetProduct (sometimes with a featureflagservice GetFlag child), and currencyservice Convert all completed without error in sub-millisecond to roughly two-millisecond times. Each of those was individually ruled out as the termination point — the traces visibly continued past them.

The last downstream call entered was checkoutservice's outbound client span to ShippingService/GetQuote, marked ERROR. The trace ended there, and the error propagated up through PlaceOrder, the frontend gRPC span and the frontend HTTP POST. Two details carried the whole conclusion: the failing GetQuote client spans had no shippingservice server-side child span at all, and they completed in roughly 0.4–2.6ms, with entire PlaceOrder traces finishing under about fourteen milliseconds.

Fast, uniform, no callee server span. That is a rejection at or before the shipping handler — connection refused, unavailable, immediate reject — not a slow dependency and not a timeout. It also ruled out checkout as the origin: checkout's error status is inherited from its own outbound call, which is the innermost erroring span in every trace. Because the abort happens inside prepareOrderItemsAndShippingQuoteFromCart, no paymentservice charge span, no shipping order placement and no queue or email span appears anywhere — which is exactly the log signature from the previous section, explained.

The traces also contradicted the metric: every sampled PlaceOrder trace was ERROR, i.e. total failure of that path, not the partial degradation the ~0.30 ratio suggested.

> Evidence `tr_bb9484cf38ae`:

```
<tool_result id="tr_bb9484cf38ae" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
service: checkoutservice
200 spans
  e63c9df394e808f8 checkoutservice/hipstershop.CurrencyService/Convert 1.2ms
  e63c9df394e808f8 currencyservice/CurrencyService/Convert 0.0ms
  e63c9df394e808f8 checkoutservice/hipstershop.ShippingService/GetQuote 2.1ms ERROR
```

## Why five other services alerted

The simultaneous alerts on accountingservice, emailservice, frauddetectionservice, quoteservice and shippingservice are best explained as traffic starvation downstream of the stall, not five separate failures. quoteservice sees no work because shipping never calls it. The post-payment services see no work because checkout never gets past the shipping quote.

This is inference from topology plus the log and trace pattern. No per-service check was run on accountingservice, emailservice or frauddetectionservice to confirm it. Treat it as the most probable reading, not a verified one.

> Evidence `tr_bb9484cf38ae`:

```
<tool_result id="tr_bb9484cf38ae" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
service: checkoutservice
200 spans
  e63c9df394e808f8 checkoutservice/hipstershop.CurrencyService/Convert 1.2ms
  e63c9df394e808f8 currencyservice/CurrencyService/Convert 0.0ms
  e63c9df394e808f8 checkoutservice/hipstershop.ShippingService/GetQuote 2.1ms ERROR
```

> Evidence `tr_d66c8ab1f361`:

```
<tool_result id="tr_d66c8ab1f361" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T09:00:52.983515+00:00  {"message":"[PlaceOrder] user_id=\"ce8d6efa-a1f5-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T09:00:52.983416708Z"}
2026-08-27T09:00:53.000754+00:00  {"message":"payment went through (transaction_id: fdb19865-d25d-486f-ae7e-eff375fc1792)","severity":"info","timestamp":"2026-08-27T09:00:53.000433917Z"}
2026-08-27T09:00:53.006113+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-08-27T09:00:53.006013917Z"}
2026-08-27T09:00:53.006624+00:00  {"message":"Successful to write message. offset: 17633","severity":"info","timestamp":"2026-08-27T09:00:53.006568083Z"}
```

## Where the investigation stopped, and why confidence is low

The mechanism is an unavailable shipping dependency. Its own failure mode was never identified, because nothing at all was queried on shippingservice — no logs, no metrics, no traces, no change history. No specialist was dispatched to shippingservice or quoteservice. That is the single largest defect in this record, and the reason the fix class is "none": whether the right action is a restart, a rollback or a config revert depends entirely on shippingservice's state, which is unknown.

This is the honest summary of the effort's shape: four deep looks at the service that was merely reporting the symptom, and zero looks at the service that was producing it. If you are reading this months later with a similar signature — client span ERROR, callee server span absent, sub-millisecond duration — go to the callee first.

> Evidence `tr_bb9484cf38ae`:

```
<tool_result id="tr_bb9484cf38ae" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
service: checkoutservice
200 spans
  e63c9df394e808f8 checkoutservice/hipstershop.CurrencyService/Convert 1.2ms
  e63c9df394e808f8 currencyservice/CurrencyService/Convert 0.0ms
  e63c9df394e808f8 checkoutservice/hipstershop.ShippingService/GetQuote 2.1ms ERROR
```

> Evidence `tr_188ed47f27e7`:

```
<tool_result id="tr_188ed47f27e7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_188ed47f27e7>
```

## Loose ends for whoever picks this up

1. shippingservice state, entirely unestablished. Are its pods running, crash-looping, failing readiness, or refusing connections? This is question one.

2. Change history for shippingservice and quoteservice around the onset minutes. The only change query run covered checkoutservice and a narrow window; the preceding half hour and every dependency are unqueried.

3. Is shippingservice failing on its own, or failing because quoteservice is unavailable to it? quoteservice also alerted at the same second. Without a shipping-side trace or log we cannot distinguish starved victim from origin.

4. The unreconciled metric. Checkout's error ratio peaks near 0.30 with zero-error intervals, while every sampled PlaceOrder trace is ERROR. Candidate explanations: pre-onset data inside the window, non-PlaceOrder RPC traffic diluting the ratio, or trace sampling weighted toward the failing period. None tested.

5. The unobserved log interval. Roughly ten minutes in the middle of the window was truncated away. Error or warning lines naming the failing dependency could live there and would change the picture materially.

> Evidence `tr_8208b7da1b41`:

```
<tool_result id="tr_8208b7da1b41" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2979 n=55
</tool_result:tr_8208b7da1b41>
```

> Evidence `tr_d66c8ab1f361`:

```
<tool_result id="tr_d66c8ab1f361" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T09:00:52.983515+00:00  {"message":"[PlaceOrder] user_id=\"ce8d6efa-a1f5-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T09:00:52.983416708Z"}
2026-08-27T09:00:53.000754+00:00  {"message":"payment went through (transaction_id: fdb19865-d25d-486f-ae7e-eff375fc1792)","severity":"info","timestamp":"2026-08-27T09:00:53.000433917Z"}
2026-08-27T09:00:53.006113+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-08-27T09:00:53.006013917Z"}
2026-08-27T09:00:53.006624+00:00  {"message":"Successful to write message. offset: 17633","severity":"info","timestamp":"2026-08-27T09:00:53.006568083Z"}
```

> Evidence `tr_188ed47f27e7`:

```
<tool_result id="tr_188ed47f27e7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:59:30.583000+00:00..2026-08-27T09:14:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_188ed47f27e7>
```
