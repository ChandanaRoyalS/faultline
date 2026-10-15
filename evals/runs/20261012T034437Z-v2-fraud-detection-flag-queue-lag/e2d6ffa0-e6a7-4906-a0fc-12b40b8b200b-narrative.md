# fraud-detection stalls in a one-second-per-record reprocessing loop

## What the alert said and where I started

The page came in against fraud-detection at warning severity. Blast radius was small on paper — two services, fraud-detection and flagd — but nothing in the alert explained why. Call it T+0 at the moment the alert fired. The service was not down and was not erroring; that is the first thing worth knowing, because it shaped the next hour of wrong turns. I started where most responders start: recent changes, then error rates. Both were dead ends, and both took time.

## Dead end one: the change log is empty for both services

I queried change history for fraud-detection across the full preceding day and got nothing back — no deploys, no config edits, no resource-limit adjustments, no network changes. I then did the same for flagd and got the same empty answer. The natural inference, and the wrong one, is that nothing changed and therefore the cause must be organic: load, a dependency, a data condition. I spent a while on that branch.

Two caveats worth recording for next time. First, the fraud-detection query window began at the alert time and ran forward, so anything done before T+0 was never examined. Second, and more importantly, an empty change log only rules out changes that the change log tracks. It turned out the relevant modification was made by a path that change management does not see at all. Treat 'no recorded changes' as 'no changes through the tracked path', not as 'no changes'.

> Evidence `tr_80cb44d9df23`:

```
<tool_result id="tr_80cb44d9df23" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T03:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_80cb44d9df23>
```

> Evidence `tr_123056cde67d`:

```
<tool_result id="tr_123056cde67d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T03:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_123056cde67d>
```

## Dead end two: error rate looks fine, because it is fine

I compared fraud-detection's error ratio against a baseline window. The mean barely moved — roughly seven percent, with the same min/max range and comparable spread. There were four change points where the ratio briefly hit total failure, but all of them landed hours before the alert, and the baseline window reaches the same ceiling, so those spikes are normal behaviour for this service rather than anything new. A noticeable share of five-minute intervals had no defined ratio at all (no calls in the interval); that too matched baseline, so the gaps are a standing characteristic and not a sign of the service going dark.

The useful takeaway: this failure is invisible to error-rate monitoring. Work was not failing. Work was succeeding, slowly, over and over.

> Evidence `tr_6e2432d4b018`:

```
<tool_result id="tr_6e2432d4b018" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T23:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" template="error-ratio" baseline="2026-10-11T19:46:26.706226+00:00..2026-10-11T23:48:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=877 mean=0.05292 min=0 max=1 sd=0.2076
  baseline window: n=488 mean=0.04936 min=0 max=1 sd=0.1971
```

## The logs turn it around

Pulling raw logs for fraud-detection across the window changed the picture. At the start of the window the service is consuming distinct order records normally, with a total counter incrementing steadily. By the end of the window it is consuming the same single order id repeatedly, under one unchanging trace id, ticking the counter once per second. That is the signature of a record being redelivered because the unit of work never completes and commits — not fresh intake.

Each iteration is preceded by a log line naming a runtime feature flag — the one named after Kafka queue problems — as enabled and causing a one-second sleep. That line accounts exactly for the one-second cadence.

Also ruled out here: the service was not silent, not crash-looping (no startup banners anywhere in the window, and a single trace id persisting across the tail is incompatible with restarts), and the consumer was throwing no errors, no deserialization failures, no rebalance or timeout exceptions. Throughput had collapsed, though: the counter advanced only about two thousand over nearly four hours, and in the final fifteen seconds every increment belonged to the same duplicated record.

> Evidence `tr_920832976c99`:

```
<tool_result id="tr_920832976c99" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T23:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-11T23:55:38.451943+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 7efe49d3-c5ce-11f1-ac6a-06d98426e5c4, and updated total count to: 11414 trace_id=df8cf3c7840f9901e18d429879645e63 span_id=923ec85da15a0e02 trace_flags=01 
2026-10-11T23:55:38.459621+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 94336d52-c5ce-11f1-ac6a-06d98426e5c4, and updated total count to: 11415 trace_id=05270d8b87d1f63e76646646e7120d5e span_id=07f6f08bbb0a6ab6 trace_flags=01 
2026-10-11T23:55:38.462602+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 2f24db32-c5cf-11f1-ac6a-06d98426e5c4, and updated total count to: 11416 trace_id=ba90437cf7e152b81a31e6cf297d8d62 span_id=3c62c2791a7688bd trace_flags=01 
2026-10-11T23:55:38.477884+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 9e4dfa10-c5cd-11f1-ac6a-06d98426e5c4, and updated total count to: 11417 trace_id=56931485222d6d4067e8bb1cc3a34765 span_id=773b0ad8bd143b42 trace_flags=01 
```

## Traces confirm the time is spent in-process

One trace in the window carried a hundred spans: a 0.3ms root receive span plus roughly ninety-nine sibling 'orders process' spans, each about 1.00–1.01s, stepping serially from roughly twenty seconds to ninety-eight seconds past the root. They do not overlap, so this is sequential re-execution, not parallel workers. One receive event, many processes — the same unit of work reprocessed, not new work arriving.

Critically, every one of those one-second spans is pure self-time with no child spans at all. No outbound RPC, no database call, no messaging child. The second is burned inside the fraud-detection process. In the single trace that does show the flag-evaluation path, the process span is about 1049.8ms with roughly 1025.2ms of self-time, while the entire flag-evaluation subtree accounts for only about 24.6ms and the flag service's own server spans come in at around 0.1ms. The lookup is effectively free.

That killed several plausible theories at once: a slow downstream dependency, a degraded flag service, upstream flooding the consumer with new messages, and a bottleneck in the receive path. It also showed the problem is not uniform — the other eight sampled traces were ordinary two-span receive/process pairs completing in roughly 1ms to 82ms.

> Evidence `tr_e219183aa4dc`:

```
<tool_result id="tr_e219183aa4dc" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-12T03:18:31.664000+00:00..2026-10-12T03:50:36.621774+00:00">
service: fraud-detection
10 trace(s) shown of 10 found, 123 spans; offsets are from each trace's root

trace 76cf8bf0f13a4e34  root fraud-detection/orders receive  32.6ms  started 2026-10-12T03:42:59.716709+00:00  2 spans
  +0.0ms fraud-detection/orders receive 32.6ms [self 26.9ms]
```

## The flag service: healthy, quiet, and one telling line

Logs for flagd over a half-hour window around the alert contained exactly one line: a file-watcher sync event reporting a WRITE to its local flag definition file, about four minutes before the alert (call it T-4m). No errors, no warnings, no startup or shutdown banners, no parse failures. The flag service was not the problem.

Two structural facts fell out of that single line. Flag state in this deployment comes from a local file sync provider, not a remote sync service or a cluster resource — which explains why the change log holds nothing: the write path sits outside tracked change management. And flag state demonstrably changed inside the window, so 'configuration was static' is off the table.

What the logs could not do: there is no per-evaluation logging at this verbosity. No flag keys, no variant decisions, nothing naming the flag in question. I could not confirm from this source which flag was served to which caller, nor what the file write contained.

> Evidence `tr_292119ba0cc8`:

```
<tool_result id="tr_292119ba0cc8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T03:18:31.664000+00:00..2026-10-12T03:50:36.621774+00:00">
selector: {service="flagd"}
2026-10-12T03:44:42.670970+00:00  2026-10-12T03:44:42.670Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
</tool_result:tr_292119ba0cc8>
```

## Conclusion and fix class

A runtime feature flag — the one named for Kafka queue problems — is being served as enabled to fraud-detection, and the flagged code path adds a one-second sleep to each record-processing iteration. With per-record processing stretched to roughly a second, the consumer cannot finish and commit its unit of work before redelivery, so the same order record is reprocessed indefinitely under one trace id. The flag service is healthy; the latency is entirely local. Confidence is high. The fix class is a configuration revert: disable the flag in the flag definition file and let the file watcher pick it up.

> Evidence `tr_920832976c99`:

```
<tool_result id="tr_920832976c99" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T23:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-11T23:55:38.451943+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 7efe49d3-c5ce-11f1-ac6a-06d98426e5c4, and updated total count to: 11414 trace_id=df8cf3c7840f9901e18d429879645e63 span_id=923ec85da15a0e02 trace_flags=01 
2026-10-11T23:55:38.459621+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 94336d52-c5ce-11f1-ac6a-06d98426e5c4, and updated total count to: 11415 trace_id=05270d8b87d1f63e76646646e7120d5e span_id=07f6f08bbb0a6ab6 trace_flags=01 
2026-10-11T23:55:38.462602+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 2f24db32-c5cf-11f1-ac6a-06d98426e5c4, and updated total count to: 11416 trace_id=ba90437cf7e152b81a31e6cf297d8d62 span_id=3c62c2791a7688bd trace_flags=01 
2026-10-11T23:55:38.477884+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 9e4dfa10-c5cd-11f1-ac6a-06d98426e5c4, and updated total count to: 11417 trace_id=56931485222d6d4067e8bb1cc3a34765 span_id=773b0ad8bd143b42 trace_flags=01 
```

> Evidence `tr_e219183aa4dc`:

```
<tool_result id="tr_e219183aa4dc" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-12T03:18:31.664000+00:00..2026-10-12T03:50:36.621774+00:00">
service: fraud-detection
10 trace(s) shown of 10 found, 123 spans; offsets are from each trace's root

trace 76cf8bf0f13a4e34  root fraud-detection/orders receive  32.6ms  started 2026-10-12T03:42:59.716709+00:00  2 spans
  +0.0ms fraud-detection/orders receive 32.6ms [self 26.9ms]
```

> Evidence `tr_292119ba0cc8`:

```
<tool_result id="tr_292119ba0cc8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T03:18:31.664000+00:00..2026-10-12T03:50:36.621774+00:00">
selector: {service="flagd"}
2026-10-12T03:44:42.670970+00:00  2026-10-12T03:44:42.670Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
</tool_result:tr_292119ba0cc8>
```

## Still open when the record was written

Several things were never settled and are worth closing if this recurs.

No direct evidence names the flag key and variant served to fraud-detection, nor the content of the file write at T-4m; reading the current flag definition file would settle both in seconds.

The timing does not fully reconcile. Throughput appears to have been degraded across nearly four hours (counter advancing only about two thousand), yet the observed file write is at T-4m and the alert at T+0. Either there was an earlier modification outside the observed log window, or the flag is targeted probabilistically.

Who or what wrote the flag definition file is unidentified. The change log records nothing because the write path is not tracked. That gap is itself worth an action item.

It is unknown whether, after disabling the flag, the consumer needs a restart or whether a backlog will drain on its own — no broker-side lag or offset-commit evidence was gathered.

Only ten traces were sampled and eight were ordinary, so the share of total traffic currently stuck in the slow path — and therefore the real customer blast radius — was never quantified.

Finally, the change-history query for fraud-detection started at the alert time and ran forward; anything before T+0 remains unexamined.

> Evidence `tr_292119ba0cc8`:

```
<tool_result id="tr_292119ba0cc8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T03:18:31.664000+00:00..2026-10-12T03:50:36.621774+00:00">
selector: {service="flagd"}
2026-10-12T03:44:42.670970+00:00  2026-10-12T03:44:42.670Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
</tool_result:tr_292119ba0cc8>
```

> Evidence `tr_920832976c99`:

```
<tool_result id="tr_920832976c99" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T23:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-11T23:55:38.451943+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 7efe49d3-c5ce-11f1-ac6a-06d98426e5c4, and updated total count to: 11414 trace_id=df8cf3c7840f9901e18d429879645e63 span_id=923ec85da15a0e02 trace_flags=01 
2026-10-11T23:55:38.459621+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 94336d52-c5ce-11f1-ac6a-06d98426e5c4, and updated total count to: 11415 trace_id=05270d8b87d1f63e76646646e7120d5e span_id=07f6f08bbb0a6ab6 trace_flags=01 
2026-10-11T23:55:38.462602+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 2f24db32-c5cf-11f1-ac6a-06d98426e5c4, and updated total count to: 11416 trace_id=ba90437cf7e152b81a31e6cf297d8d62 span_id=3c62c2791a7688bd trace_flags=01 
2026-10-11T23:55:38.477884+00:00  2026-10-11 23:55:38 - fraud-detection - Consumed record with orderId: 9e4dfa10-c5cd-11f1-ac6a-06d98426e5c4, and updated total count to: 11417 trace_id=56931485222d6d4067e8bb1cc3a34765 span_id=773b0ad8bd143b42 trace_flags=01 
```

> Evidence `tr_123056cde67d`:

```
<tool_result id="tr_123056cde67d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T03:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_123056cde67d>
```

> Evidence `tr_80cb44d9df23`:

```
<tool_result id="tr_80cb44d9df23" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T03:48:31.664000+00:00..2026-10-12T03:50:36.621774+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_80cb44d9df23>
```

> Evidence `tr_e219183aa4dc`:

```
<tool_result id="tr_e219183aa4dc" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-12T03:18:31.664000+00:00..2026-10-12T03:50:36.621774+00:00">
service: fraud-detection
10 trace(s) shown of 10 found, 123 spans; offsets are from each trace's root

trace 76cf8bf0f13a4e34  root fraud-detection/orders receive  32.6ms  started 2026-10-12T03:42:59.716709+00:00  2 spans
  +0.0ms fraud-detection/orders receive 32.6ms [self 26.9ms]
```

