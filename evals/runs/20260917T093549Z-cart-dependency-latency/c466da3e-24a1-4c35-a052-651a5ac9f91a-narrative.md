# Cart hop carrying a fixed ~300ms egress delay; checkout tips into errors

## What was visible, and the dead ends

The page named cartservice as origin, twelve services in radius, warning severity, with cartservice, loadgenerator, checkoutservice and frontend alerting. Four edges in the radius were never measured, so the starting map was partly guesswork.

First instinct was that cartservice itself had gone bad. Logs said otherwise: routine add-item/get-cart/empty-cart traces, continuous at both edges of the hour, no panics, no startup banners, no connection-refused lines. Crashloop and "cart went silent" are both out. Two caveats to carry: the result was truncated to the oldest eight and newest thirty-two lines, so most of the hour's log body was never read, and the empty userId values that look alarming are present across the whole window and predate the incident.

The cartservice error-ratio metric was a pure dead end. It returned no samples in the incident window and none in the preceding baseline hour either. That is not "cart stopped serving" — an equally empty baseline means the gap predates onset, and the series was most likely never produced or scraped for this service. It cannot discriminate in either direction. Do not spend time on it next occurrence.

The change log was noisy and most of the noise was irrelevant. A v1.2.1 cart hotfix image rolled forward and reverted three times, the last revert completing about T-15m, so the suspect build was not live at onset. A REDIS_ADDR edit to an alternate redis-cart port existed but was applied ~4.5h before onset and reverted nine minutes later, so no cache config was open. Gradual drift is out too — every earlier change was explicitly reverted. All eleven changes are attributed to platform-automation; there is no human rollout to chase.

> Evidence `tr_3e37a2185753`:

```
<tool_result id="tr_3e37a2185753" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T08:39:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T08:39:30.718578+00:00  AddItemAsync called with userId=4ce8f6ec-b273-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=5
2026-09-17T08:39:30.720419+00:00  GetCartAsync called with userId=4ce8f6ec-b273-11f1-b359-b6ed2071a170
2026-09-17T08:39:33.310953+00:00  AddItemAsync called with userId=4e7bb4a4-b273-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=2
2026-09-17T08:39:33.313034+00:00  GetCartAsync called with userId=4e7bb4a4-b273-11f1-b359-b6ed2071a170
```

> Evidence `tr_f6b9bc0254e0`:

```
<tool_result id="tr_f6b9bc0254e0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T08:39:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" template="error-ratio" baseline="2026-09-17T07:37:27.955758+00:00..2026-09-17T08:39:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_73e8163729ef`:

```
<tool_result id="tr_73e8163729ef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T09:39:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" radius="seed" hops="0">
service: cartservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T09:35:57.974825+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T09:25:21.244781+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## What survived, and where the time went

One change survived the sweep: a traffic-shaping sidecar attached to cart-service's network namespace at about T-4m, imposing a fixed 300ms egress delay with zero jitter on eth0, with no matching removal in the window. An identical attachment with the same parameters appeared and was removed hours earlier, so this is a repeating automated pattern rather than a one-off.

Traces settled it. Around T-28m cart handlers ran 0.4-2.0ms and its Redis calls 0.2-0.7ms. From about T+1m onward every cart egress call sits in a tight 300.5-310.3ms band across independent traces and both operations — that tightness rules out contention, GC, or loss, which would give a wide skewed spread. The penalty is additive per hop: a single GetCart root lands near 605ms, an AddItem+GetCart root near 1.5s. The same ~303ms appears on the caller side, in frontend's and checkoutservice's CartService client spans (~906ms where hops stack), while cart's own handler self-time stays at 0.5-1.1ms in those very traces. So the time is in the hop, not in cart's logic or CPU. Other downstreams in the slow checkout trace sat at 0-18ms while the checkout→cart hops accounted for ~1208ms and ~1225ms. No retries or errors inflated the long traces; the only ERROR spans were on an emailservice render path in a 60ms trace, unrelated. One trace at about T-14m showed a milder version of the same shape, so there may have been light perturbation before the full step — but it is a step, not a ramp.

Meanwhile checkoutservice's error ratio rose about two orders of magnitude from a clean, low-spread baseline, with a high-variance distribution reaching a substantial fraction of calls failing. This is not pure slowness. One interval has no defined ratio at all, meaning no traffic served — a zero-looking reading there must not be read as health.

> Evidence `tr_73e8163729ef`:

```
<tool_result id="tr_73e8163729ef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T09:39:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" radius="seed" hops="0">
service: cartservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T09:35:57.974825+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T09:25:21.244781+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_08e03d8a1691`:

```
<tool_result id="tr_08e03d8a1691" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T08:09:30.583000+00:00..2026-09-17T09:41:33.210242+00:00">
service: cartservice
15 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 15e71a1bcb2f3162  root frontend/HTTP POST  5.6ms  started 2026-09-17T09:11:15.244028+00:00  8 spans
  +0.0ms frontend/HTTP POST 5.6ms [self 0.4ms]
```

> Evidence `tr_b4a881275afa`:

```
<tool_result id="tr_b4a881275afa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T09:09:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" template="error-ratio" baseline="2026-09-17T08:37:27.955758+00:00..2026-09-17T09:09:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.1836 min=0 max=0.6667 sd=0.2942
  baseline window: n=117 mean=0.0008854 min=0 max=0.01887 sd=0.003478
```

## Conclusion, fix, and what is still open

A platform-automation traffic-shaping sidecar attached to cartservice's network namespace at about T-4m and never removed imposed a fixed 300ms/zero-jitter egress delay on eth0. Every trace matches that signature. cartservice is healthy and serving; what callers suffer is waiting on the cart hop, and checkoutservice — which crosses it repeatedly — tips from slow into failing. Fix class is a config revert: detach the shaping sidecar. Confidence high.

Three loose ends. First and most important, a timeline conflict: checkout's error-ratio change point lands about T-22m, roughly nineteen minutes before the sidecar was attached. Added cart latency cannot explain degradation that predates it, so either a second concurrent failure was running or the image roll-forward/revert cycle around T-25m/T-15m had an unexcluded effect. Second, an inferential gap: no checkout latency series or timeout configuration was retrieved and the failing calls' status codes were never read, so "cart wait exceeds checkout deadline" rests on trace durations alone. Third, coverage: nothing was dispatched against frontend or loadgenerator despite both alerting, four edges remain unmeasured, and because this attachment has recurred before, whether it is still attached or will be re-attached by automation after removal is unknown.

> Evidence `tr_73e8163729ef`:

```
<tool_result id="tr_73e8163729ef" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T09:39:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" radius="seed" hops="0">
service: cartservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T09:35:57.974825+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T09:25:21.244781+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_b4a881275afa`:

```
<tool_result id="tr_b4a881275afa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T09:09:30.583000+00:00..2026-09-17T09:41:33.210242+00:00" template="error-ratio" baseline="2026-09-17T08:37:27.955758+00:00..2026-09-17T09:09:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.1836 min=0 max=0.6667 sd=0.2942
  baseline window: n=117 mean=0.0008854 min=0 max=0.01887 sd=0.003478
```

> Evidence `tr_08e03d8a1691`:

```
<tool_result id="tr_08e03d8a1691" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T08:09:30.583000+00:00..2026-09-17T09:41:33.210242+00:00">
service: cartservice
15 trace(s) shown of 20 found, 200 spans; offsets are from each trace's root

trace 15e71a1bcb2f3162  root frontend/HTTP POST  5.6ms  started 2026-09-17T09:11:15.244028+00:00  8 spans
  +0.0ms frontend/HTTP POST 5.6ms [self 0.4ms]
```

