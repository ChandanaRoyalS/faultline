# Fraud detection service stuck in a boot loop after an unrestored memory limit reduction

## What the alert looked like

The page named a single service: frauddetectionservice. Severity critical, blast radius one service, no unmeasured edges crossed on the way in. There was no accompanying customer-facing symptom in the alert body and no second service alarming alongside it, so the whole investigation stayed local to this one workload from the first minute.

The first instinct — check whether the service is erroring — turned out to be the least productive path available, and it cost the first stretch of the response. See the dead ends section before repeating it.

## First look: the RED metrics, which told us nothing

The opening move was the standard error-ratio comparison for frauddetectionservice against a three-hour baseline. It came back empty. Not low, not flat — no samples at all, in either the incident window or the baseline.

The reflex reading of an empty series is that the service stopped emitting when it broke. That reading is wrong here, and it is worth spelling out why so a future responder does not spend time on it: the baseline window was equally empty. Widening the baseline to six hours before onset produced the same nothing. A series that was already absent six hours earlier cannot be an incident signal. Whatever is going on with the calls_total labelling for this service, it predates the incident and is orthogonal to it.

The practical consequence: this metric stream is dead weight for this service. It cannot time the onset, cannot confirm a crash, and cannot establish a healthy pre-incident reference. Everything the response eventually rested on came from logs and the change log instead.

> Evidence `tr_5a6dc06caae7`:

```
<tool_result id="tr_5a6dc06caae7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T13:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" template="error-ratio" baseline="2026-09-09T10:12:33.930247+00:00..2026-09-09T13:14:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_233321ed63a3`:

```
<tool_result id="tr_233321ed63a3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T10:14:30.583000+00:00..2026-09-09T16:14:30.583000+00:00" template="error-ratio" baseline="2026-09-09T04:14:30.583000+00:00..2026-09-09T10:14:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The logs, which carried the whole case

Pulling raw logs for the service across the same three-hour window gave the first real shape of the failure.

At the start of the window the service was healthy in an unambiguous way: it was steadily consuming order records off Kafka with a counter advancing monotonically. So this is not a service that was broken all along.

Around T-6m relative to alert onset the character of the output changes completely. From that point through roughly T+1m, the only thing in the log is the same three-line boot sequence, over and over: the JVM picking up its tool options, a class-sharing warning, and the OpenTelemetry agent version banner. The intervals tighten into roughly one per minute. Nothing follows those three lines. No application logging, no consumption records, no readiness message.

That pattern is a process starting, failing to reach steady state, and being restarted. It is not a degraded-but-serving instance.

Two details narrow the window in which the process dies. First, the agent banner prints successfully on every single boot, so the agent is loading fine and the fatal step is after it. Second, there is no error line anywhere — no exception, no stack trace, no connection refused, nothing naming a downstream. Log shipping is demonstrably working, because the boot lines themselves arrive on every restart. So the absence of an error is a real property of how this process dies, not a collection gap. Something is terminating the JVM between agent load and application start, and giving it no chance to say anything.

> Evidence `tr_66732c3b1fb5`:

```
<tool_result id="tr_66732c3b1fb5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T13:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T13:14:43.929543+00:00  Consumed record with orderId: 6c450c5e-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 317
2026-09-09T13:14:57.383566+00:00  Consumed record with orderId: 7449a1c2-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 318
2026-09-09T13:15:13.203156+00:00  Consumed record with orderId: 7db7973b-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 319
2026-09-09T13:15:16.331407+00:00  Consumed record with orderId: 7f945dec-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 320
```

## The change log, which supplied the cause

With the logs pointing at a silent kill during startup, the change history was the next place to look, and it was unusually clean.

Nine changes for this service across the preceding day. All nine are the same kind of thing: the container memory limit being lowered to 200m and restored, over and over, all attributed to the platform-automation actor. No deployments. No releases. No image or version bumps. No application config or feature-flag edits. No human-initiated entries at all. Every one of the usual suspects is absent from the record.

The cycle runs on a roughly five-to-six-hour cadence, with each constrained period lasting ten or twelve minutes before the revert lands. That regularity is itself informative — it reads as an automated recurring job, not an operator poking at something.

The last occurrence lands about five minutes before onset. Unlike the four before it, no matching revert is recorded. The constrained limit was still in effect when the service started failing.

This is the part that makes the conclusion hold together. The change type on its own explains nothing: four earlier identical reductions came and went without an incident. What distinguishes this one is that it was never undone, so the service had to survive a full boot under the constrained limit rather than riding out ten minutes on an already-warm process.

> Evidence `tr_8402079ce523`:

```
<tool_result id="tr_8402079ce523" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" radius="seed" hops="0">
service: frauddetectionservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T16:08:32.021281+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.4h before onset  2026-09-09T12:50:30.958805+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## Where that leaves the reading

Putting the two together: the service cannot complete JVM startup under the constrained memory limit. It gets as far as loading the agent, then dies during heap initialisation, silently, before any application code can log. The supervisor restarts it, and the loop repeats about once a minute. Kafka consumption stops dead because the process never reaches the point of consuming.

So: the missing revert is how it started; running out of memory during startup is what is happening. Fix class is a configuration revert — restore the memory limit and the boot should complete.

Confidence in this is medium, not high, and the next section says why.

> Evidence `tr_8402079ce523`:

```
<tool_result id="tr_8402079ce523" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" radius="seed" hops="0">
service: frauddetectionservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T16:08:32.021281+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.4h before onset  2026-09-09T12:50:30.958805+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_66732c3b1fb5`:

```
<tool_result id="tr_66732c3b1fb5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T13:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T13:14:43.929543+00:00  Consumed record with orderId: 6c450c5e-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 317
2026-09-09T13:14:57.383566+00:00  Consumed record with orderId: 7449a1c2-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 318
2026-09-09T13:15:13.203156+00:00  Consumed record with orderId: 7db7973b-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 319
2026-09-09T13:15:16.331407+00:00  Consumed record with orderId: 7f945dec-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 320
```

## Dead ends and what was never checked

Dead ends first, because they are the reusable part.

The error-ratio metric was queried twice, against two different baseline lengths, and returned nothing both times. Neither query was wasted exactly — the second one is what proved the emptiness predated the incident — but any further time spent on span-derived call metrics for this service would have been. Skip it.

The hypothesis that telemetry stopping at the boundary indicated the crash: ruled out, baseline equally empty.

The hypothesis that the logs would name a failing downstream: ruled out, there are no failure lines of any kind to read a dependency name off.

The hypothesis that the agent itself was killing the process: ruled out, it banners successfully every boot.

The hypothesis that some bad config value would be visible in the logs: ruled out, the only config-adjacent output is the identical JVM tool-options line on every boot, naming no application key.

Now the gaps, which matter more than the dead ends.

No container-level evidence was ever obtained. Restart count, the OOMKilled termination reason, and memory working-set against the limit were all named as the right queries and none were run. The kill mechanism is inferred from timing and log shape, not observed. That is the single largest hole in this record and the first thing to close on a repeat.

Because the crash emits no error at all, an alternative fatal-at-startup story is not positively excluded — for instance a broker handshake that blocks long enough for a liveness probe to kill the container would look identical from the log side. It is unsupported, not disproven.

Why the automation lowered the limit in the first place, and why this cycle's revert did not fire, is unknown. Whether it will self-correct on the next cadence tick or is stuck indefinitely is also unknown. Do not assume it will heal itself.

The absent calls_total series for at least six hours before onset was never explained. It may be a benign labelling artifact; it may be a second, unrelated observability defect. Worth a separate ticket either way.

Finally, blast radius was reported as one service with zero unmeasured edges, but no consumer of frauddetectionservice was actually examined. The Kafka consumption stopped; whoever depends on that being processed was not checked. Downstream impact is unquantified.

> Evidence `tr_233321ed63a3`:

```
<tool_result id="tr_233321ed63a3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T10:14:30.583000+00:00..2026-09-09T16:14:30.583000+00:00" template="error-ratio" baseline="2026-09-09T04:14:30.583000+00:00..2026-09-09T10:14:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_5a6dc06caae7`:

```
<tool_result id="tr_5a6dc06caae7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T13:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" template="error-ratio" baseline="2026-09-09T10:12:33.930247+00:00..2026-09-09T13:14:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_66732c3b1fb5`:

```
<tool_result id="tr_66732c3b1fb5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T13:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T13:14:43.929543+00:00  Consumed record with orderId: 6c450c5e-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 317
2026-09-09T13:14:57.383566+00:00  Consumed record with orderId: 7449a1c2-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 318
2026-09-09T13:15:13.203156+00:00  Consumed record with orderId: 7db7973b-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 319
2026-09-09T13:15:16.331407+00:00  Consumed record with orderId: 7f945dec-ac50-11f1-8c9e-7eeb37988879, and updated total count to: 320
```

> Evidence `tr_8402079ce523`:

```
<tool_result id="tr_8402079ce523" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:14:30.583000+00:00..2026-09-09T16:16:27.235753+00:00" radius="seed" hops="0">
service: frauddetectionservice
9 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T16:08:32.021281+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.4h before onset  2026-09-09T12:50:30.958805+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

