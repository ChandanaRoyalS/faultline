# Checkout order placement failing fast at the cart lookup

## What was visible first

Three alerts landed together: checkoutservice, frontend, and loadgenerator. That trio is what set the initial framing — a checkout-path outage with user-visible impact, blast radius counted at twelve services, severity critical. The seed for the investigation was checkoutservice, and the first instinct (wrongly, as it turned out) was that checkoutservice itself had broken.

Because all three alerts fired at effectively the same moment, the simultaneity itself was a clue rather than three separate problems: loadgenerator drives frontend, frontend calls checkoutservice, so one failing hop deep in the chain lights all three at once.

## Ruling out checkoutservice as the origin

The first substantive check was checkoutservice's own request error ratio against its immediately preceding baseline. It moved the wrong way for a culprit: the incident-window average sat at roughly a third of the baseline average, and the comparison explicitly found no sustained departure. Two other things fell out of the same result, both useful. First, every sampling interval in the incident window had a defined ratio, which requires non-zero traffic in each — so checkoutservice was not crash-looping, not scaled to zero, not out of service. Second, the error ratio is wildly variable in both windows, with intervals reaching a high fraction of requests even before onset. Checkoutservice emits bursty errors as its normal behaviour. That matters later: it means error-ratio shape cannot be used to date the onset.

What this check did not deliver, despite being asked for, was p95 latency or any per-downstream-target breakdown. Only the aggregate came back. So this result cannot clear checkoutservice of latency degradation or of a single-downstream failure hidden inside an aggregate — it only kills the "checkoutservice error spike is the origin" story.

> Evidence `tr_f010059645e4`:

```
<tool_result id="tr_f010059645e4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T17:28:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" template="error-ratio" baseline="2026-09-17T16:56:53.507902+00:00..2026-09-17T17:28:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.06517 min=0 max=0.6667 sd=0.1881
  baseline window: n=126 mean=0.1806 min=0 max=0.6667 sd=0.2912
```

## The logs: a clean cut point, seen from inside

Checkout's own logs gave the sharpest early picture. At the start of the window the service emits a complete per-order sequence — order intake, payment confirmation with a transaction id, a confirmation email, then a successful message-write with an incrementing offset. In the final few minutes only the intake line appears per request. Payment, email, and message-write completion lines vanish entirely. Intake continues steadily to the very end of the window, roughly one order every few seconds.

So orders enter PlaceOrder and do not come out the other side. Several candidate stories died here. It is not checkout's own intake or validation logic: intake lines are well-formed with valid user ids and currencies right up to the end. It is not the message broker rejecting writes: early writes succeed with consecutive offsets, and late orders never reach the write step at all. It is not confined to one currency path — two distinct currency codes appear among the late failures. It is not a restart: no startup or panic records, no traffic gap.

The frustrating part: every line returned was severity info. No error, no warn, no exception. No RPC target named, no gRPC status code, no resource name. Log-based attribution to a named dependency was simply unavailable from this side. That absence pushed the early reading toward "silent hang" — which the traces later corrected.

> Evidence `tr_ba24729e4180`:

```
<tool_result id="tr_ba24729e4180" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T17:28:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T17:28:48.266404+00:00  {"message":"[PlaceOrder] user_id=\"3de54f7a-b2bd-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T17:28:48.266207506Z"}
2026-09-17T17:28:48.288026+00:00  {"message":"payment went through (transaction_id: 12eb453b-9796-442f-95f5-cda421b23b49)","severity":"info","timestamp":"2026-09-17T17:28:48.28790659Z"}
2026-09-17T17:28:48.296308+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-17T17:28:48.296208756Z"}
2026-09-17T17:28:48.297447+00:00  {"message":"Successful to write message. offset: 65631","severity":"info","timestamp":"2026-09-17T17:28:48.297334548Z"}
```

## The traces: the actual cut point

Traces resolved it. Failing PlaceOrder traces terminate at the checkoutservice to cartservice GetCart call, which carries ERROR status. The error propagates upward through checkoutservice PlaceOrder, then frontend PlaceOrder, then the frontend HTTP POST root — which is exactly why checkoutservice, frontend and loadgenerator alerted together.

The mode is fast rejection, not a stall. The failing cart child runs in roughly 0.8 to 2.4ms, and the whole failing trace completes in about 2.7 to 3.3ms. This directly overturned the "silent hang" reading the logs had suggested. Failing traces carry only four or five spans against 36 to 53 in successful ones; payment, email, currency, shipping and productcatalog children are never reached at all. Checkout aborts immediately after the cart lookup fails.

One variant worth remembering: in one error trace the cart child span is missing altogether, with only prepareOrderItemsAndShippingQuoteFromCart present and the error attributed to the checkout PlaceOrder hop. The cart call sometimes fails before a child span is recorded. Don't read that as a different problem.

> Evidence `tr_f7268c5a7c45`:

```
<tool_result id="tr_f7268c5a7c45" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00">
service: checkoutservice
8 trace(s) shown of 25 found, 200 spans; offsets are from each trace's root

trace 85a3395ed394b135  root frontend/HTTP POST  27.5ms  started 2026-09-17T17:16:40.958010+00:00  53 spans
  +0.0ms frontend/HTTP POST 27.5ms [self 0.0ms]
```

## Dead ends worth keeping

Each downstream of checkout was considered and discarded, and the reasoning is worth preserving because the discard logic is identical each time: in successful traces these children complete with normal low-millisecond latency, and in failing traces they are never reached.

Paymentservice Charge completes in ~1.4-1.7ms with no error status. Emailservice send_order_confirmation, ~1.4-2.7ms. Currencyservice Convert, multiple calls per trace, all ~0.8-2.0ms. Productcatalogservice GetProduct, including its fan-out into the feature-flag service, ~0.2-1.5ms. Shippingservice was the most tempting red herring: the GetQuote path into quoteservice is genuinely the slowest hop in the trace at roughly 6-9ms and gets flagged as degrading — but it always completes, and the error traces never reach it. It cannot explain the failures. And generalized checkout saturation is out, because successful traces show the full fan-out at normal latencies; only the cart call carries errors.

A separate dead end: a metric check on paymentservice returned no samples at all, in either the incident window or the baseline. Because the baseline is equally empty, the honest reading is that the span-metrics series for that service is never populated under that label set — this is an instrumentation gap, not a signal about the incident. It says nothing about paymentservice latency or saturation, and it does not clear paymentservice either. Absence of data is not absence of a problem.

> Evidence `tr_f7268c5a7c45`:

```
<tool_result id="tr_f7268c5a7c45" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00">
service: checkoutservice
8 trace(s) shown of 25 found, 200 spans; offsets are from each trace's root

trace 85a3395ed394b135  root frontend/HTTP POST  27.5ms  started 2026-09-17T17:16:40.958010+00:00  53 spans
  +0.0ms frontend/HTTP POST 27.5ms [self 0.0ms]
```

> Evidence `tr_9181ce33dea2`:

```
<tool_result id="tr_9181ce33dea2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T17:28:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" template="error-ratio" baseline="2026-09-17T16:56:53.507902+00:00..2026-09-17T17:28:45.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The change-history searches, and why they were weaker than they looked

Two change-history queries were run against checkoutservice and both came back empty across a 24-hour span. That is genuine evidence for a narrow claim: no deploy, config push, flag flip, dependency-version bump, rollback or remediation is on record for checkoutservice during or after onset. So an in-incident change to checkoutservice is not available as an explanation, and no silent remediation complicates the timeline.

But both queries were built badly, in the same two ways, and a future responder should not inherit the false comfort. First, the window begins at the incident timestamp and runs forward — it does not cover the hours before onset, which is precisely where a triggering change would sit. Second, both ran at zero dependency hops, scoped to the seed service only. None of the six downstreams named in the question were examined, cartservice included. The one service the traces point at is the one whose change history was never queried.

> Evidence `tr_fd469f4c51d8`:

```
<tool_result id="tr_fd469f4c51d8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_fd469f4c51d8>
```

> Evidence `tr_6716b53e4284`:

```
<tool_result id="tr_6716b53e4284" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_6716b53e4284>
```

## Where it landed, and what is still open

Conclusion: PlaceOrder fails because cartservice returns errors on GetCart. Checkoutservice is a victim — alive, serving continuously, error ratio below its own baseline, no change on record. Confidence is medium, and the likely fix class is a restart.

The medium confidence is deliberate. Four unmeasured edges were crossed to reach cartservice and no dispatch of any kind ever ran against it: its logs, metrics, saturation and change history are all unexamined. The mechanism inside cartservice is therefore unknown and is deliberately not named here. That gap is what would decide the failure class, and it is the first thing to close on a repeat.

Two smaller loose ends. The gRPC status code on the failing GetCart was never captured, so the shape of the cart-side failure is unknown. And because checkout's error ratio was already bursty before onset, it is not firmly established that cart errors began at the declared onset time rather than earlier — comparable ratios exist in the baseline. Finally, no pre-onset change window was ever searched, for any service.

> Evidence `tr_f7268c5a7c45`:

```
<tool_result id="tr_f7268c5a7c45" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T16:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00">
service: checkoutservice
8 trace(s) shown of 25 found, 200 spans; offsets are from each trace's root

trace 85a3395ed394b135  root frontend/HTTP POST  27.5ms  started 2026-09-17T17:16:40.958010+00:00  53 spans
  +0.0ms frontend/HTTP POST 27.5ms [self 0.0ms]
```

> Evidence `tr_f010059645e4`:

```
<tool_result id="tr_f010059645e4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T17:28:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" template="error-ratio" baseline="2026-09-17T16:56:53.507902+00:00..2026-09-17T17:28:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.06517 min=0 max=0.6667 sd=0.1881
  baseline window: n=126 mean=0.1806 min=0 max=0.6667 sd=0.2912
```

> Evidence `tr_ba24729e4180`:

```
<tool_result id="tr_ba24729e4180" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T17:28:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T17:28:48.266404+00:00  {"message":"[PlaceOrder] user_id=\"3de54f7a-b2bd-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T17:28:48.266207506Z"}
2026-09-17T17:28:48.288026+00:00  {"message":"payment went through (transaction_id: 12eb453b-9796-442f-95f5-cda421b23b49)","severity":"info","timestamp":"2026-09-17T17:28:48.28790659Z"}
2026-09-17T17:28:48.296308+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-17T17:28:48.296208756Z"}
2026-09-17T17:28:48.297447+00:00  {"message":"Successful to write message. offset: 65631","severity":"info","timestamp":"2026-09-17T17:28:48.297334548Z"}
```

> Evidence `tr_fd469f4c51d8`:

```
<tool_result id="tr_fd469f4c51d8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_fd469f4c51d8>
```

> Evidence `tr_6716b53e4284`:

```
<tool_result id="tr_6716b53e4284" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T17:58:45.583000+00:00..2026-09-17T18:00:37.658098+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_6716b53e4284>
```

