# Checkout orders start and never finish: a stall with no error signal

## What was visible, in order

The page named checkoutservice at T+0. Within about three and a quarter minutes four more services joined: accountingservice, emailservice, frauddetectionservice, quoteservice. Critical, eleven services in the blast radius, entry point checkout. The instinct in the chair was that something downstream was throwing errors and the errors were fanning out.

That instinct was wrong in a useful way. The first check was checkoutservice's error ratio against the preceding hour, and it fell rather than rose — incident-window mean around 43% of baseline, window maximum below the baseline maximum, with identical sample density on both sides (262 points each) so not a coverage artifact. Checkout was not the origin of an error surge, and a downstream hard failure propagating error status upward was closed off, since that would have lifted this ratio. Latency-only degradation, which this metric cannot see, stayed open. A side effect worth noting: whatever tripped the alert at T+0 was not this metric, because nothing here crosses a threshold. That was never answered.

The logs settled the shape. Early in the window each order emitted a full sequence — order start, payment success, confirmation email, successful queue write with an incrementing offset. From roughly T+1m50s onward only order-start lines remain; the payment, email and queue-write completions vanish and the queue offsets stop entirely. Yet order-start lines continue at a steady several-per-minute cadence through T+5m, so the process is alive and accepting traffic. Every returned line is info severity: no error or warn lines, no status codes, no named dependency, no panic or stack trace. Not a crash, not a restart, not an internal exception, and not a failure at intake — the break sits strictly after the order-start line and before the payment/email/queue stage. Requests that start, never complete and never carry an error status are the signature of a synchronous outbound call that hangs instead of returning.

> Evidence `tr_6165d2b75628`:

```
<tool_result id="tr_6165d2b75628" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" template="error-ratio" baseline="2026-09-10T12:14:08.750565+00:00..2026-09-10T13:19:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=262 mean=0.03476 min=0 max=0.2957 sd=0.08116
  baseline window: n=262 mean=0.07983 min=0 max=0.6667 sd=0.2089
```

> Evidence `tr_c7bb7669feb9`:

```
<tool_result id="tr_c7bb7669feb9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T13:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T13:19:35.375041+00:00  {"message":"[PlaceOrder] user_id=\"446076c0-ad1a-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T13:19:35.374945002Z"}
2026-09-10T13:19:35.400582+00:00  {"message":"payment went through (transaction_id: 48152ba0-6861-4c3b-84fd-8fbb70ab2647)","severity":"info","timestamp":"2026-09-10T13:19:35.400464252Z"}
2026-09-10T13:19:35.405128+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-10T13:19:35.405010794Z"}
2026-09-10T13:19:35.406224+00:00  {"message":"Successful to write message. offset: 31900","severity":"info","timestamp":"2026-09-10T13:19:35.406144752Z"}
```

## Dead ends worth keeping

Blaming a change on checkoutservice. Its change history across the full preceding day came back observed and empty — no deploys, no config or flag edits, no dependency bumps, no image updates. There is no artifact to roll back, which removes the tidiest remediation path and forces attention onto unchanged-system causes.

Cartservice. This absorbed the most time and produced no verdict. Its change log holds twenty entries over the preceding day, all from platform-automation, in matched pairs on a roughly six-to-seven-hour cycle: an image tag swap to a hotfix build, a Redis connection-string override, and a 300ms network delay on eth0. Every one was reverted before onset — image about 2.2 hours prior, the traffic-shaping container about 1.8 hours prior, the Redis override about 1.6 hours prior, and that revert is the most recent change of any kind. Nothing landed in the hour before onset, so at T+0 cartservice ran baseline configuration. But its observability is thin: the error-ratio series returned zero samples in both incident and baseline windows, so the series is absent rather than flat at zero, and silence cannot be read as health. Its logs were truncated to the oldest eight and newest thirty-two lines, leaving the entire onset interval unobserved. The returned tail is clean — ordinary cart operations through T+5m, no errors or timeouts, intra-request gaps in single-digit milliseconds matching the window start — which rules out cartservice crashing, hanging or being internally slow at the end of the window, but does not clear it across onset. Cartservice is unexcluded, not cleared. One low-value oddity: several GetCart entries in the tail carry an empty userId, absent from the early lines; not an error, and unjudgeable with the middle of the window missing.

Productcatalogservice. Error ratio during the incident was lower than the preceding half hour, mean down roughly an order of magnitude, no sustained departure, equal sampling (142 points each) and lower variability. An error onset would have raised the mean; a pre-existing error condition would have kept both levels comparable. A hard failure such as crash-looping is excluded, the incident maximum being nowhere near widespread call failure. Caveat: error ratio only — no latency percentiles or request rate were ever collected here.

> Evidence `tr_aa8840893bee`:

```
<tool_result id="tr_aa8840893bee" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T14:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_aa8840893bee>
```

> Evidence `tr_183ded784091`:

```
<tool_result id="tr_183ded784091" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T14:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" radius="candidate_cause" hops="1">
service: cartservice
20 changes, ranked by suspicion
  #1  1.6h before onset  2026-09-10T12:45:53.653662+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.7h before onset  2026-09-10T12:37:19.842008+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_6de53147ad78`:

```
<tool_result id="tr_6de53147ad78" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T13:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" template="error-ratio" baseline="2026-09-10T12:14:08.750565+00:00..2026-09-10T13:19:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_07ca09e8b4d2`:

```
<tool_result id="tr_07ca09e8b4d2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:49:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T12:49:32.062726+00:00  AddItemAsync called with userId=118a148a-ad16-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=2
2026-09-10T12:49:32.065232+00:00  GetCartAsync called with userId=118a148a-ad16-11f1-b359-b6ed2071a170
2026-09-10T12:49:32.075268+00:00  GetCartAsync called with userId=118a148a-ad16-11f1-b359-b6ed2071a170
2026-09-10T12:49:32.095030+00:00  EmptyCartAsync called with userId=118a148a-ad16-11f1-b359-b6ed2071a170
```

> Evidence `tr_96ce5f7c3658`:

```
<tool_result id="tr_96ce5f7c3658" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:49:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" template="error-ratio" baseline="2026-09-10T13:14:08.750565+00:00..2026-09-10T13:49:30.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=142 mean=0.001575 min=0 max=0.06284 sd=0.008137
  baseline window: n=142 mean=0.02 min=0 max=0.1111 sd=0.03606
```

## Where it landed, and what to do first next time

The best-supported reading is that a dependency in checkout's post-intake path — payment, the confirmation email call, or the order-queue write — became slow rather than broken, and checkout's synchronous call into it hung. The fan-out fits: accounting, email, fraud-detection and quote alerting in the same minute is what you would expect if orders simply stop reaching those stages. Checkoutservice is named because it is where the stall is observed and where completion breaks, not because it is the cause. Confidence is low and no fix class is proposed, because this record identifies a shape of failure rather than a component.

Next time, in order of expected payoff: pull latency percentiles, trace spans and a per-downstream breakdown for checkoutservice, paymentservice, emailservice and the order queue — every conclusion above about a hanging call is inferred from missing completion lines, and one trace of a stalled order would name the dependency outright. Then establish what the T+0 alert actually fired on, since it demonstrably was not error ratio. Then re-query cartservice logs narrowly around onset without truncation, and pull change history for the services whose logs were never fetched, to see whether the recurring automation cycle fired inside the unqueried window.

> Evidence `tr_c7bb7669feb9`:

```
<tool_result id="tr_c7bb7669feb9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T13:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T13:19:35.375041+00:00  {"message":"[PlaceOrder] user_id=\"446076c0-ad1a-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T13:19:35.374945002Z"}
2026-09-10T13:19:35.400582+00:00  {"message":"payment went through (transaction_id: 48152ba0-6861-4c3b-84fd-8fbb70ab2647)","severity":"info","timestamp":"2026-09-10T13:19:35.400464252Z"}
2026-09-10T13:19:35.405128+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-10T13:19:35.405010794Z"}
2026-09-10T13:19:35.406224+00:00  {"message":"Successful to write message. offset: 31900","severity":"info","timestamp":"2026-09-10T13:19:35.406144752Z"}
```

> Evidence `tr_6165d2b75628`:

```
<tool_result id="tr_6165d2b75628" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:19:30.583000+00:00..2026-09-10T14:24:52.415435+00:00" template="error-ratio" baseline="2026-09-10T12:14:08.750565+00:00..2026-09-10T13:19:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=262 mean=0.03476 min=0 max=0.2957 sd=0.08116
  baseline window: n=262 mean=0.07983 min=0 max=0.6667 sd=0.2089
```

