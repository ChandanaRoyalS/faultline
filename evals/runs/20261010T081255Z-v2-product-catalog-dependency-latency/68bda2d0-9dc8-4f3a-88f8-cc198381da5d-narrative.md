# Product-catalog response-leg delay cascades to frontend and recommendation

## What the responder saw first

The page arrived as a severity-warning blast radius covering fourteen services, with the entry point named as frontend. Six services were alerting: frontend, frontend-proxy, load-generator, product-catalog, recommendation and checkout. Fifteen edges crossed in the blast radius had no measurements attached to them, so the shape of the graph was suggestive but not evidentiary. The first instinct from the alert list — that checkout was involved in the hot path — did not survive contact with the traces and is addressed below.

The useful early framing was this: nothing in the alert set told us whether this was an error event or a slowness event. That question dominated the first half of the investigation.

## Ruling out an error event

Two separate metric dispatches against product-catalog came back with the same answer on the error dimension: the error ratio is identically zero, with zero variance, across the incident window and across both baselines (one ~32 minutes, one ~2 hours). There is no step at onset, no ramp before it, and no difference whatsoever between incident and baseline behaviour. Sample coverage is continuous throughout, so the service was alive and serving the entire time — no crash, no restart, no telemetry gap.

That closed several lines at once. Product-catalog was not emitting failures that propagated to callers. The change on its network path did not break the request path outright, because a hard breakage would have registered as error-status spans and none appeared. And, importantly, the whole incident had to be describable in a dimension the error channel cannot see.

The dead end here is worth recording in full: both dispatches were *asked* for request rates and latency percentiles, and both returned only the error-ratio template. We never got p50/p95/p99 for product-catalog. Anyone re-opening this should start by actually obtaining those series.

> Evidence `tr_7a4c7ba2e4cc`:

```
<tool_result id="tr_7a4c7ba2e4cc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" template="error-ratio" baseline="2026-10-10T07:15:44.136111+00:00..2026-10-10T07:47:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_8497562b82fa`:

```
<tool_result id="tr_8497562b82fa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T06:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" template="error-ratio" baseline="2026-10-10T04:15:44.136111+00:00..2026-10-10T06:17:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=488 mean=0 min=0 max=0 sd=0
  baseline window: n=439 mean=0 min=0 max=0 sd=0
```

## Logs: a complete blank on both ends

Unfiltered queries for product-catalog and for frontend each returned zero lines across the full ~32-minute window — not zero errors, zero lines of any level. The absence covers the entire window rather than a slice around onset, which reads more like a label mismatch or a delivery gap than a service that went quiet under stress. A healthy service under traffic would produce at least routine output over half an hour.

The practical consequence: there is no self-reported account from either service. Any theory that depended on reading frontend's own words about its upstream calls — timeouts, refused connections, upstream 5xx — is unsupportable from this data, and narrowing the query further cannot help, because the unfiltered form already matched nothing. Log-based triage was blocked and stayed blocked.

> Evidence `tr_8b64d2581ea0`:

```
<tool_result id="tr_8b64d2581ea0" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
no log lines matched {service="product-catalog"} over this window
</tool_result:tr_8b64d2581ea0>
```

> Evidence `tr_c7ae3b3db44f`:

```
<tool_result id="tr_c7ae3b3db44f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_c7ae3b3db44f>
```

## Where the time actually went

Traces carried the investigation. Across ten sampled traces (158 spans) a consistent pattern appears on every caller span into product-catalog: frontend's gRPC GetProduct client spans hold roughly 300–305ms of self-time, and recommendation's ListProducts client span holds roughly 301–302ms, while the matching product-catalog server span opens only 1–2ms after its client parent. Because the server is reached almost immediately, the ~300ms is spent *after* the server returns, on the response leg — not on connection setup or request transmission.

The callers that demonstrably inherit this are frontend (on both the product-detail route and the recommendations route) and recommendation (via get_product_list into ListProducts). On the recommendations route frontend issues four concurrent GetProduct calls which serialize at product-catalog and stretch root latency to about 2.7s.

Three candidate explanations died here. The edge is not the source: frontend-proxy ingress and router egress spans carry 0.1–1.1ms of self-time while wrapping multi-second children, so they pass latency through rather than add it. Frontend application code is not the source: its GET, route and api-route-execution spans are all sub-2ms, with everything concentrated in the gRPC client span. And the slowdown is not broad across the backend: cart's AddItem/GetCart and its underlying key operations complete in fractions of a millisecond to a few milliseconds in the same traces, isolating the problem to the product-catalog path.

> Evidence `tr_e5c454946a85`:

```
<tool_result id="tr_e5c454946a85" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T07:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
service: product-catalog
10 trace(s) shown of 10 found, 158 spans; offsets are from each trace's root

trace 2ab40b7b06d43c7c  root load-generator/user_browse_product  906.3ms  started 2026-10-10T08:13:16.487082+00:00  10 spans
  +0.0ms load-generator/user_browse_product 906.3ms [self 0.5ms]
```

## The change that lines up

In the roughly 1.2 hours before onset, the only recorded changes against product-catalog are seven attach/remove cycles of a traffic-shaping sidecar container in the service's network namespace, all attributed to the platform-automation actor. Each attach applies a fixed 300ms egress delay with zero jitter on eth0; each removal reverts to no shaping. The most recent attach landed about four minutes before onset (T-4m) and no matching removal follows it in the window — it was still in place when the incident began.

The pattern is cyclical (attach, remove, attach, remove), consistent with an automated or scheduled job rather than an operator acting once. Several alternatives were checked against the same record and found absent: no deploy or image rollout, no configuration edit, no flag flip, and no ad-hoc human action. Two further framings were discarded — the delay cannot be bursty, since jitter is specified at zero, so any added time should be a flat offset; and this is not long-standing background state, because the shaping had been removed and freshly re-applied minutes before onset.

The 300ms parameter and the ~300ms response-leg gap in every caller span are the same number, arrived at from independent sources. That correspondence is the spine of the conclusion.

> Evidence `tr_b45878409cfe`:

```
<tool_result id="tr_b45878409cfe" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T08:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" radius="seed" hops="0">
service: product-catalog
7 changes, ranked by suspicion
  #1  4m before onset  2026-10-10T08:13:04.572786+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  18m before onset  2026-10-10T07:58:48.373180+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog's network namespace
```

> Evidence `tr_e5c454946a85`:

```
<tool_result id="tr_e5c454946a85" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T07:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
service: product-catalog
10 trace(s) shown of 10 found, 158 spans; offsets are from each trace's root

trace 2ab40b7b06d43c7c  root load-generator/user_browse_product  906.3ms  started 2026-10-10T08:13:16.487082+00:00  10 spans
  +0.0ms load-generator/user_browse_product 906.3ms [self 0.5ms]
```

## What this does not explain

The 300ms offset is the *smaller* of two latency components, and the record should not pretend otherwise. Every GetProduct path carries a sql.conn.query leg of roughly 600–604ms (roughly 300–301ms on the ListProducts path), which is the single largest contributor in the ~900ms fast traces. Worse, in about half the sampled traces the product-catalog server span itself holds 1205–1511ms of self-time beyond its child query, with the query starting 1.2–1.5s after the server span opens. That is time spent waiting inside the service before the database call is even issued. A flat 300ms egress offset does not account for any of this. Queuing backpressure, connection-pool saturation, or an independently slow datastore all remain live.

A second gap: all sampled traces cluster between T-4m and T-1.5m, with none at or near onset itself, even though the query window extended past it. The step is inferred from ten traces plus a change record, never confirmed against product-catalog's own latency percentiles.

Finally, every source used here is untrusted and uncorroborated, and the two sources that would normally cross-check each other — logs and latency metrics — both came back empty or off-target.

> Evidence `tr_e5c454946a85`:

```
<tool_result id="tr_e5c454946a85" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T07:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
service: product-catalog
10 trace(s) shown of 10 found, 158 spans; offsets are from each trace's root

trace 2ab40b7b06d43c7c  root load-generator/user_browse_product  906.3ms  started 2026-10-10T08:13:16.487082+00:00  10 spans
  +0.0ms load-generator/user_browse_product 906.3ms [self 0.5ms]
```

> Evidence `tr_7a4c7ba2e4cc`:

```
<tool_result id="tr_7a4c7ba2e4cc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" template="error-ratio" baseline="2026-10-10T07:15:44.136111+00:00..2026-10-10T07:47:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_8497562b82fa`:

```
<tool_result id="tr_8497562b82fa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T06:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" template="error-ratio" baseline="2026-10-10T04:15:44.136111+00:00..2026-10-10T06:17:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=488 mean=0 min=0 max=0 sd=0
  baseline window: n=439 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_8b64d2581ea0`:

```
<tool_result id="tr_8b64d2581ea0" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
no log lines matched {service="product-catalog"} over this window
</tool_result:tr_8b64d2581ea0>
```

> Evidence `tr_c7ae3b3db44f`:

```
<tool_result id="tr_c7ae3b3db44f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_c7ae3b3db44f>
```

## Conclusion and disposition

Reading: a platform-automation traffic-shaping sidecar attached to product-catalog's network namespace at roughly T-4m, applying a fixed 300ms zero-jitter egress delay on eth0, still in place at onset with no matching removal. Every caller span into product-catalog carries a matching ~300–305ms on the response leg. Product-catalog returns no errors at all in either window, so this is a pure slowness event: frontend, recommendation and the rest of the alerting set degraded because they waited, with four concurrent GetProduct calls on the recommendations route serializing to ~2.7s.

Confidence: medium. Fix class: revert the configuration — remove the shaping and ensure the automation that applies it cannot leave an attach outstanding.

Note for whoever picks this up: checkout alerted but never appeared in any sampled trace. The only entry points observed were load-generator browse, recommendations and add-to-cart. Treat checkout's inclusion in the blast radius as unexplained rather than as a caller on the hot path.

> Evidence `tr_b45878409cfe`:

```
<tool_result id="tr_b45878409cfe" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T08:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" radius="seed" hops="0">
service: product-catalog
7 changes, ranked by suspicion
  #1  4m before onset  2026-10-10T08:13:04.572786+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  18m before onset  2026-10-10T07:58:48.373180+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog's network namespace
```

> Evidence `tr_e5c454946a85`:

```
<tool_result id="tr_e5c454946a85" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T07:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00">
service: product-catalog
10 trace(s) shown of 10 found, 158 spans; offsets are from each trace's root

trace 2ab40b7b06d43c7c  root load-generator/user_browse_product  906.3ms  started 2026-10-10T08:13:16.487082+00:00  10 spans
  +0.0ms load-generator/user_browse_product 906.3ms [self 0.5ms]
```

> Evidence `tr_7a4c7ba2e4cc`:

```
<tool_result id="tr_7a4c7ba2e4cc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T07:47:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" template="error-ratio" baseline="2026-10-10T07:15:44.136111+00:00..2026-10-10T07:47:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_8497562b82fa`:

```
<tool_result id="tr_8497562b82fa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T06:17:31.664000+00:00..2026-10-10T08:19:19.191889+00:00" template="error-ratio" baseline="2026-10-10T04:15:44.136111+00:00..2026-10-10T06:17:31.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=488 mean=0 min=0 max=0 sd=0
  baseline window: n=439 mean=0 min=0 max=0 sd=0
```

