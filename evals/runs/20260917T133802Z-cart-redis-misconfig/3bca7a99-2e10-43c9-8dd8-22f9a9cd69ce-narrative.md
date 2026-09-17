# Checkout order placement fails at the cart lookup; cartservice in a startup crash loop

## What we saw first

Three alerts arrived together: checkoutservice, frontend, and loadgenerator. The declared blast radius was twelve services, severity critical, with checkoutservice named as the seed. That framing is worth flagging up front, because it sent the first hour of work into checkoutservice, which turned out to be an innocent bystander relaying someone else's error.

The first useful observation came from checkoutservice's own logs. The process was plainly alive and taking work: order-placement lines continued at a few-second cadence straight through onset and on past T+2m. But the shape of those lines had changed. Early in the retained window each request produced a full lifecycle — order placed, payment confirmed with a transaction id, confirmation email, then a successful message write with an advancing offset. From roughly T-2m onward, only the order-placement line appears. The later stages are not failing loudly; they are simply absent. No error or warning severity line appears anywhere in the window, so checkoutservice never named its own blocker.

> Evidence `tr_bb8b9d08b3a8`:

```
<tool_result id="tr_bb8b9d08b3a8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T13:10:55.315921+00:00  {"message":"[PlaceOrder] user_id=\"374cd260-b299-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T13:10:55.315726595Z"}
2026-09-17T13:10:55.336102+00:00  {"message":"payment went through (transaction_id: 008ef91b-783a-4ca8-8ce4-383f3103fa0c)","severity":"info","timestamp":"2026-09-17T13:10:55.33599047Z"}
2026-09-17T13:10:55.341172+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-17T13:10:55.341084387Z"}
2026-09-17T13:10:55.342440+00:00  {"message":"Successful to write message. offset: 64173","severity":"info","timestamp":"2026-09-17T13:10:55.342294137Z"}
```

## Traces settled where the failure originates

Ten sampled traces spanning T+4s to T+1m48s all fail in exactly the same way. The leaf span for checkoutservice's outbound cart call, hipstershop.CartService/GetCart, issued from prepareOrderItemsAndShippingQuoteFromCart, carries ERROR. The intermediate preparation span is not itself marked ERROR, so the failure is introduced at the cart hop and merely relayed upward through PlaceOrder to the frontend's HTTP POST root. That relay is the whole explanation for the simultaneous checkoutservice/frontend/loadgenerator alerting.

Two details mattered. First, this is fast, not slow: entire traces complete in roughly 1.3–2.5ms, with the cart call under 1ms. The tooling flagged GetCart as the degrading hop at 26–78% of trace time, but that is a share of a trivially short trace and is not a latency signal. Second, no spans exist for payment, shipping quote, currency, email, or order write in any of the ten traces — checkout aborts before it reaches them. That reconciles the log picture: the downstream stages are silent because they are never invoked.

> Evidence `tr_5643554a7104`:

```
<tool_result id="tr_5643554a7104" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 48 spans; offsets are from each trace's root

trace 30a33acb3ebabbbe  root checkoutservice/hipstershop.CheckoutService/PlaceOrder  1.3ms  started 2026-09-17T13:40:49.239882+00:00  3 spans, 1 unattached
  +0.0ms checkoutservice/hipstershop.CheckoutService/PlaceOrder 1.3ms [self 0.1ms]  ERROR
```

## The other side of the hop

cartservice logs explain the empty listener. The process is in a startup crash loop: it attempts a Redis connection, hangs, then dies on an unhandled application exception raised from the cart store's connection check, invoked directly from the program entry point. At least five complete cycles are visible from about T-1m25s through T+1m39s, each restart following roughly a second after the prior crash. The connection string names host redis-cart on port 6380, TLS disabled, abortConnect disabled. Because the check sits in the startup path, there is no degraded-but-serving mode — the process never reaches ready, and no request-handling lines accompany the crash cycles.

Crucially, cartservice was healthy earlier in the same window: normal AddItem and GetCart traffic with no errors around T-30m. So this is a transition, not a deploy that was never good.

> Evidence `tr_44eefec950d0`:

```
<tool_result id="tr_44eefec950d0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T13:10:47.818050+00:00  AddItemAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=3
2026-09-17T13:10:47.822162+00:00  GetCartAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170
2026-09-17T13:10:49.042206+00:00  GetCartAsync called with userId=
2026-09-17T13:10:49.090712+00:00  AddItemAsync called with userId=339a6d08-b299-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=10
```

## The change that was left behind

The cartservice change record closes the loop. Nineteen entries in the surrounding day, every one attributed to platform-automation; no human actor anywhere. The entry nearest onset, about two minutes before, sets cartservice's Redis address to redis-cart:6380 from a previously unset state.

The record also shows an automated harness running a repeating cycle roughly every four and a half hours, each cycle applying the same triplet in the same order: a hotfix image reference, a traffic-shaping sidecar attached to the cart-service network namespace with a fixed 300ms eth0 delay, and the Redis address environment variable — each applied then reverted. In the final cycle the sidecar was removed about nine minutes before onset and the image reference reverted about thirty minutes before. The Redis address edit was the only one of the three never reverted, and so the only one in effect when the incident began.

> Evidence `tr_919214de917a`:

```
<tool_result id="tr_919214de917a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:40:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" radius="candidate_cause" hops="1">
service: cartservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T13:38:07.763972+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  9m before onset  2026-09-17T13:30:49.518437+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

## Dead ends worth keeping

Change history on checkoutservice came back completely empty. That was a real answer — it rules out a checkoutservice deploy, rollback, flag flip, or ongoing config churn as trigger or sustaining factor — but the query was scoped to the seed with zero dependency hops and its window began at onset rather than before it. Both choices nearly hid the answer: cartservice was never queried by that first pass, and a change landing two minutes before onset would have fallen outside the window regardless. Widening hops and starting the window earlier is the lesson.

checkoutservice metrics were an outright red herring. Incident-window error ratio averaged about 6.2% against a roughly 7.1% six-hour baseline — a slight decrease. Two brief excursions near 04:25Z and 05:04Z crossed the detection threshold but returned immediately and are consistent with very low request counts. The baseline itself reaches a 50% error ratio and has its own traffic gaps, so intermittent errors are pre-existing behaviour here. There is no sustained error elevation in this series, no clean step onset to anchor on, and the incident window was sampled roughly sixteen times more densely than the baseline, which makes the mean comparison untrustworthy in either direction. Request rate and p95/p99 were not answerable from what was returned.

Two hypotheses from the change record were tested and discarded: the hotfix image was not the running version at onset, and the 300ms delay was not applied at onset. Either would have been a plausible story; the timeline excludes both. On the cartservice side, TLS negotiation was excluded because the client had TLS explicitly disabled, and external termination (OOM, eviction, probe kill) was excluded because every restart is preceded by an explicit application exception on its own error path.

> Evidence `tr_58d24c8ac46e`:

```
<tool_result id="tr_58d24c8ac46e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T13:40:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_58d24c8ac46e>
```

> Evidence `tr_ef7813a3e1e6`:

```
<tool_result id="tr_ef7813a3e1e6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T01:40:45.583000+00:00..2026-09-17T07:40:45.583000+00:00" template="error-ratio" baseline="2026-09-16T19:40:45.583000+00:00..2026-09-17T01:40:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=1272 mean=0.06201 min=0 max=0.6667 sd=0.1588
  baseline window: n=79 mean=0.07094 min=0 max=0.5 sd=0.08955
```

> Evidence `tr_919214de917a`:

```
<tool_result id="tr_919214de917a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:40:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" radius="candidate_cause" hops="1">
service: cartservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T13:38:07.763972+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  9m before onset  2026-09-17T13:30:49.518437+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

> Evidence `tr_44eefec950d0`:

```
<tool_result id="tr_44eefec950d0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T13:10:47.818050+00:00  AddItemAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=3
2026-09-17T13:10:47.822162+00:00  GetCartAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170
2026-09-17T13:10:49.042206+00:00  GetCartAsync called with userId=
2026-09-17T13:10:49.090712+00:00  AddItemAsync called with userId=339a6d08-b299-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=10
```

## Conclusion and fix class

An automated change harness set cartservice's REDIS_ADDR to redis-cart:6380 about two minutes before onset and, unlike four prior cycles of the same experiment, never reverted it. The connection to that address never completes; because the cart store's connection check runs in the startup path from the program entry point, the unhandled exception kills the process, which then crash-loops roughly every second. With no cart listener, every checkoutservice PlaceOrder aborts at the outbound GetCart leaf in under a millisecond, and the ERROR propagates to the frontend HTTP root. checkoutservice itself is healthy and unchanged. Confidence is high. Fix class: revert the configuration.

> Evidence `tr_919214de917a`:

```
<tool_result id="tr_919214de917a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:40:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" radius="candidate_cause" hops="1">
service: cartservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T13:38:07.763972+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  9m before onset  2026-09-17T13:30:49.518437+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

> Evidence `tr_44eefec950d0`:

```
<tool_result id="tr_44eefec950d0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T13:10:47.818050+00:00  AddItemAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=3
2026-09-17T13:10:47.822162+00:00  GetCartAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170
2026-09-17T13:10:49.042206+00:00  GetCartAsync called with userId=
2026-09-17T13:10:49.090712+00:00  AddItemAsync called with userId=339a6d08-b299-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=10
```

> Evidence `tr_5643554a7104`:

```
<tool_result id="tr_5643554a7104" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 48 spans; offsets are from each trace's root

trace 30a33acb3ebabbbe  root checkoutservice/hipstershop.CheckoutService/PlaceOrder  1.3ms  started 2026-09-17T13:40:49.239882+00:00  3 spans, 1 unattached
  +0.0ms checkoutservice/hipstershop.CheckoutService/PlaceOrder 1.3ms [self 0.1ms]  ERROR
```

> Evidence `tr_bb8b9d08b3a8`:

```
<tool_result id="tr_bb8b9d08b3a8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T13:10:55.315921+00:00  {"message":"[PlaceOrder] user_id=\"374cd260-b299-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T13:10:55.315726595Z"}
2026-09-17T13:10:55.336102+00:00  {"message":"payment went through (transaction_id: 008ef91b-783a-4ca8-8ce4-383f3103fa0c)","severity":"info","timestamp":"2026-09-17T13:10:55.33599047Z"}
2026-09-17T13:10:55.341172+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-17T13:10:55.341084387Z"}
2026-09-17T13:10:55.342440+00:00  {"message":"Successful to write message. offset: 64173","severity":"info","timestamp":"2026-09-17T13:10:55.342294137Z"}
```

> Evidence `tr_58d24c8ac46e`:

```
<tool_result id="tr_58d24c8ac46e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T13:40:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_58d24c8ac46e>
```

## Still open

Nobody queried the redis-cart service definition. It is inferred, not confirmed, that redis-cart listens on 6379 and not 6380 — the log evidence rates that inference low on its own.

The timing shape does not fully fit a simple wrong-port dial. Each connection attempt hangs roughly 20–45 seconds before failing, which is timeout-shaped, whereas a wrong port on a live, reachable host usually produces an immediate refusal. redis-cart was never dispatched on. It may additionally be unreachable or dropping packets on 6380, which would be a second contributing condition rather than a detail.

Observability gaps limit how much of this can be independently confirmed. cartservice has no Prometheus series for the span-derived call counter across a twelve-hour span, empty in both the incident and baseline windows, so the gap is collection-side and predates onset; that series cannot corroborate the GetCart failures. And the checkoutservice error-ratio baseline covers 01:40–07:40Z, which excludes onset entirely. Both the stated blast radius and the exact crash-loop start therefore rest entirely on logs.

> Evidence `tr_44eefec950d0`:

```
<tool_result id="tr_44eefec950d0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T13:10:45.583000+00:00..2026-09-17T13:42:42.273756+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T13:10:47.818050+00:00  AddItemAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=3
2026-09-17T13:10:47.822162+00:00  GetCartAsync called with userId=32d6f030-b299-11f1-b359-b6ed2071a170
2026-09-17T13:10:49.042206+00:00  GetCartAsync called with userId=
2026-09-17T13:10:49.090712+00:00  AddItemAsync called with userId=339a6d08-b299-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=10
```

> Evidence `tr_b5e85f0cad3f`:

```
<tool_result id="tr_b5e85f0cad3f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T01:40:45.583000+00:00..2026-09-17T07:40:45.583000+00:00" template="error-ratio" baseline="2026-09-16T19:40:45.583000+00:00..2026-09-17T01:40:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ef7813a3e1e6`:

```
<tool_result id="tr_ef7813a3e1e6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T01:40:45.583000+00:00..2026-09-17T07:40:45.583000+00:00" template="error-ratio" baseline="2026-09-16T19:40:45.583000+00:00..2026-09-17T01:40:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=1272 mean=0.06201 min=0 max=0.6667 sd=0.1588
  baseline window: n=79 mean=0.07094 min=0 max=0.5 sd=0.08955
```

