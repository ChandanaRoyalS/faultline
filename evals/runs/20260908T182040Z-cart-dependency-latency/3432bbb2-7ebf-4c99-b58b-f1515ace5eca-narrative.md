# Cart path latency step traced to egress delay on cart-service network namespace

## What we saw, and the dead ends

The page arrived on cartservice at warning severity; frontend, checkoutservice and loadgenerator followed within seconds. Twelve services in the blast radius, all on the cart call path, four of the crossed edges unmeasured.

First instinct was cartservice error ratio against a baseline. It came back empty, which reads like a traffic blackhole or telemetry dying at onset. It was neither: the pre-incident baseline was equally empty — zero samples, not zero errors. The span-derived call-count series for cartservice is simply unpopulated and always was, so the emptiness carries no timing information at all. We re-ran the same comparison on a second window and got the same nothing. The expensive omission: no duration-percentile or request-rate series for cartservice was ever queried, so the latency story rests entirely on sampled traces.

Logs then cleared the obvious failures in one pass. cartservice logged continuously at sub-second cadence through the whole window, serving ordinary add/get/empty operations, with no error, exception, retry or connection-failure lines and no recurring startup banners. That rules out pod down, image-pull failure, crash-restart loop, and total Redis unavailability. A trickle of requests logged with an empty user identifier appears in the earliest retained segment too — it predates the incident. Don't spend time on it; we did.

> Evidence `tr_3a00f7e8afe4`:

```
<tool_result id="tr_3a00f7e8afe4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T16:24:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" template="error-ratio" baseline="2026-09-08T14:22:37.033610+00:00..2026-09-08T16:24:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_7026064abf3e`:

```
<tool_result id="tr_7026064abf3e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T17:54:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" template="error-ratio" baseline="2026-09-08T17:22:37.033610+00:00..2026-09-08T17:54:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_de406478f270`:

```
<tool_result id="tr_de406478f270" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T16:24:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-08T16:50:08.244043+00:00  AddItemAsync called with userId=5957e3a4-aba5-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=3
2026-09-08T16:50:08.246756+00:00  GetCartAsync called with userId=5957e3a4-aba5-11f1-b359-b6ed2071a170
2026-09-08T16:50:10.931145+00:00  AddItemAsync called with userId=5af44d60-aba5-11f1-b359-b6ed2071a170, productId=6E92ZMYYFZ, quantity=3
2026-09-08T16:50:10.933054+00:00  GetCartAsync called with userId=5af44d60-aba5-11f1-b359-b6ed2071a170
```

## Traces located the delay, change history named the cause

Traces sampled earlier in the window were healthy — cartservice server spans 0.4–1.5ms, Redis ops 0.1–0.6ms — and everything from shortly before onset onward was degraded. Abrupt step, not a ramp.

The penalty is per Redis round-trip, not per RPC: GetCart (one HGET) ~301–306ms, AddItem (HGET+HMSET) ~602–606ms. The increment sits wholly in the Redis client spans (~300.8–305.1ms self-time) while the gRPC handler self-time stays sub-millisecond, so cartservice's own work is not the source. The band is tight across many traces, which killed queueing, contention and variable packet loss alike. No span carries an error status; root frontend requests completed at ~605ms (cart page), ~1.51s (add-to-cart), ~2.48s (checkout). Checkout's other dependencies stayed at 0–20ms. Callers absorb a further increment each — frontend ~302–306ms over the callee, checkoutservice ~908–921ms — because replies leave through the same shaped path.

Change history holds eleven entries, all cartservice, all from the same platform-automation actor, none touching redis-cart. The one landing near onset — roughly three minutes ahead — is a traffic-shaping container attached to cart-service's network namespace with a fixed 300ms egress delay, zero jitter, on eth0. That predicts the banded per-round-trip penalty and the caller-side increment exactly.

Three decoys cost us time: a cartservice hotfix image tag applied and reverted three times, the last revert ~4.8h before onset; a REDIS_ADDR edit to a non-default port, applied ~12.6h and reverted ~12.4h before onset; and an identical shaping attachment ~12.9h before onset, removed ~12.8h before — read the timestamps, not the entry text.

Frontend's error ratio averaged ~0.1%, peaking under 1% — far too low for an unreachable cartservice — but the baseline was exactly zero across eighteen samples, so those few error spans are genuinely new.

> Evidence `tr_0ea671ada1bb`:

```
<tool_result id="tr_0ea671ada1bb" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T17:24:30.583000+00:00..2026-09-08T18:26:24.132390+00:00">
service: cartservice
18 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 8137c0eef0510640  root frontend/HTTP POST  5.1ms  started 2026-09-08T18:11:35.348028+00:00  8 spans
  +0.0ms frontend/HTTP POST 5.1ms [self 0.5ms]
```

> Evidence `tr_3260771d0685`:

```
<tool_result id="tr_3260771d0685" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T18:24:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" radius="seed" hops="0">
service: cartservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-08T18:20:48.947534+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  4.8h before onset  2026-09-08T13:35:25.760775+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_a95591494649`:

```
<tool_result id="tr_a95591494649" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T17:54:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" template="error-ratio" baseline="2026-09-08T17:22:37.033610+00:00..2026-09-08T17:54:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=67 mean=0.0009895 min=0 max=0.008937 sd=0.002712
  baseline window: n=18 mean=0 min=0 max=0 sd=0
```

## Conclusion and what is left open

The cause is the traffic-shaping container on cart-service's network namespace imposing a fixed 300ms egress delay. Every Redis round-trip pays ~300ms of pure wait, and cartservice's replies pay it again, which is why the callers alerted seconds later while staying functionally healthy. Nothing erroring, nothing exhausted, nothing restarting. Fix class is a config revert: detach the shaping container. Confidence high — the change record and the trace geometry agree independently.

Still open: whether the container is still attached or was already detached as in the earlier cycle; the absent latency/throughput metrics, which leave the step confirmed only from sampled traces and which stem from an instrumentation gap predating this incident; and the nature of frontend's small new error population together with the exact accounting for checkoutservice's ~908–921ms, roughly three increments, which the sampled evidence does not resolve.

> Evidence `tr_3260771d0685`:

```
<tool_result id="tr_3260771d0685" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T18:24:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" radius="seed" hops="0">
service: cartservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-08T18:20:48.947534+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  4.8h before onset  2026-09-08T13:35:25.760775+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_7026064abf3e`:

```
<tool_result id="tr_7026064abf3e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T17:54:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" template="error-ratio" baseline="2026-09-08T17:22:37.033610+00:00..2026-09-08T17:54:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_a95591494649`:

```
<tool_result id="tr_a95591494649" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T17:54:30.583000+00:00..2026-09-08T18:26:24.132390+00:00" template="error-ratio" baseline="2026-09-08T17:22:37.033610+00:00..2026-09-08T17:54:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=67 mean=0.0009895 min=0 max=0.008937 sd=0.002712
  baseline window: n=18 mean=0 min=0 max=0 sd=0
```

