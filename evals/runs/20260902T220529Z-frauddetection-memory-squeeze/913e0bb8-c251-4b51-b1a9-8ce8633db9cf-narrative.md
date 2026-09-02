# frauddetectionservice restart loop after an automated container memory limit reduction

## What the responder saw first

The page named a single service, frauddetectionservice, at critical severity. Nothing else was alerting and no downstream service was flagged, so the working assumption at T+0 was a self-contained problem inside one container.

The first useful thing on screen was the log stream. It did not look like a service in trouble in the usual way: there were no errors, no exceptions, no panics, no stack traces anywhere in the retained window. What there was instead was a three-line JVM and OpenTelemetry-agent startup sequence, repeating over and over at an almost metronomic ~62-second cadence, with the last cycle beginning at 22:17:57. Ten-plus identical bootstraps in a row is not a deploy and not a one-off restart; the process was coming up and being taken down again shortly after.

The second useful thing was what had stopped. Kafka order-consumption lines carry a monotonically increasing counter. Those lines run up to 22:04:47 (count 2344) and then never appear again in the retained data. So between kills the service was not getting far enough to do work.

> Evidence `tr_ce5350e3f868`:

```
<tool_result id="tr_ce5350e3f868" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T21:47:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-02T22:03:55.179629+00:00  Consumed record with orderId: 30969456-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2337
2026-09-02T22:03:55.201521+00:00  Consumed record with orderId: 309bceeb-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2338
2026-09-02T22:04:04.588470+00:00  Consumed record with orderId: 36326049-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2339
2026-09-02T22:04:05.462038+00:00  Consumed record with orderId: 36ba0578-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2340
```

## The change that lines up

The change log for this service across the queried window held exactly one entry: a resource_limits update issued by a platform-automation actor that set the container memory limit to 200m, at 22:05:32 — about two minutes ahead of the earliest restart cycle visible in logs and roughly eleven minutes ahead of the page.

That single entry closed several branches at once. There was no code deploy or image rollout recorded. There was no feature-flag flip. There was no application config or environment-variable edit that could have altered fraud-detection thresholds or logic. And the "nothing changed locally, look upstream" branch was also closed — something did change here, close to onset. The actor being automation rather than a human, and the timestamp preceding onset, also rules this out as an emergency remediation someone applied to an already-sick service.

> Evidence `tr_5d90a328d546`:

```
<tool_result id="tr_5d90a328d546" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T22:17:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  11m before onset  2026-09-02T22:05:32.962217+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_5d90a328d546>
```

## Dead end: the error-rate metric

Two separate passes were spent trying to anchor onset on the span-derived error ratio for this service — once against a six-hour baseline, once against a three-hour one. Both returned zero samples, in the incident window and in the baseline window alike.

This is worth recording carefully, because it is easy to misread twice over. It is not a low error rate; a zero-sample response supports no health conclusion in either direction. It is also not telemetry that died at onset — the baseline periods well before the incident are equally empty, so there was never a flow of these series to lose. The label simply never yields data for this service. Any future responder reaching for this query on frauddetectionservice should expect nothing and should not spend time on it.

> Evidence `tr_152861f4d9dc`:

```
<tool_result id="tr_152861f4d9dc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T22:17:00.583000+00:00..2026-09-02T04:17:00.583000+00:00" template="error-ratio" baseline="2026-09-01T16:17:00.583000+00:00..2026-09-01T22:17:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_d87905d7d6ea`:

```
<tool_result id="tr_d87905d7d6ea" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-02T19:17:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" template="error-ratio" baseline="2026-09-02T16:15:12.937017+00:00..2026-09-02T19:17:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Dead end: trying to observe the kill directly

The obvious confirmation step was requested and produced nothing. Container working-set bytes, the memory limit spec before and after the change, container restart counts, and the container's last-terminated-reason were all asked for; none of those series came back. The dispatch that was supposed to settle the memory question returned only the same empty error-ratio comparison, which carries no container memory, restart, or termination data at all and therefore neither confirms nor refutes anything.

So the kill mechanism was never observed. It is inferred from shape: a process that re-executes its bootstrap on a near-constant interval, emits no error of its own, and dies before it resumes consuming — the signature of something outside the application terminating it, not of an application failure.

> Evidence `tr_d87905d7d6ea`:

```
<tool_result id="tr_d87905d7d6ea" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-02T19:17:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" template="error-ratio" baseline="2026-09-02T16:15:12.937017+00:00..2026-09-02T19:17:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ce5350e3f868`:

```
<tool_result id="tr_ce5350e3f868" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T21:47:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-02T22:03:55.179629+00:00  Consumed record with orderId: 30969456-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2337
2026-09-02T22:03:55.201521+00:00  Consumed record with orderId: 309bceeb-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2338
2026-09-02T22:04:04.588470+00:00  Consumed record with orderId: 36326049-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2339
2026-09-02T22:04:05.462038+00:00  Consumed record with orderId: 36ba0578-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2340
```

## Where the reasoning landed

Best available reading: the lowered memory ceiling is below what this JVM holds in steady state, so the platform terminates the container shortly after each bootstrap, and the service never gets back to consuming orders. The trigger is the limit edit; the mechanism is the process exceeding what it is allowed and being killed for it. Suggested fix class is a revert of that limit.

Confidence is medium, not high, and the reasons are listed below rather than buried.

> Evidence `tr_5d90a328d546`:

```
<tool_result id="tr_5d90a328d546" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T22:17:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  11m before onset  2026-09-02T22:05:32.962217+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_5d90a328d546>
```

> Evidence `tr_ce5350e3f868`:

```
<tool_result id="tr_ce5350e3f868" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T21:47:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-02T22:03:55.179629+00:00  Consumed record with orderId: 30969456-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2337
2026-09-02T22:03:55.201521+00:00  Consumed record with orderId: 309bceeb-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2338
2026-09-02T22:04:04.588470+00:00  Consumed record with orderId: 36326049-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2339
2026-09-02T22:04:05.462038+00:00  Consumed record with orderId: 36ba0578-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2340
```

## What stayed open

Four gaps a later responder should not assume were closed.

First, the kill is inferred, never seen. No termination reason, no restart count, no memory series.

Second, the previous memory limit is not recorded in the change log. Without it there is no way to know whether 200m is a mild trim or an order-of-magnitude cut, which matters for how confidently the limit can be blamed.

Third, and most load-bearing: 22:07:35 is not the start of the loop, it is the edge of the retained newest-lines block. It was never shown that the loop began *after* the 22:05:32 change rather than before it. If it began before, the causal link to the change weakens considerably, and that check was not performed.

Fourth, the page itself is unexplained. The loop was already well established by the time it fired, and no metric anchors onset, so what signal tripped at that moment was never identified.

Two further items were simply not investigated. Blast radius beyond this one service was never dispatched — no one looked at consumer lag, order backlog, or the downstream consumers of fraud-detection results, despite processing having been stopped since roughly 22:04:47. And nobody established *why* the automation issued the reduction: rightsizing policy, quota enforcement, or a bad recommendation. That last one decides whether a revert holds or is quietly re-applied by the same automation a cycle later.

> Evidence `tr_d87905d7d6ea`:

```
<tool_result id="tr_d87905d7d6ea" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-02T19:17:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" template="error-ratio" baseline="2026-09-02T16:15:12.937017+00:00..2026-09-02T19:17:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_5d90a328d546`:

```
<tool_result id="tr_5d90a328d546" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T22:17:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  11m before onset  2026-09-02T22:05:32.962217+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_5d90a328d546>
```

> Evidence `tr_ce5350e3f868`:

```
<tool_result id="tr_ce5350e3f868" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T21:47:00.583000+00:00..2026-09-02T22:18:48.228983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-02T22:03:55.179629+00:00  Consumed record with orderId: 30969456-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2337
2026-09-02T22:03:55.201521+00:00  Consumed record with orderId: 309bceeb-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2338
2026-09-02T22:04:04.588470+00:00  Consumed record with orderId: 36326049-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2339
2026-09-02T22:04:05.462038+00:00  Consumed record with orderId: 36ba0578-a71a-11f1-9d4d-2a9a845f0956, and updated total count to: 2340
```
