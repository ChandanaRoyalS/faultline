# Fraud Detection Goes Silent Under a Tightened Memory Ceiling

## What the responder saw first

The page named exactly one service: frauddetectionservice, severity critical, blast radius of one. Nothing else alerted, and no unmeasured edges were crossed on the way in, so there was no upstream/downstream trail to chase from the outset. Call it T+0 at the alert. The first instinct was to look for errors in the alerted service — that instinct produced nothing, and understanding why took most of the investigation.

## The metrics dead end (and it is a real dead end)

By roughly T+2m the first metric query was back: error ratio for the service, incident window and a preceding baseline window. Both empty. No samples at all, on either side. The tempting read is "telemetry went silent because the process died" — that read is wrong, and a future responder should not repeat it. The baseline window, starting well over an hour before the alert, is equally empty. The absence predates the incident. It is a missing or mislabelled series, not a signal.

That matters for a second reason. Every metric query in this investigation used the unhyphenated label value `frauddetectionservice`. The log stream, when it finally returned data, came back under the hyphenated `frauddetection-service`. So the selector almost certainly never resolved. No request rate, latency percentile, restart count, memory working-set, or memory-limit series was ever successfully retrieved. Anyone picking this up should re-run those queries against the hyphenated label before concluding the metrics backend has nothing.

> Evidence `tr_5aa7ff6cd322`:

```
<tool_result id="tr_5aa7ff6cd322" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T12:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" template="error-ratio" baseline="2026-09-09T11:43:49.644178+00:00..2026-09-09T12:15:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_f44a263a2767`:

```
<tool_result id="tr_f44a263a2767" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T11:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" template="error-ratio" baseline="2026-09-09T09:43:49.644178+00:00..2026-09-09T11:15:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The logs relocate the onset

The log query over the full window returned a clean, boring stream: routine successful Kafka consume records with a running counter climbing steadily from 496 up to 623. Consume events a few seconds apart, no widening gaps, no degradation, no warnings. And then, at 12:39:41 — about T-6m, six minutes *before* the page — the stream stops dead. Nothing follows it to the end of the window.

This reframed the whole incident. The failure did not begin at the alert; it began six minutes earlier, and the alert is a lagging indicator. Several plausible stories died here at once: there is no exception or stack trace anywhere in the retained lines; there are no startup or initialization messages and the consume counter never resets, so no fresh process instance began logging — the service did not crash and come back; and consumption is unbroken and evenly paced right up to the cutoff, which rules out a rebalance, poll timeout, or offset-commit failure quietly degrading things beforehand. The stream also proves ingestion works, so the silence is a behaviour change, not a broken pipeline.

> Evidence `tr_15c794e4c603`:

```
<tool_result id="tr_15c794e4c603" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T12:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T12:16:16.903003+00:00  Consumed record with orderId: 41eb74f0-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 496
2026-09-09T12:16:17.375277+00:00  Consumed record with orderId: 42342ad7-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 497
2026-09-09T12:16:27.071804+00:00  Consumed record with orderId: 47fb6b91-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 498
2026-09-09T12:16:30.416976+00:00  Consumed record with orderId: 49fa19b9-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 499
```

## The change log, and the trap inside it

The change history for the service over the window holds exactly seven entries. All seven are resource-limit edits to the memory limit on frauddetection-service, and all seven were made by the same platform-automation actor. That rules out a great deal in one stroke: no deploy or release, no flag flip, no library or dependency bump, no non-resource application config edit, and no human operator acting ad hoc before the incident.

Here is the trap. The obvious move is to point at the most recent edit — a lowering of the memory limit to 200m at 12:39:46, about T-6m — and call it novel. It is not novel. The six preceding entries form three complete lower-then-revert pairs, each pair about ten or eleven minutes wide, recurring every few hours across the window. The service had been through this exact constraint three times already and survived, because each time it was withdrawn. The distinguishing feature of the seventh entry is not what it did but what did not follow it: no revert. The lowered ceiling was still in effect at onset and stayed in effect.

> Evidence `tr_89bc77785074`:

```
<tool_result id="tr_89bc77785074" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T12:45:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T12:39:46.687117+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.5h before onset  2026-09-09T09:17:17.282650+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## How the pieces line up

The limit was applied at 12:39:46. The last log line is 12:39:41. Those are within seconds of each other, on either side of a clock boundary that no one should read too precisely. A healthy consumer processing steadily, then instantaneous and permanent silence with no error, no exit message, and no restart, coinciding with a newly tightened memory ceiling, is the signature of a process being terminated for exceeding what it is now allowed to use and being unable to come back up under the new limit. The failing service is frauddetectionservice itself; nothing propagated, and the blast radius stays at one.

Confidence here is medium, deliberately. The kill mechanism is inferred from timing against silence, not observed. Fix class is a config revert.

> Evidence `tr_89bc77785074`:

```
<tool_result id="tr_89bc77785074" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T12:45:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T12:39:46.687117+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.5h before onset  2026-09-09T09:17:17.282650+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_15c794e4c603`:

```
<tool_result id="tr_15c794e4c603" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T12:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T12:16:16.903003+00:00  Consumed record with orderId: 41eb74f0-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 496
2026-09-09T12:16:17.375277+00:00  Consumed record with orderId: 42342ad7-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 497
2026-09-09T12:16:27.071804+00:00  Consumed record with orderId: 47fb6b91-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 498
2026-09-09T12:16:30.416976+00:00  Consumed record with orderId: 49fa19b9-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 499
```

## Left open for the next responder

Four things were never established and should be, in roughly this order.

First, the mechanism itself. No termination event, container restart count, memory working-set figure, or memory-limit value was ever retrieved from metrics. The story is coherent but circumstantial. Re-query under the hyphenated label.

Second, the alert delay. The service went quiet at 12:39:41 and the page fired at 12:45:45 — roughly six minutes of blind time. The evaluation delay in the alerting rule, or whatever the actual detection path was, was never examined. That gap is its own defect.

Third, and most important for durability: nobody established what the platform-automation loop is or why it applies and withdraws this same memory limit every few hours. A one-off revert may simply be re-applied by the same loop on its next pass. The lasting fix probably lives in correcting or disabling the automation, not in editing the limit by hand once.

Fourth, downstream. Triage scoped this to a single service and no caller or consumer of fraud-detection results was ever dispatched on. Whether anything depending on this service degraded during the silence is unknown, not confirmed-clean.

> Evidence `tr_f44a263a2767`:

```
<tool_result id="tr_f44a263a2767" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T11:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" template="error-ratio" baseline="2026-09-09T09:43:49.644178+00:00..2026-09-09T11:15:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_5aa7ff6cd322`:

```
<tool_result id="tr_5aa7ff6cd322" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T12:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" template="error-ratio" baseline="2026-09-09T11:43:49.644178+00:00..2026-09-09T12:15:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_15c794e4c603`:

```
<tool_result id="tr_15c794e4c603" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T12:15:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T12:16:16.903003+00:00  Consumed record with orderId: 41eb74f0-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 496
2026-09-09T12:16:17.375277+00:00  Consumed record with orderId: 42342ad7-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 497
2026-09-09T12:16:27.071804+00:00  Consumed record with orderId: 47fb6b91-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 498
2026-09-09T12:16:30.416976+00:00  Consumed record with orderId: 49fa19b9-ac48-11f1-8c9e-7eeb37988879, and updated total count to: 499
```

> Evidence `tr_89bc77785074`:

```
<tool_result id="tr_89bc77785074" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T12:45:45.583000+00:00..2026-09-09T12:47:41.521822+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T12:39:46.687117+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.5h before onset  2026-09-09T09:17:17.282650+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

