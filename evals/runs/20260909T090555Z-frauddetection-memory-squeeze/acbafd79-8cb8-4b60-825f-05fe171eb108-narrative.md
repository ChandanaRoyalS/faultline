# Fraud detection consumer goes silent after a memory ceiling is lowered

## What the page said

A single alert fired on frauddetectionservice. Blast radius stayed at one service, severity critical, and no unmeasured edges were crossed on the way to it — so from the first minute this looked like a local problem rather than something arriving from a neighbour. I set T+0 at the alert. Nothing else in the checkout path paged, which is worth holding onto: it shaped every wrong turn described below.

## First instinct: look at the service's error rate (dead end)

The reflex move was to compare frauddetectionservice error ratio against a baseline. It came back with no samples at all — not zeros, no samples. I briefly read that as the symptom itself, i.e. telemetry cutting out as the service died. That reading is wrong, and I want the next responder to skip the detour: the same query is equally empty across a six-hour baseline window and again across the hour before onset. The call-count series simply does not exist under this service name (uninstrumented, renamed, or not scraped). It is a standing collection gap, not an incident artefact. No conclusion about error rate, request rate, or clean operation can be drawn from it in either direction.

> Evidence `tr_db71023b261e`:

```
<tool_result id="tr_db71023b261e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T09:12:00.583000+00:00..2026-09-08T15:12:00.583000+00:00" template="error-ratio" baseline="2026-09-08T03:12:00.583000+00:00..2026-09-08T09:12:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_884eb4f3a7cf`:

```
<tool_result id="tr_884eb4f3a7cf" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T08:12:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" template="error-ratio" baseline="2026-09-09T07:10:04.570263+00:00..2026-09-09T08:12:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The service's own log stream: an abrupt stop, no complaint

The logs were where the shape of the failure finally appeared. Every line in the window is the same routine order-consumption message carrying a running counter, climbing monotonically from 476 through 633. No warnings, no exceptions, no stack traces, and — importantly — no startup or initialisation banner anywhere. Pacing stays a few seconds apart right up to roughly T-6m, and then output ceases completely for the remaining ~8 minutes to the end of the window.

Two hypotheses died here. First, that the service logged an explicit error naming a failing dependency: there is no error text at all, because there is no text at all after the stop. Second, that it restarted or crash-looped: the counter never resets, which is inconsistent with a fresh process across the observed spans. Third, that it was degraded but still limping: the stop is a cliff, not a taper.

One caveat to carry forward: this result is truncated to the oldest handful and newest few dozen lines, so roughly a twenty-minute stretch mid-window is unobserved. If there was an early pressure signal, it would be hiding there.

> Evidence `tr_f2e43c376c06`:

```
<tool_result id="tr_f2e43c376c06" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:42:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T08:42:04.667385+00:00  Consumed record with orderId: 5563eab6-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 476
2026-09-09T08:42:09.980151+00:00  Consumed record with orderId: 588ecd00-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 477
2026-09-09T08:42:15.374486+00:00  Consumed record with orderId: 5bc6262d-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 478
2026-09-09T08:42:17.689535+00:00  Consumed record with orderId: 5d273513-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 479
```

## Corroboration from outside: traces

Traces told the same story from the caller's side. frauddetectionservice appears only as a single messaging-consumer span ('orders process'), fanned out from the checkoutservice publish alongside accountingservice. Every one of those spans is sub-millisecond with no children and no error marker — normal, fast consumption. The last trace containing it starts around T-8m; the final trace in the set, roughly T-7m, is a much smaller checkout/cart tree with no fraud span in the fan-out at all.

This is the point where I ruled out the tempting story that the whole checkout pipeline had stopped: checkout traffic is still producing traces after the last fraud span. It also killed the idea that fraud detection was the source of checkout latency or was propagating errors back — it sits off the critical path as an async consumer, and the parent publish completes in under a millisecond regardless. Note for the record: the recurring slow hop in these traces is shipping's HTTP call to quote, eating 19-26% of trace self-time. It is real, it is unexplained, and it has nothing to do with this alert. Do not let it pull you sideways.

> Evidence `tr_ddde08b71ab1`:

```
<tool_result id="tr_ddde08b71ab1" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-09T08:42:00.583000+00:00..2026-09-09T09:13:56.595737+00:00">
service: frauddetectionservice
6 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 13cccc578d9d0296  root frontend/HTTP POST  25.9ms  started 2026-09-09T09:01:44.265012+00:00  48 spans
  +0.0ms frontend/HTTP POST 25.9ms [self 0.0ms]
```

## The change history, which is where the answer was

Five recorded changes for the service in the window, all of the same type (resource limits), all by the same automated actor. Roughly T-6m, the memory limit on frauddetection-service was lowered to 200m. Two earlier instances of the identical lower-then-revert cycle appear in the window (about 11 hours and about 5 hours before onset), each with a matching revert. The T-6m reduction has no revert — it was still in force at the alert.

That pattern is what made the change credible as the cause rather than background noise. It also let me discard several alternatives cleanly: no deploy or release event is recorded, no flag or application-config edit appears, and no individual operator touched anything — every entry is the automated actor. Equally, the theory that nothing local changed and the trigger must be external does not survive: a local change landed minutes before onset and stayed.

> Evidence `tr_b8cb8d8fc042`:

```
<tool_result id="tr_b8cb8d8fc042" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T09:12:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T09:06:01.001618+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  4.9h before onset  2026-09-09T04:15:24.360103+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## Conclusion as it stood

A healthy, continuously-running consumer was abruptly terminated about a minute after its memory ceiling was lowered to 200m and, unlike the two prior cycles, left there. No slowdown, no error text, no restart banner beforehand — that is the signature of a process killed from outside rather than one that degraded or threw. The most economical reading is that 200m was below the running working set of the consumer, the container exceeded it, and was killed, ending message consumption. The mechanism is loss of memory headroom; the limit edit is how it started. Confidence: medium. Indicated remedy: revert the limit to its prior value.

> Evidence `tr_b8cb8d8fc042`:

```
<tool_result id="tr_b8cb8d8fc042" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T09:12:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T09:06:01.001618+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  4.9h before onset  2026-09-09T04:15:24.360103+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_f2e43c376c06`:

```
<tool_result id="tr_f2e43c376c06" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:42:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T08:42:04.667385+00:00  Consumed record with orderId: 5563eab6-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 476
2026-09-09T08:42:09.980151+00:00  Consumed record with orderId: 588ecd00-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 477
2026-09-09T08:42:15.374486+00:00  Consumed record with orderId: 5bc6262d-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 478
2026-09-09T08:42:17.689535+00:00  Consumed record with orderId: 5d273513-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 479
```

> Evidence `tr_ddde08b71ab1`:

```
<tool_result id="tr_ddde08b71ab1" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-09T08:42:00.583000+00:00..2026-09-09T09:13:56.595737+00:00">
service: frauddetectionservice
6 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 13cccc578d9d0296  root frontend/HTTP POST  25.9ms  started 2026-09-09T09:01:44.265012+00:00  48 spans
  +0.0ms frontend/HTTP POST 25.9ms [self 0.0ms]
```

## Still open — read this before you trust the conclusion

The kill itself was never observed. No kill event, no container memory working-set series, and no pod restart-count series was ever retrieved; the only metric result available was the empty error-ratio template. The kill is therefore inferred from timing, not seen. A kubelet-event or container-memory query would settle it in one step, and that is the first thing I would run on a repeat.

Also unresolved: the service's normal working set is unknown, so it is unproven that 200m is genuinely below requirement rather than the stop having some other cause; whether the pod restarted or looped after onset is unobserved, since the log result is truncated and ends before the stop; the ~twenty-minute log gap could contain an earlier warning; why the automation runs this recurring lower/revert cycle at all, and why this instance was not reverted, is unexplained; the shipping-to-quote hop remains a separate unexplained drag; and the downstream consequence of halted order consumption (backlog, unprocessed orders) was never measured.

> Evidence `tr_884eb4f3a7cf`:

```
<tool_result id="tr_884eb4f3a7cf" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T08:12:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" template="error-ratio" baseline="2026-09-09T07:10:04.570263+00:00..2026-09-09T08:12:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_f2e43c376c06`:

```
<tool_result id="tr_f2e43c376c06" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:42:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-09T08:42:04.667385+00:00  Consumed record with orderId: 5563eab6-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 476
2026-09-09T08:42:09.980151+00:00  Consumed record with orderId: 588ecd00-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 477
2026-09-09T08:42:15.374486+00:00  Consumed record with orderId: 5bc6262d-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 478
2026-09-09T08:42:17.689535+00:00  Consumed record with orderId: 5d273513-ac2a-11f1-b949-02b2b162ac8d, and updated total count to: 479
```

> Evidence `tr_b8cb8d8fc042`:

```
<tool_result id="tr_b8cb8d8fc042" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T09:12:00.583000+00:00..2026-09-09T09:13:56.595737+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  5m before onset  2026-09-09T09:06:01.001618+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  4.9h before onset  2026-09-09T04:15:24.360103+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_ddde08b71ab1`:

```
<tool_result id="tr_ddde08b71ab1" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-09T08:42:00.583000+00:00..2026-09-09T09:13:56.595737+00:00">
service: frauddetectionservice
6 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 13cccc578d9d0296  root frontend/HTTP POST  25.9ms  started 2026-09-09T09:01:44.265012+00:00  48 spans
  +0.0ms frontend/HTTP POST 25.9ms [self 0.0ms]
```

