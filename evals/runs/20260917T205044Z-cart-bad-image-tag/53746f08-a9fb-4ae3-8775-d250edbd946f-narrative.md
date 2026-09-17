# Checkout orders aborting at cart retrieval

## What we saw first

The board opened with three alerting services — checkoutservice, frontend, and loadgenerator — and a blast radius of twelve services, severity critical. The starting point handed to us was checkoutservice, which is where the alert fired and where, for the first twenty minutes of work, everyone assumed the problem lived. Four edges in the affected path were never measured by anyone, so the graph we reasoned over had holes in it from the beginning; it is worth knowing that before reading anything below.

The first useful shape came from the error-ratio series on checkoutservice. Over the incident window the average error ratio was about 7.4%, against a 7.8% pre-incident baseline — essentially unchanged. That is the trap: if you stop at the window average you conclude nothing happened. The series has a single detected change point roughly 75 seconds before the timestamp under investigation (call it T-75s), where the error ratio jumped to about two-thirds of all calls, more than double the worst baseline value. Window variability was also markedly higher than baseline (sd ~0.20 vs ~0.12) with the same floor of zero, which reads as a short sharp burst rather than a level shift.

> Evidence `tr_c2fc18f61dac`:

```
<tool_result id="tr_c2fc18f61dac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:24:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" template="error-ratio" baseline="2026-09-17T19:52:26.847957+00:00..2026-09-17T20:24:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.07369 min=0 max=0.6667 sd=0.2026
  baseline window: n=128 mean=0.07804 min=0 max=0.2951 sd=0.1151
```

## Dead end: the change log

The obvious first move was to look for a change on checkoutservice. Two separate change-history queries were run and both came back completely empty — no deploys, no config edits, no flag flips — across the entire queried window. A third query against productcatalogservice was likewise empty.

The important caveat, and the reason this is a dead end rather than a finding: the queried window starts at the incident timestamp and runs roughly 24 hours *forward*. It does not cover the hours before onset, which is exactly the period a responder would want. So what these queries legitimately rule out is narrow: no change landed on checkoutservice at or after onset, no rollout was in flight through the incident, and no remediation or rollback on checkoutservice explains any recovery. What they do not rule out is a change that landed before onset. If you are re-running this, re-run the change query with the window shifted backwards.

> Evidence `tr_21d4fce94b8b`:

```
<tool_result id="tr_21d4fce94b8b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_21d4fce94b8b>
```

> Evidence `tr_ee55b3ed60c5`:

```
<tool_result id="tr_ee55b3ed60c5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_ee55b3ed60c5>
```

> Evidence `tr_4c2289e9930b`:

```
<tool_result id="tr_4c2289e9930b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_4c2289e9930b>
```

## Dead end: productcatalogservice

productcatalogservice was pulled in as a plausible neighbour and turned out to matter not at all. Its error ratio is flat at exactly zero across both the incident window and the preceding baseline, with zero variance in either, across 128 samples each. Because the ratio is defined for every sample, the denominator was non-zero throughout — the service kept taking and completing requests, so it was not silently dark either.

Note what this evidence does not cover: only the error-ratio series was returned. No p95 latency and no request-rate series came back for this service, and none came back for checkoutservice either, so the committed 37.8ms p95 target was never actually compared against observed latency. That comparison remains undone.

> Evidence `tr_0a565369e268`:

```
<tool_result id="tr_0a565369e268" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:24:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" template="error-ratio" baseline="2026-09-17T19:52:26.847957+00:00..2026-09-17T20:24:15.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_c2fc18f61dac`:

```
<tool_result id="tr_c2fc18f61dac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:24:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" template="error-ratio" baseline="2026-09-17T19:52:26.847957+00:00..2026-09-17T20:24:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.07369 min=0 max=0.6667 sd=0.2026
  baseline window: n=128 mean=0.07804 min=0 max=0.2951 sd=0.1151
```

## The logs: loud silence

An unfiltered query of checkoutservice logs returned only info-severity lines. Not one error, not one warning, anywhere in the returned output — and therefore no line naming cart, productcatalog, shipping, payment, currency, email, ad, or recommendation. The instinct here is to conclude the log query was wrong; it was not, and the silence is itself the signal.

The contiguous newest block, covering roughly T-2m to T+2m, shows every order attempt appearing only as the opening PlaceOrder entry. The payment-confirmation, email-confirmation, and order-message-write entries that accompany each attempt in the early-window lines are simply absent. Because that block is contiguous with no gap inside it, the absence is real: orders begin and never reach the later stages. Earlier in the window the same service was logging complete, healthy order flows including payment and email confirmation, so this is a change during the window and not a steady state.

This also killed three candidate stories. checkoutservice had not crashed or lost traffic — PlaceOrder entries continue steadily right through the end of the window, so the service is up and accepting orders and the failure is mid-request. The failure is not in the final stages of checkout, because those stages emit nothing at all, meaning execution never reaches them. And it is not currency-specific: USD and CAD attempts show the identical truncated pattern.

One real limitation: the result is truncated to the oldest 8 and newest 32 lines, so roughly an hour in the middle of the window is unobserved. Onset cannot be placed precisely from logs.

> Evidence `tr_500ce94e6edd`:

```
<tool_result id="tr_500ce94e6edd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T19:54:16.788429+00:00  {"message":"[PlaceOrder] user_id=\"907e33dc-b2d1-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T19:54:16.788270588Z"}
2026-09-17T19:54:16.805675+00:00  {"message":"payment went through (transaction_id: 55491254-424a-471f-b5dc-641472388351)","severity":"info","timestamp":"2026-09-17T19:54:16.805541922Z"}
2026-09-17T19:54:16.811670+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-17T19:54:16.81159913Z"}
2026-09-17T19:54:16.812394+00:00  {"message":"Successful to write message. offset: 66764","severity":"info","timestamp":"2026-09-17T19:54:16.812303338Z"}
```

## The traces, which settled it

Ten sampled PlaceOrder traces in the window all share an identical five-span shape: frontend HTTP POST, frontend PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, and CartService/GetCart. GetCart is the deepest and last span entered in every single trace, and it carries an error status in all ten. That error propagates upward and marks checkoutservice PlaceOrder, frontend PlaceOrder, and the frontend HTTP root as errors too — which is precisely why the alert fired where it did.

The timing is the decisive detail. End-to-end root durations are 3-14ms and the GetCart span is 2-4ms of almost entirely self time. That is an immediate rejection, not a wait. Anyone arriving with a timeout or slow-dependency theory should discard it here: single-digit-millisecond traces are far too fast for a deadline expiry or a connection stall.

Several further hypotheses died on this evidence. Payment is not the failing dependency — no payment span exists in any of the fifty spans sampled, because execution terminates before the charge step. Email confirmation, order-write, and shipping-order steps are likewise entirely absent. The frontend is not sending malformed requests, since it propagates cleanly into checkoutservice PlaceOrder every time; the break is one hop further down. And the failure is not intermittent or path-specific — all ten traces fail identically.

Most importantly, checkoutservice itself is exonerated. Its PlaceOrder and prepareOrderItemsAndShippingQuoteFromCart spans have negligible self time (0.1-0.3ms), and prepareOrderItems is not even marked as an error. The error originates in the outbound GetCart call. checkoutservice and frontend are reporters, not the origin.

> Evidence `tr_ecd6b0a2ed0a`:

```
<tool_result id="tr_ecd6b0a2ed0a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T19:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace a51cad1a00d51bcd  root frontend/HTTP POST  3.2ms  started 2026-09-17T20:54:23.029015+00:00  5 spans
  +0.0ms frontend/HTTP POST 3.2ms [self 0.1ms]  ERROR
```

## Where blame lands, and how firmly

Blame lands on cartservice: it rejects cart reads outright, in 2-4ms of self time, consistently, and every PlaceOrder dies at that first downstream call. Confidence is medium and the fix class is restart.

The honest limit on that confidence: no specialist was ever dispatched to cartservice or to its backing store. The mechanism behind the rejection is not established by this board. We know *where* the request dies and that it dies fast; we do not know why.

> Evidence `tr_ecd6b0a2ed0a`:

```
<tool_result id="tr_ecd6b0a2ed0a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T19:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace a51cad1a00d51bcd  root frontend/HTTP POST  3.2ms  started 2026-09-17T20:54:23.029015+00:00  5 spans
  +0.0ms frontend/HTTP POST 3.2ms [self 0.1ms]  ERROR
```

> Evidence `tr_500ce94e6edd`:

```
<tool_result id="tr_500ce94e6edd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T19:54:16.788429+00:00  {"message":"[PlaceOrder] user_id=\"907e33dc-b2d1-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T19:54:16.788270588Z"}
2026-09-17T19:54:16.805675+00:00  {"message":"payment went through (transaction_id: 55491254-424a-471f-b5dc-641472388351)","severity":"info","timestamp":"2026-09-17T19:54:16.805541922Z"}
2026-09-17T19:54:16.811670+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-17T19:54:16.81159913Z"}
2026-09-17T19:54:16.812394+00:00  {"message":"Successful to write message. offset: 66764","severity":"info","timestamp":"2026-09-17T19:54:16.812303338Z"}
```

## Still open for the next responder

First, cartservice's own telemetry at the onset minute is entirely unexamined — error logs, memory or connection saturation, restart counts, and whether any deploy or config edit landed on it. Nothing on this board touches cartservice directly. That is the single highest-value next query.

Second, the cart backing store. A wrong endpoint or credential and an exhausted connection pool would both produce exactly this fast rejection signature, and they imply different fixes. Check reachability and health of the store before accepting the restart fix class.

Third, onset cannot be pinned. The log result is truncated across roughly an hour in the middle of the window, and the change queries run forward from onset rather than backward, so the hours preceding the incident are unobserved on both axes. The error-ratio change point at T-75s is currently the only anchor we have.

Finally, four edges in the affected path were crossed without measurement. If the cartservice investigation comes back clean, those unmeasured edges are where to look next.

> Evidence `tr_500ce94e6edd`:

```
<tool_result id="tr_500ce94e6edd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T19:54:16.788429+00:00  {"message":"[PlaceOrder] user_id=\"907e33dc-b2d1-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T19:54:16.788270588Z"}
2026-09-17T19:54:16.805675+00:00  {"message":"payment went through (transaction_id: 55491254-424a-471f-b5dc-641472388351)","severity":"info","timestamp":"2026-09-17T19:54:16.805541922Z"}
2026-09-17T19:54:16.811670+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-17T19:54:16.81159913Z"}
2026-09-17T19:54:16.812394+00:00  {"message":"Successful to write message. offset: 66764","severity":"info","timestamp":"2026-09-17T19:54:16.812303338Z"}
```

> Evidence `tr_ee55b3ed60c5`:

```
<tool_result id="tr_ee55b3ed60c5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:54:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_ee55b3ed60c5>
```

> Evidence `tr_c2fc18f61dac`:

```
<tool_result id="tr_c2fc18f61dac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:24:15.583000+00:00..2026-09-17T20:56:04.318043+00:00" template="error-ratio" baseline="2026-09-17T19:52:26.847957+00:00..2026-09-17T20:24:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.07369 min=0 max=0.6667 sd=0.2026
  baseline window: n=128 mean=0.07804 min=0 max=0.2951 sd=0.1151
```

