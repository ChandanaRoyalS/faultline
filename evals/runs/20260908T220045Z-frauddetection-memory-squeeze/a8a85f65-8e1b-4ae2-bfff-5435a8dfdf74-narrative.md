# frauddetectionservice goes silent minutes after an automated memory-limit change

## What the responder saw first

The page named exactly one service: frauddetectionservice. Severity critical, blast radius one service, and no unmeasured edges crossed on the way in — so from the first minute this looked local rather than a spreading problem. The alert's point of interest sits at T+0. The first instinct was to look for the usual shape of a critical single-service page: errors, timeouts, or a latency ramp. None of those turned up. What eventually explained the page was the opposite of error output — it was the absence of any output at all, beginning roughly six minutes before the alert fired.

## Logs: a clean stop, not a crash

The most informative single pull was the raw log stream for frauddetection-service across the half hour before the alert. Every retained line is a routine Kafka order-consumption record with a running counter that advances monotonically to 1508. Cadence is a record every few seconds, no gaps, no resets, healthy from the oldest retained lines at roughly T-26m all the way to T-6m. Then it stops. The newest line in the window is at T-6m (22:00:48 wall clock) and there is nothing for the remaining eight minutes of the window.

Because the query keeps the newest lines in the window, the emptiness of the tail is meaningful rather than an artefact of truncation: the service genuinely emitted nothing after that moment. Crucially, there is no error, no exception, no stack trace, no out-of-memory line, no broker-unreachable or DNS complaint preceding the silence. That combination — perfect health, then nothing — is what steered the investigation away from application-level breakage and toward the process itself no longer being there.

> Evidence `tr_6aa7098319b9`:

```
<tool_result id="tr_6aa7098319b9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-08T21:40:37.399659+00:00  Consumed record with orderId: edee395d-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1333
2026-09-08T21:40:41.873267+00:00  Consumed record with orderId: f09a1b8a-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1334
2026-09-08T21:40:49.044261+00:00  Consumed record with orderId: f4df84e8-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1335
2026-09-08T21:40:59.857147+00:00  Consumed record with orderId: fb51dce2-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1336
```

## The change that lines up

The change log for the service in the window contains exactly three entries, all of them memory-limit mutations, all attributed to the same automated actor rather than a human release. The relevant one landed approximately five minutes before the alert — essentially coincident with the log cutoff — and moved the container from no explicit memory limit to a 200m limit.

The history around it is the part worth remembering. The identical reduction had been applied once before, roughly 15.9 hours earlier, and reverted about 15.7 hours earlier. So the constraint was not long-standing; it was reintroduced minutes before onset by automation that had already backed it out once. That prior revert is the strongest circumstantial argument that 200m is below the container's steady-state working set and that the limit is known-unsurvivable in this environment.

The most coherent reading: the reapplied limit took effect, the process exceeded it almost immediately, and it was terminated — which is why the failure mode is loss of output rather than error output. Confidence is medium, not high, for reasons set out below. The fix class is a revert of the change.

> Evidence `tr_c4ec650eee6e`:

```
<tool_result id="tr_c4ec650eee6e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T22:06:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  5m before onset  2026-09-08T22:00:50.045471+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  15.7h before onset  2026-09-08T06:23:05.012220+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_6aa7098319b9`:

```
<tool_result id="tr_6aa7098319b9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-08T21:40:37.399659+00:00  Consumed record with orderId: edee395d-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1333
2026-09-08T21:40:41.873267+00:00  Consumed record with orderId: f09a1b8a-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1334
2026-09-08T21:40:49.044261+00:00  Consumed record with orderId: f4df84e8-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1335
2026-09-08T21:40:59.857147+00:00  Consumed record with orderId: fb51dce2-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1336
```

## Why nothing user-facing broke

Traces settled the question of blast radius and explain why only one service alerted. frauddetectionservice appears in these traces solely as a single messaging-consumer span ('orders process'), always a child of a checkoutservice producer span, with an accountingservice consumer as sibling. It is an async fan-out consumer, not a synchronous callee. The producer span completes in under about 1.1ms independent of the consumer, and the root PlaceOrder trace succeeds regardless. A fraud outage therefore shows up as missing consumer spans, never as caller errors or timeouts.

The consumer spans immediately before the cutoff are flat at roughly 0.1–0.2ms with no error markers — no ramp, no creep. The stop was abrupt. The practical consequence is that the outage is contained to fraud checks going unprocessed; checkout continued to work for users.

> Evidence `tr_2ef732b65192`:

```
<tool_result id="tr_2ef732b65192" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00">
service: frauddetectionservice
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 5c610f291a46cdfe  root frontend/HTTP POST  25.6ms  started 2026-09-08T21:49:45.788013+00:00  42 spans
  +0.0ms frontend/HTTP POST 25.6ms [self 0.0ms]
```

## Dead ends worth keeping

Metrics were the biggest time sink and contributed nothing. The error-ratio query against calls_total for this service name returned no samples at all — not in the alert window, and not in the preceding baseline window either. Because the denominator is also empty, there is no call-derived traffic signal for this service under that name for roughly an hour spanning onset. It is tempting to read the empty series as evidence the container was killed; that reading is wrong, because the baseline before the suspected kill is equally empty. The absence predates the event and cannot be attributed to it. Whether this is a service-name/telemetry gap or genuinely absent instrumentation was never determined, and it leaves the alert's own trigger signal unexplained.

Second dead end: a code deploy or new service version. The change log contains no deploy or release event in the window. Third: a flag flip or application config change — no such entries either, only the memory-limit class. Fourth: 'nothing changed locally, look upstream' — a change did land on the service itself minutes before onset, so that premise fails. Fifth: a slow leak under a long-standing constraint — the limit had been reverted and was only minutes old.

Sixth, and worth flagging for anyone chasing latency: four of the five rendered traces flag shippingservice's HTTP client into quoteservice/getquote as the degrading hop, consuming 19–23% of trace self-time. That is not the fraud path and appears to be unrelated background behaviour. It was not investigated.

> Evidence `tr_2c74fe8b5805`:

```
<tool_result id="tr_2c74fe8b5805" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" template="error-ratio" baseline="2026-09-08T21:04:47.122325+00:00..2026-09-08T21:36:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_229206830158`:

```
<tool_result id="tr_229206830158" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" template="error-ratio" baseline="2026-09-08T21:04:47.122325+00:00..2026-09-08T21:36:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_c4ec650eee6e`:

```
<tool_result id="tr_c4ec650eee6e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T22:06:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  5m before onset  2026-09-08T22:00:50.045471+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  15.7h before onset  2026-09-08T06:23:05.012220+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_2ef732b65192`:

```
<tool_result id="tr_2ef732b65192" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00">
service: frauddetectionservice
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 5c610f291a46cdfe  root frontend/HTTP POST  25.6ms  started 2026-09-08T21:49:45.788013+00:00  42 spans
  +0.0ms frontend/HTTP POST 25.6ms [self 0.0ms]
```

## What was never confirmed

No container-level evidence was retrieved at any point. Working-set bytes against the 200m limit, restart-counter increments, and container termination reasons were not queried. The termination is inferred entirely from timing and silence; it is not confirmed. Anyone reopening this should start there — it is a single query away from turning medium confidence into high.

A nagging ordering problem: log silence begins at 22:00:48, marginally *before* the recorded change timestamp of 22:00:50. Clock skew, change-record lag, and genuine precedence are all live explanations, and they are not equivalent — if the silence truly preceded the limit landing, the causal story inverts.

Also unresolved: whether upstream checkoutservice kept producing order records past the cutoff. If production stopped, the consumer's silence is a downstream artefact rather than a local termination, and nobody checked. The trace evidence cannot help here — only 5 of 10 matching traces rendered, the result is marked truncated, and all five displayed traces predate the cutoff, so traces cannot independently confirm the cutoff moment or the absence of activity after it. One of those five (the latest, at roughly T-14m) is oddly shaped: no producer span and no shipping/quote leg, with checkout self-time concentrated in cart-and-quote preparation. Unexplained, possibly unrelated.

Finally, the operational gap: nobody established why the automation reapplied a limit it had already backed out 15.7 hours earlier. Until that is understood, a revert can be undone again by the same actor.

> Evidence `tr_229206830158`:

```
<tool_result id="tr_229206830158" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" template="error-ratio" baseline="2026-09-08T21:04:47.122325+00:00..2026-09-08T21:36:45.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_6aa7098319b9`:

```
<tool_result id="tr_6aa7098319b9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-08T21:40:37.399659+00:00  Consumed record with orderId: edee395d-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1333
2026-09-08T21:40:41.873267+00:00  Consumed record with orderId: f09a1b8a-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1334
2026-09-08T21:40:49.044261+00:00  Consumed record with orderId: f4df84e8-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1335
2026-09-08T21:40:59.857147+00:00  Consumed record with orderId: fb51dce2-abcd-11f1-bd05-f22ce56931b9, and updated total count to: 1336
```

> Evidence `tr_c4ec650eee6e`:

```
<tool_result id="tr_c4ec650eee6e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T22:06:45.583000+00:00..2026-09-08T22:08:44.043675+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  5m before onset  2026-09-08T22:00:50.045471+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  15.7h before onset  2026-09-08T06:23:05.012220+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_2ef732b65192`:

```
<tool_result id="tr_2ef732b65192" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T21:36:45.583000+00:00..2026-09-08T22:08:44.043675+00:00">
service: frauddetectionservice
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 5c610f291a46cdfe  root frontend/HTTP POST  25.6ms  started 2026-09-08T21:49:45.788013+00:00  42 spans
  +0.0ms frontend/HTTP POST 25.6ms [self 0.0ms]
```

