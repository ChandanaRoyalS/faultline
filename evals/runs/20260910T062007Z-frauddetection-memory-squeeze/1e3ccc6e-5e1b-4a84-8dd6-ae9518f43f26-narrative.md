# frauddetection-service crash-restart loop after an automated memory-cap edit

## What the responder saw first

The page named a single service, frauddetectionservice, at critical severity. Blast radius as scoped was one service; no unmeasured edges were crossed on the way in. There was no accompanying error-rate alert, no latency alert, and no complaint from a neighbour — just the one service going critical, which is worth noting because it shaped the first half hour of the investigation. The instinct was to look for a spike in errors. There wasn't one to find.

## The metrics dead end (T+0 to roughly T+10m)

First move was the standard error-ratio comparison against baseline for frauddetectionservice. It came back empty — not zero, empty. No samples in the incident window and none in the half-hour of presumed-healthy time before it. The instinct at that point is to read the emptiness as 'the service stopped serving at onset', but the baseline window being equally barren kills that reading: a traffic stop at onset would have left the healthy samples behind. Repeating the same comparison over a much wider six-hour window a day earlier produced the same nothing.

So the call/span-derived series for this service simply does not exist under the label selector we were querying, in sickness or in health. That is almost certainly an instrumentation or label mismatch and not a symptom. It cost time and it proved nothing, but it is the single most useful thing in this record for the next responder: do not spend your first ten minutes here. It also means we never established, from metrics, that the service was serving before onset — the only positive evidence of prior health came later, from logs.

Worth being explicit about what these queries did *not* cover: request rate, latency percentiles, restart counts, container working-set memory, memory limits, and kill counters were never retrieved at all. Nothing in the metric evidence speaks to memory pressure in either direction.

> Evidence `tr_749b14d0b8a1`:

```
<tool_result id="tr_749b14d0b8a1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T05:56:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" template="error-ratio" baseline="2026-09-10T05:24:23.696659+00:00..2026-09-10T05:56:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1229d1eb8d69`:

```
<tool_result id="tr_1229d1eb8d69" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T07:26:15.583000+00:00..2026-09-09T13:26:15.583000+00:00" template="error-ratio" baseline="2026-09-09T01:26:15.583000+00:00..2026-09-09T07:26:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The logs, which actually said something

Pulling the raw log stream for frauddetection-service across the incident window changed the picture immediately. Early in the window — roughly T-30m — the service was plainly healthy: a steady run of Kafka record-consumption lines with a monotonically climbing counter. That output stops dead at about T-6m and never resumes.

From that point to the end of capture, the stream contains one thing repeated: a three-line JVM startup sequence (the JAVA_TOOL_OPTIONS pickup, the OpenJDK class-sharing warning, and the OpenTelemetry agent version banner). Fresh occurrences land at roughly T-5m, T-4m, T-3m, T-2m, T-1m, T+0 and T+1m — a start every sixty seconds or so.

What is absent matters as much as what is present. No exception. No panic. No stack trace. No per-request rejection lines. The process reaches agent initialisation, logs the banner successfully, and then goes away without writing a word about why. That shape — silent teardown, clean startup boilerplate, fixed cadence — is an external kill, not something the application decided for itself.

Three hypotheses died here. The service is not hung or deadlocked: a stalled long-lived process would not re-emit startup banners on a minute cycle. It is not rejecting work at high volume: it emits no application output at all after T-6m, so it is not processing anything to reject. And the telemetry agent is not the culprit: its banner is written cleanly on every restart with no error following it.

> Evidence `tr_375a5b63f2a2`:

```
<tool_result id="tr_375a5b63f2a2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T05:56:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-10T05:56:17.008588+00:00  Consumed record with orderId: 56895ff4-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 442
2026-09-10T05:56:31.800554+00:00  Consumed record with orderId: 5f5a9c9f-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 443
2026-09-10T05:56:40.068435+00:00  Consumed record with orderId: 64486211-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 444
2026-09-10T05:56:40.543529+00:00  Consumed record with orderId: 6490dfc4-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 445
```

## The change history

The change log for this service over the preceding twenty-four hours contains seven entries, and all seven are the same kind of thing: resource-limit adjustments on frauddetection-service, all from the same automated platform actor. No deployments. No releases. No feature-flag flips. No application config or environment edits. No human hands anywhere in the record.

The entry that matters landed at roughly T-6m — the same minute the Kafka consumption lines stopped — and it set a memory cap of 200m where the service had previously had none configured.

The same lower-then-restore pattern appears three times earlier in the window, at approximately twenty-one, eighteen and fourteen hours before onset. Each of those earlier lowerings was followed by an automated restore about ten or eleven minutes later. The one adjacent to onset had no matching restore entry at the time the history was captured, so the cap was still in force when we were looking at it.

That last detail is the one to check first on a repeat. It is tempting to assume the automation self-heals and the current state is already clean; the history says it usually does, and says it hadn't this time.

> Evidence `tr_9628629cabea`:

```
<tool_result id="tr_9628629cabea" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T06:26:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T06:20:12.323360+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  14.1h before onset  2026-09-09T16:19:24.622462+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## Where the evidence lands

A JVM cannot live inside a 200m memory cap. The cap arrives at T-6m; useful work stops at T-6m; from then on the process is repeatedly started and silently killed on a roughly one-minute cycle without ever writing a reason. The failing mechanism is memory exhaustion against a limit the runtime cannot fit in, and the trigger is the automated limit edit.

Confidence is medium, not high, and the reason is stated plainly in the next section. Fix class is a revert of the configuration: restore the memory allocation to its prior unconfigured state, or to a value the JVM can actually occupy, and confirm the Kafka consumption lines resume.

> Evidence `tr_9628629cabea`:

```
<tool_result id="tr_9628629cabea" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T06:26:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T06:20:12.323360+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  14.1h before onset  2026-09-09T16:19:24.622462+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_375a5b63f2a2`:

```
<tool_result id="tr_375a5b63f2a2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T05:56:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-10T05:56:17.008588+00:00  Consumed record with orderId: 56895ff4-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 442
2026-09-10T05:56:31.800554+00:00  Consumed record with orderId: 5f5a9c9f-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 443
2026-09-10T05:56:40.068435+00:00  Consumed record with orderId: 64486211-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 444
2026-09-10T05:56:40.543529+00:00  Consumed record with orderId: 6490dfc4-acdc-11f1-b3b3-0a86ba8b9e4a, and updated total count to: 445
```

## Open questions and what a repeat should measure

The memory kill is inferred, not observed. No container working-set, no configured-limit series, no kill counter, no kube restart count was ever pulled. The whole chain rests on log shape and timing correlation. Someone hitting this again should retrieve those four series first; they would settle it in a minute.

A liveness-probe restart is not excluded. It produces the same silent teardown with no application log line and could plausibly fire on the same cadence. Nothing dispatched can tell the two apart.

The empty call series remains unexplained. It is empty across healthy baselines too, so it is an observability defect rather than an incident symptom, but it should be fixed — it is why we could not confirm the service was serving traffic before onset by any route other than reading Kafka log lines.

We do not know whether the automation will restore this limit on its own, as it did three times earlier, or whether this instance is stuck. Nor do we know what drives the automation to lower the cap in the first place. That is the real durable question: the immediate revert fixes today, not the fourth cycle.

Finally, blast radius was scoped to one service and nothing was dispatched downstream. Consumers of frauddetection, and the backlog on the Kafka topic it stopped draining at T-6m, were never examined. Treat the one-service radius as unverified rather than confirmed.

> Evidence `tr_1229d1eb8d69`:

```
<tool_result id="tr_1229d1eb8d69" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T07:26:15.583000+00:00..2026-09-09T13:26:15.583000+00:00" template="error-ratio" baseline="2026-09-09T01:26:15.583000+00:00..2026-09-09T07:26:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_749b14d0b8a1`:

```
<tool_result id="tr_749b14d0b8a1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T05:56:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" template="error-ratio" baseline="2026-09-10T05:24:23.696659+00:00..2026-09-10T05:56:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_9628629cabea`:

```
<tool_result id="tr_9628629cabea" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T06:26:15.583000+00:00..2026-09-10T06:28:07.469341+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-10T06:20:12.323360+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  14.1h before onset  2026-09-09T16:19:24.622462+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

