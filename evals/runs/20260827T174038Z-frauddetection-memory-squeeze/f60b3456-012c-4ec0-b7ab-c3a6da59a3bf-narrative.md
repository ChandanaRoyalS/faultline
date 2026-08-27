# frauddetectionservice restart loop following a container memory limit reduction

## What the alert showed

The page named a single service, frauddetectionservice, at critical severity, with an incident timestamp of 17:46:45. Blast radius stayed at one service for the whole investigation; nothing downstream or upstream ever paged. That narrowness shaped the order of work — there was no fan-out to trace, so the first question was simply "what is wrong with this one process."

## First look: metrics, and the hole in them

The obvious opening move was a RED-style error ratio for the service off span metrics. It came back empty — not zero errors, but no series at all, across the entire 17:36–17:51 window. Crucially the denominator was missing too: no total-call counter for the service in that period.

This is worth dwelling on because it is easy to misread. An empty error series alone would be good news. An empty total-call series means the service was either serving nothing or not reporting at all. The metric family was therefore unusable as a basis for either error rate or throughput, and two hypotheses died here: that the incident would present as an error spike, and that the service was quietly healthy while a dependency misbehaved. Both require the denominator to exist.

The practical lesson for the next responder: an empty ratio is a finding, not a failed query. It sent the investigation to logs.

> Evidence `tr_7b4ae7c5d59e`:

```
<tool_result id="tr_7b4ae7c5d59e" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_7b4ae7c5d59e>
```

> Evidence `tr_b84f84a22924`:

```
<tool_result id="tr_b84f84a22924" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_b84f84a22924>
```

## Logs: the shape of the failure

The log stream told the story the metrics could not. Through roughly 17:37:45 the service was doing ordinary work — Kafka order-consumption lines with an incrementing processed counter. After that, nothing at application level for the rest of the window.

From about 17:40:56 onward the only content is a three-line JVM/agent startup sequence — tool options pickup, an OpenJDK class-data-sharing warning, an OpenTelemetry javaagent version banner — repeating at roughly sixty-second intervals, at least eight times through 17:48:54. A cycle begins at ~17:46:50, immediately after the alert timestamp. The process never reaches application output before the next cycle starts.

That pattern rules out several softer readings. An idle-but-healthy service emits one startup sequence and then goes quiet; this one restarts about once a minute. A service merely lagging or processing slowly would still be running continuously; this one is not surviving long enough to lag. And 17:46:45 is not the onset of anything — it falls inside a loop that began around 17:40:56.

Two things that looked like leads and were not: the class-data-sharing warning is a benign artifact printed on every JVM start, and the javaagent banner printing successfully each cycle means telemetry initialization is completing before the process dies. Neither is a defect. Also worth recording: there is no exception, no stack trace, and no dependency name anywhere in the returned lines. The logs implicate no code path, which is itself informative — the process is being terminated from outside, not failing inward.

> Evidence `tr_51230664f086`:

```
<tool_result id="tr_51230664f086" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-27T17:36:48.412816+00:00  Consumed record with orderId: e16c17a4-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2322
2026-08-27T17:36:48.774768+00:00  Consumed record with orderId: e1a3a8d4-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2323
2026-08-27T17:37:14.012603+00:00  Consumed record with orderId: f0aee6b0-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2324
2026-08-27T17:37:23.162204+00:00  Consumed record with orderId: f6227c8d-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2325
```

## Change history: the one thing that landed

Exactly one change touched frauddetectionservice in the fifteen-minute window: at 17:40:38Z an automated actor, platform-automation, applied a resource-limits update lowering the container memory limit to 200m. Roughly twenty seconds later the application-level output stops and the restart cycling begins.

The change log contains nothing else — no deploy or image rollout, no feature flag flip, no library or dependency bump, no application config push. Each of those was checked and each is absent. The complementary hypothesis, that nothing changed locally and the trouble originated elsewhere, is also excluded: something did change here.

The record does not capture the prior limit value, so the size of the reduction is unknown from this evidence.

> Evidence `tr_20bb2395825f`:

```
<tool_result id="tr_20bb2395825f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-27T17:40:38.695607+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_20bb2395825f>
```

## The dead end worth keeping: traces looked fine

Traces were sampled expecting to find the failure, and instead argued against it. frauddetectionservice appears only as an asynchronous consumer span on the orders topic — never as the server side of a synchronous call, and no client span from any service targets it directly. In every complete checkout trace sampled, the chain checkoutservice 'orders send' → accountingservice 'orders receive' → frauddetectionservice 'orders process' was present and intact. The consumer spans complete in well under a millisecond with no error markers, no retries, no long tail. End-to-end checkout latency of roughly 25–43ms is dominated by the shipping quote path, nothing fraud-related.

This killed four plausible framings at once: callers hitting connection refusals (nobody connects directly), timeouts (sub-millisecond spans), spans silently vanishing (they are present throughout), and fraud being a synchronous blocker in the PlaceOrder path (it is not in that path at all). It also appears to contradict a total outage across 17:40–17:50.

Do not skip past this. The trace evidence and the log evidence disagree, and the disagreement was never resolved — see the open items below. A responder who reads only the traces will conclude the service is healthy.

One further loose thread from the same sample: trace 923ba06e89d3ae48 shows a checkoutservice CurrencyService/Convert client span with no matching currencyservice server span, unlike its siblings. It was judged unrelated to this incident and not pursued.

> Evidence `tr_01d14b6e534d`:

```
<tool_result id="tr_01d14b6e534d" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
service: frauddetectionservice
200 spans
  49463cdd7120c316 emailservice/sinatra.render_template 0.1ms
  49463cdd7120c316 emailservice/sinatra.render_template 0.0ms
  49463cdd7120c316 checkoutservice/orders send 0.5ms
```

## Where the evidence lands

The reading that fits most of the record: the new 200m ceiling sits below what the JVM's committed heap needs. The process starts, the agent loads, the heap grows into its configured size, the kernel terminates it, and the supervisor relaunches it — a roughly sixty-second cycle that never gets far enough to resume consuming from the orders topic. The absent span-metric series follow from the same mechanism: a container that keeps dying between scrapes reports neither successful nor errored calls. The limit edit is how it started; running out of memory is what is happening.

Confidence is medium, not high, and the reason is stated plainly in the next section. Fix class is a configuration revert.

> Evidence `tr_20bb2395825f`:

```
<tool_result id="tr_20bb2395825f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-27T17:40:38.695607+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_20bb2395825f>
```

> Evidence `tr_51230664f086`:

```
<tool_result id="tr_51230664f086" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-27T17:36:48.412816+00:00  Consumed record with orderId: e16c17a4-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2322
2026-08-27T17:36:48.774768+00:00  Consumed record with orderId: e1a3a8d4-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2323
2026-08-27T17:37:14.012603+00:00  Consumed record with orderId: f0aee6b0-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2324
2026-08-27T17:37:23.162204+00:00  Consumed record with orderId: f6227c8d-a23d-11f1-b0f0-0a04ae95d871, and updated total count to: 2325
```

> Evidence `tr_b84f84a22924`:

```
<tool_result id="tr_b84f84a22924" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_b84f84a22924>
```

## Open questions and what to check first

The kill was never directly observed. No memory working-set, container memory limit, kill-counter, or pod restart series was queried at any point — the only metric touched was the call-based error ratio. The mechanism is inferred from the restart signature and the twenty-second gap after the change. First action for anyone reopening this: pull container_memory_working_set and kube_pod_container_status_last_terminated_reason for the pod. That single check either confirms or refutes the whole conclusion.

The prior limit value is not recorded, so it is unknown whether 200m is merely tight or drastically undersized relative to the JVM's heap settings. That value determines what a revert should restore to, and it needs to be recovered before reverting.

The trace/log contradiction is unresolved. Traces show unbroken consumer spans; logs show no consumption after ~17:37:45 and a continuous restart loop. Three explanations were floated and none tested: the sampled traces may predate 17:40, there may be multiple replicas with only some affected, or the consumer may briefly drain between restarts. Check the replica count and the timestamps on the sampled traces first — the multi-replica explanation would reconcile everything cheaply.

It is also not settled which side of the mismatch is wrong. 200m may be correct policy with the JVM's -Xmx being the offending setting, in which case raising the limit is the wrong repair and lowering the heap configuration is the right one.

Finally, the change came from an automated actor. Whether that automation will re-apply the same limit after a manual revert — i.e. whether its input needs correcting rather than its output — was not investigated. Assume a manual revert may not hold.

> Evidence `tr_b84f84a22924`:

```
<tool_result id="tr_b84f84a22924" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_b84f84a22924>
```

> Evidence `tr_20bb2395825f`:

```
<tool_result id="tr_20bb2395825f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-27T17:40:38.695607+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_20bb2395825f>
```

> Evidence `tr_01d14b6e534d`:

```
<tool_result id="tr_01d14b6e534d" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T17:36:45.583000+00:00..2026-08-27T17:51:45.583000+00:00">
service: frauddetectionservice
200 spans
  49463cdd7120c316 emailservice/sinatra.render_template 0.1ms
  49463cdd7120c316 emailservice/sinatra.render_template 0.0ms
  49463cdd7120c316 checkoutservice/orders send 0.5ms
```
