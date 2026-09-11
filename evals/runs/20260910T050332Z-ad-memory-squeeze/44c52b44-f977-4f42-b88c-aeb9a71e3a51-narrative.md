# Frontend error spike traced to ad-service boot loop under a lowered memory ceiling

## What was visible first

Frontend and loadgenerator paged together; frontend was named as the seed, which framed the first twenty minutes of the response and turned out to be misleading. Frontend's own numbers confirmed something real but oddly shaped: error ratio around 0.04% for the preceding hour, then a single change point at T+0 (05:05), an incident-window mean near 0.65% and a peak around 11.3% against a baseline maximum of ~1.6%. So: outside normal variation, but late-onset and narrow. Any theory about slow saturation building through the hour dies here, and frontend was never hard-down — most requests succeeded throughout.

The reflex move was to look for a frontend change. There was none: the change history over the full window returned empty for frontend, no deploys, config edits, or flag flips. That closes the rollback path for frontend entirely. One caveat that cost time: that query ran at seed radius, covering frontend only, so its emptiness said nothing about the dependencies. It was briefly read as "nothing changed anywhere."

> Evidence `tr_b40dbc22c764`:

```
<tool_result id="tr_b40dbc22c764" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T04:06:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" template="error-ratio" baseline="2026-09-10T03:04:39.263721+00:00..2026-09-10T04:06:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=249 mean=0.006524 min=0 max=0.1128 sd=0.02134
  baseline window: n=249 mean=0.0004244 min=0 max=0.01562 sd=0.002502
```

> Evidence `tr_f3e14df687d2`:

```
<tool_result id="tr_f3e14df687d2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T05:06:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_f3e14df687d2>
```

## Two dead ends, then the failing edge

The frontend error metric could not name a downstream — it is aggregated by service name with no dependency, route, or duration dimension, so it neither implicates nor exonerates anything. That is why the work moved to logs.

Frontend logs resolved it. Every error originates in the gRPC client path reporting an upstream transport status, consistently code 14 UNAVAILABLE, and the only target named is the ad-service endpoint on port 9555 via a dns: target. The late-window failures are name resolution failures — no RPC ever reached a server. This rules out frontend business logic, application-level errors from a live upstream, and a slow-but-reachable peer causing deadline exceeded (no code 4 appears). No other backend name shows up.

The second dead end: pulling ad-service's error ratio returned no samples at all — and none in the baseline window either. The tempting reading, that telemetry went silent at T+0 because instances died then, is wrong; the silence predates onset. That series simply is not produced. This edge is unmeasured, so everything past it rests on logs and change records.

> Evidence `tr_b40dbc22c764`:

```
<tool_result id="tr_b40dbc22c764" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T04:06:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" template="error-ratio" baseline="2026-09-10T03:04:39.263721+00:00..2026-09-10T04:06:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=249 mean=0.006524 min=0 max=0.1128 sd=0.02134
  baseline window: n=249 mean=0.0004244 min=0 max=0.01562 sd=0.002502
```

> Evidence `tr_06e20fa34668`:

```
<tool_result id="tr_06e20fa34668" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T04:06:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T04:35:08.381584+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-10T04:35:08.381636+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T04:35:08.381663+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T04:35:08.381666+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_f572198ff0f1`:

```
<tool_result id="tr_f572198ff0f1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T04:36:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" template="error-ratio" baseline="2026-09-10T04:04:39.263721+00:00..2026-09-10T04:36:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Ad-service, the change trail, and what remains open

Ad-service logs showed normal ad-request serving with trace context around T-28m, then from roughly T-2m nothing but repeated JVM startup banners — the same boot sequence at least ten times, with gaps growing from seconds to ~15s, ~29s, ~54s, ~63s. That backoff shape is a supervisor restart loop. No boot reaches application traffic. This excludes a broken log pipeline, a single restart or rollout blip, and a clean drain or scale-down (no shutdown or SIGTERM lines). Notably there is no OutOfMemoryError, stack trace, or exception either: the process dies silently, which points to an external kill or a probe failing before readiness rather than an in-process error. The log result was truncated mid-window, so that absence is weaker than it looks.

The change log for ad-service holds eleven entries, all automated memory-limit toggles alternating between 256m and a revert. The most recent lowering to 256m landed about T-3m. It also rules out deployments, replica or scaling changes, Service/endpoint/DNS edits, non-resource config changes, and any human edit.

Conclusion, at medium confidence: the ceiling drop at T-3m left the JVM unable to stay resident; it is killed shortly after each boot, no pod reaches ready, and frontend's client fails at name resolution — the spike at T+0. Frontend is the reporter, not the cause. The edit is how it started; exhausting the ceiling is what is happening. Fix class: revert the configuration.

Still open: no direct confirmation of the kill — exit codes, runtime kill events, and ad-service memory or heap metrics were never queried, and a failing startup probe under a constrained heap fits equally well. The same lower/revert pair has repeated at least five times in the preceding ~21 hours without a recorded incident, so either those episodes also looped unnoticed or something else changed too. Kubernetes endpoint and DNS state was never inspected directly.

> Evidence `tr_7f31a4dfd996`:

```
<tool_result id="tr_7f31a4dfd996" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T04:36:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-10T04:36:46.096094+00:00  2026-09-10 04:36:46 - hipstershop.AdService - received ad request (context_words=[telescopes]) trace_id=ff0af103759b5920fdcbc0eee04246d0 span_id=ec7b29322896e246 trace_flags=01 
2026-09-10T04:36:47.762669+00:00  2026-09-10 04:36:47 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=4e4c0c3d5a65c531b3274b4ecb094644 span_id=73f37d0251c95d85 trace_flags=01 
2026-09-10T04:36:48.515035+00:00  2026-09-10 04:36:48 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=bb997d5cfa3a40bee8eb2752480e5eb5 span_id=6101c0c33a3bab5c trace_flags=01 
2026-09-10T04:36:49.009184+00:00  2026-09-10 04:36:49 - hipstershop.AdService - received ad request (context_words=[telescopes]) trace_id=02341166a711d14e4fd1fdd5519d1572 span_id=57351a2abcdd1c51 trace_flags=01 
```

> Evidence `tr_066fd3438efe`:

```
<tool_result id="tr_066fd3438efe" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T05:06:45.583000+00:00..2026-09-10T05:08:51.902279+00:00" radius="candidate_cause" hops="1">
service: adservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T05:03:36.554416+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  2.7h before onset  2026-09-10T02:22:13.375179+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

