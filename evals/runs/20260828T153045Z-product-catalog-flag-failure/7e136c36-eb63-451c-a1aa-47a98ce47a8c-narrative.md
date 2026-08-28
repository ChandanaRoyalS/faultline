# Selective fast-failing catalog lookups surfacing as frontend errors

## What was visible, in order

Alerts landed together on frontend, loadgenerator, and productcatalogservice; severity critical, blast radius seven services, with one edge on the path reported as unmeasured.

Frontend's error-status proportion rose from a clean zero baseline to a peak near 12%. That established a real onset (not a monitoring artifact, not pre-existing noise) and ruled out a hard-down frontend, since most calls still succeeded. But the series was aggregated by service name only, with no per-dependency attribution and no latency companion, so it pointed nowhere.

productcatalogservice's own error ratio was non-zero in the same window. Two passes agreed on character and differed on ceiling — one reporting up to roughly a third of calls across 58 samples, the other up to about 10.6% across 61. Both had a floor of zero and returned to zero inside the window: bursty, not sustained. That excluded a total outage (the ratio never approaches 1.0) and a slow-burn rising floor, and it confirmed the errors were attributed to this service's own span status. Neither pass returned request rate, latency percentiles, or CPU/memory/connection-pool saturation, so the resource dimension was never measured either way.

> Evidence `tr_8f8b891724ff`:

```
<tool_result id="tr_8f8b891724ff" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1218 n=60
</tool_result:tr_8f8b891724ff>
```

> Evidence `tr_98b6b827ea31`:

```
<tool_result id="tr_98b6b827ea31" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.3333 n=58
</tool_result:tr_98b6b827ea31>
```

> Evidence `tr_24fe91908077`:

```
<tool_result id="tr_24fe91908077" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1062 n=61
</tool_result:tr_24fe91908077>
```

## The dead ends worth keeping

Logs were never actually read. Two queries over the full window returned zero lines, no truncation. This briefly looked like a meaningful negative and is not: both used a hyphenated service label value for a service whose name has no hyphens, and the label naming was never verified against the index. The tell is that nothing came back at all, not merely nothing at error level — a service demonstrably serving traffic emits some non-error lines in fifteen minutes. So this supports no claim about panics or error spam, and no first-occurrence timestamp was ever obtained.

Change history was asked the wrong question twice. It returned empty for productcatalogservice, but the query covered only the fifteen-minute onset window rather than the preceding hour. The re-run used identical bounds and returned empty again, which was mistaken for corroboration; a wider window was never tried. What it legitimately supports is narrow: no deploy immediately preceded onset, and no mid-incident hotfix is confounding the signal.

Many downstream suspects cleared on traces: adservice (all GetAds and getAdsByCategory spans succeeded), cartservice (every GetCart/AddItem and Redis child sub-millisecond, no error), recommendationservice (ListRecommendations and children clean), and checkoutservice's own logic. Timeouts and deadline pressure were plausible on the alert profile and contradicted every time. The unmeasured edge stopped mattering for the error-bearing path only, because the deepest ERROR-carrying span is itself instrumented.

> Evidence `tr_b42a58370eb7`:

```
<tool_result id="tr_b42a58370eb7" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_b42a58370eb7>
```

> Evidence `tr_dc952facefe4`:

```
<tool_result id="tr_dc952facefe4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_dc952facefe4>
```

> Evidence `tr_93da289dfd7f`:

```
<tool_result id="tr_93da289dfd7f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_93da289dfd7f>
```

## Where it turned, and what is still open

Sampled frontend error traces gave a continuous chain: loadgenerator, frontend HTTP handler, frontend's outbound client span, and at the bottom a productcatalogservice GetProduct span carrying ERROR. Every error trace ended there. Three details mattered: the failing spans were fast (roughly 0.8–2.9ms, against near-0.0ms for successful ones), so this is a fast-fail status and not a timeout — indeed the slowest frontend requests sampled, 62ms and 64ms, carried no error. The failure was per-call, with sibling GetProduct calls succeeding inside the same trace. And each erroring span carried a FeatureFlagService/GetFlag child that itself succeeded and appeared only on the failing calls. Checkout's PlaceOrder error was inherited: its cart lookup, first product lookup, and currency conversion all succeeded, with only a later product lookup in ERROR.

Conclusion, medium confidence: upstream errors are inherited from a selective error branch in the catalog service's GetProduct handler, gated on a configuration value whose wrongness is itself what breaks the request. Fix class: revert the config.

Still open. First, no change record covering the pre-onset hour was ever queried — the config change is inferred, not observed; run this before acting. Second, the flag lookup's value is unknown, so the causal link rests on co-occurrence in sampled traces. Third, the burstiness is unexplained (specific product IDs, a percentage rollout, or caching), and some frontend errors appeared at the HTTP handler with no child spans, which may be the same cause or a second mode.

> Evidence `tr_31436dddb636`:

```
<tool_result id="tr_31436dddb636" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T15:24:00.583000+00:00..2026-08-28T15:39:00.583000+00:00">
service: frontend
200 spans
  eca709f891024b2a frontend/grpc.hipstershop.CartService/GetCart 1.1ms
  eca709f891024b2a cartservice/hipstershop.CartService/GetCart 0.4ms
  eca709f891024b2a cartservice/HGET 0.2ms
```
