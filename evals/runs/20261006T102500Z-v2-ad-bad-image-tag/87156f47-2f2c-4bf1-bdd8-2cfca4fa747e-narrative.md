# Ads calls refused from the frontend; ad service never came back after an image churn

## What was visible first

Two pages arrived together: frontend and frontend-proxy. Nothing else alerted, which set the initial framing badly — the edge is where the symptom surfaced, not where it originated. The blast radius was counted at eight services and the severity was called critical, but the first look at the frontend's own numbers argued against a total outage: the error ratio over the window averaged about 4.2% and peaked near 8.9%, across 208 samples, with plenty of samples at zero. Intermittent bursts on one route, not a service down. Worth recording as the first correction of the day: the paging service was mostly healthy.

One caveat on that metric that cost time later — the comparison window for the preceding hour returned no samples at all, so the apparent jump "from zero" is absence of baseline data, not a measured pre-incident rate. Request rate and p95 were never actually returned by that call; only the error-ratio template ran.

> Evidence `tr_a556759caeaa`:

```
<tool_result id="tr_a556759caeaa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" template="error-ratio" baseline="2026-10-06T08:28:42.603040+00:00..2026-10-06T09:30:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=208 mean=0.04158 min=0 max=0.08921 sd=0.03253
  baseline window: no samples
```

## Following the error down the trace

The traces settled it quickly. Of ten frontend traces sampled (198 spans), exactly one carried errors: the /api/data path. The error propagates from the load-generator GET through frontend-proxy ingress and egress, frontend's GET, the /api/data handler, and stops at the frontend's own client span for the AdService GetAds gRPC call. That span is a leaf — no ad-side server span beneath it — and it fails in roughly 0.2ms inside a 4.0ms trace.

Two readings follow. The failure is fast, not a hang, so nothing was timing out. And the absence of a child span means the call was refused at or before ad produced any span, which is the shape of an RPC that never reached a running server.

What the trace view would not give us: the gRPC status code or message. Only span names, timings, and an ERROR marker were exposed. "Unavailable/refused" is an inference from the leaf shape and the sub-millisecond duration, not something read off the span. That remains open.

> Evidence `tr_3debc72cec5a`:

```
<tool_result id="tr_3debc72cec5a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00">
service: frontend
10 trace(s) shown of 10 found, 198 spans; offsets are from each trace's root

trace 5149cf348c03d0a1  root load-generator/user_checkout_single  33.5ms  started 2026-10-06T10:00:50.696262+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 33.5ms [self 13.1ms]
```

## The dead ends, which are most of the record

**product-catalog.** Checked twice and cleared twice. Its change history over the queried window is completely empty — no rollouts, no environment edits, no flag flips. Its span-metrics series returned no samples at all, in the incident window *and* in the preceding baseline hour, so the emptiness predates the incident and is not a symptom; the service simply is not reporting under that label. In the traces, GetProduct and ListProducts appear repeatedly, all successful, with SQL child spans consistently under about a millisecond.

**frontend itself.** The change log holds nothing for it either — no deploy, no config edit, no flag. A frontend rollback would have had no target. Note the window flaw though: the query ran from onset forward about 24 hours, so it says nothing about changes made *before* onset. Same flaw on the product-catalog query. Neither service is fully excluded on pre-onset changes; they are only excluded on in-window ones.

**frontend-proxy.** Looked guilty because it paged. The proxy spans carry the error only as inherited propagation from the child chain, and a sibling proxy request in the same trace succeeds. Routing was fine.

**cart and Redis, checkout, recommendation, product-reviews.** All present in sampled traces, all sub-millisecond or otherwise unremarkable, no error markers anywhere. The 49-span checkout trace completed in 33.5ms clean end to end.

**Latency as a hypothesis.** Dropped early. The slowest sampled trace was 33.5ms; the rest 4–14ms. Nothing stalled.

> Evidence `tr_251454706271`:

```
<tool_result id="tr_251454706271" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_251454706271>
```

> Evidence `tr_7dd5c4871cd1`:

```
<tool_result id="tr_7dd5c4871cd1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_7dd5c4871cd1>
```

> Evidence `tr_7529fa721568`:

```
<tool_result id="tr_7529fa721568" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" template="error-ratio" baseline="2026-10-06T08:28:42.603040+00:00..2026-10-06T09:30:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3debc72cec5a`:

```
<tool_result id="tr_3debc72cec5a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00">
service: frontend
10 trace(s) shown of 10 found, 198 spans; offsets are from each trace's root

trace 5149cf348c03d0a1  root load-generator/user_checkout_single  33.5ms  started 2026-10-06T10:00:50.696262+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 33.5ms [self 13.1ms]
```

## The ad service, and the turn

Ad's change history is the opposite of everyone else's: five entries, all image reference updates, all attributed to the same automation actor, clustered in the roughly 51 minutes before onset. The remaining ~23 hours of the window are empty. The reference oscillates between one hotfix artifact and unset — three applications, two reverts. Only one distinct artifact is involved, so this is presence/absence churn, not competing versions. The last recorded action before onset is an *application*, about five minutes ahead of the page (≈T−5m), not a revert. So the hotfix was in place going in.

Ad's own logs line up with that to the second. The stream is routine request handling right up to about T−5m30s, then an orderly gRPC server shutdown tied to JVM shutdown, then nothing — no startup banner, no listening line, no further request lines, through the end of the window. The container was recreated onto the hotfix image and did not come back up.

Two things the logs ruled out on the way: this was not an abrupt kill — the shutdown is intentional and there is no allocation-failure signature — and it was not a telemetry export problem, since no exporter or collector-connection errors appear and trace context is intact on the normal lines. Nor was ad logging application errors beforehand; the last thirty-odd lines are unremarkable.

> Evidence `tr_765348808ebd`:

```
<tool_result id="tr_765348808ebd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="candidate_cause" hops="1">
service: ad
5 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T10:25:05.922843+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  18m before onset  2026-10-06T10:12:20.590089+00:00  platform-automation  image reverted: image reference reverted on ad
```

> Evidence `tr_61be572c8a85`:

```
<tool_result id="tr_61be572c8a85" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T10:00:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-06T10:00:31.898246+00:00  2026-10-06 10:00:31 - oteldemo.AdService - no baggage found in context trace_id=74f07ad1300d7c40bf2ba9961f32cf39 span_id=b34ad2df70058524 trace_flags=01 
2026-10-06T10:00:31.898270+00:00  2026-10-06 10:00:31 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=74f07ad1300d7c40bf2ba9961f32cf39 span_id=b34ad2df70058524 trace_flags=01 
2026-10-06T10:00:35.458630+00:00  2026-10-06 10:00:35 - oteldemo.AdService - no baggage found in context trace_id=7389354b35767d292802b06b1c5cfdf2 span_id=e3d3d7282845af1f trace_flags=01 
2026-10-06T10:00:35.458811+00:00  2026-10-06 10:00:35 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=7389354b35767d292802b06b1c5cfdf2 span_id=e3d3d7282845af1f trace_flags=01 
```

## The ad metrics, and why they nearly misled

Ad's error-ratio series does exist and returns data in both windows, so "metrics missing" was not the story. Mean error ratio rose about 4.35x over baseline with a single change point flagged a few minutes after the window opened — tempting, but the absolute level stays low even at peak.

The thing that matters here is coverage. A majority of incident-window samples and a third of baseline samples are undefined — intervals with no ad traffic at all, not intervals with zero errors. Undefined intervals appear in the baseline too, so the gaps are not themselves new. Read naively, this series argues ad was serving some traffic throughout and is a low-volume error contributor. Read against the logs, the thin coverage is exactly what a process that stopped at T−5m looks like under a five-minute rate window. Do not let this series talk you out of the log evidence.

> Evidence `tr_18c4e9525a3b`:

```
<tool_result id="tr_18c4e9525a3b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T10:00:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" template="error-ratio" baseline="2026-10-06T09:28:42.603040+00:00..2026-10-06T10:00:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=80 mean=0.007575 min=0 max=0.0625 sd=0.01429
  baseline window: n=96 mean=0.001741 min=0 max=0.0122 sd=0.003953
```

## Where it landed

The ad service is not running the artifact it should be. Platform-automation churned its image reference five times in the 51 minutes before onset, the last application at ≈T−5m, and ad's process shut down cleanly at ≈T−5m30s and never came back. From the caller side that reads as a refused GetAds RPC — a childless leaf failing in a fifth of a millisecond — which accounts for the frontend's ~4% mean / ~8.9% peak error ratio on the single /api/data route, and for the proxy's page as inherited propagation.

Confidence: medium. Fix class: rollback — redeploy ad at the image it ran before the most recent change and recreate the container. Callers see a connection reset during the recreate; the frontend is the inbound edge that will notice.

> Evidence `tr_765348808ebd`:

```
<tool_result id="tr_765348808ebd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="candidate_cause" hops="1">
service: ad
5 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T10:25:05.922843+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  18m before onset  2026-10-06T10:12:20.590089+00:00  platform-automation  image reverted: image reference reverted on ad
```

> Evidence `tr_61be572c8a85`:

```
<tool_result id="tr_61be572c8a85" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T10:00:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-06T10:00:31.898246+00:00  2026-10-06 10:00:31 - oteldemo.AdService - no baggage found in context trace_id=74f07ad1300d7c40bf2ba9961f32cf39 span_id=b34ad2df70058524 trace_flags=01 
2026-10-06T10:00:31.898270+00:00  2026-10-06 10:00:31 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=74f07ad1300d7c40bf2ba9961f32cf39 span_id=b34ad2df70058524 trace_flags=01 
2026-10-06T10:00:35.458630+00:00  2026-10-06 10:00:35 - oteldemo.AdService - no baggage found in context trace_id=7389354b35767d292802b06b1c5cfdf2 span_id=e3d3d7282845af1f trace_flags=01 
2026-10-06T10:00:35.458811+00:00  2026-10-06 10:00:35 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=7389354b35767d292802b06b1c5cfdf2 span_id=e3d3d7282845af1f trace_flags=01 
```

> Evidence `tr_3debc72cec5a`:

```
<tool_result id="tr_3debc72cec5a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00">
service: frontend
10 trace(s) shown of 10 found, 198 spans; offsets are from each trace's root

trace 5149cf348c03d0a1  root load-generator/user_checkout_single  33.5ms  started 2026-10-06T10:00:50.696262+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 33.5ms [self 13.1ms]
```

> Evidence `tr_a556759caeaa`:

```
<tool_result id="tr_a556759caeaa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" template="error-ratio" baseline="2026-10-06T08:28:42.603040+00:00..2026-10-06T09:30:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=208 mean=0.04158 min=0 max=0.08921 sd=0.03253
  baseline window: no samples
```

## Still open for whoever reads this next

Three gaps, all worth closing before or during the fix.

First, the gRPC status on the failing GetAds span was never recovered. If you can get the status description out of the span store, do — it would turn the refusal from inference into fact.

Second, no container-state or image-pull evidence was gathered at all. Whether ad is stopped, restarting in a loop, or failing to retrieve the image is unsettled. The logs show a clean shutdown and then silence, which is consistent with all three. Check container state directly.

Third, the change record carries no prior value for ad's image, so the rollback target has to be confirmed against the declared compose definition rather than read out of the change log. And because the frontend and product-catalog change queries only looked forward from onset, a pre-onset change on either is not excluded — unlikely given the trace evidence, but not ruled out.

> Evidence `tr_3debc72cec5a`:

```
<tool_result id="tr_3debc72cec5a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00">
service: frontend
10 trace(s) shown of 10 found, 198 spans; offsets are from each trace's root

trace 5149cf348c03d0a1  root load-generator/user_checkout_single  33.5ms  started 2026-10-06T10:00:50.696262+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 33.5ms [self 13.1ms]
```

> Evidence `tr_765348808ebd`:

```
<tool_result id="tr_765348808ebd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="candidate_cause" hops="1">
service: ad
5 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T10:25:05.922843+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  18m before onset  2026-10-06T10:12:20.590089+00:00  platform-automation  image reverted: image reference reverted on ad
```

> Evidence `tr_7dd5c4871cd1`:

```
<tool_result id="tr_7dd5c4871cd1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_7dd5c4871cd1>
```

> Evidence `tr_251454706271`:

```
<tool_result id="tr_251454706271" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T10:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_251454706271>
```

> Evidence `tr_a556759caeaa`:

```
<tool_result id="tr_a556759caeaa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T09:30:31.664000+00:00..2026-10-06T10:32:20.724960+00:00" template="error-ratio" baseline="2026-10-06T08:28:42.603040+00:00..2026-10-06T09:30:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=208 mean=0.04158 min=0 max=0.08921 sd=0.03253
  baseline window: no samples
```

