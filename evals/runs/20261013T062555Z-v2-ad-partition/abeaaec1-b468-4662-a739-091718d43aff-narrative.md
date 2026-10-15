# Ad service reachable in process but cut off from the network

## What we saw first

Three alerts opened essentially together: ad, frontend-proxy and load-generator. Severity was called critical, with five services inside the blast radius and the trail from ad crossing three edges we had no measurements on. The shape of the alerting was the first useful clue and we under-weighted it at the time: when a callee starts returning errors, callers usually get loud. Here the callers went quiet-but-slow, which is what you see when requests hang against something unreachable rather than something broken.

For the first stretch of the investigation we treated ad as a service that had started failing requests. That framing is what sent us down most of the dead ends below.

## The log trail on ad

The ad logs were the turning point. At roughly T-30m the service was behaving entirely normally: targeted-ad requests logged with live trace context across several categories, no errors, no warnings. At T+1m and again at T+2m the same process logged repeated OpenTelemetry Java agent export failures - the periodic metric export to the collector endpoint failing with an unknown-host resolution error, stack traces running down through the HTTP client's route-selection path. The one-minute spacing matches the export cadence exactly, so this is every attempt failing, not an occasional blip.

Two details matter. First, the failure happens before any TCP connect is attempted, which pushes the problem upstream of the collector process itself - this is not a refused connection, a timeout, or a TLS or auth problem at the far end. Second, these frames are all in the agent's exporter thread pool; no application logger and no ad-serving code appears in them. The process was alive and the telemetry path out of it was not.

The log result was truncated to the newest 32 lines, and all 32 were exporter stack traces. That is the single largest hole in this record: we have no evidence at all about ad's request-serving path after T+0.

> Evidence `tr_284d6db8df50`:

```
<tool_result id="tr_284d6db8df50" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T06:03:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-13T06:03:18.281359+00:00  2026-10-13 06:03:18 - oteldemo.AdService - no baggage found in context trace_id=d6ba2ff39a9e3bc33838ecf8ba28f0f0 span_id=7d5f92200ee66f13 trace_flags=01 
2026-10-13T06:03:18.282138+00:00  2026-10-13 06:03:18 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=d6ba2ff39a9e3bc33838ecf8ba28f0f0 span_id=7d5f92200ee66f13 trace_flags=01 
2026-10-13T06:03:24.453835+00:00  2026-10-13 06:03:24 - oteldemo.AdService - no baggage found in context trace_id=36ec0373e349ee447790fb4406d6fc78 span_id=5af9a6512f9168e9 trace_flags=01 
2026-10-13T06:03:24.455777+00:00  2026-10-13 06:03:24 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=36ec0373e349ee447790fb4406d6fc78 span_id=5af9a6512f9168e9 trace_flags=01 
```

## Ruling out a restart or a crash loop

The obvious first hypothesis was that ad died at onset. It did not. No bootstrap banner, no shutdown line, no restart marker appears anywhere in the window, and the service is logging continuously at both the old and new ends of what we retrieved. The error-ratio series backs this up independently: intervals with a defined ratio require non-zero call volume, and a crash-loop would have punched visible gaps in it. We saw continuous traffic instead.

Worth noting for anyone reading the metric comparison fresh: the intervals with no defined ratio that do appear show up in comparable proportion in the baseline period and in the window. They are a pre-existing pattern in this service, not a symptom of this incident. We chased them briefly and they went nowhere.

> Evidence `tr_284d6db8df50`:

```
<tool_result id="tr_284d6db8df50" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T06:03:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-13T06:03:18.281359+00:00  2026-10-13 06:03:18 - oteldemo.AdService - no baggage found in context trace_id=d6ba2ff39a9e3bc33838ecf8ba28f0f0 span_id=7d5f92200ee66f13 trace_flags=01 
2026-10-13T06:03:18.282138+00:00  2026-10-13 06:03:18 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=d6ba2ff39a9e3bc33838ecf8ba28f0f0 span_id=7d5f92200ee66f13 trace_flags=01 
2026-10-13T06:03:24.453835+00:00  2026-10-13 06:03:24 - oteldemo.AdService - no baggage found in context trace_id=36ec0373e349ee447790fb4406d6fc78 span_id=5af9a6512f9168e9 trace_flags=01 
2026-10-13T06:03:24.455777+00:00  2026-10-13 06:03:24 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=36ec0373e349ee447790fb4406d6fc78 span_id=5af9a6512f9168e9 trace_flags=01 
```

> Evidence `tr_019bfef1e54d`:

```
<tool_result id="tr_019bfef1e54d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:33:16.664000+00:00..2026-10-13T06:33:16.664000+00:00" template="error-ratio" baseline="2026-10-12T18:33:16.664000+00:00..2026-10-13T00:33:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1392 mean=0.008427 min=0 max=0.3684 sd=0.03856
  baseline window: n=849 mean=0.003672 min=0 max=0.02381 sd=0.00492
```

> Evidence `tr_40f1b779b523`:

```
<tool_result id="tr_40f1b779b523" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-12T12:33:16.664000+00:00" template="error-ratio" baseline="2026-10-12T00:33:16.664000+00:00..2026-10-12T06:33:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=81 mean=0.003214 min=0 max=0.02381 sd=0.006822
  baseline window: n=1409 mean=0.008904 min=0 max=0.3848 sd=0.041
```

## The change-log dead end

We checked ad's changes across the preceding day. Two records, both from platform automation, both resource-limit edits: a memory limit lowered, then that same limit reverted about twenty-eight minutes later. Both landed roughly fifteen hours before onset, so the constrained configuration was not even in force when the incident began, and the hours immediately preceding onset are completely change-free. No deploy, no release, no human actor.

We also pulled flagd's change history on the theory that a flag re-targeting ad might explain it. The window was empty - no flag edits, no config updates, no rollouts. There is nothing there to roll back and no reason to freeze changes on that service.

Both of these were reasonable checks and both cost time. Record them as closed.

> Evidence `tr_69349dae6979`:

```
<tool_result id="tr_69349dae6979" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" radius="seed" hops="0">
service: ad
2 changes, ranked by suspicion
  #1  14.9h before onset  2026-10-12T15:39:50.144328+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
      memory=144m  ->  None
  #2  15.4h before onset  2026-10-12T15:11:51.018012+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
```

> Evidence `tr_fbbb7559eea9`:

```
<tool_result id="tr_fbbb7559eea9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_fbbb7559eea9>
```

## What the traces did and did not tell us

Ten ad traces came back, all with an identical shape: load generator to the proxy, proxy to frontend, frontend's gRPC client span into ad's server span, and a single in-process leaf underneath. No error status anywhere. Ad's server spans ran one to thirteen milliseconds with one outlier near thirty-four, and in the slowest end-to-end trace the dominant self-time sat at the proxy hop, not at ad.

This killed three side theories cleanly: ad was not the latency bottleneck, no caller other than frontend was driving it, and the ad-selection leaf work was not hanging or looping. It also showed ad emitting no outbound spans to any downstream service at all - so the theory that ad was stuck waiting on a flag evaluation has no supporting hop in the data.

The catch, which we did not notice until late: although the query covered six hours, every returned trace started inside a two-and-a-half minute band well before onset. The sample says nothing about the window that actually matters.

> Evidence `tr_a7cbce30f09b`:

```
<tool_result id="tr_a7cbce30f09b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T00:33:16.664000+00:00..2026-10-13T06:33:16.664000+00:00">
service: ad
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace 1b89197c6eaf455e  root load-generator/user_get_ads  23.6ms  started 2026-10-13T05:55:14.154991+00:00  13 spans
  +0.0ms load-generator/user_get_ads 23.6ms [self 0.9ms]
```

## The frontend log query that produced nothing

We went looking for frontend-side errors on calls to ad - timeouts, connection refused, deadline exceeded. The query returned zero lines. Because the substring we searched is short and common enough that it would match plenty of ordinary application text, zero matches most likely means the frontend stream was effectively silent under that selector, not that ad-related errors were specifically absent.

So this is a weak negative, not a strong one. It is consistent with callers hanging rather than erroring, which supports the overall picture, but it cannot carry attribution on its own. Do not treat frontend logs as a usable channel under the current labels without fixing the selector first.

> Evidence `tr_a3dce78b06d8`:

```
<tool_result id="tr_a3dce78b06d8" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T06:03:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" contains="ad">
no log lines matched {service="frontend"} |= "ad" over this window
</tool_result:tr_a3dce78b06d8>
```

## The metric excursion we never explained

The error-ratio comparison over the six hours before onset showed the window mean roughly 2.3x the preceding baseline. That sounds alarming until you look at the shape: a single change point reaching about 37% of calls in error, against a window mean still under one percent. The baseline period never exceeded about 2.4%, so the excursion is genuinely anomalous - but it is a narrow spike, not sustained degradation, and it sits hours before the onset we care about.

We never connected it to anything. It remains open. Note also that the metric queries we issued for container memory, CPU and restart counts never came back - only the error-ratio template evaluated. An underlying node-level or memory-pressure trigger is therefore untested rather than excluded.

> Evidence `tr_019bfef1e54d`:

```
<tool_result id="tr_019bfef1e54d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:33:16.664000+00:00..2026-10-13T06:33:16.664000+00:00" template="error-ratio" baseline="2026-10-12T18:33:16.664000+00:00..2026-10-13T00:33:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1392 mean=0.008427 min=0 max=0.3684 sd=0.03856
  baseline window: n=849 mean=0.003672 min=0 max=0.02381 sd=0.00492
```

> Evidence `tr_40f1b779b523`:

```
<tool_result id="tr_40f1b779b523" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-12T12:33:16.664000+00:00" template="error-ratio" baseline="2026-10-12T00:33:16.664000+00:00..2026-10-12T06:33:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=81 mean=0.003214 min=0 max=0.02381 sd=0.006822
  baseline window: n=1409 mean=0.008904 min=0 max=0.3848 sd=0.041
```

## Where we landed

Best reading of the evidence: ad is cut off from the network while its process stays alive. From T+0 its agent fails every periodic export with a name-resolution error for the collector, on the export cadence, before any connect is attempted. The process is not dead and not restarting. No change sits near onset. The simultaneous alerts on ad, the proxy and the load generator fit callers hanging against an unreachable callee rather than receiving errors, which matches the absence of any frontend-side error text.

Confidence is medium, and the fix class is reconnect rather than rollback. Four things remain genuinely open and should be the first queries next time: whether ad was still answering gRPC calls after T+0 at all, or only failing telemetry; what was happening in the T+0 to T+2m band, which no trace or metric sample we hold actually covers; whether the resolution failure was specific to the collector name or affected all names, and whether other services shared it; and whether a node-level or memory event was the underlying trigger, which the missing container metrics would have answered.

> Evidence `tr_284d6db8df50`:

```
<tool_result id="tr_284d6db8df50" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T06:03:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-13T06:03:18.281359+00:00  2026-10-13 06:03:18 - oteldemo.AdService - no baggage found in context trace_id=d6ba2ff39a9e3bc33838ecf8ba28f0f0 span_id=7d5f92200ee66f13 trace_flags=01 
2026-10-13T06:03:18.282138+00:00  2026-10-13 06:03:18 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=d6ba2ff39a9e3bc33838ecf8ba28f0f0 span_id=7d5f92200ee66f13 trace_flags=01 
2026-10-13T06:03:24.453835+00:00  2026-10-13 06:03:24 - oteldemo.AdService - no baggage found in context trace_id=36ec0373e349ee447790fb4406d6fc78 span_id=5af9a6512f9168e9 trace_flags=01 
2026-10-13T06:03:24.455777+00:00  2026-10-13 06:03:24 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=36ec0373e349ee447790fb4406d6fc78 span_id=5af9a6512f9168e9 trace_flags=01 
```

> Evidence `tr_019bfef1e54d`:

```
<tool_result id="tr_019bfef1e54d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:33:16.664000+00:00..2026-10-13T06:33:16.664000+00:00" template="error-ratio" baseline="2026-10-12T18:33:16.664000+00:00..2026-10-13T00:33:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1392 mean=0.008427 min=0 max=0.3684 sd=0.03856
  baseline window: n=849 mean=0.003672 min=0 max=0.02381 sd=0.00492
```

> Evidence `tr_69349dae6979`:

```
<tool_result id="tr_69349dae6979" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" radius="seed" hops="0">
service: ad
2 changes, ranked by suspicion
  #1  14.9h before onset  2026-10-12T15:39:50.144328+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
      memory=144m  ->  None
  #2  15.4h before onset  2026-10-12T15:11:51.018012+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
```

> Evidence `tr_fbbb7559eea9`:

```
<tool_result id="tr_fbbb7559eea9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_fbbb7559eea9>
```

> Evidence `tr_a3dce78b06d8`:

```
<tool_result id="tr_a3dce78b06d8" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T06:03:16.664000+00:00..2026-10-13T06:35:15.830812+00:00" contains="ad">
no log lines matched {service="frontend"} |= "ad" over this window
</tool_result:tr_a3dce78b06d8>
```

> Evidence `tr_a7cbce30f09b`:

```
<tool_result id="tr_a7cbce30f09b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T00:33:16.664000+00:00..2026-10-13T06:33:16.664000+00:00">
service: ad
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace 1b89197c6eaf455e  root load-generator/user_get_ads  23.6ms  started 2026-10-13T05:55:14.154991+00:00  13 spans
  +0.0ms load-generator/user_get_ads 23.6ms [self 0.9ms]
```

> Evidence `tr_40f1b779b523`:

```
<tool_result id="tr_40f1b779b523" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T06:33:16.664000+00:00..2026-10-12T12:33:16.664000+00:00" template="error-ratio" baseline="2026-10-12T00:33:16.664000+00:00..2026-10-12T06:33:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=81 mean=0.003214 min=0 max=0.02381 sd=0.006822
  baseline window: n=1409 mean=0.008904 min=0 max=0.3848 sd=0.041
```

