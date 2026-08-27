# frauddetectionservice silent crash-restart loop after a memory ceiling change

## What the responder saw first

The page named exactly one service: frauddetectionservice. Blast radius stayed at one service for the whole investigation, severity critical, and no unmeasured edges were crossed on the way in. There was no fan-out to chase — no downstream service complaining, no upstream caller alerting. That narrowness is itself a clue, and it shaped the order of work: start at the workload, not at its neighbours.

For offsets in this record, T+0 is the moment a configuration change landed on the frauddetection-service workload. The incident marker that produced the page arrives at roughly T+6m.

## The change window

The first productive query was the change history for the service across the incident window. It returned exactly one entry: an automated actor, platform-automation, lowered the memory resource limit on the frauddetection-service workload at T+0, about six minutes before the marker. Everything else a responder normally reaches for in the first two minutes came back empty — no code deploy, no new service version, no feature flag flip, no library or dependency version bump. The window was also not empty, which rules out the tempting framing that this must be purely external (a traffic surge or an upstream outage) with no local trigger.

Two gaps in that record matter later. The prior limit value is not captured, so the size of the reduction is unknown from the change entry alone. And the recorded new value, "200m", is written in milli-unit notation, which is a CPU unit rather than a memory unit. Neither gap was closed during the investigation.

> Evidence `tr_4215e952dfd4`:

```
<tool_result id="tr_4215e952dfd4" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-27T08:08:02.859514+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4215e952dfd4>
```

## The metrics dead end (worth keeping)

The natural second move was to quantify the damage: an error-ratio expression over the span-derived call counter for the service, across the window. It returned nothing. Not a low ratio, not a zero — no matching series at all.

The important detail is that the denominator was missing too. If only the error-status numerator had been absent, that would suggest a service serving cleanly. With the total-calls series also absent, there is no evidence of any recorded request flow at all. A responder can spend a long time here deciding whether that means the scrape target is down, the service is not emitting, or the label selector is wrong. It is worth naming plainly: this query answered nothing about error rate and any error-rate figure quoted for this window from this source would be invented.

A second metrics pass over the same window reached the same wall and added the honest admission that the interesting series were never asked for at all: container restart counts, last-terminated-reason, memory working set, and the effective memory limit were all left unqueried. That is the single largest hole in this record.

> Evidence `tr_358bb2221bb0`:

```
<tool_result id="tr_358bb2221bb0" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_358bb2221bb0>
```

> Evidence `tr_f69cbcf7cffc`:

```
<tool_result id="tr_f69cbcf7cffc" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_f69cbcf7cffc>
```

## What the logs actually showed

Logs were the turn. The query returned a dense, well-timestamped stream, which immediately disposes of the theory that the pipeline was broken and the service was merely silent.

Up to roughly four minutes before T+0 the service is plainly healthy: a steady sequence of per-order Kafka consumption records with a monotonically climbing counter. Then, about eighteen seconds after T+0, the character of the stream changes completely. From roughly T+18s through at least T+8m17s the log contains nothing but full JVM and OpenTelemetry-agent bootstrap sequences — tool-options pickup, the class-sharing warning, the agent version banner — repeating as a complete set roughly every sixty seconds. No order-consumption records appear after the first restart.

What is absent is as informative as what is present. There are no ERROR lines, no Java exceptions, no stack traces, no business-logic or downstream-dependency complaints, and no explicit kill message on stdout. The only non-INFO content in the entire returned stream is the benign OpenJDK class-data-sharing warning emitted once per start; a responder scanning for the loudest repeated warning will land on it and it means nothing. The process is not degrading inside one long-lived instance — the repeated startup banners prove it is dying and coming back.

Caveat on coverage: the returned lines span only about four minutes before T+0 to about T+8m, narrower than the window asked for, and the middle was elided (oldest few and newest few lines retained). An error in the dropped segment cannot be excluded, and whether the loop continued past T+8m17s is unknown.

> Evidence `tr_8d36cfc8aff2`:

```
<tool_result id="tr_8d36cfc8aff2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-27T08:04:12.481758+00:00  Consumed record with orderId: e3b1e07d-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4148
2026-08-27T08:04:12.969976+00:00  Consumed record with orderId: e3fc78c7-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4149
2026-08-27T08:04:16.092389+00:00  Consumed record with orderId: e5d85a33-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4150
2026-08-27T08:04:16.354559+00:00  Consumed record with orderId: e600f0ff-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4151
```

## How the pieces fit

A JVM that starts cleanly, does no visible work, and terminates without writing anything is the signature of a process being killed from outside itself rather than failing on a code path. Place that eighteen seconds after its memory ceiling was tightened and the reading is that the ceiling now sits below what the heap is configured to commit, so the container is killed on startup, restarted, and killed again.

The missing call metrics stop being a mystery under that reading and become a consequence: a process that never lives long enough to serve a request emits no RPC spans, so neither numerator nor denominator ever exists. That is why the metrics dead end and the log finding are the same fact seen twice.

Confidence in this is medium, not high. The kill itself was inferred, never observed.

> Evidence `tr_4215e952dfd4`:

```
<tool_result id="tr_4215e952dfd4" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-27T08:08:02.859514+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4215e952dfd4>
```

> Evidence `tr_8d36cfc8aff2`:

```
<tool_result id="tr_8d36cfc8aff2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-27T08:04:12.481758+00:00  Consumed record with orderId: e3b1e07d-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4148
2026-08-27T08:04:12.969976+00:00  Consumed record with orderId: e3fc78c7-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4149
2026-08-27T08:04:16.092389+00:00  Consumed record with orderId: e5d85a33-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4150
2026-08-27T08:04:16.354559+00:00  Consumed record with orderId: e600f0ff-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4151
```

> Evidence `tr_f69cbcf7cffc`:

```
<tool_result id="tr_f69cbcf7cffc" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_f69cbcf7cffc>
```

## Fix taken and what remains open

Fix class: revert the configuration. Because the prior limit was not recorded, the value to restore has to be derived from the JVM heap settings or read off a healthy peer rather than lifted from the change entry.

Open items a future responder should close before trusting this record:

One query settles the mechanism. Ask for last-terminated-reason on the container; if it reports an out-of-memory kill, the inference becomes an observation. While there, pull restart counts, memory working set, and the effective limit series. None of these were ever run.

The unit notation is unresolved. "200m" is a CPU unit. If the limit was written with the wrong unit rather than deliberately lowered, this is a malformed value, not a tight-but-intentional ceiling, and the correct remediation is to fix the unit rather than to restore a number.

The log window is incomplete at both ends. Re-run it wide and without elision to confirm nothing was logged in the dropped middle and to find where the loop ended.

The actor was automation. Nobody examined why the change was made — policy rollout, a scaling recommendation, or a templating error — which determines whether a revert simply gets re-applied on the next pass. Relatedly, nobody checked whether other workloads received the same automated adjustment. Triage scoped this to one service on the strength of the alert, but an automated actor typically touches more than one target, and that assumption was never tested.

> Evidence `tr_4215e952dfd4`:

```
<tool_result id="tr_4215e952dfd4" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-27T08:08:02.859514+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4215e952dfd4>
```

> Evidence `tr_f69cbcf7cffc`:

```
<tool_result id="tr_f69cbcf7cffc" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_f69cbcf7cffc>
```

> Evidence `tr_8d36cfc8aff2`:

```
<tool_result id="tr_8d36cfc8aff2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T08:04:00.583000+00:00..2026-08-27T08:19:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-27T08:04:12.481758+00:00  Consumed record with orderId: e3b1e07d-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4148
2026-08-27T08:04:12.969976+00:00  Consumed record with orderId: e3fc78c7-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4149
2026-08-27T08:04:16.092389+00:00  Consumed record with orderId: e5d85a33-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4150
2026-08-27T08:04:16.354559+00:00  Consumed record with orderId: e600f0ff-a1ed-11f1-b0f0-0a04ae95d871, and updated total count to: 4151
```
