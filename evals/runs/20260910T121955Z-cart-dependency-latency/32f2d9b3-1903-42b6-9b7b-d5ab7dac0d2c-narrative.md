# Cart-path slowdown propagating into checkout

## What was visible at the start

The page named four services — cartservice, checkoutservice, frontend and loadgenerator — with a stated blast radius of twelve services and severity warning. Nothing in the alert text said what was wrong, only that the cart path was unhappy. Four edges in the reported radius had no measurement behind them at all, so from the first minute the responder was working with a map that had holes in it.

The first useful shape came from checkoutservice's error ratio. Against a flat, near-zero half-hour baseline (~0.13%), the incident window averaged around 15.7% — roughly a 125x step. Crucially it was a step, not a ramp, and it was partial: the peak sat near two thirds and the series touched zero repeatedly. Checkout was hurting, not dead.

> Evidence `tr_091795de4d3f`:

```
<tool_result id="tr_091795de4d3f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:53:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" template="error-ratio" baseline="2026-09-10T11:21:22.699864+00:00..2026-09-10T11:53:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1574 min=0 max=0.6667 sd=0.2733
  baseline window: n=129 mean=0.001259 min=0 max=0.01935 sd=0.003778
```

## Following the change record

The change log for cartservice was the highest-yield source. Eighteen entries, all attributed to the same platform-automation actor, arranged in a repeating triplet that recurs every six to seven hours: an image update and its revert, a traffic-shaping attach and its removal, a redis environment edit and its revert. The pattern reads as a scheduled routine rather than delivery work.

The entry that matters is roughly T-3m: a traffic-shaping sidecar attached to cart-service's network namespace, imposing a fixed 300ms egress delay with no jitter on eth0. Every earlier attachment in the window has a matching removal recorded. This one does not. It was still in force when the alerts fired.

> Evidence `tr_1a6b4ecd47ad`:

```
<tool_result id="tr_1a6b4ecd47ad" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T12:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" radius="seed" hops="0">
service: cartservice
18 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T12:20:04.006779+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-10T12:09:26.976076+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## Dead ends, in the order they were closed

A cartservice hotfix image was moved into place about T-22m. That is close enough to onset to be tempting, but it was reverted at about T-14m, so the deployment was back on its prior image before anything broke. Not it.

REDIS_ADDR had been pointed at redis-cart on port 6380 several times in the window. Every one of those edits is paired with a revert, the last pair completing roughly six hours before onset. No redis config was outstanding. Not it.

A human or ad-hoc change was considered and dismissed: every recorded change carries the same automation actor.

The cartservice error-ratio query was a wasted round trip in the most instructive way. It returned nothing — not for the incident window, and not for the two-hour baseline preceding it either. The temptation is to read empty as "traffic went to zero" or "emission broke at onset." Both are wrong: the series is equally absent when the service was healthy, so the gap belongs to the metric pipeline or the series naming, not to the incident. Do not spend time on this query next time; go to logs instead.

Logs then closed several structural stories. cartservice was logging steady-state cart operations continuously to within seconds of the window end, so it was neither down nor crash-looping nor failing to pull an image, and there was no total loss of its cache backend. checkoutservice's tail showed whole orders completing — place, pay, email, publish with strictly increasing offsets — so payment and the publish path were both fine, and the service had recovered correctness by query time.

> Evidence `tr_1a6b4ecd47ad`:

```
<tool_result id="tr_1a6b4ecd47ad" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T12:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" radius="seed" hops="0">
service: cartservice
18 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T12:20:04.006779+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-10T12:09:26.976076+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_d9521161aa64`:

```
<tool_result id="tr_d9521161aa64" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T10:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" template="error-ratio" baseline="2026-09-10T08:21:22.699864+00:00..2026-09-10T10:23:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_eb7e3f4ea605`:

```
<tool_result id="tr_eb7e3f4ea605" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T10:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T10:23:31.903430+00:00  AddItemAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=5
2026-09-10T10:23:31.906136+00:00  GetCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
2026-09-10T10:23:31.916754+00:00  GetCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
2026-09-10T10:23:31.938667+00:00  EmptyCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
```

> Evidence `tr_40505355587d`:

```
<tool_result id="tr_40505355587d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T11:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T11:23:30.605010+00:00  {"message":"[PlaceOrder] user_id=\"0d109638-ad0a-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T11:23:30.604900334Z"}
2026-09-10T11:23:30.622423+00:00  {"message":"payment went through (transaction_id: 195410a7-807f-4372-a680-56ec5516eb0b)","severity":"info","timestamp":"2026-09-10T11:23:30.62234575Z"}
2026-09-10T11:23:30.627748+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-10T11:23:30.627649792Z"}
2026-09-10T11:23:30.628732+00:00  {"message":"Successful to write message. offset: 31049","severity":"info","timestamp":"2026-09-10T11:23:30.62867425Z"}
```

## The signal that survived

With errors and outages excluded, what remained was timing. In cartservice's logs, successive operations on the same user sat a few milliseconds apart early in the window and about 0.9s apart late in it. checkoutservice showed the same shape at a coarser grain: tens of milliseconds between order steps at the head, roughly a second per step in the tail. That is a slowdown signature, not a breakage signature, and it lines up with a fixed egress delay on cart's namespace being paid by every call up the checkout path.

A minor oddity worth noting but not chasing: several late GetCart calls carried an empty userId where earlier lines were fully populated. Nothing was built on this.

> Evidence `tr_eb7e3f4ea605`:

```
<tool_result id="tr_eb7e3f4ea605" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T10:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T10:23:31.903430+00:00  AddItemAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=5
2026-09-10T10:23:31.906136+00:00  GetCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
2026-09-10T10:23:31.916754+00:00  GetCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
2026-09-10T10:23:31.938667+00:00  EmptyCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
```

> Evidence `tr_40505355587d`:

```
<tool_result id="tr_40505355587d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T11:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T11:23:30.605010+00:00  {"message":"[PlaceOrder] user_id=\"0d109638-ad0a-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T11:23:30.604900334Z"}
2026-09-10T11:23:30.622423+00:00  {"message":"payment went through (transaction_id: 195410a7-807f-4372-a680-56ec5516eb0b)","severity":"info","timestamp":"2026-09-10T11:23:30.62234575Z"}
2026-09-10T11:23:30.627748+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-10T11:23:30.627649792Z"}
2026-09-10T11:23:30.628732+00:00  {"message":"Successful to write message. offset: 31049","severity":"info","timestamp":"2026-09-10T11:23:30.62867425Z"}
```

## Conclusion and fix class

The reading is that the unpaired traffic-shaping attachment on cartservice's network namespace at about T-3m is the cause: a fixed 300ms egress delay, never removed, paid by every cart call and propagating into checkout. The mechanism is waiting on a slowed dependency, not a broken artifact and not a wrong value in cart's own configuration. Fix class is a configuration revert — detach the shaping and confirm the removal is recorded.

Confidence is medium, and the reasons for that are in the next section.

> Evidence `tr_1a6b4ecd47ad`:

```
<tool_result id="tr_1a6b4ecd47ad" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T12:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" radius="seed" hops="0">
service: cartservice
18 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T12:20:04.006779+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-10T12:09:26.976076+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_091795de4d3f`:

```
<tool_result id="tr_091795de4d3f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:53:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" template="error-ratio" baseline="2026-09-10T11:21:22.699864+00:00..2026-09-10T11:53:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1574 min=0 max=0.6667 sd=0.2733
  baseline window: n=129 mean=0.001259 min=0 max=0.01935 sd=0.003778
```

## Still open — read this before you trust the above

The timing does not fully close. checkoutservice's only change point is at about T-21m, some eighteen minutes before the shaping attachment. The shaping cannot explain that earlier elevation. Either an earlier attachment in the same repeating routine was responsible, or the change point is an artifact of the detector. This was not resolved.

No latency metric was ever queried for either service. The 300ms figure comes entirely from the change record; the only corroboration is log timestamp gaps, which is a weak proxy. A direct latency query is the first thing to run next time.

Both log queries were truncated — only the oldest eight and newest thirty-two lines came back, and the gap swallowed essentially the whole interval of interest. Onset behaviour was never observed, and no peer was ever named in a failure context. Separately, checkout's error metric aggregates by service only, with no peer dimension, so nothing here actually proves the failing calls were cart calls. That link is inference, not measurement.

> Evidence `tr_091795de4d3f`:

```
<tool_result id="tr_091795de4d3f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:53:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" template="error-ratio" baseline="2026-09-10T11:21:22.699864+00:00..2026-09-10T11:53:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1574 min=0 max=0.6667 sd=0.2733
  baseline window: n=129 mean=0.001259 min=0 max=0.01935 sd=0.003778
```

> Evidence `tr_1a6b4ecd47ad`:

```
<tool_result id="tr_1a6b4ecd47ad" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T12:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" radius="seed" hops="0">
service: cartservice
18 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T12:20:04.006779+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-10T12:09:26.976076+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_eb7e3f4ea605`:

```
<tool_result id="tr_eb7e3f4ea605" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T10:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T10:23:31.903430+00:00  AddItemAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=5
2026-09-10T10:23:31.906136+00:00  GetCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
2026-09-10T10:23:31.916754+00:00  GetCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
2026-09-10T10:23:31.938667+00:00  EmptyCartAsync called with userId=ac12a6f8-ad01-11f1-b359-b6ed2071a170
```

> Evidence `tr_40505355587d`:

```
<tool_result id="tr_40505355587d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T11:23:30.583000+00:00..2026-09-10T12:25:38.466136+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T11:23:30.605010+00:00  {"message":"[PlaceOrder] user_id=\"0d109638-ad0a-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T11:23:30.604900334Z"}
2026-09-10T11:23:30.622423+00:00  {"message":"payment went through (transaction_id: 195410a7-807f-4372-a680-56ec5516eb0b)","severity":"info","timestamp":"2026-09-10T11:23:30.62234575Z"}
2026-09-10T11:23:30.627748+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-10T11:23:30.627649792Z"}
2026-09-10T11:23:30.628732+00:00  {"message":"Successful to write message. offset: 31049","severity":"info","timestamp":"2026-09-10T11:23:30.62867425Z"}
```

