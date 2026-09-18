# Uniform per-call delay on cartservice egress, surfacing as slow checkout

## What we saw first

The page covered four services — cartservice, checkoutservice, frontend, loadgenerator — with a blast radius of twelve and a severity of warning. Nothing in the alert text said what was wrong, only that cartservice was the origin and that four edges out from it had no measurements attached at all. Severity stayed at warning throughout: orders kept completing, users kept getting pages back. The complaint was time, not availability.

If you are reading this cold, the shape of the answer is: a fixed cost was added to every outbound call leg from cartservice's network namespace, and everything else in the record is either confirmation of that or a road that went nowhere.

## Traces were the load-bearing evidence

Ten sampled cartservice traces spanning the window told the story without ambiguity. Every Redis-operation span sat in a tight band around 300–311ms of self-time. Reads (HGET) and writes (HMSET) were indistinguishable. There were no fast calls at all — not a long tail, a uniformly shifted distribution.

The handlers themselves were doing nothing. AddItem and GetCart server spans reported roughly 0.4–1.1ms of self-time while running 300–613ms wall clock; the entire duration lived in their children. One hop up, the frontend's client spans to CartService carried the same ~302–310ms of unexplained self-time beyond the server span they wrapped. So the penalty attached to the call leg, on both the frontend→cart hop and the cart→Redis hop.

Because the cost was per call, total latency scaled with call count in a way you could do arithmetic on: single-read flows landed at ~605–615ms (two inflated hops), AddItem flows that do HGET then HMSET then a follow-up GetCart landed at ~1518–1528ms. None of the 59 spans carried an error status, and every trace completed to its root.

> Evidence `tr_bb25958836ff`:

```
<tool_result id="tr_bb25958836ff" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00">
service: cartservice
10 trace(s) shown of 10 found, 59 spans; offsets are from each trace's root

trace 7a35c4cec62b34c1  root cartservice/HGET  300.6ms  started 2026-09-18T00:46:09.220015+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

## The change that explains it

The change log for cartservice covers about 21 hours and 35 entries, all attributed to platform-automation, and it repeats a cycle: a hotfix image tag applied then reverted, REDIS_ADDR pointed at an alternate cache port then reverted, a traffic-shaping container attached to the cart-service network namespace then removed.

At roughly T-3m, one of those shaping containers was attached to the cart-service network namespace with a constant ~300ms egress delay on eth0, zero jitter, no loss parameter. Every earlier attachment in the log had a matching removal. This one did not. It was the only change still in effect when symptoms began, and its parameters match the trace signature exactly — constant, not variable; egress, not command-cost; per-leg, not per-service.

> Evidence `tr_d4304d852c3c`:

```
<tool_result id="tr_d4304d852c3c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T00:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" radius="seed" hops="0">
service: cartservice
35 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T00:41:39.845467+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-18T00:31:04.246813+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## Dead ends, in the order we walked them

The hotfix image tag. It was live earlier in the day and looks guilty on a skim. It was reverted about 14 minutes before onset, and the same tag had been applied and rolled back repeatedly through the day without producing this. cartservice was on its baseline image when things went wrong.

The Redis endpoint override. REDIS_ADDR had been pointed at an alternate cache port at one stage. That was reverted roughly 3.2 hours before onset and never re-applied; there is no cache or Redis config change anywhere in the three hours before symptoms. Ruled out.

Redis being slow. Tempting, given every inflated span was a Redis span. But a cheap read and a write cost the same to the millisecond, which no workload-dependent datastore problem produces. Ruled out.

Handler-resident cost — serialization, lock contention, GC. Sub-2ms handler self-time leaves no room for it.

Retries and timeouts as the source of the latency. No error status on any sampled span, and each inflated span is one occurrence per call, not a repeated attempt.

A crash loop or cold start on cartservice. Logs at window close show ordinary cart reads, adds and clears interleaved across multiple distinct user sessions right up to about T+2m — no restart banner, no fatal line, no cache-connection error. The oldest retained lines, three hours earlier, are equally ordinary, so the service was not already broken at window open.

cartservice metrics. We asked for error ratio, request rate, p95, restarts, saturation and readiness. The only query that ran was the span-derived error ratio, and it returned nothing — not in the incident window and not in the baseline either. The symmetric emptiness matters: it means this series has no coverage for cartservice, not that telemetry stopped at onset. Every other requested signal for cartservice is simply unmeasured. Do not read this result as evidence of health.

> Evidence `tr_d4304d852c3c`:

```
<tool_result id="tr_d4304d852c3c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T00:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" radius="seed" hops="0">
service: cartservice
35 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T00:41:39.845467+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-18T00:31:04.246813+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_bb25958836ff`:

```
<tool_result id="tr_bb25958836ff" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00">
service: cartservice
10 trace(s) shown of 10 found, 59 spans; offsets are from each trace's root

trace 7a35c4cec62b34c1  root cartservice/HGET  300.6ms  started 2026-09-18T00:46:09.220015+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

> Evidence `tr_14cf4af246df`:

```
<tool_result id="tr_14cf4af246df" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T21:45:18.080819+00:00  GetCartAsync called with userId=
2026-09-17T21:45:19.257676+00:00  AddItemAsync called with userId=13a66da6-b2e1-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=2
2026-09-17T21:45:19.260721+00:00  GetCartAsync called with userId=13a66da6-b2e1-11f1-b359-b6ed2071a170
2026-09-17T21:45:19.385611+00:00  GetCartAsync called with userId=
```

> Evidence `tr_d9a7131639af`:

```
<tool_result id="tr_d9a7131639af" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" template="error-ratio" baseline="2026-09-17T18:42:56.603571+00:00..2026-09-17T21:45:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## What it did to callers

checkoutservice logs show the propagation cleanly. Early in the window a full PlaceOrder flow — order placement, payment, confirmation email, message write — completed end to end in tens of milliseconds. In the final minutes the same stages were separated by roughly a second each. Orders still completed: Kafka offsets advanced contiguously with no gaps, confirmation emails kept going out.

checkoutservice's error ratio moved into a distinct regime during the window — mean around 0.177 against an immediate-prior baseline of about 0.0004, with high variance and peaks near two thirds of requests failing but a floor at zero. That is bursty partial failure, consistent with timeouts firing on the slowest cart calls, not a service that is down.

> Evidence `tr_486ff2e60d91`:

```
<tool_result id="tr_486ff2e60d91" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-18T00:15:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-18T00:15:16.990793+00:00  {"message":"[PlaceOrder] user_id=\"06b0c6d6-b2f6-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-18T00:15:16.990696629Z"}
2026-09-18T00:15:17.010468+00:00  {"message":"payment went through (transaction_id: 0998063a-ff36-4c73-a30d-7c7b7bec0a14)","severity":"info","timestamp":"2026-09-18T00:15:17.010202462Z"}
2026-09-18T00:15:17.016451+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-18T00:15:17.016363379Z"}
2026-09-18T00:15:17.017629+00:00  {"message":"Successful to write message. offset: 68572","severity":"info","timestamp":"2026-09-18T00:15:17.017504046Z"}
```

> Evidence `tr_7f11aad5b931`:

```
<tool_result id="tr_7f11aad5b931" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-18T00:15:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" template="error-ratio" baseline="2026-09-17T23:42:56.603571+00:00..2026-09-18T00:15:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.1773 min=0 max=0.6667 sd=0.2857
  baseline window: n=130 mean=0.0004321 min=0 max=0.01587 sd=0.002
```

## Still open — read this before you close anything

The timeline does not fully close. checkoutservice's error change point sits at roughly T-22m, about nineteen minutes before the shaping container was attached. A delay applied at T-3m cannot cause errors that were already elevated at T-22m. Either an earlier automation action in that repeating cycle is implicated, or there is a second overlapping failure we never isolated. The baseline used for that comparison was also only the ~32 preceding minutes, not the three hours the question assumed, so the multiplier is against a short recent reference.

No log lines from the onset interval itself were returned for either service. Both queries were truncated to the oldest handful and newest few dozen lines, and onset falls inside the dropped span. We therefore never observed the failure mode at the alert moment — timeout versus refused versus application error is unknown. A narrower time range would fix this.

Whether the shaping container is still attached is unconfirmed, and the two signals disagree. Checkout's log tail looks recovered by about T+1m, while cart traces sampled at roughly T+1m still carry the full per-call penalty. Verify directly on the host rather than inferring.

Finally, the cartservice log selector used the label value cart-service; anything emitted under a different stream label for the same component would not appear in what we looked at.

> Evidence `tr_7f11aad5b931`:

```
<tool_result id="tr_7f11aad5b931" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-18T00:15:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" template="error-ratio" baseline="2026-09-17T23:42:56.603571+00:00..2026-09-18T00:15:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.1773 min=0 max=0.6667 sd=0.2857
  baseline window: n=130 mean=0.0004321 min=0 max=0.01587 sd=0.002
```

> Evidence `tr_d4304d852c3c`:

```
<tool_result id="tr_d4304d852c3c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T00:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" radius="seed" hops="0">
service: cartservice
35 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T00:41:39.845467+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-18T00:31:04.246813+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_14cf4af246df`:

```
<tool_result id="tr_14cf4af246df" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T21:45:18.080819+00:00  GetCartAsync called with userId=
2026-09-17T21:45:19.257676+00:00  AddItemAsync called with userId=13a66da6-b2e1-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=2
2026-09-17T21:45:19.260721+00:00  GetCartAsync called with userId=13a66da6-b2e1-11f1-b359-b6ed2071a170
2026-09-17T21:45:19.385611+00:00  GetCartAsync called with userId=
```

> Evidence `tr_486ff2e60d91`:

```
<tool_result id="tr_486ff2e60d91" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-18T00:15:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-18T00:15:16.990793+00:00  {"message":"[PlaceOrder] user_id=\"06b0c6d6-b2f6-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-18T00:15:16.990696629Z"}
2026-09-18T00:15:17.010468+00:00  {"message":"payment went through (transaction_id: 0998063a-ff36-4c73-a30d-7c7b7bec0a14)","severity":"info","timestamp":"2026-09-18T00:15:17.010202462Z"}
2026-09-18T00:15:17.016451+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-18T00:15:17.016363379Z"}
2026-09-18T00:15:17.017629+00:00  {"message":"Successful to write message. offset: 68572","severity":"info","timestamp":"2026-09-18T00:15:17.017504046Z"}
```

> Evidence `tr_bb25958836ff`:

```
<tool_result id="tr_bb25958836ff" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00">
service: cartservice
10 trace(s) shown of 10 found, 59 spans; offsets are from each trace's root

trace 7a35c4cec62b34c1  root cartservice/HGET  300.6ms  started 2026-09-18T00:46:09.220015+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

## Disposition

Fix class is a config revert: detach the traffic-shaping container from the cart-service network namespace and confirm the egress delay is gone by re-sampling cart traces for sub-5ms Redis span self-time. Confidence in the cause is medium — the signature match is strong and the timing is close, but the unexplained earlier error onset on checkoutservice means this may not be the whole incident. The repeating apply/revert cycle from platform-automation is itself worth a follow-up; an automated action that can leave a network-level delay in place with no removal is a standing hazard regardless of what else was going on.

> Evidence `tr_d4304d852c3c`:

```
<tool_result id="tr_d4304d852c3c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T00:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00" radius="seed" hops="0">
service: cartservice
35 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T00:41:39.845467+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-18T00:31:04.246813+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_bb25958836ff`:

```
<tool_result id="tr_bb25958836ff" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T21:45:15.583000+00:00..2026-09-18T00:47:34.562429+00:00">
service: cartservice
10 trace(s) shown of 10 found, 59 spans; offsets are from each trace's root

trace 7a35c4cec62b34c1  root cartservice/HGET  300.6ms  started 2026-09-18T00:46:09.220015+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

