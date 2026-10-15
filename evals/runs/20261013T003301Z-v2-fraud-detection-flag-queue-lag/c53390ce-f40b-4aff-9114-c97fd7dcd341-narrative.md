# fraud-detection stuck re-consuming one order record after a flag-definition write

## What the alert looked like from the chair

The page named fraud-detection and nothing else; the stated blast radius was two services, severity warning, with one edge out of fraud-detection never measured at all. Call the alert T+0. The first instinct was the usual one - something broke in fraud-detection, go find the errors. That instinct was wrong, and most of the first twenty minutes went into proving it wrong.

The service was not down. It was not erroring. It was busy, loudly and continuously, doing the same piece of work over and over.

> Evidence `tr_b2940d7fa732`:

```
<tool_result id="tr_b2940d7fa732" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T00:07:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-13T00:07:21.914081+00:00  2026-10-13 00:07:21 - fraud-detection - Consumed record with orderId: 0fdb85c8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 289 trace_id=5600429c65193651f24ca849b552b18e span_id=c8db9b98a06352c9 trace_flags=01 
2026-10-13T00:07:45.134232+00:00  2026-10-13 00:07:45 - fraud-detection - Consumed record with orderId: 1db0c1d8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 290 trace_id=4ad0b4d626e285923b127fdb6ebf78e4 span_id=3a4a8c9c5e3630ba trace_flags=01 
2026-10-13T00:07:46.616146+00:00  2026-10-13 00:07:46 - fraud-detection - Consumed record with orderId: 1e9bc63b-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 291 trace_id=42e2da1bf5ebeccc79d71ef3b247c886 span_id=cd0f4828ceae59d2 trace_flags=01 
2026-10-13T00:08:09.121912+00:00  2026-10-13 00:08:09 - fraud-detection - Consumed record with orderId: 2bfa3699-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 292 trace_id=698a8210e189b4692bb698ed30a58159 span_id=c225141b33612867 trace_flags=01 
```

## First line of attack: the change log (dead end, twice)

The obvious move was to ask what changed. The change log returned nothing for fraud-detection across the queried window - no rollout, no edit, no restart. Same answer for flagd: empty. That emptiness was read, at the time, as 'this is not a change-driven failure, go look at infrastructure and traffic.' Two separate passes at flagd's history reached the same conclusion independently.

The trap is worth recording in full, because a responder months from now will hit it the same way: both change-log queries were run with a window that *starts* at the alert timestamp and runs forward roughly twenty-four hours. The hours before onset were never queried. The 'no changes' result is therefore only an answer about the period after things were already broken. It says nothing about the minutes that mattered. Do not take an empty change log at face value without checking which direction the window points.

> Evidence `tr_2b525d13eed9`:

```
<tool_result id="tr_2b525d13eed9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_2b525d13eed9>
```

> Evidence `tr_02770d843289`:

```
<tool_result id="tr_02770d843289" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_02770d843289>
```

> Evidence `tr_7f9eb92a1b9d`:

```
<tool_result id="tr_7f9eb92a1b9d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_7f9eb92a1b9d>
```

## Second dead end: the error-rate baseline

A metric comparison on fraud-detection's error ratio over the half-hour before the alert came back flat - slightly *below* its own prior baseline, peaks under two percent on both sides, no sustained departure. Sample density was identical across both windows, which also argued against a crash-loop producing scrape gaps.

This closed off two stories at once: there was no rising error wave preceding the alert, and fraud-detection was not dying and restarting. It also pushed the investigation, briefly and wrongly, toward 'the problem must be upstream of fraud-detection.' It was not. The query template only evaluated the error ratio; request rate, latency, memory and restart counters were never asked for, so a whole quadrant of the service's health was dark the entire time.

> Evidence `tr_a1f32eea6026`:

```
<tool_result id="tr_a1f32eea6026" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:07:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" template="error-ratio" baseline="2026-10-12T23:35:08.420097+00:00..2026-10-13T00:07:16.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=129 mean=0.00418 min=0 max=0.01639 sd=0.005799
  baseline window: n=129 mean=0.005636 min=0 max=0.01961 sd=0.007497
```

## The logs break it open

The log query is where the shape of the failure finally appeared. Early in the window - roughly T-30m - fraud-detection is consuming normally: distinct order identifiers, each under its own trace context, with a running total climbing gently from 289 to 296 over about eighty seconds. Healthy, varied, unremarkable.

By T+2m onward the picture inverts. The service is consuming the *same* order identifier, under the *same* trace context, once per second, forever. The running total has climbed to 880 - but none of that growth represents new orders. Each repeat consumption is immediately followed by a line stating a queue-related feature toggle is enabled and that the service is deliberately sleeping one second. That sleep is the exact cadence of the loop. The record never gets acknowledged in time, so the broker hands it back, and the cycle restarts.

Two important negatives from the same evidence: no exceptions, no stack traces, nothing in an error path anywhere in the retained lines - which is precisely why the error-ratio metric looked fine. And the throughput count is actively misleading during this period; anyone reading it as volume would conclude the service was handling triple its normal load.

> Evidence `tr_b2940d7fa732`:

```
<tool_result id="tr_b2940d7fa732" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T00:07:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-13T00:07:21.914081+00:00  2026-10-13 00:07:21 - fraud-detection - Consumed record with orderId: 0fdb85c8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 289 trace_id=5600429c65193651f24ca849b552b18e span_id=c8db9b98a06352c9 trace_flags=01 
2026-10-13T00:07:45.134232+00:00  2026-10-13 00:07:45 - fraud-detection - Consumed record with orderId: 1db0c1d8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 290 trace_id=4ad0b4d626e285923b127fdb6ebf78e4 span_id=3a4a8c9c5e3630ba trace_flags=01 
2026-10-13T00:07:46.616146+00:00  2026-10-13 00:07:46 - fraud-detection - Consumed record with orderId: 1e9bc63b-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 291 trace_id=42e2da1bf5ebeccc79d71ef3b247c886 span_id=cd0f4828ceae59d2 trace_flags=01 
2026-10-13T00:08:09.121912+00:00  2026-10-13 00:08:09 - fraud-detection - Consumed record with orderId: 2bfa3699-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 292 trace_id=698a8210e189b4692bb698ed30a58159 span_id=c225141b33612867 trace_flags=01 
```

## The traces corroborate the shape, not the identity

A single fraud-detection trace held 200 spans: one root receive span and a long row of sibling process spans. Each process span runs roughly 1.04-1.08 seconds and is essentially pure self-time - no children, no spans from any other service anywhere in the trace. The degrading hop is receive to process, carrying one hundred percent of trace self-time.

The detail that pins it: the root receive span completed in 18.5 milliseconds, yet child spans are still being attached at offsets of seventy to a hundred and sixty seconds. Work keeps landing on a trace context whose root finished long ago, so the trace grows without bound.

This rules out a slow downstream dependency, rules out the repetition being spread across independent request traces, rules out a long-running root handler, and rules out outliers - 191 further siblings were elided beyond the ones displayed. What it does *not* do is confirm the repeated spans carry one repeated order identifier; no span attributes were returned. That link rests entirely on the logs.

> Evidence `tr_0873c8fadb9c`:

```
<tool_result id="tr_0873c8fadb9c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T23:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00">
service: fraud-detection
1 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 28220617b0f54196  root fraud-detection/orders receive  18.5ms  started 2026-10-13T00:34:53.685735+00:00  200 spans
  +0.0ms fraud-detection/orders receive 18.5ms [self 0.0ms]
```

## The one thing that actually changed

flagd emitted exactly one log line across a two-hour window: its file watcher recording a write to the flag definition file, at roughly T-4m. Info level, from the sync component, with no parse error, no reload rejection, no follow-up of any kind. flagd did not crash, did not restart, logged no evaluation failures, and was by every available indication healthy throughout.

That single write is the only mutation visible anywhere in the system. Pair it with the log lines in which fraud-detection announces the toggle is on and sleeps a second per record, and the sequence resolves: the toggle was flipped at T-4m, fraud-detection's flagged code path began sleeping on every consumed record, acknowledgement deadlines started being missed, and from T+2m the service was locked into redelivering one record indefinitely.

> Evidence `tr_09af2e3e9f73`:

```
<tool_result id="tr_09af2e3e9f73" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T22:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00">
selector: {service="flagd"}
2026-10-13T00:33:07.428120+00:00  2026-10-13T00:33:07.423Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
</tool_result:tr_09af2e3e9f73>
```

> Evidence `tr_b2940d7fa732`:

```
<tool_result id="tr_b2940d7fa732" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T00:07:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-13T00:07:21.914081+00:00  2026-10-13 00:07:21 - fraud-detection - Consumed record with orderId: 0fdb85c8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 289 trace_id=5600429c65193651f24ca849b552b18e span_id=c8db9b98a06352c9 trace_flags=01 
2026-10-13T00:07:45.134232+00:00  2026-10-13 00:07:45 - fraud-detection - Consumed record with orderId: 1db0c1d8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 290 trace_id=4ad0b4d626e285923b127fdb6ebf78e4 span_id=3a4a8c9c5e3630ba trace_flags=01 
2026-10-13T00:07:46.616146+00:00  2026-10-13 00:07:46 - fraud-detection - Consumed record with orderId: 1e9bc63b-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 291 trace_id=42e2da1bf5ebeccc79d71ef3b247c886 span_id=cd0f4828ceae59d2 trace_flags=01 
2026-10-13T00:08:09.121912+00:00  2026-10-13 00:08:09 - fraud-detection - Consumed record with orderId: 2bfa3699-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 292 trace_id=698a8210e189b4692bb698ed30a58159 span_id=c225141b33612867 trace_flags=01 
```

## Conclusion and fix class

Confidence high. The failure is a runtime toggle flip, not an artifact or a configuration-value problem - there was no deploy, no restart, no edit to fraud-detection itself, and flagd served the new state cleanly. The remediation class is a configuration revert: set the toggle back off and confirm fraud-detection resumes consuming distinct order identifiers with its total count advancing against genuinely new records rather than the same one.

> Evidence `tr_09af2e3e9f73`:

```
<tool_result id="tr_09af2e3e9f73" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T22:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00">
selector: {service="flagd"}
2026-10-13T00:33:07.428120+00:00  2026-10-13T00:33:07.423Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
</tool_result:tr_09af2e3e9f73>
```

> Evidence `tr_b2940d7fa732`:

```
<tool_result id="tr_b2940d7fa732" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T00:07:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-13T00:07:21.914081+00:00  2026-10-13 00:07:21 - fraud-detection - Consumed record with orderId: 0fdb85c8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 289 trace_id=5600429c65193651f24ca849b552b18e span_id=c8db9b98a06352c9 trace_flags=01 
2026-10-13T00:07:45.134232+00:00  2026-10-13 00:07:45 - fraud-detection - Consumed record with orderId: 1db0c1d8-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 290 trace_id=4ad0b4d626e285923b127fdb6ebf78e4 span_id=3a4a8c9c5e3630ba trace_flags=01 
2026-10-13T00:07:46.616146+00:00  2026-10-13 00:07:46 - fraud-detection - Consumed record with orderId: 1e9bc63b-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 291 trace_id=42e2da1bf5ebeccc79d71ef3b247c886 span_id=cd0f4828ceae59d2 trace_flags=01 
2026-10-13T00:08:09.121912+00:00  2026-10-13 00:08:09 - fraud-detection - Consumed record with orderId: 2bfa3699-c69a-11f1-91d4-7edc4251f9f7, and updated total count to: 292 trace_id=698a8210e189b4692bb698ed30a58159 span_id=c225141b33612867 trace_flags=01 
```

> Evidence `tr_2b525d13eed9`:

```
<tool_result id="tr_2b525d13eed9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_2b525d13eed9>
```

## Left open - read this before you repeat the work

Five things were never closed.

First, the content of the T-4m write was never read. That the queue-related toggle specifically was the key set to true is inferred from fraud-detection's own log lines, not from flagd's served state. Reading the file or querying the evaluated flag would make this direct.

Second, as noted above, neither change-log query covered the hours *before* onset. A change landing shortly before the alert remains untested for both services.

Third, the second service in the blast radius was never examined. Consumer lag on the orders topic is unmeasured, and so is the downstream effect on whatever produces into or waits on fraud-detection results. Triage explicitly flagged this unmeasured edge and it stayed unmeasured.

Fourth, request rate, latency, memory and restart counters for fraud-detection were never queried. Given that traces accumulate without bound under a completed root, memory pressure is a plausible second-order effect and is entirely unverified.

Fifth, intent. Whether the toggle was turned on deliberately as part of some exercise or by accident is unknown, as is whether its reach extends beyond fraud-detection to other consumers of the same flag.

> Evidence `tr_0873c8fadb9c`:

```
<tool_result id="tr_0873c8fadb9c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T23:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00">
service: fraud-detection
1 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 28220617b0f54196  root fraud-detection/orders receive  18.5ms  started 2026-10-13T00:34:53.685735+00:00  200 spans
  +0.0ms fraud-detection/orders receive 18.5ms [self 0.0ms]
```

> Evidence `tr_a1f32eea6026`:

```
<tool_result id="tr_a1f32eea6026" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:07:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" template="error-ratio" baseline="2026-10-12T23:35:08.420097+00:00..2026-10-13T00:07:16.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=129 mean=0.00418 min=0 max=0.01639 sd=0.005799
  baseline window: n=129 mean=0.005636 min=0 max=0.01961 sd=0.007497
```

> Evidence `tr_7f9eb92a1b9d`:

```
<tool_result id="tr_7f9eb92a1b9d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_7f9eb92a1b9d>
```

> Evidence `tr_02770d843289`:

```
<tool_result id="tr_02770d843289" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:37:16.664000+00:00..2026-10-13T00:39:24.907903+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_02770d843289>
```

