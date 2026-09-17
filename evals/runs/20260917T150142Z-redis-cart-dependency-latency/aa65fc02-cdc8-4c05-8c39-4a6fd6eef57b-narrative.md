# Cart cache operations acquire a fixed ~300ms penalty; checkout and frontend slow behind it

## What we saw, and what wasted time

Four alerts landed together at T+0: cartservice, checkoutservice, frontend and loadgenerator. Everything that paged sits on the cart/checkout path, and it all paged in the same minute — that simultaneity argues for one shared slow hop rather than a rollout propagating service by service. Note the symptom was slowness, not failure.

First dead end: the error-ratio comparison on cartservice returned no samples at all, in the incident window and in the four-hour baseline alike. Empty is not zero. Read as a flat-zero error line it would suggest cartservice stopped receiving traffic, and you would go hunting a routing problem that does not exist. The gap predates onset, so the series simply is not collected or not labelled as queried. cartservice cannot be confirmed or cleared from this path — go to traces instead.

Second dead end: log queries on cartservice and checkoutservice both used plain service selectors over multi-hour windows, and both truncated to the oldest few and newest few dozen lines, discarding the onset minute itself. Twice. What survives is still useful: cartservice handling dense routine cart RPCs across many users at both ends of its window, no panic, no restart banner; checkoutservice completing eight consecutive orders just after onset with payment authorized, email sent and monotonic queue offsets. So no crash loop and no failing payment/email/queue dependency — but nothing about onset, and no failure line naming a downstream peer. Filter on error patterns first next time.

> Evidence `tr_b31c4a72c063`:

```
<tool_result id="tr_b31c4a72c063" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T11:05:15.583000+00:00..2026-09-17T15:07:06.426393+00:00" template="error-ratio" baseline="2026-09-17T07:03:24.739607+00:00..2026-09-17T11:05:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_4160e7d59250`:

```
<tool_result id="tr_4160e7d59250" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T11:05:15.583000+00:00..2026-09-17T15:07:06.426393+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T11:05:17.548981+00:00  AddItemAsync called with userId=aa730afa-b287-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=3
2026-09-17T11:05:17.551676+00:00  GetCartAsync called with userId=aa730afa-b287-11f1-b359-b6ed2071a170
2026-09-17T11:05:18.871176+00:00  GetCartAsync called with userId=
2026-09-17T11:05:20.339153+00:00  AddItemAsync called with userId=ac1d133c-b287-11f1-b359-b6ed2071a170, productId=6E92ZMYYFZ, quantity=10
```

> Evidence `tr_358eccc1f9bb`:

```
<tool_result id="tr_358eccc1f9bb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T14:35:15.583000+00:00..2026-09-17T15:07:06.426393+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T14:35:16.729714+00:00  {"message":"[PlaceOrder] user_id=\"0023b644-b2a5-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T14:35:16.729528549Z"}
2026-09-17T14:35:16.751638+00:00  {"message":"payment went through (transaction_id: b128a8bf-0a96-4d64-948d-76b886d05ad8)","severity":"info","timestamp":"2026-09-17T14:35:16.751576091Z"}
2026-09-17T14:35:16.756593+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T14:35:16.756421424Z"}
2026-09-17T14:35:16.757474+00:00  {"message":"Successful to write message. offset: 64826","severity":"info","timestamp":"2026-09-17T14:35:16.757374258Z"}
```

## The turn: traces put the time inside the cache calls

Traces resolved it. Spans from frontend and checkoutservice into cartservice RPCs run 300ms and up after onset, and none carry an error or timeout marker — callers see slow, not broken.

The time is not in cartservice. Its handler spans show sub-millisecond self-time while the child cache spans hold nearly the whole duration, HGET and HMSET each at ~300-311ms. The penalty is near-fixed per operation and accumulates: AddItem (read then write) lands at ~605-615ms, a full checkout at ~650-660ms end to end — exactly the magnitude frontend, checkoutservice and loadgenerator noticed. Reads and writes are hit equally, so it is the whole cache dependency, not one command family. Pre-onset traces show the same paths at 0.2-0.5ms per cache span, confirming a genuine onset.

This also cleared several plausible stories at once: caller self-times are 1-3ms with a 1-2ms gap to the server span, so no client-side queueing or pool starvation; other downstream peers still answer in 0-20ms; and each affected operation issues only one or two cache calls, so this is per-call latency, not fan-out.

> Evidence `tr_a3ca6f1897ee`:

```
<tool_result id="tr_a3ca6f1897ee" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T14:05:15.583000+00:00..2026-09-17T15:07:06.426393+00:00">
service: cartservice
14 trace(s) shown of 40 found, 200 spans; offsets are from each trace's root

trace 1e192a043727ca9c  root frontend/HTTP GET  4.4ms  started 2026-09-17T14:58:16.376051+00:00  4 spans
  +0.0ms frontend/HTTP GET 4.4ms [self 0.7ms]
```

## The change-history lookalike, checkoutservice, and what is still open

cartservice's change history holds twenty entries over the preceding day, all from platform-automation, forming four matched apply/revert cycles that each set and then unset an override image, a REDIS_ADDR on a non-default port, and a traffic-shaping sidecar carrying a fixed 300ms egress delay. All reverted before onset — nearest change 1.3h prior, sidecar removed ~1.6h prior. On the record the configuration at onset is baseline, which rules out a rollout at onset, a lingering image or port override, and any human edit. Yet the measured penalty is that same fixed, command-agnostic 300ms. The change log is a dead end as a trigger and a live lead as a fingerprint: either a fifth cycle never reached the log, or an equivalent delay sits on the network path. Do not let the clean revert record talk you out of checking the running pod spec for a traffic-shaping container.

checkoutservice is fallout. Errors were new but small — ~0.4% mean, ~4.1% peak against a flat-zero baseline, spiky rather than a sustained step, with the majority of calls succeeding. It has no recorded changes of its own, so there is no release to roll back. That metric has no per-callee dimension, so the cartservice link is inferred from trace timing and co-alerting, not measured.

Conclusion, medium confidence: the cache dependency began adding ~300ms to every cache operation at T+0 and cartservice fails by waiting. Fix class is a configuration revert — undo whatever imposes the delay on cartservice's path to its cache. Still open: redis-cart itself was never queried, and its own latency, memory, eviction and connection metrics would distinguish an imposed delay from genuine cache-side degradation.

> Evidence `tr_7ed48a0748fe`:

```
<tool_result id="tr_7ed48a0748fe" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T15:05:15.583000+00:00..2026-09-17T15:07:06.426393+00:00" radius="seed" hops="0">
service: cartservice
20 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-17T13:46:36.420307+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.5h before onset  2026-09-17T13:38:07.763972+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_81d78e6a5d7b`:

```
<tool_result id="tr_81d78e6a5d7b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T14:35:15.583000+00:00..2026-09-17T15:07:06.426393+00:00" template="error-ratio" baseline="2026-09-17T14:03:24.739607+00:00..2026-09-17T14:35:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.004374 min=0 max=0.0411 sd=0.008734
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_39ea4f72ea51`:

```
<tool_result id="tr_39ea4f72ea51" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T15:05:15.583000+00:00..2026-09-17T15:07:06.426393+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_39ea4f72ea51>
```

