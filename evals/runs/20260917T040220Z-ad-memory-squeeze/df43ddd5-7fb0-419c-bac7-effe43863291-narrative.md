# Frontend alert traced to unreachable adservice name; frontend itself clean

## What we saw first

The page named frontend and loadgenerator, severity critical, blast radius seven services. The natural reading was that the shop's entry point had started failing users at T+0. That reading did not survive contact with the data. Nothing in either alerted service's own signals shows a transition at T+0, and every piece of frontend-local health evidence came back normal or better than the preceding hour. The one genuinely anomalous thing in the whole record is a cluster of outbound gRPC client errors in frontend's logs, and those point outward, not inward.

> Evidence `tr_c27c47009e12`:

```
<tool_result id="tr_c27c47009e12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:06:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T03:10:49.734851+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T03:10:49.734892+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T03:10:49.734896+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T03:10:49.734897+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## First pass: frontend error rate (dead end)

The obvious first move was to characterise the onset: step or ramp? We pulled frontend's error ratio against a preceding baseline, twice, at two different baseline lengths. Both came back the wrong way round. Over the shorter comparison the incident-window mean sat at roughly two-thirds of baseline with no sustained departure flagged; over the longer comparison it was about half. Spikes appear in both windows and the baseline maximum actually exceeds the incident maximum, so the occasional error bursts are a standing feature of this service, not something new. Sample counts were identical across the shorter pair of windows, which also kills the idea that traffic simply stopped flowing. Whatever the alert was reacting to, frontend was not returning more errors during it.

Worth flagging for anyone re-running this: the longer pull returned roughly three times the sample density in the incident window compared to baseline, so treat those mean ratios as indicative rather than precise.

> Evidence `tr_c45cdaf0ba47`:

```
<tool_result id="tr_c45cdaf0ba47" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T03:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T03:04:01.701776+00:00..2026-09-17T03:36:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02106 min=0 max=0.26 sd=0.04292
  baseline window: n=128 mean=0.03255 min=0 max=0.4076 sd=0.05967
```

> Evidence `tr_1e14b9d3d52c`:

```
<tool_result id="tr_1e14b9d3d52c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T02:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T01:04:01.701776+00:00..2026-09-17T02:36:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=368 mean=0.03967 min=0 max=0.4076 sd=0.05081
  baseline window: n=122 mean=0.07515 min=0 max=0.1168 sd=0.02239
```

## The 03:35 excursion (real, but not ours)

Both the frontend and loadgenerator error-ratio series contain exactly one detected change point, and it is at 03:35:30 — roughly half an hour before the page. It is a brief spike well above the baseline maximum, not a sustained shift; the window means stay low on either side of it. It is tempting to treat this as the precursor, and it may be worth a look, but it is not the alert. No change point appears at or near T+0 in either series. The high variance in the incident window despite the lower mean is consistent with this single excursion riding on an otherwise quiet line.

> Evidence `tr_1e14b9d3d52c`:

```
<tool_result id="tr_1e14b9d3d52c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T02:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T01:04:01.701776+00:00..2026-09-17T02:36:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=368 mean=0.03967 min=0 max=0.4076 sd=0.05081
  baseline window: n=122 mean=0.07515 min=0 max=0.1168 sd=0.02239
```

> Evidence `tr_88dbd8dfe2d2`:

```
<tool_result id="tr_88dbd8dfe2d2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T02:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T01:04:01.701776+00:00..2026-09-17T02:36:00.583000+00:00">
service: loadgenerator
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="loadgenerator",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="loadgenerator"}[2m]))
  incident window: n=368 mean=0.04344 min=0 max=0.4167 sd=0.0547
  baseline window: n=122 mean=0.08873 min=0 max=0.2222 sd=0.02968
```

## Client side: loadgenerator (dead end)

If frontend was not generating errors, perhaps the client was seeing them anyway. It was not. Loadgenerator's observed error ratio is about half its baseline through the window, with no transition at T+0. So the hypothesis that the incident opened with a wave of client-side timeouts or failures is ruled out from the client's own vantage point. The only client-visible anomaly in the whole span is the same 03:35:30 spike.

> Evidence `tr_88dbd8dfe2d2`:

```
<tool_result id="tr_88dbd8dfe2d2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T02:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T01:04:01.701776+00:00..2026-09-17T02:36:00.583000+00:00">
service: loadgenerator
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="loadgenerator",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="loadgenerator"}[2m]))
  incident window: n=368 mean=0.04344 min=0 max=0.4167 sd=0.0547
  baseline window: n=122 mean=0.08873 min=0 max=0.2222 sd=0.02968
```

## Traces: no coverage where it mattered

Ten frontend traces came back, all of them bunched into a sixteen-second band at roughly T+1m42s to T+1m58s. There is no trace coverage of T+0 at all, which is the single biggest hole in this record. Within the band that was sampled: every trace completes in single-digit to low-tens of milliseconds, the slowest root at about 21.6ms, and not one span is marked errored.

Three specific suspicions died here, with the caveat that they died only for the sampled band. No checkoutservice span appears anywhere in the 37 spans returned, so there is no trace-side support for a slow frontend-to-checkout hop. The productcatalogservice GetProduct spans register essentially zero duration. The cartservice AddItem/GetCart spans and their Redis children are all sub-millisecond inside a 3.2ms root. Where time is spent, it is frontend's own self-time on leaf HTTP GET/POST spans, around 4.5–15ms — which is to say, in frontend or its client/network path, not below it in the call graph. That last observation is the one that actually pointed somewhere useful.

> Evidence `tr_0fadf4f5fafb`:

```
<tool_result id="tr_0fadf4f5fafb" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T03:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00">
service: frontend
10 trace(s) shown of 10 found, 37 spans; offsets are from each trace's root

trace 662c6391fd47cb78  root frontend/HTTP GET  2.6ms  started 2026-09-17T04:07:42.659041+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.6ms]
```

## Logs: the one thing that was actually wrong

Frontend's logs over the hour are dominated by outbound gRPC client failures carrying status 14 UNAVAILABLE, raised from call-stream and client-interceptor code. That location matters: frontend is failing as a caller, not rejecting inbound work. The newest lines, clustered around T+1m38s to T+1m53s, name the specific reason — DNS name resolution failing for the adservice target on port 9555.

Because name resolution is where it breaks, the connection is never established. That rules out the reading that adservice is up but slow and frontend is blocked waiting on it; this is discovery or endpoint availability, not response latency. An older line of the same family, around fifty-five minutes before the page, describes a dropped connection to a dependency, so intermittent trouble on this path predates T+0.

What is absent from the logs is as useful as what is present: no GC pauses, no connection-pool exhaustion, no event-loop or thread starvation warnings, no queue-depth or saturation messages, no server-side timeouts. Frontend-local pressure as an explanation has nothing supporting it in the retained lines, including the block immediately around the log cluster.

> Evidence `tr_c27c47009e12`:

```
<tool_result id="tr_c27c47009e12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:06:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T03:10:49.734851+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T03:10:49.734892+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T03:10:49.734896+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T03:10:49.734897+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Change history: empty on both candidates (dead end)

We queried the change log for frontend and for checkoutservice. Both came back completely empty — no deploys, no rollbacks, no config edits, no flag flips. That removes rollback as a lever and removes any anchor tying the timeline to a release event.

Two caveats a future responder should not skip. First, the frontend query window opens at T+0, essentially at onset, so it covers the aftermath rather than the lead-up; anything that landed earlier would not show. Second, the checkoutservice query was scoped at one hop and returned nothing for the secondary services either, so their change status is unconfirmed rather than positively clear. Empty is not the same as clean here.

> Evidence `tr_b4f84b5748b1`:

```
<tool_result id="tr_b4f84b5748b1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T04:06:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_b4f84b5748b1>
```

> Evidence `tr_d6f70a4c5c7c`:

```
<tool_result id="tr_d6f70a4c5c7c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T04:06:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_d6f70a4c5c7c>
```

## Where this lands

The evidence supports a dependency availability or discovery failure on the adservice path, not a frontend failure. Frontend's request handling, error rate and downstream span timings are all normal or better than baseline; the only anomaly is frontend being unable to resolve the adservice name. That makes the user-visible impact partial — the ad panel — rather than a full outage, which is consistent with error ratios staying flat everywhere else. Suggested fix class is a restart of the affected component, but confidence in this conclusion is low for the reasons below.

> Evidence `tr_c27c47009e12`:

```
<tool_result id="tr_c27c47009e12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:06:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T03:10:49.734851+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T03:10:49.734892+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T03:10:49.734896+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T03:10:49.734897+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_c45cdaf0ba47`:

```
<tool_result id="tr_c45cdaf0ba47" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T03:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T03:04:01.701776+00:00..2026-09-17T03:36:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02106 min=0 max=0.26 sd=0.04292
  baseline window: n=128 mean=0.03255 min=0 max=0.4076 sd=0.05967
```

## Still open

Three things were never resolved and should be the first moves next time.

Is adservice actually running with ready endpoints, or is cluster DNS itself unhealthy? No adservice-side metrics, logs or change history were ever pulled. The log line tells us resolution failed; it does not tell us why.

What fired the page at T+0? No metric at frontend or loadgenerator shows a transition there, and no latency series was ever returned by any query — every metric pull came back as the error-ratio template. The step-versus-ramp question is still unanswered because the data to answer it was never retrieved.

The onset minute is unobserved. Traces cover only that sixteen-second band well after the page, with no adservice span present at all. Pull traces scoped to T+0 and query adservice directly before trusting any of the above.

> Evidence `tr_1e14b9d3d52c`:

```
<tool_result id="tr_1e14b9d3d52c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T02:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" template="error-ratio" baseline="2026-09-17T01:04:01.701776+00:00..2026-09-17T02:36:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=368 mean=0.03967 min=0 max=0.4076 sd=0.05081
  baseline window: n=122 mean=0.07515 min=0 max=0.1168 sd=0.02239
```

> Evidence `tr_0fadf4f5fafb`:

```
<tool_result id="tr_0fadf4f5fafb" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T03:36:00.583000+00:00..2026-09-17T04:07:59.464224+00:00">
service: frontend
10 trace(s) shown of 10 found, 37 spans; offsets are from each trace's root

trace 662c6391fd47cb78  root frontend/HTTP GET  2.6ms  started 2026-09-17T04:07:42.659041+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.6ms]
```

> Evidence `tr_c27c47009e12`:

```
<tool_result id="tr_c27c47009e12" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:06:00.583000+00:00..2026-09-17T04:07:59.464224+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T03:10:49.734851+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T03:10:49.734892+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T03:10:49.734896+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T03:10:49.734897+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

