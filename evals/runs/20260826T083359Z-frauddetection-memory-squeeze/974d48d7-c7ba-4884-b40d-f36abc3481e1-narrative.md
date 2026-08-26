# Fraud Detection Service Restart Loop Following an Automated Memory Limit Reduction

## What the responder saw first

The page came in against frauddetectionservice alone. Blast radius stayed at one service for the whole of triage; nothing else alerted and no unmeasured edges were crossed to reach it. The alert marker lands at roughly T+0 (08:40 wall clock, used here only as an anchor for the offsets below). There was no error text attached to the alert, which is worth saying plainly up front: the first instinct — go find the exception — is the first dead end, and it costs about ten minutes.

## Working backwards through the change history

The change log for the service in the surrounding window contains exactly one entry. About six minutes before the alert (T-6m), an automated actor named platform-automation lowered the container memory limit on the frauddetection-service resource to 200m. That is the whole of it — one line, one field.

Several hypotheses die here quickly and cleanly, and it is worth recording that they were checked rather than assumed. There was no code deploy or version rollout on this service in the window. No feature flag was flipped. No library or dependency version was bumped. And the opposite premise — that nothing changed locally and the cause must be external, an upstream shift or an infrastructure event — also fails, because a concrete self-inflicted change sits inside the window minutes ahead of the alert.

One detail shaped the response: the actor is automation, not a human. There was no on-call engineer to ask what they were doing, and no interactive session to correlate against. The prior limit value is not recorded either — only the new one. Both of those gaps matter later.

> Evidence `tr_91f6abb9990d`:

```
<tool_result id="tr_91f6abb9990d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-26T08:33:59.560823+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_91f6abb9990d>
```

## The logs, and what they refused to say

The log query returned a continuously populated stream through T+2m, so ingestion was healthy throughout. That rules out the tempting explanation that the logging pipeline broke and swallowed the errors. Whatever is missing from the logs is missing because the process never emitted it.

Early in the window, before the change, the service was behaving normally: steady Kafka order-consumption lines with an incrementing counter that reached 388 around T-9m. Those lines then stop. They do not degrade, thin out, or start erroring — they simply cease.

What replaces them, from roughly T-6m onward, is process-startup output: a JAVA_TOOL_OPTIONS pickup line, a benign JVM class-sharing/bootstrap-classpath warning, and the OpenTelemetry javaagent version banner. Always the same three lines, always in the same order. The group repeats at 08:35:08, 08:36:01, 08:37:04, 08:38:06, 08:39:08, 08:40:10, 08:41:12, 08:42:15 — a near-constant ~62-second cadence spanning at least eight cycles across seven minutes.

That cadence is the finding. A single restart or a rolling deploy produces one banner, or a handful; it does not produce a regular periodic sequence. The service was in a sustained crash/restart loop straight through the alert.

Two further readings were closed off. The agent is not the problem — the javaagent banner completes successfully on every single cycle, so attach is never the blocking step. And the service was not merely idle under low load; healthy idleness does not replace consumption lines with repeated JVM init.

Critically, there is no ERROR-level line and no exception text anywhere in the window, including around the alert itself. The container reaches JVM and agent initialisation each cycle and then dies before producing any post-init application logging. The failure sits after agent attach and at or before application readiness — a window in which the process has nothing to say.

> Evidence `tr_48f2dfb41dd7`:

```
<tool_result id="tr_48f2dfb41dd7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-26T08:30:08.271618+00:00  Consumed record with orderId: 589a513f-a128-11f1-930d-06da4393bc82, and updated total count to: 381
2026-08-26T08:30:22.250777+00:00  Consumed record with orderId: 60ef7c4e-a128-11f1-930d-06da4393bc82, and updated total count to: 382
2026-08-26T08:30:22.288436+00:00  Consumed record with orderId: 60f601a0-a128-11f1-930d-06da4393bc82, and updated total count to: 383
2026-08-26T08:30:30.943043+00:00  Consumed record with orderId: 661e30b8-a128-11f1-930d-06da4393bc82, and updated total count to: 384
```

## The metrics dead end

Two separate metrics dispatches were made against this service. Both ran the same thing: a span-metrics error-ratio query, error-status calls over total calls, across the fifteen minutes bracketing the alert. Both returned no matching series at all.

This is the most instructive dead end in the record, because the empty result is easy to misread in three different directions, and all three were checked and discarded. It does not mean the error ratio was elevated — there is no ratio to measure. It does not mean the service was healthy with a low error fraction — a healthy service still emits a denominator, and there was none. And it does not support any throughput claim either, because the total-call term matched nothing.

An empty numerator is ambiguous. An empty numerator *and* an empty denominator means either the service produced no spans at all in the window, or the metric family is not named or labelled the way the query assumed. The first reading is consistent with the log evidence: a container that never lives long enough past agent attach to serve a request cannot export span metrics. The second reading is the honest alternative and was never eliminated.

The larger problem: neither dispatch ever queried what the hypothesis actually needed. No container working-set bytes, no container memory limit series, no OOM-kill counter, no restart count from kube-state-metrics. The second dispatch explicitly acknowledged leaving this open. The responder should understand that the memory story below is inferred from change timing and log shape, not confirmed by memory telemetry.

> Evidence `tr_6a4a801562db`:

```
<tool_result id="tr_6a4a801562db" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_6a4a801562db>
```

> Evidence `tr_897542911029`:

```
<tool_result id="tr_897542911029" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_897542911029>
```

## Conclusion, and how much to trust it

The reconstruction: at T-6m an automated actor reduced the container memory limit to 200m. Within about a minute the service stopped emitting steady-state order-consumption lines and entered a crash/restart loop that ran on a ~62s cadence from T-5m through at least T+2m, with no application error output at any point.

The pieces fit. A process killed by the kernel for exceeding its cgroup ceiling dies without emitting an application-level error — which is exactly the silence observed. The empty call-count series is the metrics-side shadow of the same fact: the container never reaches the point of serving traffic. The timing gap of roughly one minute between the change and the loss of consumption lines is what you would expect from a limit change propagating to a pod restart.

Confidence is medium, not high. The fix class is a revert of the change. But the record should be read with the following unresolved, because a future responder facing the same shape may be able to close them in minutes with the right query.

> Evidence `tr_91f6abb9990d`:

```
<tool_result id="tr_91f6abb9990d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-26T08:33:59.560823+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_91f6abb9990d>
```

> Evidence `tr_48f2dfb41dd7`:

```
<tool_result id="tr_48f2dfb41dd7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-26T08:30:08.271618+00:00  Consumed record with orderId: 589a513f-a128-11f1-930d-06da4393bc82, and updated total count to: 381
2026-08-26T08:30:22.250777+00:00  Consumed record with orderId: 60ef7c4e-a128-11f1-930d-06da4393bc82, and updated total count to: 382
2026-08-26T08:30:22.288436+00:00  Consumed record with orderId: 60f601a0-a128-11f1-930d-06da4393bc82, and updated total count to: 383
2026-08-26T08:30:30.943043+00:00  Consumed record with orderId: 661e30b8-a128-11f1-930d-06da4393bc82, and updated total count to: 384
```

> Evidence `tr_897542911029`:

```
<tool_result id="tr_897542911029" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_897542911029>
```

## Open questions for the next responder

First and most important: no container memory telemetry was ever retrieved. Working-set bytes against the limit series, an OOM-kill counter, or a restart count would confirm or refute the memory-ceiling hypothesis directly and in one query. This should be the first thing pulled next time.

Second: the prior memory limit is not recorded, so the magnitude of the reduction is unknown. It has not actually been shown that 200m is below the JVM's configured heap plus overhead. A JAVA_TOOL_OPTIONS or -Xmx value would settle whether 200m is genuinely insufficient or whether something else is killing the process.

Third: why the automation made the change is unknown. A limit-tuning controller, a policy rollout, and a bad admission-webhook default each imply a very different scope. Triage covered only frauddetectionservice; other services may have received the same reduction and not yet alerted.

Fourth: the empty call-count series has a second candidate explanation that was flagged but never eliminated — a label or metric-name mismatch, or an absent span-metrics pipeline for this service specifically. If that is the case, the metrics evidence corroborates nothing at all and the verdict rests entirely on change timing plus log shape.

Fifth: downstream impact is unmeasured. Order consumption stopped with the counter at 388. Whether consumer lag built, whether orders went unprocessed, and whether dependent services degraded were never investigated.

> Evidence `tr_91f6abb9990d`:

```
<tool_result id="tr_91f6abb9990d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-26T08:33:59.560823+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_91f6abb9990d>
```

> Evidence `tr_6a4a801562db`:

```
<tool_result id="tr_6a4a801562db" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_6a4a801562db>
```

> Evidence `tr_897542911029`:

```
<tool_result id="tr_897542911029" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_897542911029>
```

> Evidence `tr_48f2dfb41dd7`:

```
<tool_result id="tr_48f2dfb41dd7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T08:30:00.583000+00:00..2026-08-26T08:45:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-26T08:30:08.271618+00:00  Consumed record with orderId: 589a513f-a128-11f1-930d-06da4393bc82, and updated total count to: 381
2026-08-26T08:30:22.250777+00:00  Consumed record with orderId: 60ef7c4e-a128-11f1-930d-06da4393bc82, and updated total count to: 382
2026-08-26T08:30:22.288436+00:00  Consumed record with orderId: 60f601a0-a128-11f1-930d-06da4393bc82, and updated total count to: 383
2026-08-26T08:30:30.943043+00:00  Consumed record with orderId: 661e30b8-a128-11f1-930d-06da4393bc82, and updated total count to: 384
```
