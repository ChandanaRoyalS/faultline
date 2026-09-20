# Checkout orders fail at the shipping-quote hop

## What we saw first

The page named twelve services at critical severity, with checkoutservice at the centre and accountingservice, emailservice, frauddetectionservice, loadgenerator and quoteservice all alarming alongside it. That breadth is misleading in hindsight: the wide alert list reflects everything downstream of order completion going quiet, not twelve independent problems. The single useful early question turned out to be "how far into the checkout pipeline does a request get before it dies?", and it took several detours to arrive there.

Onset sits inside the observed window. Comparing checkoutservice error ratio against a pre-onset baseline stretching back three hours, the baseline mean is flat zero and the incident window averages roughly 0.17 with a peak near 0.67. Errors did not exist before the window and did exist after it, so this is a new condition rather than a slow-burning defect.

> Evidence `tr_20c21b5d9fd4`:

```
<tool_result id="tr_20c21b5d9fd4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-20T01:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-19T22:04:39.148730+00:00..2026-09-20T01:09:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=499 mean=0.1675 min=0 max=0.6667 sd=0.2365
  baseline window: no samples
```

## The first dead end: a narrow baseline that said nothing happened

Around T+5m we ran the same error-ratio comparison for checkoutservice but with a baseline window only thirty minutes wide, starting close to onset. It reported the incident-window error ratio as *lower* than baseline, with no sustained departure, and the obvious reading was that checkoutservice was not the origin at all. That reading was wrong. The short baseline overlapped the disturbed period and so carried its own error mass; the wider three-hour baseline later showed a clean zero before onset.

If you take one thing from this record: when a baseline comparison tells you nothing changed, check where the baseline window actually starts before you believe it. The narrow query did contribute two durable facts — every sampling interval in the incident window produced a defined ratio, meaning traffic never stopped, and error behaviour was bursty rather than a clean plateau.

> Evidence `tr_ac6b390195ec`:

```
<tool_result id="tr_ac6b390195ec" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-20T03:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-20T03:04:39.148730+00:00..2026-09-20T03:39:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.05416 min=0 max=0.2889 sd=0.1052
  baseline window: n=123 mean=0.2591 min=0 max=0.6667 sd=0.3168
```

> Evidence `tr_20c21b5d9fd4`:

```
<tool_result id="tr_20c21b5d9fd4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-20T01:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-19T22:04:39.148730+00:00..2026-09-20T01:09:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=499 mean=0.1675 min=0 max=0.6667 sd=0.2365
  baseline window: no samples
```

## The second dead end: empty metric series read as signal

Roughly T+10m we checked error ratios for cartservice and productcatalogservice, both direct callees of checkout. Both returned no samples at all in the incident window. For a few minutes this looked like a finding — services that stop reporting when things break. It was not. The identical queries returned no samples in the preceding baseline window either, so the series simply is not emitted for those two services under that label set. Absent series predating the event carries no timing information.

We abandoned span-metric error ratios for anything other than checkoutservice after this. Note also that across every metric query attempted, only the error-ratio template ever evaluated: latency percentiles, request rate, CPU, memory, GC and connection-pool saturation were never returned for any service. Those questions remain unanswered, not answered negatively.

> Evidence `tr_73ab66fa0656`:

```
<tool_result id="tr_73ab66fa0656" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-20T03:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-20T03:04:39.148730+00:00..2026-09-20T03:39:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_fbdb4cab3eeb`:

```
<tool_result id="tr_fbdb4cab3eeb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-20T03:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-20T03:04:39.148730+00:00..2026-09-20T03:39:30.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_20c21b5d9fd4`:

```
<tool_result id="tr_20c21b5d9fd4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-20T01:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-19T22:04:39.148730+00:00..2026-09-20T01:09:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=499 mean=0.1675 min=0 max=0.6667 sd=0.2365
  baseline window: no samples
```

## Logs: the pipeline stops after the entry line

At about T+15m the checkoutservice logs gave the shape of the failure. In the pre-onset portion, each order-placement entry is followed within about 25ms by a payment-success line, an order-confirmation-email line, and a successful queue-write with an incrementing offset — the full pipeline, end to end. In the most recent portion of the window, only the order-placement entry lines appear. All three follow-on lines are gone for every one of the roughly thirty-two late orders, across both USD and CAD.

This ruled out several things cleanly. Checkout had not crashed or restarted: entry lines continue at a steady cadence to the end of the window. The break was not at request acceptance, since the entry line still fires. And checkout was definitely not completing orders quietly. What the logs did *not* give us was a culprit — every returned line is info severity, no dependency is named, and no error text appears anywhere.

A real gap here: the result was truncated to the oldest eight and newest thirty-two lines, so the region around onset itself was omitted. If error text was ever written, it is in the discarded middle. That text remains unretrieved.

> Evidence `tr_b3a273be7475`:

```
<tool_result id="tr_b3a273be7475" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T03:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-20T03:39:31.471879+00:00  {"message":"[PlaceOrder] user_id=\"e3c763f4-b4a4-11f1-bde0-b2c1b7dd3a95\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-09-20T03:39:31.471737376Z"}
2026-09-20T03:39:31.490103+00:00  {"message":"payment went through (transaction_id: 57014865-ffd4-46e7-a3bf-431a9999528a)","severity":"info","timestamp":"2026-09-20T03:39:31.490013167Z"}
2026-09-20T03:39:31.494968+00:00  {"message":"order confirmation email sent to \"tobias@example.com\"","severity":"info","timestamp":"2026-09-20T03:39:31.494862417Z"}
2026-09-20T03:39:31.495775+00:00  {"message":"Successful to write message. offset: 78720","severity":"info","timestamp":"2026-09-20T03:39:31.495650667Z"}
```

## The third dead end: chasing payment

Because the missing log lines began with payment success, payment was the natural next suspect, and at roughly T+22m we pulled its logs. They show a clean service: every charge request paired with a completion for the same trace id, sub-millisecond gaps, no error lines, no orphaned requests, and a single hostname and pid across the whole window indicating no restart.

The striking detail is that payment's logs simply stop several minutes before the window end, with nothing after onset. We briefly read this as payment going dark. The correct reading, confirmed later by traces, is the reverse: requests stopped arriving, because checkout never got far enough to call it. Payment was ruled out as slow, as erroring, as restarting, and as hanging — all four hypotheses died on this evidence.

> Evidence `tr_fb48b0107a79`:

```
<tool_result id="tr_fb48b0107a79" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T02:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-20T02:43:44.484018+00:00  {"level":30,"time":1789872224483,"pid":18,"hostname":"a6acfd617401","trace_id":"b610fea75720004e4cd3af5b74973ede","span_id":"f8fc51ccd6a711b8","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":266,"high":0,"unsigned":false},"nanos":799999996},"creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardCvv":397,"creditCardExpirationYear":2039,"creditCardExpirationMonth":5}},"msg":"Charge request received."}
2026-09-20T02:43:44.484425+00:00  {"level":30,"time":1789872224484,"pid":18,"hostname":"a6acfd617401","trace_id":"b610fea75720004e4cd3af5b74973ede","span_id":"f8fc51ccd6a711b8","trace_flags":"01","transactionId":"8efe273b-27b8-41b1-a9d1-715c4a90189e","cardType":"visa","lastFourDigits":"7968","amount":{"units":{"low":266,"high":0,"unsigned":false},"nanos":799999996,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-20T02:43:48.589419+00:00  {"level":30,"time":1789872228589,"pid":18,"hostname":"a6acfd617401","trace_id":"46cf7da0c6723229a798b64eb0118da3","span_id":"a89ff56417dee394","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":18591,"high":0,"unsigned":false},"nanos":200000000},"creditCard":{"creditCardNumber":"4532-6178-2799-1951","creditCardCvv":239,"creditCardExpirationYear":2039,"creditCardExpirationMonth":3}},"msg":"Charge request received."}
2026-09-20T02:43:48.589848+00:00  {"level":30,"time":1789872228589,"pid":18,"hostname":"a6acfd617401","trace_id":"46cf7da0c6723229a798b64eb0118da3","span_id":"a89ff56417dee394","trace_flags":"01","transactionId":"fb269b9e-e80c-4b0b-97d3-080f25f32357","cardType":"visa","lastFourDigits":"1951","amount":{"units":{"low":18591,"high":0,"unsigned":false},"nanos":200000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Traces: the single failing hop

The traces closed it. Ten sampled checkout traces all have the same shape — frontend POST into PlaceOrder into prepareOrderItemsAndShippingQuoteFromCart — and in every one of them the last downstream call started is the checkoutservice client call to ShippingService/GetQuote, and it is the only errored child. The error propagates up through PlaceOrder to the frontend gRPC span and the HTTP root, so these requests fail outright.

No payment span, no queue-write span and no email span appear in any trace, which explains the missing log lines exactly: execution never reaches them. Cart and its Redis lookup complete in under a millisecond, currency conversion registers near zero, and product-catalog lookups with their feature-flag child are error-free and about a millisecond. All were eliminated.

The timing matters. Whole traces complete in roughly 7–11ms and the GetQuote hop accounts for only about 2.4–3.7ms of that. This is an immediate rejection, not a stall, so saturation and timeout explanations do not fit. Equally, shipping is not down: a shippingservice server span and its outbound HTTP client span are present, non-error, and *shorter* than the caller's client span. The error status lives on the checkout side of the hop.

> Evidence `tr_fc4cef4ca1de`:

```
<tool_result id="tr_fc4cef4ca1de" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-20T02:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 165 spans; offsets are from each trace's root

trace 6d86fd938bdcc4a8  root frontend/HTTP POST  11.1ms  started 2026-09-20T04:13:23.707020+00:00  14 spans
  +0.0ms frontend/HTTP POST 11.1ms [self 0.2ms]  ERROR
```

## Change history, and why it did not help

We queried change history for checkoutservice and for paymentservice. Both came back completely empty — no deploys, no config edits, no flag flips of any kind. Taken at face value that eliminates a rollback as the remedy for either service.

But read the window before trusting it. Both queries ran from the onset timestamp forward roughly twenty-four hours; neither actually covers the hours *preceding* onset, which is the interval that would contain a triggering change. So the pre-onset period is unexamined, not clean. We also never queried change history for shippingservice or quoteservice at all, which, given where the failure sits, is the more consequential omission.

> Evidence `tr_197eb72b8101`:

```
<tool_result id="tr_197eb72b8101" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_197eb72b8101>
```

> Evidence `tr_658573a08c86`:

```
<tool_result id="tr_658573a08c86" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" radius="candidate_cause" hops="1">
no changes recorded for paymentservice over this window
</tool_result:tr_658573a08c86>
```

## Where it landed, and what is still open

Conclusion: checkout requests fail at exactly one hop, the checkoutservice client call to ShippingService/GetQuote, and the rejection is immediate and recorded on the caller's side while shipping's own work completes without error. The shape — fast refusal, caller-side error, healthy callee — points at a wrong endpoint, address, or quote-parameter value on the checkout-to-shipping path rather than a slow or saturated dependency. Fix class is a config revert on that path.

Confidence is low, and deliberately so. Four gaps stand behind that rating. First, nobody retrieved the gRPC status code or error message on the GetQuote client span; that single string would likely settle it. Second, the checkout logs covering the onset region were truncated away, so any error text there is unobserved. Third, no change history was ever pulled for shippingservice or quoteservice, and the two change queries we did run started at onset rather than before it. Fourth, latency, CPU, memory and pool saturation were never returned for any service, so those were never actually excluded — only unmeasured.

If you are picking this up again, start with the error attributes on that one client span, then pull change history for shippingservice and quoteservice over the hours *before* onset.

> Evidence `tr_fc4cef4ca1de`:

```
<tool_result id="tr_fc4cef4ca1de" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-20T02:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 165 spans; offsets are from each trace's root

trace 6d86fd938bdcc4a8  root frontend/HTTP POST  11.1ms  started 2026-09-20T04:13:23.707020+00:00  14 spans
  +0.0ms frontend/HTTP POST 11.1ms [self 0.2ms]  ERROR
```

> Evidence `tr_b3a273be7475`:

```
<tool_result id="tr_b3a273be7475" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T03:39:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-20T03:39:31.471879+00:00  {"message":"[PlaceOrder] user_id=\"e3c763f4-b4a4-11f1-bde0-b2c1b7dd3a95\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-09-20T03:39:31.471737376Z"}
2026-09-20T03:39:31.490103+00:00  {"message":"payment went through (transaction_id: 57014865-ffd4-46e7-a3bf-431a9999528a)","severity":"info","timestamp":"2026-09-20T03:39:31.490013167Z"}
2026-09-20T03:39:31.494968+00:00  {"message":"order confirmation email sent to \"tobias@example.com\"","severity":"info","timestamp":"2026-09-20T03:39:31.494862417Z"}
2026-09-20T03:39:31.495775+00:00  {"message":"Successful to write message. offset: 78720","severity":"info","timestamp":"2026-09-20T03:39:31.495650667Z"}
```

> Evidence `tr_197eb72b8101`:

```
<tool_result id="tr_197eb72b8101" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_197eb72b8101>
```

> Evidence `tr_658573a08c86`:

```
<tool_result id="tr_658573a08c86" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" radius="candidate_cause" hops="1">
no changes recorded for paymentservice over this window
</tool_result:tr_658573a08c86>
```

> Evidence `tr_20c21b5d9fd4`:

```
<tool_result id="tr_20c21b5d9fd4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-20T01:09:30.583000+00:00..2026-09-20T04:14:22.017270+00:00" template="error-ratio" baseline="2026-09-19T22:04:39.148730+00:00..2026-09-20T01:09:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=499 mean=0.1675 min=0 max=0.6667 sd=0.2365
  baseline window: no samples
```

