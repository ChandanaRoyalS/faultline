# Uniform added delay on the cart path slows four upstream services

## What was visible, in order

Four services alerted together at warning severity — cartservice, checkoutservice, frontend, loadgenerator — with cartservice named as origin and a blast radius of twelve. The useful observation before any tool was opened: the three non-cart alerters all sit upstream of cart. That pattern says one slow node with unhappy callers, and it justified starting at cart rather than fanning out. Onset was T+0; four network edges in the affected region were never measured at all.

The first instinct was metrics, and it failed twice. Cart's error-ratio query returned nothing — no samples in the incident window and none in the four-hour baseline. That emptiness is a trap: it looks like a flat zero and a flat zero looks like health. Because the baseline was equally empty, the honest reading is that the series does not exist under the queried label, not that cart went quiet when it degraded. Checkout's identical template did return data — 129 samples, all zero, no variance — which usefully says requests were completing, but it is an error ratio and the question was latency. No p95, p99 or request-rate series was ever retrieved for any service.

Cart's logs came next. Ordinary request-handling chatter throughout: no error text, no panic, no startup banner, nothing about the backing store refusing connections, and normal operations logged right to the end of the window. So the process was alive and serving. But coverage was truncated to the oldest eight and newest thirty-two lines, leaving roughly four hours in the middle — including the minutes just before onset — unexamined. Clean ends rule out a loud continuous failure; they rule out nothing quieter.

> Evidence `tr_a31334102793`:

```
<tool_result id="tr_a31334102793" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-18T01:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" template="error-ratio" baseline="2026-09-17T21:22:57.430650+00:00..2026-09-18T01:25:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_9e702118bff8`:

```
<tool_result id="tr_9e702118bff8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-18T04:55:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" template="error-ratio" baseline="2026-09-18T04:22:57.430650+00:00..2026-09-18T04:55:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_4657d029c4b2`:

```
<tool_result id="tr_4657d029c4b2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-18T01:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-18T01:25:04.095145+00:00  GetCartAsync called with userId=
2026-09-18T01:25:09.546974+00:00  AddItemAsync called with userId=c9ad0bb4-b2ff-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=4
2026-09-18T01:25:09.549659+00:00  GetCartAsync called with userId=c9ad0bb4-b2ff-11f1-b359-b6ed2071a170
2026-09-18T01:25:09.562565+00:00  GetCartAsync called with userId=c9ad0bb4-b2ff-11f1-b359-b6ed2071a170
```

## The turn: traces, then the change record

Ten traces resolved it. Cart's own gRPC handlers were sub-millisecond (0.4–1.0ms self time); all elapsed time sat elsewhere. Every Redis operation cost ~300–304ms of self time, and HMSET writes matched HGET reads exactly, which killed the cache-miss theory immediately. Jitter was almost nil — three or four milliseconds of spread around a ~301ms mode — so saturation and pool exhaustion were out, since those produce wide skewed tails.

The delay was per round trip, not per service. Frontend's cart client spans carried ~301–315ms of self time above cart's server span. Checkout's were worse and asymmetric: ~1206–1211ms total with ~904–910ms self time, the cart child span not starting until ~605ms in — ~300ms outbound plus ~300ms back, atop the ~300ms Redis leg. Totals then become arithmetic: cart page views ~608–610ms, AddItem+GetCart ~1509–1536ms, PlaceOrder ~2455–2475ms. Other dependencies in the same traces stayed fast (catalog, currency, payment 0–4ms; email 12–17ms), so this was never broad degradation.

The change history closed it. About three minutes before onset, automated platform tooling attached a traffic-shaping container to cart-service's network namespace applying a fixed 300ms egress delay with zero jitter on eth0 — the only change within hours, and its parameters match the trace measurements exactly.

> Evidence `tr_02879345d918`:

```
<tool_result id="tr_02879345d918" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-18T01:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00">
service: cartservice
10 trace(s) shown of 10 found, 123 spans; offsets are from each trace's root

trace 1f18d93fd181dc90  root frontend/HTTP POST  1516.8ms  started 2026-09-18T05:26:18.146027+00:00  8 spans
  +0.0ms frontend/HTTP POST 1516.8ms [self 1.6ms]
```

> Evidence `tr_c693fdf24eef`:

```
<tool_result id="tr_c693fdf24eef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T05:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" radius="seed" hops="0">
service: cartservice
31 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T05:21:47.543094+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  4.3h before onset  2026-09-18T01:08:34.298853+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

## Dead ends worth keeping

The empty cart error-ratio result. Not a symptom of the incident, just a label mismatch predating it.

Two prominent decoys in the change log. The history shows a repeating machine-driven cycle: a cart hotfix image tag applied then reverted, REDIS_ADDR pointed at an alternate port then reverted, shaping attached then removed. Both the hotfix image and the alternate port look like excellent suspects and both were already reverted — 4.9 and 4.3 hours before onset respectively. The cycle beginning at onset had only reached the shaping step.

Anything involving failures, timeouts or retries. Checkout's error ratio was flat zero across 129 samples and every trace completed its full span tree through payment, email and order publish, with no duplicated cart spans. Work was delayed, never abandoned. Likewise ruled out: cart's application code (handlers under a millisecond), packet loss or instability (fixed delay, zero jitter, no loss term), and the idea that checkout was the locus (plain frontend cart views showed the same doubled structure with checkout absent).

> Evidence `tr_a31334102793`:

```
<tool_result id="tr_a31334102793" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-18T01:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" template="error-ratio" baseline="2026-09-17T21:22:57.430650+00:00..2026-09-18T01:25:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_c693fdf24eef`:

```
<tool_result id="tr_c693fdf24eef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T05:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" radius="seed" hops="0">
service: cartservice
31 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T05:21:47.543094+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  4.3h before onset  2026-09-18T01:08:34.298853+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_9e702118bff8`:

```
<tool_result id="tr_9e702118bff8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-18T04:55:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" template="error-ratio" baseline="2026-09-18T04:22:57.430650+00:00..2026-09-18T04:55:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

## Conclusion, and what is still open

A traffic-shaping container on cart-service's network namespace imposed a fixed ~300ms delay with no jitter. Every round trip crossing that namespace pays it once — cart's outbound Redis leg and each caller's leg in and back out — which is why totals scale linearly with hop count and why checkout, two hops deep, suffered most. Nothing broke; callers simply waited. Fix class is a revert of the change. Confidence is high, resting on the numerical agreement between the recorded delay and the measured per-hop cost.

Three gaps a future responder should close. No latency or request-rate series was ever measured, so the step-up rests entirely on traces plus the change record with no metric before/after boundary. The backing store was never inspected directly, and the shaping container's presence at onset was never confirmed on the live pods — the change log is a single untrusted source. And log coverage skipped the minutes immediately before onset, while no service beyond cart and checkout was probed despite four unmeasured edges.

> Evidence `tr_02879345d918`:

```
<tool_result id="tr_02879345d918" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-18T01:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00">
service: cartservice
10 trace(s) shown of 10 found, 123 spans; offsets are from each trace's root

trace 1f18d93fd181dc90  root frontend/HTTP POST  1516.8ms  started 2026-09-18T05:26:18.146027+00:00  8 spans
  +0.0ms frontend/HTTP POST 1516.8ms [self 1.6ms]
```

> Evidence `tr_c693fdf24eef`:

```
<tool_result id="tr_c693fdf24eef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-17T05:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" radius="seed" hops="0">
service: cartservice
31 changes, ranked by suspicion
  #1  3m before onset  2026-09-18T05:21:47.543094+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  4.3h before onset  2026-09-18T01:08:34.298853+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_4657d029c4b2`:

```
<tool_result id="tr_4657d029c4b2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-18T01:25:00.583000+00:00..2026-09-18T05:27:03.735350+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-18T01:25:04.095145+00:00  GetCartAsync called with userId=
2026-09-18T01:25:09.546974+00:00  AddItemAsync called with userId=c9ad0bb4-b2ff-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=4
2026-09-18T01:25:09.549659+00:00  GetCartAsync called with userId=c9ad0bb4-b2ff-11f1-b359-b6ed2071a170
2026-09-18T01:25:09.562565+00:00  GetCartAsync called with userId=c9ad0bb4-b2ff-11f1-b359-b6ed2071a170
```

