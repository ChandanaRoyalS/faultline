# Ad service cut off from the network while still serving; callers hang

## What we saw, in order

Three pages arrived close together: frontend-proxy and load-generator at the leading edge (clock 02:26:31), with ad following roughly a minute later at 02:27:31. Five services in the blast radius, severity critical, walk started from frontend-proxy, three unmeasured edges crossed. The ordering — callers shouting before the callee — framed everything that followed.

The obvious first story, that frontend was drowning in errors from a downstream, did not survive. Frontend's aggregate span error ratio was flat zero across all 128 samples in the window. Worse for the framing, the preceding comparison window averaged roughly 9% error with peaks near 29%. All the error signal sits before the declared window, not inside it; the window appears offset from the disturbance it was drawn around. Note also that this series is aggregated by service only, with no per-dependency dimension, so it could never have named ad on its own.

> Evidence `tr_87c23a856e03`:

```
<tool_result id="tr_87c23a856e03" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" template="error-ratio" baseline="2026-10-12T01:24:46.473218+00:00..2026-10-12T01:56:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.0933 min=0 max=0.2917 sd=0.1197
```

## Chasing ad's error rate — a dead end that paid off sideways

Two separate metric pulls targeted ad's error ratio on different windows. Both said nothing was wrong: the incident window averaged about 0.4% error with a max near 1.2%, at or slightly below baseline (roughly 0.91x), with incident min/max/variance all sitting inside the baseline envelope. That killed three readings at once — ad as the error-emitting origin, a step-change at onset, and a gradual degradation ramp. It also killed the brownout theory: a service erroring on everything drives the ratio toward 1.0, and this one stayed low wherever it was defined.

The payoff was accidental. Sixteen intervals in the incident window had no defined value at all, versus zero in baseline; the second pull showed roughly 742 datapoints against 1441 for an equal-length comparison. The ratio is undefined when the denominator is zero. Missing denominators mean missing span metrics — telemetry that never left the pod.

Caveat for whoever reads this next: both dispatches returned only the error-ratio template. Latency, request volume, memory, CPU and restarts were asked for and never retrieved.

> Evidence `tr_c134676a6942`:

```
<tool_result id="tr_c134676a6942" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" template="error-ratio" baseline="2026-10-12T01:24:46.473218+00:00..2026-10-12T01:56:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=112 mean=0.004927 min=0 max=0.02564 sd=0.006427
  baseline window: n=128 mean=0.003994 min=0 max=0.01333 sd=0.00523
```

> Evidence `tr_f47c2221b2ec`:

```
<tool_result id="tr_f47c2221b2ec" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T02:26:31.664000+00:00..2026-10-11T08:26:31.664000+00:00" template="error-ratio" baseline="2026-10-10T20:26:31.664000+00:00..2026-10-11T02:26:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=742 mean=0.003643 min=0 max=0.01205 sd=0.00456
  baseline window: n=1441 mean=0.004003 min=0 max=0.01562 sd=0.005002
```

## Logs, and the shape of onset

A broad log pull showed ad handling requests cleanly at 01:56:33–01:56:55 with trace context attached, and then an UnknownHostException against the OpenTelemetry collector at 02:27:49. That result retained only the oldest eight and newest thirty-two lines, so the entire middle — including the 02:27:31 alert — was missing. The follow-up closed the gap.

Filtering for exceptions across the full window: nothing before 02:20:15. Then two interrupted-IO timeout plus cancellation exceptions at 02:20:15 and 02:20:47, about 32s apart. Then, from 02:21:43 through 02:27:49, eight unknown-host exceptions naming the collector endpoint on a near-exact 60-second cadence, the last explicitly a name-resolution failure.

This eliminated the remaining alternatives. The process logged at both ends of the window and retried on a steady rhythm, so it was neither dead nor crashlooping. Every exception is network-layer, with the stack sitting entirely in the OTLP exporter's OkHttp sender path on a background thread — no ad-serving or persistence frames. And the collector's own health is untested, because the failures occur at name lookup before any connection is opened.

> Evidence `tr_7fc0ec7ab852`:

```
<tool_result id="tr_7fc0ec7ab852" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-12T01:56:33.483491+00:00  2026-10-12 01:56:33 - oteldemo.AdService - no baggage found in context trace_id=87edb5e09c3e9e9a45323d1a74bda456 span_id=479d1f7f40452a68 trace_flags=01 
2026-10-12T01:56:33.483562+00:00  2026-10-12 01:56:33 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=87edb5e09c3e9e9a45323d1a74bda456 span_id=479d1f7f40452a68 trace_flags=01 
2026-10-12T01:56:35.723158+00:00  2026-10-12 01:56:35 - oteldemo.AdService - no baggage found in context trace_id=54a27cc1f9046cb85dc4c44b958121c8 span_id=ea408ecd5f8fed64 trace_flags=01 
2026-10-12T01:56:35.723200+00:00  2026-10-12 01:56:35 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=54a27cc1f9046cb85dc4c44b958121c8 span_id=ea408ecd5f8fed64 trace_flags=01 
```

> Evidence `tr_7cbb7774eda9`:

```
<tool_result id="tr_7cbb7774eda9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" contains="Exception">
selector: {service="ad"} |= "Exception"
2026-10-12T02:20:15.617974+00:00  java.io.InterruptedIOException: timeout
2026-10-12T02:20:15.621886+00:00  Caused by: java.io.IOException: Canceled
2026-10-12T02:20:47.316139+00:00  java.io.InterruptedIOException: timeout
2026-10-12T02:20:47.316482+00:00  Caused by: java.io.IOException: Canceled
```

## Change history and traces: both ruled out

Both change-history pulls returned empty, and empty is the finding. For ad, the window reached roughly 24 hours before onset and held nothing — no deploys, config pushes or flag changes. A practical consequence worth remembering under pressure: there was no prior version to roll back to, so rollback was never a lever and effort should have moved on at once. For flagd, one hop out, also empty — but read its window carefully, since it starts at onset and runs forward, covering post-onset remediation while leaving the minutes immediately before onset uncovered.

The trace pull on frontend looked promising and turned out not to matter. Ten traces, 168 spans, no errored or timed-out span on any outbound hop, and exactly one trace touching ad (2.5ms client, 1.5ms server). Every sampled trace falls between 01:56:36 and 01:57:00 — the first ninety seconds of a thirty-two-minute window, some twenty-three minutes before the first exception. It did usefully clear the neighbours: cart/Redis sub-millisecond, frontend self-times under 3ms, and the slowest hops normal-magnitude work rather than distress.

> Evidence `tr_8ca45e663bc4`:

```
<tool_result id="tr_8ca45e663bc4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T02:26:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" radius="seed" hops="0">
no changes recorded for ad over this window
</tool_result:tr_8ca45e663bc4>
```

> Evidence `tr_c96cdeb4c480`:

```
<tool_result id="tr_c96cdeb4c480" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T02:26:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_c96cdeb4c480>
```

> Evidence `tr_bbc68afa079b`:

```
<tool_result id="tr_bbc68afa079b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00">
service: frontend
10 trace(s) shown of 10 found, 168 spans; offsets are from each trace's root

trace 15deed4b6fe5eed9  root load-generator/user_get_recommendations  12.2ms  started 2026-10-12T01:56:36.714721+00:00  25 spans
  +0.0ms load-generator/user_get_recommendations 12.2ms [self 0.4ms]
```

## Where it landed, and what is still open

Conclusion: ad lost network reachability — name resolution in particular — while its process stayed alive and kept serving. The error ratio never moves because ad is not failing requests, it is failing to report them; the missing span-metric denominators are telemetry that cannot leave the pod. Frontend's flat-zero error ratio means its ad calls are not erroring but hanging, which explains why the callers paged a minute ahead of ad itself. No change act is recorded for ad or flagd. Confidence: medium. Fix class: reconnect.

Three things remain unsettled. The only host named in any resolution failure is the collector; no dispatch showed ad failing to reach a product dependency, so a broad loss of reachability versus a collector/DNS-only outage is inferred from caller alerts and metric gaps, not observed. No latency or volume series was ever retrieved for ad or frontend, so the 'callers hang to deadline' step is unconfirmed by measurement. And frontend-proxy and load-generator, which alerted first, were never dispatched against at all — nothing here rules out a problem at the proxy layer independent of ad.

> Evidence `tr_7cbb7774eda9`:

```
<tool_result id="tr_7cbb7774eda9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" contains="Exception">
selector: {service="ad"} |= "Exception"
2026-10-12T02:20:15.617974+00:00  java.io.InterruptedIOException: timeout
2026-10-12T02:20:15.621886+00:00  Caused by: java.io.IOException: Canceled
2026-10-12T02:20:47.316139+00:00  java.io.InterruptedIOException: timeout
2026-10-12T02:20:47.316482+00:00  Caused by: java.io.IOException: Canceled
```

> Evidence `tr_87c23a856e03`:

```
<tool_result id="tr_87c23a856e03" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T01:56:31.664000+00:00..2026-10-12T02:28:16.854782+00:00" template="error-ratio" baseline="2026-10-12T01:24:46.473218+00:00..2026-10-12T01:56:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.0933 min=0 max=0.2917 sd=0.1197
```

> Evidence `tr_f47c2221b2ec`:

```
<tool_result id="tr_f47c2221b2ec" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T02:26:31.664000+00:00..2026-10-11T08:26:31.664000+00:00" template="error-ratio" baseline="2026-10-10T20:26:31.664000+00:00..2026-10-11T02:26:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=742 mean=0.003643 min=0 max=0.01205 sd=0.00456
  baseline window: n=1441 mean=0.004003 min=0 max=0.01562 sd=0.005002
```

