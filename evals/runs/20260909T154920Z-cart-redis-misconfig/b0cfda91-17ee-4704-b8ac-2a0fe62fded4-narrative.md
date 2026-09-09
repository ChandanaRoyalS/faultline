# Checkout failures traced to an un-reverted cart Redis endpoint change

## What was visible, in order

Three alerts fired together at T+0: checkoutservice, frontend, loadgenerator. The seed handed to the responder was checkoutservice, and the first stretch of work went into a service that turned out to be the noticer, not the source. Its error ratio roughly doubled against a two-hour baseline (about 0.067 to 0.109) with a change point at T-30s, which looked like confirmation until two things undercut it: the signal is spiky rather than sustained (standard deviation above the mean, minimum zero, an exact two-thirds peak in both windows, consistent with low call volume), and a second change point about 38 minutes earlier reaches the identical peak. Errors of this shape pre-date the moment we were called about. The metric did rule out a total outage — most calls still succeeded. The change log for checkoutservice came back empty, removing a checkout rollout as trigger, though it was scoped to the seed only and its left edge sat at onset rather than before it.

> Evidence `tr_a218d5d0625e`:

```
<tool_result id="tr_a218d5d0625e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T13:52:00.583000+00:00..2026-09-09T15:54:00.768055+00:00" template="error-ratio" baseline="2026-09-09T11:50:00.397945+00:00..2026-09-09T13:52:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=489 mean=0.1093 min=0 max=0.6667 sd=0.1988
  baseline window: n=489 mean=0.06686 min=0 max=0.6667 sd=0.1867
```

> Evidence `tr_1f8b4cc4f5ea`:

```
<tool_result id="tr_1f8b4cc4f5ea" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T15:52:00.583000+00:00..2026-09-09T15:54:00.768055+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_1f8b4cc4f5ea>
```

## Traces and cartservice: the actual chain

Every sampled failing trace shares one five-span shape ending in a checkoutservice client call to CartService/GetCart. That span is the deepest and first to error; the status propagates up through PlaceOrder to the frontend root, which explains all three alerts. There is no cartservice server-side child span and the GetCart span is essentially all self time, so the failure sits at the connection boundary. Checkout's nine-dependency fan-out never gets past its first hop — no shipping, currency, payment, email, catalog, or ads spans exist — so none of them can be first to fail.

Cartservice logs settle it: a repeating startup cycle every 20-40 seconds of a Redis connection attempt, a failure, and an unhandled ApplicationException killing the process from Program.Main via RedisCartStore.InitializeAsync. No RPC handler lines at all; an hour earlier the same service was serving cart operations cleanly. The logged target is the redis-cart host on port 6380 rather than the default 6379, TLS off. Its change history shows an automation-applied REDIS_ADDR update about 2m35s before onset that, unlike every prior turn of the same four-to-five-hour cycle, was never reverted. Fix class: revert that configuration.

> Evidence `tr_0e912c305552`:

```
<tool_result id="tr_0e912c305552" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T15:22:00.583000+00:00..2026-09-09T15:54:00.768055+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace da7072107b0f5a34  root frontend/HTTP POST  2.0ms  started 2026-09-09T15:53:04.326019+00:00  5 spans
  +0.0ms frontend/HTTP POST 2.0ms [self 0.2ms]  ERROR
```

> Evidence `tr_4e0e835daef0`:

```
<tool_result id="tr_4e0e835daef0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T14:52:00.583000+00:00..2026-09-09T15:54:00.768055+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T14:52:02.948479+00:00  AddItemAsync called with userId=049b2b14-ac5e-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=2
2026-09-09T14:52:02.949722+00:00  GetCartAsync called with userId=049b2b14-ac5e-11f1-b359-b6ed2071a170
2026-09-09T14:52:02.955639+00:00  GetCartAsync called with userId=049b2b14-ac5e-11f1-b359-b6ed2071a170
2026-09-09T14:52:02.971974+00:00  EmptyCartAsync called with userId=049b2b14-ac5e-11f1-b359-b6ed2071a170
```

> Evidence `tr_84686b861921`:

```
<tool_result id="tr_84686b861921" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T15:52:00.583000+00:00..2026-09-09T15:54:00.768055+00:00" radius="candidate_cause" hops="1">
service: cartservice
33 changes, ranked by suspicion
  #1  2m before onset  2026-09-09T15:49:25.709034+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  10m before onset  2026-09-09T15:41:35.352657+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

## Dead ends worth keeping

Checkoutservice logs read as a silent stall: after T-1m30s, PlaceOrder start lines continue at normal cadence with no completion, no error, no exception, no restart. Read alone this suggests blocking on something that never returns — but the traces show fast 1-3ms rejections instead. The two signatures were never reconciled, and the traces sampled only a 43-second stretch after onset, so the onset minute may genuinely have behaved differently. A single email-service 500 warning about thirty minutes before onset involved an order that completed and never recurred. The cartservice hotfix image was reverted roughly thirty minutes before onset and the traffic-shaping sidecar detached about ten minutes before, so neither was in force. The cartservice error-ratio metric returns nothing in both incident and baseline windows — an instrumentation or label gap that pre-dates the incident, not evidence of health, and not worth re-querying with the same selector.

Still open: nothing was queried against redis-cart itself, so 6380 being closed is inferred rather than confirmed; the earlier error change point is unexplained; four unmeasured edges were crossed and redis-cart, frontend and the remaining checkout dependencies were never examined directly; and why the automation left this cycle un-reverted — failed revert job or changed definition — is unknown, which decides whether a manual revert will hold.

> Evidence `tr_cabe3dc7ba76`:

```
<tool_result id="tr_cabe3dc7ba76" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T15:22:00.583000+00:00..2026-09-09T15:54:00.768055+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T15:22:09.829123+00:00  {"message":"[PlaceOrder] user_id=\"39928714-ac62-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T15:22:09.828957879Z"}
2026-09-09T15:22:09.848042+00:00  {"message":"payment went through (transaction_id: af8a72fa-f0bf-45cf-b13e-0976cc3d14ee)","severity":"info","timestamp":"2026-09-09T15:22:09.847937962Z"}
2026-09-09T15:22:09.853950+00:00  {"message":"failed to send order confirmation to \"jack@example.com\": failed POST to email service: expected 200, got 500","severity":"warning","timestamp":"2026-09-09T15:22:09.853875087Z"}
2026-09-09T15:22:09.854861+00:00  {"message":"Successful to write message. offset: 23771","severity":"info","timestamp":"2026-09-09T15:22:09.854779879Z"}
```

> Evidence `tr_0e912c305552`:

```
<tool_result id="tr_0e912c305552" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T15:22:00.583000+00:00..2026-09-09T15:54:00.768055+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace da7072107b0f5a34  root frontend/HTTP POST  2.0ms  started 2026-09-09T15:53:04.326019+00:00  5 spans
  +0.0ms frontend/HTTP POST 2.0ms [self 0.2ms]  ERROR
```

> Evidence `tr_10f15934be01`:

```
<tool_result id="tr_10f15934be01" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T13:52:00.583000+00:00..2026-09-09T15:54:00.768055+00:00" template="error-ratio" baseline="2026-09-09T11:50:00.397945+00:00..2026-09-09T13:52:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

