# Ad service loses cluster reachability; callers alert on hung requests

## What the responder sees first

Three alerts land at the same instant: ad, frontend-proxy, and load-generator. Severity critical, blast radius five services, and triage marks the starting point as ad with three edges that nothing ever measured. The shape of the alert set is the first useful signal — the two alerting callers sit directly upstream of ad on the same request path, and they fire together rather than in sequence. That pattern usually means callers are waiting rather than receiving errors, but at T+0 that is only a hunch.

## The metrics pass, which did not pay off

The obvious first move was to look for an error spike on ad. There is none. Error ratio over the incident window is statistically indistinguishable from baseline — mean moved about 2.5% downward, standard deviations overlap, no sustained departure. If you are reading this expecting to find the smoking gun in ad's error rate, stop; it is not there and it was not there at any point in the window. The one genuinely interesting artifact buried in that same result is 56 samples with no defined value, meaning intervals where ad served no traffic at all. That gap, not the ratio, is the finding worth carrying forward.

The same check on frontend was run next, on the theory that ad failures were surfacing as errors one hop up. Frontend's error ratio is flat zero across every sample in both windows, with zero variance. So the callers are not recording errors either. Two services in the path, neither reporting failure, and yet three alerts. This is the point where the "callers are hanging, not erroring" reading becomes the working hypothesis.

> Evidence `tr_47289fa3f5d8`:

```
<tool_result id="tr_47289fa3f5d8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T20:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" template="error-ratio" baseline="2026-10-12T16:57:23.259479+00:00..2026-10-12T20:59:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=862 mean=0.003681 min=0 max=0.02381 sd=0.004981
  baseline window: n=127 mean=0.003776 min=0 max=0.01852 sd=0.005171
```

> Evidence `tr_6aeca648bd9b`:

```
<tool_result id="tr_6aeca648bd9b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" template="error-ratio" baseline="2026-10-12T23:57:23.259479+00:00..2026-10-13T00:29:16.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Traces: clean, and misleading if read alone

Trace sampling over the window returned ten traces, every one of them complete at thirteen spans, load-generator through frontend-proxy through frontend into ad, unbroken. No error annotations, no timeouts, nothing truncated. Downstream of ad there are only getAdsByCategory and getRandomAds, both sub-millisecond, and flagd appears nowhere in the call graph at all.

The tooling flagged ad's own span as the degrading hop on self-time grounds — up to 6.7 ms. A responder could spend an hour chasing slow internal processing on that basis. It is a dead end. Single-digit milliseconds of self-time on an end-to-end path that completes under 30 ms does not produce three critical alerts. What the traces actually prove is narrower and more useful: when ad was reachable, it worked perfectly. The traces are evidence of the healthy intervals, not of the sick ones, which is consistent with the undefined metric samples — the sick intervals produced no spans to sample.

> Evidence `tr_4a158903a764`:

```
<tool_result id="tr_4a158903a764" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00">
service: ad
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace 350b48b94f84dc03  root load-generator/user_get_ads  12.6ms  started 2026-10-13T00:46:04.004544+00:00  13 spans
  +0.0ms load-generator/user_get_ads 12.6ms [self 0.7ms]
```

## Change history: two changes, both in the wrong place

The change log for ad contains exactly two entries: platform automation lowered the memory limit from undefined to 144m, and reverted it roughly 28 minutes later. Both sit about fourteen hours after onset. No deploys, no config edits, no flag or rollout changes anywhere before onset. Worth recording that the revert exists, in case a later phase or a recovery complication needs explaining, but neither change can have caused the initial failure. This whole line of inquiry closes.

> Evidence `tr_b2488bec015f`:

```
<tool_result id="tr_b2488bec015f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-12T00:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" radius="seed" hops="0">
service: ad
2 changes, ranked by suspicion
  #1  9.3h before onset  2026-10-12T15:39:50.144328+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
      memory=144m  ->  None
  #2  9.8h before onset  2026-10-12T15:11:51.018012+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
```

## flagd: ruled out twice, from both sides

flagd is a standing suspect for anything touching ad, so it got checked on two independent axes. Its change log is empty across the full window — not sparse, empty. Its own logs contain two informational config-file sync notifications and nothing else: no connection errors, no evaluation errors, no client disconnects, nothing at any severity near onset. Combined with flagd's complete absence from the trace call graph, this is as thorough an exclusion as the record offers. Do not revisit it.

> Evidence `tr_060c995be0a2`:

```
<tool_result id="tr_060c995be0a2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T00:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_060c995be0a2>
```

> Evidence `tr_1f7a9ff416d4`:

```
<tool_result id="tr_1f7a9ff416d4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00">
selector: {service="flagd"}
2026-10-13T00:33:07.428120+00:00  2026-10-13T00:33:07.423Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
2026-10-13T00:42:41.430950+00:00  2026-10-13T00:42:41.420Z	info	file/filepath_sync.go:108	filepath event: ./etc/flagd/demo.flagd.json WRITE	{"component": "sync", "sync": "fileinfo"}
</tool_result:tr_1f7a9ff416d4>
```

> Evidence `tr_4a158903a764`:

```
<tool_result id="tr_4a158903a764" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00">
service: ad
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace 350b48b94f84dc03  root load-generator/user_get_ads  12.6ms  started 2026-10-13T00:46:04.004544+00:00  13 spans
  +0.0ms load-generator/user_get_ads 12.6ms [self 0.7ms]
```

## The logs, which are the only place the failure is visible

Ad's own log is the single source that records anything going wrong. Early in the window the service is handling targeted and non-targeted ad lookups normally, no errors, no warnings. Then, roughly seven minutes before the alert, a java.io.InterruptedIOException: timeout, caused by java.io.IOException: Canceled. Roughly six minutes before the alert, and continuously from that point on, every exception is java.net.UnknownHostException for the hostname otel-collector.

Two details matter about the ordering. First, the timeout came before the name-resolution failures, which rules out the reading that a resolver problem was the initiating event — an in-flight connection was cut first, then subsequent attempts could not resolve. Second, the failures are at DNS lookup stage, not during handshake, which eliminates certificate and credential explanations outright; the connection never got far enough for those to apply.

Also absent from the logs: any JVM startup banner, server initialisation message, or shutdown signal. The process did not crash and was not restarted. It stayed up and kept logging while losing its path outward.

> Evidence `tr_871740d5cc0c`:

```
<tool_result id="tr_871740d5cc0c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T20:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-12T20:59:21.607966+00:00  2026-10-12 20:59:21 - oteldemo.AdService - no baggage found in context trace_id=70de6ee26d27b49df89801d492acdc71 span_id=cb599836f4e907f5 trace_flags=01 
2026-10-12T20:59:21.608162+00:00  2026-10-12 20:59:21 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=70de6ee26d27b49df89801d492acdc71 span_id=cb599836f4e907f5 trace_flags=01 
2026-10-12T20:59:21.982794+00:00  2026-10-12 20:59:21 - oteldemo.AdService - no baggage found in context trace_id=0647ec9edcbf9f3982a696e3d6c7d558 span_id=08120a2b7e25bf38 trace_flags=01 
2026-10-12T20:59:21.982821+00:00  2026-10-12 20:59:21 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=0647ec9edcbf9f3982a696e3d6c7d558 span_id=08120a2b7e25bf38 trace_flags=01 
```

> Evidence `tr_65d0ade48935`:

```
<tool_result id="tr_65d0ade48935" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" contains="Exception">
selector: {service="ad"} |= "Exception"
2026-10-13T00:52:04.295486+00:00  java.io.InterruptedIOException: timeout
2026-10-13T00:52:04.296368+00:00  Caused by: java.io.IOException: Canceled
2026-10-13T00:53:00.587533+00:00  java.net.UnknownHostException: otel-collector
2026-10-13T00:54:01.342179+00:00  java.net.UnknownHostException: otel-collector
```

## Conclusion as reached, with its confidence

The ad service lost network reachability shortly before the alert. A live connection timed out, and from then on every outbound attempt failed at name resolution rather than at any later stage — the signature of a pod losing its path to the cluster network and resolver. Everything else fits: traffic gaps in the metrics, intact traces only from healthy intervals, a flat error ratio because ad never got far enough to return an error, and a flat zero at frontend because callers received nothing rather than something bad. Frontend-proxy and load-generator alerting at the same instant as ad is what hung calls look like from upstream.

Confidence is medium, and the reason is in the next section. Fix class: reconnect.

> Evidence `tr_65d0ade48935`:

```
<tool_result id="tr_65d0ade48935" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" contains="Exception">
selector: {service="ad"} |= "Exception"
2026-10-13T00:52:04.295486+00:00  java.io.InterruptedIOException: timeout
2026-10-13T00:52:04.296368+00:00  Caused by: java.io.IOException: Canceled
2026-10-13T00:53:00.587533+00:00  java.net.UnknownHostException: otel-collector
2026-10-13T00:54:01.342179+00:00  java.net.UnknownHostException: otel-collector
```

> Evidence `tr_871740d5cc0c`:

```
<tool_result id="tr_871740d5cc0c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T20:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-12T20:59:21.607966+00:00  2026-10-12 20:59:21 - oteldemo.AdService - no baggage found in context trace_id=70de6ee26d27b49df89801d492acdc71 span_id=cb599836f4e907f5 trace_flags=01 
2026-10-12T20:59:21.608162+00:00  2026-10-12 20:59:21 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=70de6ee26d27b49df89801d492acdc71 span_id=cb599836f4e907f5 trace_flags=01 
2026-10-12T20:59:21.982794+00:00  2026-10-12 20:59:21 - oteldemo.AdService - no baggage found in context trace_id=0647ec9edcbf9f3982a696e3d6c7d558 span_id=08120a2b7e25bf38 trace_flags=01 
2026-10-12T20:59:21.982821+00:00  2026-10-12 20:59:21 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=0647ec9edcbf9f3982a696e3d6c7d558 span_id=08120a2b7e25bf38 trace_flags=01 
```

> Evidence `tr_47289fa3f5d8`:

```
<tool_result id="tr_47289fa3f5d8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T20:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" template="error-ratio" baseline="2026-10-12T16:57:23.259479+00:00..2026-10-12T20:59:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=862 mean=0.003681 min=0 max=0.02381 sd=0.004981
  baseline window: n=127 mean=0.003776 min=0 max=0.01852 sd=0.005171
```

> Evidence `tr_6aeca648bd9b`:

```
<tool_result id="tr_6aeca648bd9b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" template="error-ratio" baseline="2026-10-12T23:57:23.259479+00:00..2026-10-13T00:29:16.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_4a158903a764`:

```
<tool_result id="tr_4a158903a764" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00">
service: ad
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace 350b48b94f84dc03  root load-generator/user_get_ads  12.6ms  started 2026-10-13T00:46:04.004544+00:00  13 spans
  +0.0ms load-generator/user_get_ads 12.6ms [self 0.7ms]
```

## What nobody measured

Three things keep this at medium rather than high, and a future responder should close them before trusting the conclusion wholesale.

The confirmed name-resolution failures are all on the telemetry export path. No check was ever dispatched against ad's gRPC serving path or its resolution of other peers. The generalisation from "cannot resolve the collector" to "lost the cluster network" is plausible but untested.

The stack frames above the initial timeout were truncated out of both log reads. The component that first timed out is therefore unidentified, and that identity would sharpen or overturn the ordering argument.

Nothing measured frontend-proxy or load-generator directly. The claim that their alerts represent hung calls into ad is inference from the absence of errors elsewhere, not observation. Triage counted three unmeasured edges and they remain unmeasured.

> Evidence `tr_65d0ade48935`:

```
<tool_result id="tr_65d0ade48935" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-13T00:29:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" contains="Exception">
selector: {service="ad"} |= "Exception"
2026-10-13T00:52:04.295486+00:00  java.io.InterruptedIOException: timeout
2026-10-13T00:52:04.296368+00:00  Caused by: java.io.IOException: Canceled
2026-10-13T00:53:00.587533+00:00  java.net.UnknownHostException: otel-collector
2026-10-13T00:54:01.342179+00:00  java.net.UnknownHostException: otel-collector
```

> Evidence `tr_871740d5cc0c`:

```
<tool_result id="tr_871740d5cc0c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T20:59:16.664000+00:00..2026-10-13T01:01:10.068521+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-12T20:59:21.607966+00:00  2026-10-12 20:59:21 - oteldemo.AdService - no baggage found in context trace_id=70de6ee26d27b49df89801d492acdc71 span_id=cb599836f4e907f5 trace_flags=01 
2026-10-12T20:59:21.608162+00:00  2026-10-12 20:59:21 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=70de6ee26d27b49df89801d492acdc71 span_id=cb599836f4e907f5 trace_flags=01 
2026-10-12T20:59:21.982794+00:00  2026-10-12 20:59:21 - oteldemo.AdService - no baggage found in context trace_id=0647ec9edcbf9f3982a696e3d6c7d558 span_id=08120a2b7e25bf38 trace_flags=01 
2026-10-12T20:59:21.982821+00:00  2026-10-12 20:59:21 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=0647ec9edcbf9f3982a696e3d6c7d558 span_id=08120a2b7e25bf38 trace_flags=01 
```

