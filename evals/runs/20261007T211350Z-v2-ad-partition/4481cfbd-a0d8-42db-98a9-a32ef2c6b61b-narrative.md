# Ad service alive but cut off: inbound traffic ceased without errors

## What was visible, in order

Three alerts fired together — ad, frontend-proxy, load-generator. That shape mattered: callers paging alongside the callee, with nobody shouting 5xx, suggests hanging rather than failing. Starting from ad, the first question was whether it had begun erroring. It had not. Across a tight ~32-minute comparison and a wider six-hour one, the error ratio sat at or slightly below baseline (roughly 0.39% incident vs 0.49% baseline on the long window), with comparable sampling density on both sides. The useful signal came out sideways: a majority of incident intervals had no defined ratio at all — about 45 of 84 versus 32 of 97 at baseline — meaning no ad spans were recorded in them. Traffic, not correctness, was the anomaly. Traces confirmed it: only ten ad-involving traces in the whole window, nine bunched around T-30m and one isolated at T-8m33s, then nothing. Every trace runs load-generator → frontend-proxy → frontend → ad; ad has no other caller. Server spans stay between ~0.6ms and ~6.7ms throughout, with the final call among the fastest. Ad's own logs show normal request handling early, then, after onset, only OpenTelemetry agent metric-export errors: the exporter cannot resolve the collector hostname, recurring at T+45s and T+1m46s, with the JVM still emitting lines.

> Evidence `tr_0436f1b59aa8`:

```
<tool_result id="tr_0436f1b59aa8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" template="error-ratio" baseline="2026-10-07T20:19:15.020913+00:00..2026-10-07T20:51:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=84 mean=0.06823 min=0 max=0.3683 sd=0.1375
  baseline window: n=97 mean=0.07964 min=0 max=0.7767 sd=0.1852
```

> Evidence `tr_c7c9ce4eccaf`:

```
<tool_result id="tr_c7c9ce4eccaf" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T21:21:16.664000+00:00..2026-10-07T03:21:16.664000+00:00" template="error-ratio" baseline="2026-10-06T15:21:16.664000+00:00..2026-10-06T21:21:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1223 mean=0.003875 min=0 max=0.01389 sd=0.004908
  baseline window: n=1277 mean=0.004852 min=0 max=0.03448 sd=0.007027
```

> Evidence `tr_8e6042e441f7`:

```
<tool_result id="tr_8e6042e441f7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00">
service: ad
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 1cb6612e4a3099f0  root load-generator/user_get_ads  14.9ms  started 2026-10-07T20:51:22.380133+00:00  13 spans
  +0.0ms load-generator/user_get_ads 14.9ms [self 1.0ms]
```

> Evidence `tr_bcf16c853e28`:

```
<tool_result id="tr_bcf16c853e28" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-07T20:51:22.391929+00:00  2026-10-07 20:51:22 - oteldemo.AdService - no baggage found in context trace_id=1cb6612e4a3099f0ec8003958cba71f9 span_id=aee1ee0458f9cd10 trace_flags=01 
2026-10-07T20:51:22.392098+00:00  2026-10-07 20:51:22 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=1cb6612e4a3099f0ec8003958cba71f9 span_id=aee1ee0458f9cd10 trace_flags=01 
2026-10-07T20:51:29.505533+00:00  2026-10-07 20:51:29 - oteldemo.AdService - no baggage found in context trace_id=7a4c975be8db6dab5fb2062fbf390e19 span_id=006f02f15e032d50 trace_flags=01 
2026-10-07T20:51:29.505592+00:00  2026-10-07 20:51:29 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=7a4c975be8db6dab5fb2062fbf390e19 span_id=006f02f15e032d50 trace_flags=01 
```

## Dead ends worth keeping

Ad slow or hung: ruled out — span durations are flat sub-millisecond to few-millisecond right up to the last observed call, with no upward trend as traffic thinned. Crash or restart: ruled out from logs — no shutdown, termination, or startup banner anywhere, and the process is still logging after onset; the metric side agrees indirectly, though restart counts were never retrieved. Ad erroring and clients backing off: ruled out — every sampled trace completes cleanly through ad and back. A flag or flag-provider cause absorbed real effort and yielded nothing: ad emits no outbound spans to flagd or any downstream service at all, its logs contain no flag-evaluation lines, and flagd's change history is empty. A change to ad: change history returned nothing — no deploys, image updates, config edits, or resource-limit changes. But every change query ran forward from onset for ~24 hours, so it establishes absence only for the aftermath, not for the hours before, which is exactly where a change-driven cause would sit. That window was never examined.

> Evidence `tr_8e6042e441f7`:

```
<tool_result id="tr_8e6042e441f7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00">
service: ad
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 1cb6612e4a3099f0  root load-generator/user_get_ads  14.9ms  started 2026-10-07T20:51:22.380133+00:00  13 spans
  +0.0ms load-generator/user_get_ads 14.9ms [self 1.0ms]
```

> Evidence `tr_bcf16c853e28`:

```
<tool_result id="tr_bcf16c853e28" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-07T20:51:22.391929+00:00  2026-10-07 20:51:22 - oteldemo.AdService - no baggage found in context trace_id=1cb6612e4a3099f0ec8003958cba71f9 span_id=aee1ee0458f9cd10 trace_flags=01 
2026-10-07T20:51:22.392098+00:00  2026-10-07 20:51:22 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=1cb6612e4a3099f0ec8003958cba71f9 span_id=aee1ee0458f9cd10 trace_flags=01 
2026-10-07T20:51:29.505533+00:00  2026-10-07 20:51:29 - oteldemo.AdService - no baggage found in context trace_id=7a4c975be8db6dab5fb2062fbf390e19 span_id=006f02f15e032d50 trace_flags=01 
2026-10-07T20:51:29.505592+00:00  2026-10-07 20:51:29 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=7a4c975be8db6dab5fb2062fbf390e19 span_id=006f02f15e032d50 trace_flags=01 
```

> Evidence `tr_9b4a746e1fd2`:

```
<tool_result id="tr_9b4a746e1fd2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-06T21:21:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" radius="seed" hops="0">
no changes recorded for ad over this window
</tool_result:tr_9b4a746e1fd2>
```

> Evidence `tr_4c0d67afa997`:

```
<tool_result id="tr_4c0d67afa997" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-06T21:21:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" radius="seed" hops="0">
no changes recorded for ad over this window
</tool_result:tr_4c0d67afa997>
```

> Evidence `tr_fd7faf55dc4a`:

```
<tool_result id="tr_fd7faf55dc4a" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-06T21:21:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_fd7faf55dc4a>
```

## Where it landed and what is still open

The surviving reading: ad lost network reachability while its process stayed alive. That fits every piece — callers hang rather than receive errors (explaining the simultaneous three-service alert), ad's error ratio stays benign because it is not serving anything to fail, inbound calls stop with no degradation beforehand, and ad's only complaint is a hostname it can no longer resolve. Fix class: reconnect. Confidence is low, and the gaps are the reason. Request rate, latency, CPU/memory, and restart counts for ad were requested but never returned — only the error-ratio template came back, both times, so the traffic story is inferred from the shape of absence rather than measured. Nothing is known about the pre-onset period for changes. And no specialist examined frontend, frontend-proxy, or load-generator directly, so whether traffic stopped at the generator or was blocked en route to ad is unresolved; the traces say only that the proxy and frontend hops were intact for every trace that was observed.

> Evidence `tr_0436f1b59aa8`:

```
<tool_result id="tr_0436f1b59aa8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00" template="error-ratio" baseline="2026-10-07T20:19:15.020913+00:00..2026-10-07T20:51:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=84 mean=0.06823 min=0 max=0.3683 sd=0.1375
  baseline window: n=97 mean=0.07964 min=0 max=0.7767 sd=0.1852
```

> Evidence `tr_c7c9ce4eccaf`:

```
<tool_result id="tr_c7c9ce4eccaf" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T21:21:16.664000+00:00..2026-10-07T03:21:16.664000+00:00" template="error-ratio" baseline="2026-10-06T15:21:16.664000+00:00..2026-10-06T21:21:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1223 mean=0.003875 min=0 max=0.01389 sd=0.004908
  baseline window: n=1277 mean=0.004852 min=0 max=0.03448 sd=0.007027
```

> Evidence `tr_8e6042e441f7`:

```
<tool_result id="tr_8e6042e441f7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T20:51:16.664000+00:00..2026-10-07T21:23:18.307087+00:00">
service: ad
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 1cb6612e4a3099f0  root load-generator/user_get_ads  14.9ms  started 2026-10-07T20:51:22.380133+00:00  13 spans
  +0.0ms load-generator/user_get_ads 14.9ms [self 1.0ms]
```

