# Constant per-call delay on the cart path surfaces as multi-second checkout latency

## What we saw, and what turned out not to matter

Four services alerted within the same minute: cartservice, frontend, checkoutservice and loadgenerator, with cartservice named as origin and a blast radius of twelve. Treat the alert timestamp as T+0. The page looked like a cartservice failure, and the first three lines of enquiry all chased that reading. All three came back empty, which is the most useful part of this record.

Metrics: cartservice's ratio of error-status calls to total calls was flat zero across the entire window, continuously sampled, no gaps, min equal to max. That killed several hypotheses at once — no intermittent dependency failure (which would show a spiky ratio), no crash or reschedule (an outage would break the series rather than hold it at zero), no circuit-breaker shedding, and no error-driven retry amplification, since retries of that class need an error population to retry against. The continuity also proved cartservice was still taking real traffic. Two separate passes both returned only this ratio; no latency percentile, CPU, memory or pool series was ever retrieved.

Logs: every returned line was routine informational RPC activity — add, get and empty handlers — with no error severity, no timeout, no stack trace, and no dependency named anywhere. Handlers kept firing past T+3m, so the process was alive. One hint did emerge: the gap between a cart-add entry and its paired cart-get stretched from a few milliseconds early on to roughly a second near T+2m to T+3m. Coverage was truncated — about twelve minutes in the middle were not returned and the window stopped short of the requested end — so "no errors" holds for the head and tail only.

Frontend changes: the change history for frontend over the alert window was completely empty. No deploy, config edit, rollback or flag flip. That removes frontend as a trigger and kills the coincidental-dual-deploy story outright, since that needs a change on both sides. It also removes rollback as a lever there. This query covered frontend only; checkoutservice change history was never retrieved.

> Evidence `tr_06e83135c0b3`:

```
<tool_result id="tr_06e83135c0b3" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
1 series
  {service_name=cartservice} min=0 max=0 n=58
</tool_result:tr_06e83135c0b3>
```

> Evidence `tr_789c1de8dfa1`:

```
<tool_result id="tr_789c1de8dfa1" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
1 series
  {service_name=cartservice} min=0 max=0 n=61
</tool_result:tr_789c1de8dfa1>
```

> Evidence `tr_5f66d89c5b74`:

```
<tool_result id="tr_5f66d89c5b74" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-30T03:47:30.932454+00:00  AddItemAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593, productId=0PUK6V6EV0, quantity=5
2026-08-30T03:47:30.935039+00:00  GetCartAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593
2026-08-30T03:47:30.947557+00:00  GetCartAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593
2026-08-30T03:47:30.967665+00:00  EmptyCartAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593
```

> Evidence `tr_685c90555df7`:

```
<tool_result id="tr_685c90555df7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_685c90555df7>
```

## What resolved it

The traces settled the question in one look. Cartservice's outbound Redis spans — reads (HGET) and writes (HMSET) alike — clustered tightly at 300–307ms in every sampled trace, with nothing at all observed between the sub-millisecond baseline and ~300ms. That absence of intermediate values matters more than the magnitude: a fixed quantum, not a distribution of calls degrading.

The penalty multiplied by egress count. Single-egress GetCart ran ~301–306ms; two-egress AddItem ran ~603–610ms, almost exactly double. In-process time was negligible — server spans exceeded the sum of their children by under a millisecond — ruling out CPU saturation, GC pauses, lock contention and serialization in the handler. Everything off the cart path was clean at 0–19ms, and in the PlaceOrder traces the payment, shipping, currency, email and fraud legs totalled tens of milliseconds against two cart-facing legs at ~1.2s each. So no other downstream service and no checkout-side order logic is implicated. The uniformity also excludes queueing tails and payload-size effects, and since writes carry the same penalty as reads, it is not a cold-cache or replica-read story.

The change log for cartservice contained exactly one entry. At roughly T-3m a platform-automation principal created a traffic-shaping container attached to the cart-service network namespace, applying a fixed 300ms egress delay with zero jitter on eth0. Zero jitter is what ties it to the traces: a constant delay produces exactly the quantized floor observed. That entry also shows no deploy, no image or version change, no flag flip, and no change to cache or dependency connection settings — the delay sits at the network interface layer, outside the service's own config — and its discrete arrival means a step onset, not an organic ramp.

Every cartservice outbound call therefore pays a constant ~300ms toll, and the frontend, checkout and loadgenerator alerts are that same toll surfacing upstream. The failure is a wait, not an error, which is precisely why the error-ratio and log lines produced nothing. Confidence high. Fix class is a config revert: remove the shaping rule; do not redeploy or restart anything.

> Evidence `tr_8bf12cc31348`:

```
<tool_result id="tr_8bf12cc31348" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
service: cartservice
200 spans
  59471f79d55a9993 emailservice/sinatra.render_template 0.2ms
  59471f79d55a9993 checkoutservice/orders send 1.4ms
  59471f79d55a9993 accountingservice/orders receive 0.0ms
```

> Evidence `tr_bbac30367df9`:

```
<tool_result id="tr_bbac30367df9" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
service: cartservice
1 changes
  2026-08-30T03:54:12.243873+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_bbac30367df9>
```

## Still open

The ~300ms step rests on traces alone. No quantile series was ever pulled for cartservice, so the step was never corroborated by a latency percentile showing a clean transition at the change time. Pull one before closing.

The quantum also appears on the caller side: frontend's client span for GetCart ran ~603–608ms against a ~301–303ms cartservice server span, and checkoutservice's client spans ~1204–1222ms against ~301–303ms server spans. Extra multiples are being spent on the callers' egress paths. Whether the shaping was applied beyond the cart-service namespace, or whether the delay is paid on both request and response legs, is unresolved and changes the scope of the fix. Relatedly, checkoutservice's change history was never queried, so a second concurrent change on that side is not excluded.

Three smaller threads. Several cart-get log entries near T+2m to T+3m carried an empty user identifier, a pattern absent earlier; nothing explained this, and it may be a benign artifact of timed-out upstream sessions or a separate correctness issue. Redis itself was never examined directly — the uniform quantum makes an intrinsic store problem unlikely, but nothing confirms it is healthy underneath. And the intent and lifetime of the platform-automation change are unknown, which determines whether removing it unilaterally is safe and whether it will recur.

> Evidence `tr_8bf12cc31348`:

```
<tool_result id="tr_8bf12cc31348" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
service: cartservice
200 spans
  59471f79d55a9993 emailservice/sinatra.render_template 0.2ms
  59471f79d55a9993 checkoutservice/orders send 1.4ms
  59471f79d55a9993 accountingservice/orders receive 0.0ms
```

> Evidence `tr_5f66d89c5b74`:

```
<tool_result id="tr_5f66d89c5b74" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-30T03:47:30.932454+00:00  AddItemAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593, productId=0PUK6V6EV0, quantity=5
2026-08-30T03:47:30.935039+00:00  GetCartAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593
2026-08-30T03:47:30.947557+00:00  GetCartAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593
2026-08-30T03:47:30.967665+00:00  EmptyCartAsync called with userId=86e45294-a425-11f1-8c4e-9e12df7a2593
```

> Evidence `tr_685c90555df7`:

```
<tool_result id="tr_685c90555df7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T03:47:30.583000+00:00..2026-08-30T04:02:30.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_685c90555df7>
```
