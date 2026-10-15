# fraud-detection order-consumer stalled at one record per second by an enabled runtime flag

## What was visible, in order

The page named fraud-detection alone; warning severity, two services in the declared radius, one edge out of fraud-detection never measured.

The first move (~T+3m) was an error-ratio baseline. It looked promising: mean error ratio roughly doubled (0.0266 to 0.0485), variance up, five discrete change points reaching 1.0 before recovering, and 124 intervals with no defined ratio against 4 in the baseline. It did kill two ideas cleanly — this was not a sustained hard outage (mean under 5%, recovery between episodes) and not a previously-clean service (baseline already touched 1.0, so the change was frequency, not kind) — and the step pattern argued against slow resource starvation. But keep the caveat: that metrics window does not overlap the window where the actual behaviour was later seen, roughly a day apart. Those five episodes cannot be attributed to the cause below. Also, only the error-ratio template evaluated; latency, throughput, memory, CPU and restart counters were requested and never returned.

Raw logs (~T+12m) made the behaviour legible. Early in the window: routine consumption, distinct orderIds, no flag lines. Late in the window: every consumption line paired with a line reporting `kafkaQueueProblems` enabled and a one-second handler sleep, a flat ~1 record/second cadence, and the same orderId consumed repeatedly under one constant trace_id with the counter ticking up — the delay preventing offset commit, so the broker redelivers. Absences mattered: no stack traces, no rebalance or partition-revocation lines, no heap/OOM, no restart signature, no flag-evaluation errors. Crash loop, rebalance storm, memory pressure and flag-client timeout all fall away; the problem is the flag's value, not the client's health.

A filtered re-query (~T+20m) placed first appearance about 26 minutes into a 32-minute window, with nothing before it and no cessation by window close. Caveat: results were truncated to oldest 8 and newest 32 lines, so a gap in the middle ~5 minutes cannot be excluded.

Traces (~T+26m) settled it. One trace carried 200 spans: a sub-millisecond root receive and many repeated `orders process` children at ~1.004–1.009s each, almost entirely self-time, with no outbound child spans. That disposes of a slow downstream dependency (there is no downstream call to be slow), of ingress latency, and of queue-depth-driven degradation (durations flat across spans separated by minutes). Only 10 traces in the window, so the span volume is repetition, not request flood.

> Evidence `tr_edbf05bf6eb3`:

```
<tool_result id="tr_edbf05bf6eb3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T20:57:31.664000+00:00..2026-10-14T02:57:31.664000+00:00" template="error-ratio" baseline="2026-10-13T14:57:31.664000+00:00..2026-10-13T20:57:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=1300 mean=0.04848 min=0 max=1 sd=0.195
  baseline window: n=750 mean=0.02656 min=0 max=1 sd=0.144
```

> Evidence `tr_b2161a5c6c9a`:

```
<tool_result id="tr_b2161a5c6c9a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T19:57:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-14T19:57:40.560795+00:00  2026-10-14 19:57:40 - fraud-detection - Consumed record with orderId: 8319b9fd-c809-11f1-8619-ae8195338abe, and updated total count to: 1362 trace_id=5b5c4b1e4c3efde0ee226455ae53acf5 span_id=27dfbf00da541192 trace_flags=01 
2026-10-14T19:57:58.116342+00:00  2026-10-14 19:57:58 - fraud-detection - Consumed record with orderId: 8d89bb57-c809-11f1-8619-ae8195338abe, and updated total count to: 1363 trace_id=487d525a83b2050362165610cc88b99d span_id=0b910cdd5e7fec6f trace_flags=01 
2026-10-14T19:58:02.325578+00:00  2026-10-14 19:58:02 - fraud-detection - Consumed record with orderId: 90083c39-c809-11f1-8619-ae8195338abe, and updated total count to: 1364 trace_id=6d2f37041ba225e41cb9edd30b869234 span_id=f53ca99f1ee0bd92 trace_flags=01 
2026-10-14T19:58:18.943022+00:00  2026-10-14 19:58:18 - fraud-detection - Consumed record with orderId: 99ea96cf-c809-11f1-8619-ae8195338abe, and updated total count to: 1365 trace_id=9f8e831ab75a08b050cfbdd2870cacb2 span_id=6a960bcea46257f6 trace_flags=01 
```

> Evidence `tr_6cd205f7d850`:

```
<tool_result id="tr_6cd205f7d850" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T20:27:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" oldest_kept="8" newest_kept="32" contains="kafkaQueueProblems">
selector: {service="fraud-detection"} |= "kafkaQueueProblems"
2026-10-14T20:53:54.467770+00:00  2026-10-14 20:53:54 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=898cbc8481d2ccd47285c57d7717ec38 span_id=04961034b622d6ad trace_flags=01 
2026-10-14T20:53:55.467525+00:00  2026-10-14 20:53:55 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=c4f74ce1be8aa7eebf877927c5aa22d4 span_id=b9bb9363b230aaf6 trace_flags=01 
2026-10-14T20:53:56.468722+00:00  2026-10-14 20:53:56 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=e0725fcae5740428f390e3926f10a96e span_id=c8d3599bf6182b97 trace_flags=01 
2026-10-14T20:53:57.470084+00:00  2026-10-14 20:53:57 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=e0725fcae5740428f390e3926f10a96e span_id=30afdcd1a4c1d608 trace_flags=01 
```

> Evidence `tr_5c5089be0b50`:

```
<tool_result id="tr_5c5089be0b50" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T20:27:31.664000+00:00..2026-10-14T20:59:28.463161+00:00">
service: fraud-detection
1 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace e0725fcae5740428  root fraud-detection/orders receive  0.6ms  started 2026-10-14T20:53:56.467906+00:00  200 spans
  +0.0ms fraud-detection/orders receive 0.6ms [self 0.0ms]
```

## The change-history dead end

Three change-log queries were run — one on fraud-detection, two on flagd — and all three returned empty. Read carefully before reusing them: every window started at the alert timestamp and ran ~24 hours forward, so the pre-onset period was never queried at all.

What they legitimately establish is narrow: no change during or after onset, so nothing in-flight is sustaining the problem, no quiet remediation was applied, and there is no recent release to roll back. What they do not establish is that nothing changed beforehand — the question everyone wanted answered, who flipped the flag and when, was never put to the data. The same wrong window was used three times and each empty result read as reassurance. That is the most repeatable mistake in this record.

> Evidence `tr_f6c32d9532b0`:

```
<tool_result id="tr_f6c32d9532b0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T20:57:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_f6c32d9532b0>
```

> Evidence `tr_e01e1e3a6214`:

```
<tool_result id="tr_e01e1e3a6214" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T20:57:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_e01e1e3a6214>
```

> Evidence `tr_f05812f8d4b1`:

```
<tool_result id="tr_f05812f8d4b1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T20:57:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_f05812f8d4b1>
```

## Conclusion and what is still open

fraud-detection's order-consumer is running the code path gated by `kafkaQueueProblems`, which evaluates to enabled and adds a fixed ~1 second sleep to every handler invocation. Flag lines are paired with every consumption line from onset and absent before it; traces show ~1.004–1.009s of pure self-time inside `orders process` with no outbound children. The ~1 record/second throttle prevents offset commit, so the same record is redelivered and reprocessed under one trace_id. No deploy, config edit or restart is recorded for either service post-onset — the expected signature of a value flipped at runtime in the flag store rather than shipped through a release. Confidence high; fix is to revert the flag value, not to roll back code.

Open threads for the next responder: (1) the flip's time and actor are unestablished — query change history backwards from onset first; (2) the five full-failure episodes from the metrics baseline sit outside the observed window and remain unattributed; (3) flagd itself was never inspected for logs or current flag state, and neither the second service in the radius nor the one unmeasured edge was investigated.

> Evidence `tr_6cd205f7d850`:

```
<tool_result id="tr_6cd205f7d850" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T20:27:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" oldest_kept="8" newest_kept="32" contains="kafkaQueueProblems">
selector: {service="fraud-detection"} |= "kafkaQueueProblems"
2026-10-14T20:53:54.467770+00:00  2026-10-14 20:53:54 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=898cbc8481d2ccd47285c57d7717ec38 span_id=04961034b622d6ad trace_flags=01 
2026-10-14T20:53:55.467525+00:00  2026-10-14 20:53:55 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=c4f74ce1be8aa7eebf877927c5aa22d4 span_id=b9bb9363b230aaf6 trace_flags=01 
2026-10-14T20:53:56.468722+00:00  2026-10-14 20:53:56 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=e0725fcae5740428f390e3926f10a96e span_id=c8d3599bf6182b97 trace_flags=01 
2026-10-14T20:53:57.470084+00:00  2026-10-14 20:53:57 - fraud-detection - FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second trace_id=e0725fcae5740428f390e3926f10a96e span_id=30afdcd1a4c1d608 trace_flags=01 
```

> Evidence `tr_5c5089be0b50`:

```
<tool_result id="tr_5c5089be0b50" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T20:27:31.664000+00:00..2026-10-14T20:59:28.463161+00:00">
service: fraud-detection
1 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace e0725fcae5740428  root fraud-detection/orders receive  0.6ms  started 2026-10-14T20:53:56.467906+00:00  200 spans
  +0.0ms fraud-detection/orders receive 0.6ms [self 0.0ms]
```

> Evidence `tr_b2161a5c6c9a`:

```
<tool_result id="tr_b2161a5c6c9a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T19:57:31.664000+00:00..2026-10-14T20:59:28.463161+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-14T19:57:40.560795+00:00  2026-10-14 19:57:40 - fraud-detection - Consumed record with orderId: 8319b9fd-c809-11f1-8619-ae8195338abe, and updated total count to: 1362 trace_id=5b5c4b1e4c3efde0ee226455ae53acf5 span_id=27dfbf00da541192 trace_flags=01 
2026-10-14T19:57:58.116342+00:00  2026-10-14 19:57:58 - fraud-detection - Consumed record with orderId: 8d89bb57-c809-11f1-8619-ae8195338abe, and updated total count to: 1363 trace_id=487d525a83b2050362165610cc88b99d span_id=0b910cdd5e7fec6f trace_flags=01 
2026-10-14T19:58:02.325578+00:00  2026-10-14 19:58:02 - fraud-detection - Consumed record with orderId: 90083c39-c809-11f1-8619-ae8195338abe, and updated total count to: 1364 trace_id=6d2f37041ba225e41cb9edd30b869234 span_id=f53ca99f1ee0bd92 trace_flags=01 
2026-10-14T19:58:18.943022+00:00  2026-10-14 19:58:18 - fraud-detection - Consumed record with orderId: 99ea96cf-c809-11f1-8619-ae8195338abe, and updated total count to: 1365 trace_id=9f8e831ab75a08b050cfbdd2870cacb2 span_id=6a960bcea46257f6 trace_flags=01 
```

> Evidence `tr_edbf05bf6eb3`:

```
<tool_result id="tr_edbf05bf6eb3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T20:57:31.664000+00:00..2026-10-14T02:57:31.664000+00:00" template="error-ratio" baseline="2026-10-13T14:57:31.664000+00:00..2026-10-13T20:57:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=1300 mean=0.04848 min=0 max=1 sd=0.195
  baseline window: n=750 mean=0.02656 min=0 max=1 sd=0.144
```

