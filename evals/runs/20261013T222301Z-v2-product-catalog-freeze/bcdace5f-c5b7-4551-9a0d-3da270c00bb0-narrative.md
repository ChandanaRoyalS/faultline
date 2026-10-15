# Ad-serving route stalls behind a silent ad service; proxy abandons at its cutoff

## What was visible, in order

Three services paged within minutes: frontend-proxy, load-generator, frontend. That shape reads like an edge problem on arrival, and the blast-radius count (nine services, seven unmeasured edges) made it look wider than it was.

The proxy error ratio was the first anchor. Against the half hour immediately prior it went from effectively nothing to roughly 4% mean, peaking near 27%, as a single discrete step at T+0 rather than a ramp — more than 160 baseline standard deviations out, so not noise. Two things mattered for direction: most requests still succeeded, so this was never a total outage; and the query aggregated by service name only, with no route or upstream dimension, so it could not say which traffic was failing. That gap sent the investigation to traces.

Ten sampled proxy traces settled it. Nine were ordinary and fast (3-20ms): cart, product browse, add-to-cart, recommendations. Exactly one carried an error — the user_get_ads flow, where proxy ingress ended at about 15s in error. The failing hop is frontend's gRPC call to AdService/GetAds from /api/data, with nearly all elapsed time as self-time on that client span.

The reframing detail: 15s is a proxy-side cutoff, not the real duration. The frontend's GetAds client span stayed outstanding several hundred seconds longer (~667s). When ad's server span and getAdsByCategory finally run they take single-digit milliseconds, starting hundreds of seconds after the call opened. Time is spent before the handler, not inside it. Inside that same failing trace, a second independent proxy-to-frontend pair completed in milliseconds.

> Evidence `tr_f7ded29ec077`:

```
<tool_result id="tr_f7ded29ec077" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T21:57:31.664000+00:00..2026-10-13T22:29:22.456275+00:00" template="error-ratio" baseline="2026-10-13T21:25:40.871725+00:00..2026-10-13T21:57:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.03954 min=0 max=0.2695 sd=0.06752
  baseline window: n=128 mean=9.272e-05 min=0 max=0.0007657 sd=0.0002464
```

> Evidence `tr_6027eb63aade`:

```
<tool_result id="tr_6027eb63aade" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T21:57:31.664000+00:00..2026-10-13T22:29:22.456275+00:00">
service: frontend-proxy
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 14254fff406531cc  root load-generator/user_view_cart  5.8ms  started 2026-10-13T21:59:09.104362+00:00  10 spans
  +0.0ms load-generator/user_view_cart 5.8ms [self 0.6ms]
```

## Dead ends worth keeping

The proxy itself was the obvious suspect since it alerted first and owns the error. Ruled out: its ingress and egress spans carry near-zero self-time in every trace, including the healthy concurrent ingress inside the failing one. It only errors after waiting on something that never returns.

Cart and Redis (GetCart, AddItem, HGET/HMSET/EXPIRE) all finished well under a millisecond. Product-catalog and its SQL queries completed sub-millisecond to low-millisecond everywhere. The recommendation fan-out — five parallel GetProduct calls, a tempting concurrency suspect — completed end to end in about 20ms. Broad frontend slowness was excluded because every other frontend route rendered in milliseconds. The load-generator-to-proxy network path was excluded because the client span's time is almost entirely accounted for by nested spans. Ad being down was excluded too: its server spans do appear and execute quickly, just far too late.

Ad's own logs over six hours are strikingly boring — only routine INFO request lines with trace context, no errors, no exceptions, no rejection or pool-exhaustion messages, no startup or shutdown banner, and a varied request mix. That closed out crash/restart, pool exhaustion, and application exceptions. The GC line of inquiry is only weakly closed, since GC logging may simply not be enabled.

> Evidence `tr_6027eb63aade`:

```
<tool_result id="tr_6027eb63aade" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T21:57:31.664000+00:00..2026-10-13T22:29:22.456275+00:00">
service: frontend-proxy
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 14254fff406531cc  root load-generator/user_view_cart  5.8ms  started 2026-10-13T21:59:09.104362+00:00  10 spans
  +0.0ms load-generator/user_view_cart 5.8ms [self 0.6ms]
```

> Evidence `tr_754f439f95c5`:

```
<tool_result id="tr_754f439f95c5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T22:27:31.664000+00:00..2026-10-13T04:27:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-12T22:27:33.541073+00:00  2026-10-12 22:27:33 - oteldemo.AdService - no baggage found in context trace_id=f66ea456353e47b69627d9bde11bc685 span_id=9e38d1369c7653fe trace_flags=01 
2026-10-12T22:27:33.541107+00:00  2026-10-12 22:27:33 - oteldemo.AdService - Targeted ad request received for [accessories] trace_id=f66ea456353e47b69627d9bde11bc685 span_id=9e38d1369c7653fe trace_flags=01 
2026-10-12T22:27:35.568584+00:00  2026-10-12 22:27:35 - oteldemo.AdService - no baggage found in context trace_id=84d175e6bd0899d06c35a05778d26dce span_id=b8b4cf1c329deeb3 trace_flags=01 
2026-10-12T22:27:35.568727+00:00  2026-10-12 22:27:35 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=84d175e6bd0899d06c35a05778d26dce span_id=b8b4cf1c329deeb3 trace_flags=01 
```

## Conclusion and what remains unexamined

The failing flow is confined to user_get_ads: proxy ingress, frontend /api/data, frontend's call to AdService/GetAds. Everything else through the same proxy and frontend process is healthy in the same seconds. The signature is a process that is up but not progressing: the socket still accepts so calls are admitted without connection errors, the handler is fast when it finally runs, and the whole gap sits between acceptance and execution. Ad's metrics show 72 intervals with no defined error ratio at all — stretches with zero traffic, where the baseline has none — which is the same phenomenon from the other side. Confidence medium; indicated remediation class is a restart of ad.

Three gaps, all in what was looked at rather than what was found. First, both change-log queries (proxy and ad) returned genuinely empty results, but both windows ran forward from onset by about twenty-four hours, not backward — the hours before onset were never searched, so a prior deploy or config edit remains unexamined. What they do legitimately exclude is anything ongoing or subsequent: no rollout in flight, no quiet rollback explaining recovery. The proxy query also covered the seed service at zero hops only. Second, the only ad metric retrieved was span error ratio — no CPU, heap, GC, thread-pool or in-flight series — so saturation on the ad side is neither confirmed nor excluded. Third, ad's log result was truncated to the oldest eight and newest thirty-two lines, leaving the middle of the window unobserved and no coverage overlapping onset itself.

> Evidence `tr_6027eb63aade`:

```
<tool_result id="tr_6027eb63aade" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T21:57:31.664000+00:00..2026-10-13T22:29:22.456275+00:00">
service: frontend-proxy
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 14254fff406531cc  root load-generator/user_view_cart  5.8ms  started 2026-10-13T21:59:09.104362+00:00  10 spans
  +0.0ms load-generator/user_view_cart 5.8ms [self 0.6ms]
```

> Evidence `tr_0bbeab3dc343`:

```
<tool_result id="tr_0bbeab3dc343" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T22:27:31.664000+00:00..2026-10-13T04:27:31.664000+00:00" template="error-ratio" baseline="2026-10-12T16:27:31.664000+00:00..2026-10-12T22:27:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1369 mean=0.008293 min=0 max=0.3684 sd=0.03883
  baseline window: n=430 mean=0.003727 min=0 max=0.02381 sd=0.005044
```

> Evidence `tr_6db6c50998d3`:

```
<tool_result id="tr_6db6c50998d3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T22:27:31.664000+00:00..2026-10-13T22:29:22.456275+00:00" radius="candidate_cause" hops="1">
no changes recorded for ad over this window
</tool_result:tr_6db6c50998d3>
```

