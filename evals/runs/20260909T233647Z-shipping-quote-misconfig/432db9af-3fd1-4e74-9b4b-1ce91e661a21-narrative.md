# Checkout orders stop completing while requests keep arriving

## What the responder saw first

The page came in as a critical event seeded on checkoutservice, with a blast radius of fourteen services and companion alerts on accountingservice, emailservice, frauddetectionservice, quoteservice, loadgenerator and frontend. The shape of that alert list is the first useful clue: the three order-consuming services all fire together, which is what you would expect if checkout stopped emitting completed orders rather than if each of them broke independently.

The single most informative artefact was the checkoutservice log stream. At the start of the observed window each PlaceOrder line is followed by a full downstream sequence — payment authorization with a transaction id, confirmation email dispatch, then a successful order-message write with an incrementing offset. From roughly 23:41:50 onward, only the PlaceOrder entry lines remain. Payment, email and message-write lines are all absent. PlaceOrder entries themselves keep arriving every few seconds through the end of the window, so the process is alive and still accepting work; it simply never reaches the second stage.

> Evidence `tr_fb44839c21d4`:

```
<tool_result id="tr_fb44839c21d4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T23:09:51.340461+00:00  {"message":"[PlaceOrder] user_id=\"8f896232-aca3-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T23:09:51.340305465Z"}
2026-09-09T23:09:51.360302+00:00  {"message":"payment went through (transaction_id: 54c6fc33-de42-421b-95c4-bd43e2545245)","severity":"info","timestamp":"2026-09-09T23:09:51.360150965Z"}
2026-09-09T23:09:51.365193+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-09T23:09:51.365089382Z"}
2026-09-09T23:09:51.365921+00:00  {"message":"Successful to write message. offset: 25875","severity":"info","timestamp":"2026-09-09T23:09:51.365835548Z"}
```

## Reading the silence correctly

There are no error- or warning-severity lines anywhere in the returned checkout logs. Every line is info. That absence is the load-bearing observation: requests are blocking inside checkout's first downstream call rather than failing fast. A hard failure would have produced a status code, an RPC name, or at minimum an error line, and none exists.

The metrics agree, in a way that is easy to misread. Two separate dispatches asked for checkoutservice behaviour and both returned only an aggregate error ratio. Over the incident window that ratio averaged roughly 2.7% with brief excursions near 28%, against a baseline averaging about 8.5% with peaks near 67% — the incident window is the calmer of the two, and the comparison flags no sustained departure. A responder arriving expecting an error spike will find the opposite and should not conclude the service is healthy. The correct reading is that the failure mode does not set error status at all.

> Evidence `tr_fb44839c21d4`:

```
<tool_result id="tr_fb44839c21d4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T23:09:51.340461+00:00  {"message":"[PlaceOrder] user_id=\"8f896232-aca3-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T23:09:51.340305465Z"}
2026-09-09T23:09:51.360302+00:00  {"message":"payment went through (transaction_id: 54c6fc33-de42-421b-95c4-bd43e2545245)","severity":"info","timestamp":"2026-09-09T23:09:51.360150965Z"}
2026-09-09T23:09:51.365193+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-09T23:09:51.365089382Z"}
2026-09-09T23:09:51.365921+00:00  {"message":"Successful to write message. offset: 25875","severity":"info","timestamp":"2026-09-09T23:09:51.365835548Z"}
```

> Evidence `tr_766519f01883`:

```
<tool_result id="tr_766519f01883" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" template="error-ratio" baseline="2026-09-09T22:34:41.039358+00:00..2026-09-09T23:09:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=141 mean=0.04979 min=0 max=0.2759 sd=0.1004
  baseline window: n=141 mean=0.07506 min=0 max=0.6667 sd=0.2042
```

> Evidence `tr_1575d9d26299`:

```
<tool_result id="tr_1575d9d26299" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T22:39:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" template="error-ratio" baseline="2026-09-09T21:34:41.039358+00:00..2026-09-09T22:39:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=261 mean=0.02718 min=0 max=0.2759 sd=0.07768
  baseline window: n=226 mean=0.08481 min=0 max=0.6667 sd=0.2141
```

## Dead end: the change log

The obvious first move was to look for something that shipped. Scoped to checkoutservice alone across a full 24 hours around the event, the change log came back completely empty — no deploy, no image or tag update, no config or environment-variable edit. That closes the rollback path for the seed service outright. Worth noting that this query was scoped to the seed with zero hops, so it said nothing about dependencies; that gap had to be filled separately.

The wider query returned 26 entries, every one of them on cartservice and every one attributed to the same automation actor. They arrive as repeating paired cycles: an image reference set to a hotfix tag then reverted, a traffic-shaping sidecar attached to the cart network namespace with a fixed egress delay then removed, and a Redis address environment variable set then reverted. The cycle repeats four or five times across the window. Critically, every set has a matching revert that completes before onset — the image and sidecar reverts about eight hours prior, the environment revert about one hour prior. Nothing from that activity was live when the incident began. The same query also confirms that none of the six peer dependencies (productcatalog, currency, payment, ad, recommendation, shipping) has any recorded change at all. This whole line of inquiry consumed real time and produced nothing causal.

> Evidence `tr_ab815e19d831`:

```
<tool_result id="tr_ab815e19d831" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T23:39:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_ab815e19d831>
```

> Evidence `tr_674659df4315`:

```
<tool_result id="tr_674659df4315" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T23:39:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" radius="candidate_cause" hops="1">
service: cartservice
26 changes, ranked by suspicion
  #1  1.0h before onset  2026-09-09T22:37:51.973364+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.2h before onset  2026-09-09T22:29:53.992613+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Dead end: cartservice

Because the change activity all pointed at cartservice, it drew attention it did not deserve. Its logs show routine cart reads and item-adds at both ends of the window, with no error, exception, timeout, retry or backend-failure lines anywhere, and operations still completing within seconds of the window end — multiple distinct users served in the same second. No restart markers, no tail gap. cartservice was serving normally throughout.

The cartservice error-ratio query was worse than unhelpful: it returned no samples in either the incident or baseline window. Because the emptiness spans both windows equally, it is a metric-availability or label-matching gap rather than a symptom of the event. It cannot be used to time onset and it cannot be used to implicate or exonerate — the exoneration comes from the logs, not from that series.

> Evidence `tr_1539009e3c6e`:

```
<tool_result id="tr_1539009e3c6e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T23:09:47.825754+00:00  GetCartAsync called with userId=
2026-09-09T23:09:49.374347+00:00  AddItemAsync called with userId=8e5f3c1a-aca3-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=10
2026-09-09T23:09:49.376961+00:00  GetCartAsync called with userId=8e5f3c1a-aca3-11f1-b359-b6ed2071a170
2026-09-09T23:09:49.793773+00:00  AddItemAsync called with userId=8e9f3306-aca3-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=2
```

> Evidence `tr_9ec27e6b79a0`:

```
<tool_result id="tr_9ec27e6b79a0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" template="error-ratio" baseline="2026-09-09T22:34:41.039358+00:00..2026-09-09T23:09:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where the evidence points

What survives is narrow. checkoutservice is up and accepting requests at a steady cadence. It is not erroring. Its first downstream call is not completing. The last stage that ever succeeded is payment authorization, and in the stalled period that line is absent too — so the break sits at or before the payment step, not in the email or message-write stages after it. Currency was checked as a discriminator and does not separate stalled from healthy requests; the late-window stalls are overwhelmingly USD with one CAD request looking no different.

The working conclusion is a downstream call on the payment path that became slow rather than errored, with the secondary alerts on accounting, email and frauddetection following mechanically from checkout no longer emitting completed orders. Confidence in this is low, and deliberately so — the attribution rests entirely on where the log trail stops.

> Evidence `tr_fb44839c21d4`:

```
<tool_result id="tr_fb44839c21d4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T23:09:51.340461+00:00  {"message":"[PlaceOrder] user_id=\"8f896232-aca3-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T23:09:51.340305465Z"}
2026-09-09T23:09:51.360302+00:00  {"message":"payment went through (transaction_id: 54c6fc33-de42-421b-95c4-bd43e2545245)","severity":"info","timestamp":"2026-09-09T23:09:51.360150965Z"}
2026-09-09T23:09:51.365193+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-09T23:09:51.365089382Z"}
2026-09-09T23:09:51.365921+00:00  {"message":"Successful to write message. offset: 25875","severity":"info","timestamp":"2026-09-09T23:09:51.365835548Z"}
```

> Evidence `tr_1575d9d26299`:

```
<tool_result id="tr_1575d9d26299" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T22:39:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" template="error-ratio" baseline="2026-09-09T21:34:41.039358+00:00..2026-09-09T22:39:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=261 mean=0.02718 min=0 max=0.2759 sd=0.07768
  baseline window: n=226 mean=0.08481 min=0 max=0.6667 sd=0.2141
```

## What was never measured

Five unmeasured edges were crossed to reach the conclusion above. A responder revisiting this should start here rather than repeating the work already done.

No dispatch ever touched paymentservice. Its latency, saturation and health are entirely unmeasured; the case against it is log-sequence position and nothing else. No latency or request-rate series was returned for any service — both metric dispatches came back with aggregate error ratio only, so neither the stall duration nor its onset time is directly measured. The checkout logs are truncated to the oldest eight and newest thirty-two lines, leaving roughly 23:10 to 23:41:50 unobserved, so the transition from healthy to stalled was never seen and cannot be timed against the 23:39:45 alert. The order-message path shared by accounting, email and frauddetection was never queried, so it remains untested as a common upstream for those three alerts. And checkoutservice's own resource state — thread pools, connection pools, memory — was never sampled, so self-inflicted blocking inside checkout has not been excluded and remains a live alternative to the payment-path hypothesis.

No fix class was identified. Nothing here supports a rollback.

> Evidence `tr_fb44839c21d4`:

```
<tool_result id="tr_fb44839c21d4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T23:09:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T23:09:51.340461+00:00  {"message":"[PlaceOrder] user_id=\"8f896232-aca3-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T23:09:51.340305465Z"}
2026-09-09T23:09:51.360302+00:00  {"message":"payment went through (transaction_id: 54c6fc33-de42-421b-95c4-bd43e2545245)","severity":"info","timestamp":"2026-09-09T23:09:51.360150965Z"}
2026-09-09T23:09:51.365193+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-09T23:09:51.365089382Z"}
2026-09-09T23:09:51.365921+00:00  {"message":"Successful to write message. offset: 25875","severity":"info","timestamp":"2026-09-09T23:09:51.365835548Z"}
```

> Evidence `tr_1575d9d26299`:

```
<tool_result id="tr_1575d9d26299" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T22:39:45.583000+00:00..2026-09-09T23:44:50.126642+00:00" template="error-ratio" baseline="2026-09-09T21:34:41.039358+00:00..2026-09-09T22:39:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=261 mean=0.02718 min=0 max=0.2759 sd=0.07768
  baseline window: n=226 mean=0.08481 min=0 max=0.6667 sd=0.2141
```

