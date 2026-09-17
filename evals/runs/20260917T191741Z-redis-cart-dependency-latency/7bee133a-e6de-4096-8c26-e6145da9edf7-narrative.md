# Slow checkout with no errors: cart leg suspected, unconfirmed

## Arrival and the one positive signal

A warning-severity page, twelve services in the radius, cartservice named as the seed, four edges in the radius never measured at all. Alert ordering was the first useful thing: cartservice and checkoutservice at t0, frontend and loadgenerator about fifteen seconds later — the shape of something inside the checkout fan-out rather than an edge problem working inward.

By about T+10m the only affirmative anomaly had surfaced in checkoutservice's logs. Early in the window, PlaceOrder completed all four stages — order placement, payment, confirmation email, message write — within roughly thirty milliseconds. Late in the window each stage took several hundred milliseconds, about 650 ms end to end. Every line info-level, every order succeeding, message offsets advancing monotonically to the window close. A latency shift with no error signal at all.

Caveat worth keeping: that log result was truncated to the oldest eight and newest thirty-two lines, leaving roughly thirty minutes in the middle unobserved. Orders succeeded on both sides of the gap, which makes a hard failure hiding inside it implausible but not impossible.

> Evidence `tr_c2d2f8babdf6`:

```
<tool_result id="tr_c2d2f8babdf6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T18:51:15.583000+00:00..2026-09-17T19:23:05.059352+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T18:51:18.241463+00:00  {"message":"[PlaceOrder] user_id=\"c4504ac8-b2c8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T18:51:18.241340756Z"}
2026-09-17T18:51:18.258689+00:00  {"message":"payment went through (transaction_id: 11b58bce-b1b9-466a-b280-62dcc0085470)","severity":"info","timestamp":"2026-09-17T18:51:18.258588131Z"}
2026-09-17T18:51:18.264356+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-17T18:51:18.264212464Z"}
2026-09-17T18:51:18.269546+00:00  {"message":"Successful to write message. offset: 66280","severity":"info","timestamp":"2026-09-17T18:51:18.269469672Z"}
```

## The seed looked healthy, which proved nothing

Around T+15m cartservice itself was examined. Six hours of logs were entirely routine — add item, get cart, empty cart, all info-level, steady multi-request-per-second cadence, serving normally at both edges of the window. No startup banners, no restart-shaped discontinuities, no cache connection errors, no timeouts or retries. That cleared crash-looping, an unreachable cache backend, and an image that never came up.

It did not clear cartservice. A dependency answering every request correctly but slowly looks exactly like this from the inside: healthy in its own logs, painful from the caller's chair. There is also a recurring pattern of cart reads with an empty user identifier at both edges of the window, logged as normal handling. Almost certainly unrelated; chasing it would waste time.

> Evidence `tr_9955fcf607ee`:

```
<tool_result id="tr_9955fcf607ee" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:21:15.583000+00:00..2026-09-17T19:21:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T13:21:17.990086+00:00  AddItemAsync called with userId=aa731712-b29a-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=3
2026-09-17T13:21:18.371385+00:00  AddItemAsync called with userId=aaada1c0-b29a-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=3
2026-09-17T13:21:18.901052+00:00  GetCartAsync called with userId=aa731712-b29a-11f1-b359-b6ed2071a170
2026-09-17T13:21:19.281959+00:00  GetCartAsync called with userId=aaada1c0-b29a-11f1-b359-b6ed2071a170
```

## Three dead ends

Metrics: the cartservice error-ratio query was run against the incident window and the preceding six-hour baseline, and both returned empty — not zero, empty. Because the baseline is equally barren, the gap predates the incident and is an instrumentation or label mismatch, not the incident signal. It cannot be read as a spike, and it equally cannot be read as health. Only the error ratio was queried; request rate, latency percentiles, restarts and CPU/memory remain unmeasured.

Traces: the obvious move — read the PlaceOrder span breakdown and see which child call grew — failed outright. Zero traces for checkoutservice across the full six-hour window. An empty trace store is symmetric: it neither implicates nor clears paymentservice, shippingservice, productcatalogservice, currencyservice, emailservice or cartservice, and it leaves checkoutservice's own self-time (GC, lock contention, thread-pool queueing) just as unexcluded as downstream time. Zero traces for a service demonstrably serving orders is itself a finding about the tracing path.

Changes on checkoutservice: a ~24-hour change history scoped to the service returned nothing — no deploys, image rollouts, environment edits, timeout or retry adjustments, resource-limit or sidecar changes. That closes the tidy rollback path. Note the scope limit: zero hops, so it says nothing about shared platform layers or dependencies.

> Evidence `tr_fb1f01991f7f`:

```
<tool_result id="tr_fb1f01991f7f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T07:21:15.583000+00:00..2026-09-17T13:21:15.583000+00:00" template="error-ratio" baseline="2026-09-17T01:21:15.583000+00:00..2026-09-17T07:21:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_d0ff8d9d0b30`:

```
<tool_result id="tr_d0ff8d9d0b30" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T07:21:15.583000+00:00..2026-09-17T13:21:15.583000+00:00">
no traces for checkoutservice over this window
</tool_result:tr_d0ff8d9d0b30>
```

> Evidence `tr_5854db8767ce`:

```
<tool_result id="tr_5854db8767ce" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T19:21:15.583000+00:00..2026-09-17T19:23:05.059352+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_5854db8767ce>
```

## The cartservice change log, and where it stops making sense

The richest and most frustrating artifact. Twenty-six entries across the day, every one attributed to the same platform-automation actor; no human or ad-hoc change anywhere. They form a repeating four-to-six-step cycle running about five times: an image reference set to a hotfix tag then reverted; a traffic-shaping sidecar attached to the cart-service network namespace with a fixed egress delay then removed; a REDIS_ADDR variable pointed at an alternate Redis port then reverted. Every mutation is paired with a revert; nothing is left applied by the end of the log. The evenly-spaced, self-reverting structure reads as scheduled platform automation, not a release pipeline.

The sidecar step is the only documented mechanism here that produces the observed shape — correct answers, no errors, just slow.

And here the record breaks. The last sidecar removal landed about 1.6h before onset, the image revert about 1.9h before, the final REDIS_ADDR revert about 1.3h before. The 1.3h immediately preceding the alert contain no recorded change, and neither does the period after. Read literally, the log rules out the very hypotheses it otherwise supports: lingering bad image, redirected Redis address, and an active traffic-shaping sidecar. It also rules out any human trigger and any change landing inside the alert window.

> Evidence `tr_99567f16582c`:

```
<tool_result id="tr_99567f16582c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T19:21:15.583000+00:00..2026-09-17T19:23:05.059352+00:00" radius="seed" hops="0">
service: cartservice
26 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-17T18:04:20.470761+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.4h before onset  2026-09-17T17:56:03.098388+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Conclusion, confidence, and what is still open

I attribute the incident to egress delay on cartservice making the cart call slow for checkoutservice, which simply waited — hundreds of milliseconds per stage, every order succeeding, no error line anywhere, cartservice untroubled in its own logs. Fix class: config revert. Confidence: low, and the low confidence is load-bearing: the reasoning runs backwards from a mechanism that fits the symptom to a change log stating the mechanism was not in effect. Either that log is incomplete near onset, a further cycle went unrecorded, or the attribution is wrong.

Open items for the next responder. First, go look directly: is a traffic-shaping sidecar or egress delay rule present in the cart-service network namespace right now? The log cannot settle this. Second, with no traces and no per-dependency client latency, paymentservice, shippingservice, productcatalogservice, currencyservice and emailservice remain exactly as unexcluded as cartservice. Third, checkoutservice self-time is unmeasured, and the unobserved middle of its log window could hold errors nobody saw.

> Evidence `tr_99567f16582c`:

```
<tool_result id="tr_99567f16582c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T19:21:15.583000+00:00..2026-09-17T19:23:05.059352+00:00" radius="seed" hops="0">
service: cartservice
26 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-17T18:04:20.470761+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.4h before onset  2026-09-17T17:56:03.098388+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_d0ff8d9d0b30`:

```
<tool_result id="tr_d0ff8d9d0b30" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T07:21:15.583000+00:00..2026-09-17T13:21:15.583000+00:00">
no traces for checkoutservice over this window
</tool_result:tr_d0ff8d9d0b30>
```

> Evidence `tr_c2d2f8babdf6`:

```
<tool_result id="tr_c2d2f8babdf6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T18:51:15.583000+00:00..2026-09-17T19:23:05.059352+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T18:51:18.241463+00:00  {"message":"[PlaceOrder] user_id=\"c4504ac8-b2c8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T18:51:18.241340756Z"}
2026-09-17T18:51:18.258689+00:00  {"message":"payment went through (transaction_id: 11b58bce-b1b9-466a-b280-62dcc0085470)","severity":"info","timestamp":"2026-09-17T18:51:18.258588131Z"}
2026-09-17T18:51:18.264356+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-17T18:51:18.264212464Z"}
2026-09-17T18:51:18.269546+00:00  {"message":"Successful to write message. offset: 66280","severity":"info","timestamp":"2026-09-17T18:51:18.269469672Z"}
```

