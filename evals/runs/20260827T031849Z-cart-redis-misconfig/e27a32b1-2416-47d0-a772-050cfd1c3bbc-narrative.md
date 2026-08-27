# Cart-path degradation traced to a cartservice environment rewrite

## What paged, and in what order

Three pages arrived close together: frontend, loadgenerator, and checkoutservice. Blast radius was scored at twelve services, severity critical, with frontend named as the entry point. Four edges in that radius were never measured at all, which matters more than it sounds — see the open items at the end.

The shape of the frontend signal was the first useful thing on the screen. Error ratio over the queried window ran from exactly zero up to about 31% of calls across 61 samples. That is a partial degradation, not an outage: at the worst sample roughly two calls in three still completed normally. The presence of clean zero-error samples in the same window also ruled out the comfortable explanation that this was chronic background noise someone finally noticed.

checkoutservice looked worse. Same window, same 61 samples, error ratio climbing from zero to roughly two-thirds of calls. Again both healthy and heavily degraded samples in one series, so a transition happened inside the window.

> Evidence `tr_76bb207abfbe`:

```
<tool_result id="tr_76bb207abfbe" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3083 n=61
</tool_result:tr_76bb207abfbe>
```

> Evidence `tr_6b8eb46ecb6a`:

```
<tool_result id="tr_6b8eb46ecb6a" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_6b8eb46ecb6a>
```

## The asymmetry that pointed the way

The thing that made the picture tractable was productcatalogservice being completely clean. Sixty-one samples, every one at zero errors, series populated throughout — so the denominator existed and the service was genuinely serving calls, not silently absent.

That splits the frontend in two. Browse paths, which lean on the product catalog, kept working. Checkout paths, which must touch the cart, broke. A frontend that is only ~31% errored while its checkout dependency is ~67% errored is exactly what you get when one family of request paths fails and the other does not. This is the reasoning that redirected attention from frontend itself toward the cart side of the graph.

> Evidence `tr_451444fb25c0`:

```
<tool_result id="tr_451444fb25c0" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_451444fb25c0>
```

> Evidence `tr_76bb207abfbe`:

```
<tool_result id="tr_76bb207abfbe" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3083 n=61
</tool_result:tr_76bb207abfbe>
```

> Evidence `tr_6b8eb46ecb6a`:

```
<tool_result id="tr_6b8eb46ecb6a" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_6b8eb46ecb6a>
```

## The change that fits

At T-2.4m relative to the frontend page, platform-automation rewrote cartservice's environment configuration, setting the Redis address variable to point at redis-cart on port 6380. The change log for that window records exactly one change for cartservice — not a deploy, not an image roll, not a flag flip, a single environment edit made by an automation actor rather than a human.

The reasoning from there is short: 6379 is the conventional Redis port, so an address naming 6380 most likely points at something that is not accepting cart traffic. cartservice's calls to its backing store fail, checkout cannot read or write the cart, and the failure surfaces at frontend on exactly the request paths that need a cart. The timing, the direction of propagation, and the browse/checkout split all agree.

Be honest about what this rests on. The change record shows no prior value. The claim that 6380 is wrong is an argument from convention, not from any observation of this system. If redis-cart was legitimately moved to 6380, the whole verdict inverts and the real cause is elsewhere.

> Evidence `tr_4fb900a9ca0a`:

```
<tool_result id="tr_4fb900a9ca0a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
service: cartservice
1 changes
  2026-08-27T03:18:50.107455+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_4fb900a9ca0a>
```

## Dead ends worth keeping

Four separate change-history queries came back completely empty, and each one closed off a plausible line of attack. Someone will be tempted to re-run these; do not bother unless you widen the window.

frontend: no deploys, no config edits, no flag flips. A frontend release immediately before onset is excluded, and there is nothing to roll back there — which is worth knowing, because "revert the last frontend release" is the reflex and it has no target.

checkoutservice: also empty. No deploy, no toggle, no concurrent edit. This shifted causation away from the checkout team's own release activity and toward its dependencies.

productcatalogservice: empty, and consistent with its flat-zero error metrics. Nothing landed there, nothing was mid-flight there.

featureflagservice: empty. A flag toggle at onset is the most attractive story in a system that has a flag service, and it is not supported by any artifact in the window.

The net effect of four empty logs is that the cartservice edit is the only change candidate anywhere in the queried set. That is a real result, but it is also a narrow one — see below.

> Evidence `tr_7e86a1c0e57d`:

```
<tool_result id="tr_7e86a1c0e57d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_7e86a1c0e57d>
```

> Evidence `tr_2e5599d80ba6`:

```
<tool_result id="tr_2e5599d80ba6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_2e5599d80ba6>
```

> Evidence `tr_260da502b58b`:

```
<tool_result id="tr_260da502b58b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_260da502b58b>
```

> Evidence `tr_d6b4445dd2d4`:

```
<tool_result id="tr_d6b4445dd2d4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for featureflagservice over this window
</tool_result:tr_d6b4445dd2d4>
```

## The hole in the middle

The single most uncomfortable gap: cartservice itself was never measured. The error-ratio query returned no series at all — not a flat zero, but nothing. Neither the error numerator nor the total-calls denominator matched any data over the window.

That absence has at least three explanations and this record cannot distinguish them: the service is not emitting span-derived call metrics, it emits under a different service label value, or data was dropped during the window. If the pipeline was simply broken for cartservice, the missing series carries no information about cartservice health whatsoever, and the verdict is being carried entirely by the change record plus the shape of the neighbours.

The metrics budget was exhausted — four of four calls spent — before the service at the centre of the conclusion could be measured. Latency and saturation for cartservice were never assessed. If you inherit this, spend your first query there.

> Evidence `tr_88d26cfee601`:

```
<tool_result id="tr_88d26cfee601" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_88d26cfee601>
```

## What the evidence does not cover

Two structural limits on everything above.

First, window scope. Every change query actually covered about fifteen minutes around onset, not the ninety-minute lookback that was asked for. Roughly eighty minutes before that window are unexamined for all five services. An earlier release or configuration push that only manifested at onset is entirely consistent with what we saw.

Second, timing. Both metrics results returned min/max aggregates with no per-sample timestamps. So the statement that degradation began after the cartservice edit is a correlation between a change record and an alert clock, not a measured before/after comparison. Nobody in this investigation observed the transition point.

Also worth flagging: no latency evidence was collected anywhere. If cartservice is timing out against an unreachable endpoint rather than being refused immediately, a slow-dependency framing fits the partial degradation about as well. The remediation would be the same; the mechanism in this record would be wrong.

> Evidence `tr_7e86a1c0e57d`:

```
<tool_result id="tr_7e86a1c0e57d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_7e86a1c0e57d>
```

> Evidence `tr_2e5599d80ba6`:

```
<tool_result id="tr_2e5599d80ba6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_2e5599d80ba6>
```

> Evidence `tr_260da502b58b`:

```
<tool_result id="tr_260da502b58b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_260da502b58b>
```

> Evidence `tr_76bb207abfbe`:

```
<tool_result id="tr_76bb207abfbe" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3083 n=61
</tool_result:tr_76bb207abfbe>
```

> Evidence `tr_6b8eb46ecb6a`:

```
<tool_result id="tr_6b8eb46ecb6a" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_6b8eb46ecb6a>
```

## Conclusion and what to do first

Working conclusion, medium confidence: the cartservice environment rewrite pointing Redis at port 6380 is the cause, and the fix class is reverting that configuration to its prior value. Confidence is medium rather than high because the value's wrongness is inferred from convention, the central service is unmeasured, and onset was never timed directly.

If this recurs, the order I would work it: (1) confirm from redis-cart itself which port is actually serving — this single fact either confirms or inverts the verdict; (2) fix or work around the missing cartservice call metrics before spending any other budget; (3) widen the change lookback past the fifteen-minute box; (4) dispatch to redis-cart and to the remaining seven of twelve services in the radius. Four unmeasured edges were crossed and no specialist ever reached redis-cart, so an origin outside the queried set is not excluded.

> Evidence `tr_4fb900a9ca0a`:

```
<tool_result id="tr_4fb900a9ca0a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
service: cartservice
1 changes
  2026-08-27T03:18:50.107455+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_4fb900a9ca0a>
```

> Evidence `tr_88d26cfee601`:

```
<tool_result id="tr_88d26cfee601" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T03:11:15.583000+00:00..2026-08-27T03:26:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_88d26cfee601>
```
