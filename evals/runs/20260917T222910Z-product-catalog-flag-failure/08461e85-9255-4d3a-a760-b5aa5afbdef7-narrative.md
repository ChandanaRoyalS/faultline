# Frontend latency with no downstream explanation — origin unestablished

## What was visible, and the early dead ends

The page named frontend, loadgenerator and productcatalogservice at once, with frontend as the declared start point and one edge crossed that carried no measurement. Three alerts along a single request path looks like one upstream problem echoing downward, and that framing drove the first half hour. It was largely wrong.

The first instinct was that something had shipped. The change log for productcatalogservice was queried across a full day ending at the focus time and came back completely empty — no releases, no config edits, no flag flips. Three doors close at once: nothing to roll back, no flag to restore, no operator action to reconstruct.

A parallel look at adservice was more interesting to read than useful. Twelve entries, all memory-limit adjustments by the same automated actor, arranged as six identical paired cycles — limit lowered to 256m, restored roughly ten to twelve minutes later, repeating every four to six hours across the preceding day. The pair nearest to onset ended about 1.9 hours before it, and nothing at all was recorded in those 1.9 hours. The repetition is what kills it: a thing that happens six times a day without incident is background. Record it so the next responder does not spend twenty minutes there.

> Evidence `tr_58c274c424c7`:

```
<tool_result id="tr_58c274c424c7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T22:33:00.583000+00:00..2026-09-17T22:34:54.071925+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_58c274c424c7>
```

> Evidence `tr_20ac9b3ec41c`:

```
<tool_result id="tr_20ac9b3ec41c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T22:33:00.583000+00:00..2026-09-17T22:34:54.071925+00:00" radius="candidate_cause" hops="1">
service: adservice
12 changes, ranked by suspicion
  #1  1.9h before onset  2026-09-17T20:39:43.619416+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
      memory=256m  ->  None
  #2  2.0h before onset  2026-09-17T20:30:58.535347+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
```

## The productcatalogservice signal that dissolved under a wider baseline

Measured against the preceding half hour only, productcatalogservice's error ratio went from exactly zero — 128 consecutive samples, zero standard deviation — to a window mean near 1.1%, peaking around 8.3%, with a single change point about two minutes before the focus time. Zero to something is compelling, and for a while this looked like the origin.

Widening the comparison to four hours undid it. The mean moves from roughly 0.35% to 0.43%, a factor of 1.22, with comparable spread and comparable maxima of 9-10% on both sides. The late excursion is matched in magnitude by two earlier ones well outside the incident. The jump was an artifact of a short, quiet baseline. Reusable lesson: on this service a brief few-percent error excursion is normal variability, and any baseline shorter than a couple of hours manufactures a signal. Even at peak these numbers cannot carry broad user-visible failure.

An attempt to read this service's logs returned nothing, but the selector used a hyphenated service name that does not match the identifier used elsewhere. The result was empty rather than truncated, so the pipeline was fine — treat these logs as unread, not as clean. Both metric queries were asked with latency percentiles and saturation in mind; neither returned them.

> Evidence `tr_bf8410dff58c`:

```
<tool_result id="tr_bf8410dff58c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T22:03:00.583000+00:00..2026-09-17T22:34:54.071925+00:00" template="error-ratio" baseline="2026-09-17T21:31:07.094075+00:00..2026-09-17T22:03:00.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.01057 min=0 max=0.08311 sd=0.02464
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_90363d0ff249`:

```
<tool_result id="tr_90363d0ff249" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T18:33:00.583000+00:00..2026-09-17T22:34:54.071925+00:00" template="error-ratio" baseline="2026-09-17T14:31:07.094075+00:00..2026-09-17T18:33:00.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=968 mean=0.004265 min=0 max=0.1025 sd=0.0171
  baseline window: n=791 mean=0.003502 min=0 max=0.09409 sd=0.01531
```

> Evidence `tr_bc86f5cbbc83`:

```
<tool_result id="tr_bc86f5cbbc83" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T22:03:00.583000+00:00..2026-09-17T22:34:54.071925+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_bc86f5cbbc83>
```

## Frontend: the one surviving signal, and what was never measured

Frontend's own error ratio moved the wrong way — roughly a fifth of its preceding baseline, no sustained departure. That eliminates a whole family of hypotheses: no hard downstream failure propagating up as error status, no error-driven onset, no continuation of a prior degraded state. It is service-level only, so it cannot name which edge changed; it can only say that whatever changed did not change by failing.

Ten traces, thirty-three spans, no error status anywhere. Only two of four outbound edges appeared: GetProduct at roughly 0.7-2.0ms client-side with near-zero server spans, and one GetCart at about 3.5ms with a sub-millisecond Redis HGET beneath it. What survives is the shape of the frontend spans themselves — handler spans of about 4-7ms, one HTTP GET at ~55.5ms, carrying their duration as self-time with no child spans. Latency in self-time with no outbound children is not inherited.

So the direction points inward at frontend, but no mechanism was established. Confidence low, no fix class. Open, in priority order: frontend's own change history and its resource and latency-percentile series were never queried at all — the largest gap, and it exists only because early change queries went elsewhere on the assumption frontend was a victim. Then re-run the catalog log query with the correct label. Then widen the trace sample so "no child spans" can be told apart from "not sampled." The unmeasured edge from triage was never crossed, and loadgenerator's simultaneous alert was never investigated.

> Evidence `tr_d18ea2b81967`:

```
<tool_result id="tr_d18ea2b81967" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T22:03:00.583000+00:00..2026-09-17T22:34:54.071925+00:00" template="error-ratio" baseline="2026-09-17T21:31:07.094075+00:00..2026-09-17T22:03:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.01041 min=0 max=0.08532 sd=0.02391
  baseline window: n=128 mean=0.04815 min=0 max=0.3297 sd=0.1065
```

> Evidence `tr_82279b161d2a`:

```
<tool_result id="tr_82279b161d2a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T22:03:00.583000+00:00..2026-09-17T22:34:54.071925+00:00">
service: frontend
10 trace(s) shown of 10 found, 33 spans; offsets are from each trace's root

trace 51af5987a92738b8  root frontend/HTTP GET  0.9ms  started 2026-09-17T22:33:19.090014+00:00  3 spans
  +0.0ms frontend/HTTP GET 0.9ms [self 0.2ms]
```

