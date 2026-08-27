# Frontend partial error onset traced to an adservice memory ceiling

## What we saw first

The page came in from two places at once: loadgenerator and frontend. Blast radius was reported as seven services, severity critical, with frontend as the entry point and one dependency edge flagged as unmeasured. The first useful discriminator was frontend's own error shape. Over the fifteen-minute slice we could query, the aggregate error ratio started at zero and climbed to a peak near 12.7% across sixty-one samples. That is an onset inside the window, not a pre-existing background level, and it is a partial failure: at the worst point roughly seven of every eight frontend requests still completed cleanly.

That number set the shape of the whole investigation. A core checkout-path dependency going down would not leave seven-eighths of traffic healthy. A single non-critical leaf failing would. So from about T+3m onward we were looking for a leaf, not a spine.

> Evidence `tr_6fb9e287712e`:

```
<tool_result id="tr_6fb9e287712e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1267 n=61
</tool_result:tr_6fb9e287712e>
```

## Walking the change logs

We pulled change history for six services in parallel: frontend, cartservice, productcatalogservice, checkoutservice, adservice, recommendationservice. Five of them came back completely empty — no deploys, no config edits, no flag flips, no scaling or replica-count events. That mattered as much as any positive finding, because it took rollback of those services off the table entirely as a remediation for this window.

adservice was the exception and the only one. At 06:48:46Z, an automated actor (platform-automation, not a human release pipeline) applied a resource_limits update lowering ad-service's container memory limit to 256m. No prior value was recorded. The timestamp lands a few minutes before the alerts, which makes it temporally eligible as the trigger. It is worth noting what this change was *not*: not a code deploy, not an image rollout, not a replica change, not an application config or flag edit.

> Evidence `tr_6dcada371f1a`:

```
<tool_result id="tr_6dcada371f1a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
service: adservice
1 changes
  2026-08-27T06:48:46.883468+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
</tool_result:tr_6dcada371f1a>
```

> Evidence `tr_1b0cebe10f45`:

```
<tool_result id="tr_1b0cebe10f45" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_1b0cebe10f45>
```

> Evidence `tr_49f80feef9b8`:

```
<tool_result id="tr_49f80feef9b8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_49f80feef9b8>
```

> Evidence `tr_0ba63624ef69`:

```
<tool_result id="tr_0ba63624ef69" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_0ba63624ef69>
```

> Evidence `tr_3f8aba9fd5cf`:

```
<tool_result id="tr_3f8aba9fd5cf" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_3f8aba9fd5cf>
```

> Evidence `tr_65cee649184b`:

```
<tool_result id="tr_65cee649184b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for recommendationservice over this window
</tool_result:tr_65cee649184b>
```

## Telemetry silence on adservice

The corroborating signal was an absence. The span-metrics error-ratio query for adservice matched no series at all — and critically, that includes the unfiltered denominator, not just the error-filtered numerator. This is not "zero errors." A service serving cleanly still emits a call-count denominator. A service emitting nothing is either not running or repeatedly dying and restarting.

Put next to a memory ceiling that was lowered minutes earlier, that silence reads as a process being killed for exceeding a limit it cannot fit under. The failure in the world is resource starvation; the limit edit is the trigger that started it. Note honestly that we inferred the mechanism — we never observed it.

> Evidence `tr_32a9bb14d792`:

```
<tool_result id="tr_32a9bb14d792" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))' over this window
</tool_result:tr_32a9bb14d792>
```

> Evidence `tr_6dcada371f1a`:

```
<tool_result id="tr_6dcada371f1a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
service: adservice
1 changes
  2026-08-27T06:48:46.883468+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
</tool_result:tr_6dcada371f1a>
```

## Dead end: productcatalogservice

productcatalogservice was an early suspect on the strength of being in the blast radius and sitting on a heavily-used path. It was cleanly eliminated. Its error ratio is flat at zero across all sixty-one samples, and the series *resolves* — meaning a real non-zero denominator, meaning the service kept reporting spans throughout and did not drop out of the mesh. It is not returning errors to callers, and there is no inflection point anywhere in the covered interval to use as an onset marker. Time spent here was not wasted: it established that a healthy service looks different from adservice's silence, which is what let us read that silence correctly.

> Evidence `tr_7160a3df4e1b`:

```
<tool_result id="tr_7160a3df4e1b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_7160a3df4e1b>
```

## Dead end that never fully closed: cartservice

cartservice looked, on first glance at the query result, exactly like adservice: no error-ratio series returned. We nearly treated it as a second failing service. It is not resolved, and it should not be treated as resolved by whoever reads this. Both numerator and denominator are empty, so we cannot claim a spike and we equally cannot claim a healthy baseline — absence of errors here is not evidence of health. cartservice also had no recorded change, which cuts against it being the origin.

The plausible benign reading is that cartservice is simply not instrumented for span metrics in this environment. Two prior incidents in the corpus turned on cartservice silence being misread in one direction or the other. If you are reading this during a live repeat, check the instrumentation question first before spending time on cartservice as a suspect.

> Evidence `tr_1a39804e166d`:

```
<tool_result id="tr_1a39804e166d" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_1a39804e166d>
```

> Evidence `tr_49f80feef9b8`:

```
<tool_result id="tr_49f80feef9b8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_49f80feef9b8>
```

## Conclusion and fix class

Best-supported account: adservice was starved by an externally imposed memory limit lowered to 256m by platform-automation, killing the process and silencing its telemetry; frontend's non-critical ad call path failed, producing a partial ~12.7% error ratio while the rest of traffic served normally. Fix class is config_revert — restore adservice's memory limit.

Confidence is medium, deliberately. The chain has two inferred links rather than observed ones, described below.

> Evidence `tr_6dcada371f1a`:

```
<tool_result id="tr_6dcada371f1a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
service: adservice
1 changes
  2026-08-27T06:48:46.883468+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
</tool_result:tr_6dcada371f1a>
```

> Evidence `tr_32a9bb14d792`:

```
<tool_result id="tr_32a9bb14d792" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))' over this window
</tool_result:tr_32a9bb14d792>
```

> Evidence `tr_6fb9e287712e`:

```
<tool_result id="tr_6fb9e287712e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1267 n=61
</tool_result:tr_6fb9e287712e>
```

## Open questions and what we never measured

Read this section before acting on the conclusion.

We never confirmed the kill. No memory or saturation metric, no restart count, no container event, no pod log was retrieved for adservice. The starvation mechanism is inferred from a limit change plus telemetry silence.

We never traced the errors. Frontend metrics carry no endpoint, route, or operation dimension, so attributing its ~12.7% errors to the ad call path is circumstantial. A different leaf could produce a similar magnitude.

We never established the correct restore value. adservice's prior memory limit was not recorded and its actual working-set requirement is unknown, so 256m cannot be *confirmed* as too low — only strongly suspected. Reverting to the previous value requires finding that value elsewhere.

Every change-log query started at 06:42:30. The interval 06:20–06:42:30 was never queried for any service. An earlier deploy or config edit on frontend, cartservice, checkoutservice, productcatalogservice or recommendationservice remains entirely possible and is the largest unexamined space.

Three services had no metrics dispatched at all: checkoutservice, recommendationservice, and loadgenerator — one of which alerted. Their error and latency behaviour is unmeasured; the budget ran out.

Triage flagged one unmeasured dependency edge crossed. We never identified which link that was, and never ruled out that it conceals a slow downstream returning success codes — a latency-shaped story that our error-only queries would be blind to by construction.

> Evidence `tr_32a9bb14d792`:

```
<tool_result id="tr_32a9bb14d792" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))' over this window
</tool_result:tr_32a9bb14d792>
```

> Evidence `tr_6fb9e287712e`:

```
<tool_result id="tr_6fb9e287712e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1267 n=61
</tool_result:tr_6fb9e287712e>
```

> Evidence `tr_1b0cebe10f45`:

```
<tool_result id="tr_1b0cebe10f45" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_1b0cebe10f45>
```

> Evidence `tr_49f80feef9b8`:

```
<tool_result id="tr_49f80feef9b8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_49f80feef9b8>
```

> Evidence `tr_0ba63624ef69`:

```
<tool_result id="tr_0ba63624ef69" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_0ba63624ef69>
```

> Evidence `tr_3f8aba9fd5cf`:

```
<tool_result id="tr_3f8aba9fd5cf" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_3f8aba9fd5cf>
```

> Evidence `tr_65cee649184b`:

```
<tool_result id="tr_65cee649184b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no changes recorded for recommendationservice over this window
</tool_result:tr_65cee649184b>
```

> Evidence `tr_1a39804e166d`:

```
<tool_result id="tr_1a39804e166d" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_1a39804e166d>
```

> Evidence `tr_7160a3df4e1b`:

```
<tool_result id="tr_7160a3df4e1b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T06:42:30.583000+00:00..2026-08-27T06:57:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_7160a3df4e1b>
```
