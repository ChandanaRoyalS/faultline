# Fraud Detection Service Restart Loop Following a Container Memory Limit Change

## What the alert looked like from the chair

The page named one service — frauddetectionservice — and nothing else. Blast radius stayed at one service throughout; no unmeasured edges were crossed during triage. The alert timestamp (call it T+0) turned out to be misleading in a specific way that is worth internalising: it was not the moment something broke. It was one tick of a loop that had already been running for roughly six minutes. Anyone arriving at the page and anchoring on T+0 as "onset" will waste time looking for a triggering event at that instant. There isn't one.

> Evidence `tr_386f315a11ba`:

```
<tool_result id="tr_386f315a11ba" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-10T12:09:36.079499+00:00  Consumed record with orderId: 7d2d5c7b-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 166
2026-09-10T12:09:44.476311+00:00  Consumed record with orderId: 826964db-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 167
2026-09-10T12:09:51.316235+00:00  Consumed record with orderId: 867f2fae-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 168
2026-09-10T12:09:52.049055+00:00  Consumed record with orderId: 86efa5b3-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 169
```

## First move: metrics, and the dead end that ate the most time

The instinct was to characterise the service the way every other service in this estate gets characterised: span-derived error ratio, throughput, latency percentiles. The error-ratio query returned nothing. Not zero — nothing. No samples at all.

The natural next thought is "the service went silent, that's the signal." It isn't. We ran the same query against a baseline window roughly three hours earlier and got the same empty answer, then again across a six-hour window the previous day and got the same empty answer a third time. Two independent, non-overlapping windows spanning about six hours both held nothing, which rules out a windowing artifact. The conclusion is unglamorous: this service simply does not produce server-side RPC call metrics. It never did. The gap predates the incident by at least a day and is not an onset signal.

The practical lesson for a future responder: do not try to characterise frauddetectionservice through `calls_total`-shaped queries. It is a Kafka consumer, not an RPC server, and the standard template returns an empty set that reads like a crash but means nothing. Go straight to logs or to consumer-side/runtime metrics.

> Evidence `tr_785013925cd8`:

```
<tool_result id="tr_785013925cd8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T10:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" template="error-ratio" baseline="2026-09-10T07:00:39.439583+00:00..2026-09-10T10:02:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_0534648ae890`:

```
<tool_result id="tr_0534648ae890" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T13:02:30.583000+00:00..2026-09-09T19:02:30.583000+00:00" template="error-ratio" baseline="2026-09-09T07:02:30.583000+00:00..2026-09-09T13:02:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## What the logs actually showed

Logs were where the shape of the failure became visible. Two things stood out.

First, the negative: across the whole hour-plus window there is not one error line, not one throwable, not one stack frame, not one panic. The only non-INFO output is benign JVM class-sharing warnings. That immediately kills the two most common hypotheses. There is no application code path failing — there is no code path to cluster on. And there is no downstream dependency error: no broker connection failures, no timeouts, no retry storms. Nothing in this service's own logging points at a named dependency.

Second, the positive: from roughly T-6m onward the log stream degenerates into repeating JVM and OpenTelemetry-agent startup banners, a fresh startup sequence arriving at an almost exactly 60-second cadence. One of those sequences lands within about eight seconds of the alert timestamp. The process is dying and coming back roughly once a minute.

The detail that mattered most: the late startup sequences never progress past agent initialisation into real work. The oldest kept lines, about fifty minutes before the alert, show steady Kafka record consumption with an incrementing counter. After the loop begins, no consumption lines follow any restart. So the service is not degraded-but-working; it never reaches steady state at all. And because no farewell or graceful-shutdown message is ever emitted, the process is being terminated from outside rather than exiting on its own.

One more thing we checked and set aside: the startup banners are byte-identical across iterations — same agent version, same JAVA_TOOL_OPTIONS. Nothing about a code or config change is observable *from within the logs*. That is why the change record, not the logs, is what closed the case.

> Evidence `tr_386f315a11ba`:

```
<tool_result id="tr_386f315a11ba" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-10T12:09:36.079499+00:00  Consumed record with orderId: 7d2d5c7b-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 166
2026-09-10T12:09:44.476311+00:00  Consumed record with orderId: 826964db-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 167
2026-09-10T12:09:51.316235+00:00  Consumed record with orderId: 867f2fae-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 168
2026-09-10T12:09:52.049055+00:00  Consumed record with orderId: 86efa5b3-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 169
```

## The change record

The change log for this service in the surrounding day contains exactly one class of entry: container resource-limit adjustments, five of them, every single one authored by the same automated actor against the frauddetection-service workload.

This rules out a great deal in one stroke. No deployment or release events. No feature-flag flips. No image or library version bumps. No application-level configuration touched — no timeouts, thresholds, or pool sizes. And no ad-hoc human change during the window; there is no individual operator anywhere in the record.

The entry that matters landed roughly six minutes before the loop began. It lowered the container memory limit to 200m where no limit had previously been set. That is the closest change in time to the incident by a wide margin.

The wrinkle: this is not the first time. The same 200m lowering was applied and then reverted twice earlier in the window — once about twenty-one hours before, once about seven hours before. So the setting itself is recurrent, and the actor applying it is on some kind of cycle. What distinguishes this occasion is that the pre-onset application has no matching revert in the record, which is why the 200m limit was still in effect when the loop started.

> Evidence `tr_b95d9ef21001`:

```
<tool_result id="tr_b95d9ef21001" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T13:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T12:56:26.773511+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  6.5h before onset  2026-09-10T06:31:25.813281+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## How the pieces fit

A JVM confined to a 200m container, followed within minutes by a silent, externally-terminated, minute-cadence restart loop that never reaches steady-state work, is the signature of the container being killed for exceeding its memory ceiling. The service is not erroring on a code path and it is not blocked on a dependency; it cannot finish starting up inside the memory it has been given, and is killed for it. Recovery class is a revert of that limit.

Confidence here is medium, not high, and the reason is stated plainly in the next section.

> Evidence `tr_b95d9ef21001`:

```
<tool_result id="tr_b95d9ef21001" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T13:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T12:56:26.773511+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  6.5h before onset  2026-09-10T06:31:25.813281+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_386f315a11ba`:

```
<tool_result id="tr_386f315a11ba" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-10T12:09:36.079499+00:00  Consumed record with orderId: 7d2d5c7b-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 166
2026-09-10T12:09:44.476311+00:00  Consumed record with orderId: 826964db-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 167
2026-09-10T12:09:51.316235+00:00  Consumed record with orderId: 867f2fae-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 168
2026-09-10T12:09:52.049055+00:00  Consumed record with orderId: 86efa5b3-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 169
```

## What we never confirmed

The memory mechanism is inferred, not observed. We never queried container working-set or RSS, never pulled restart counts, and never looked at the last-terminated-reason or an OOMKilled flag. Every metric attempt in this investigation ran the same span-based error-ratio template, which carries none of that data. A responder picking this up should start exactly where we stopped: kubelet/cAdvisor container metrics for this pod.

That gap leaves one live alternative. A liveness-probe failure, or an orchestrator SIGKILL for some non-memory reason, would produce an identical silent minute-cadence restart loop with no farewell message. Nothing in the evidence we gathered distinguishes it from a memory kill. The change timing is what tips the balance, not the log shape alone.

Several other questions are open. We do not know why the two earlier applications of the same 200m limit were reverted without an apparent incident, nor whether restarts clustered during those windows — the metric windows we pulled do not even reach back far enough to cover the earlier one, so this is untested rather than answered. We do not know what the automated actor is doing or on what trigger, which means a manual revert may not hold if the automation reapplies the limit. We do not know this JVM's actual working-set requirement, so whether 200m is merely tight or wildly insufficient is unsettled — that number matters for choosing a safe replacement value rather than just reverting to unset. Finally, triage covered one service only, so the effect of a stalled fraud-detection consumer on upstream order flow was never measured; the topic backlog and any consumer-lag consequence are unquantified.

> Evidence `tr_0534648ae890`:

```
<tool_result id="tr_0534648ae890" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T13:02:30.583000+00:00..2026-09-09T19:02:30.583000+00:00" template="error-ratio" baseline="2026-09-09T07:02:30.583000+00:00..2026-09-09T13:02:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_386f315a11ba`:

```
<tool_result id="tr_386f315a11ba" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-10T12:09:36.079499+00:00  Consumed record with orderId: 7d2d5c7b-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 166
2026-09-10T12:09:44.476311+00:00  Consumed record with orderId: 826964db-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 167
2026-09-10T12:09:51.316235+00:00  Consumed record with orderId: 867f2fae-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 168
2026-09-10T12:09:52.049055+00:00  Consumed record with orderId: 86efa5b3-ad10-11f1-b695-a6d3fecbda3c, and updated total count to: 169
```

> Evidence `tr_b95d9ef21001`:

```
<tool_result id="tr_b95d9ef21001" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T13:02:30.583000+00:00..2026-09-10T13:04:21.726417+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T12:56:26.773511+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  6.5h before onset  2026-09-10T06:31:25.813281+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

