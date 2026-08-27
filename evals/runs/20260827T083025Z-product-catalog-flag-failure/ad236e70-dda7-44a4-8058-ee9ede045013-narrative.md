# Partial GetProduct failures traced to a feature-flag environment change

## What we saw first

Three pages arrived together at T+0 (08:33:30 UTC): frontend, loadgenerator, and productcatalogservice. Nothing looked like an outage. The first thing worth checking was whether the edge was actually broken or merely reporting someone else's trouble, and frontend's own error-to-total call ratio answered that immediately: non-zero, peaking near 13%, with at least one sample sitting at zero inside the same fifteen-minute view. That last detail mattered more than the peak. A series that touches zero and then climbs is an onset; a series that sits flat at 13% is a long-standing instrumentation artifact or a baseline someone forgot to tune. So we had a real, recent, partial degradation visible at the edge, and frontend was emitting error spans itself rather than passing traffic through cleanly.

productcatalogservice looked the same shape one hop down: error ratio non-zero, peak around 11%, minimum zero, 61 samples continuously collected across the window. Partial, not total. Recent, not chronic. Recorded at the service itself, not attributed to it by a caller.

> Evidence `tr_5135d50e2665`:

```
<tool_result id="tr_5135d50e2665" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1304 n=57
</tool_result:tr_5135d50e2665>
```

> Evidence `tr_3bcb172ff367`:

```
<tool_result id="tr_3bcb172ff367" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1105 n=61
</tool_result:tr_3bcb172ff367>
```

## The traces that settled the direction

Traces from frontend were the turning point. Two of the sampled two hundred spans carried ERROR, both on product-detail/recommendation GET paths. In one, the error chain ran loadgenerator to frontend HTTP GET to frontend's client span for ProductCatalogService/GetProduct to productcatalogservice's own GetProduct server span, every hop marked ERROR. Because the error status was present on the server span, the origin was below frontend, not in frontend's handler.

Two properties of those spans killed most of our candidate theories at once. First, the failing spans were fast: roughly 2ms at productcatalogservice, 3-4ms at frontend's client span, indistinguishable from healthy calls. Nothing was waiting on anything. That rules out timeouts, saturation, and slow dependencies as a class; a deadline being hit leaves a long or truncated span, and there were none. Second, every erroring GetProduct chain contained a client-side child call to a FeatureFlagService GetFlag operation, and that child was absent from the many successful GetProduct chains in the same window. Presence-in-failures, absence-in-successes is about as clean a discriminator as traces offer.

The same traces cleared several neighbours. cartservice AddItem/GetCart chains and their Redis children completed without error in sub-millisecond to low-millisecond times. Both sampled adservice GetAds chains, including the getAdsByCategory child, were clean. recommendationservice was the most tempting false lead: one erroring trace ran through ListRecommendations, but that span and all its recommendationservice children succeeded, and the error appeared only on a subsequent GetProduct fan-out call. Three of the four fan-out GetProduct calls in that trace succeeded. Selective failure, not a dependency outage.

> Evidence `tr_3e7f1d8f4665`:

```
<tool_result id="tr_3e7f1d8f4665" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
service: frontend
200 spans
  5580013145f0229e loadgenerator/HTTP GET 17.8ms
  5580013145f0229e loadgenerator/HTTP GET 15.5ms
  5580013145f0229e frontend/HTTP GET 11.0ms
```

## The change hunt, and the four empty answers

We walked the change history service by service. productcatalogservice: nothing recorded — no deploy, no config edit, no flag flip. frontend: nothing. cartservice: nothing. adservice: nothing. Four consecutive empty results is demoralising in the chair and easy to misread as "changes aren't the story." It wasn't the story for those four services in that window; it was the story one service over.

featureflagservice had exactly one record: at 08:30:29 UTC, roughly three minutes before the pages, a platform-automation actor performed an environment update setting FAULTLINE_ENABLED_FLAGS to enable a product-catalog failure flag. The prior value was unset, so this was an activation rather than a tweak of something already live — which also disposes of the "it has been on for ages and traffic finally exposed it" theory. It was classified as an environment/configuration update, not a deploy or image rollout, and it was attributed to automation, not to a human making an emergency edit. Only one change, so no ambiguity about which of several concurrent edits to blame.

> Evidence `tr_07167402dd7b`:

```
<tool_result id="tr_07167402dd7b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
service: featureflagservice
1 changes
  2026-08-27T08:30:29.272653+00:00  platform-automation  environment updated: FAULTLINE_ENABLED_FLAGS updated on featureflagservice
      None  ->  FAULTLINE_ENABLED_FLAGS=productCatalogFailure
</tool_result:tr_07167402dd7b>
```

> Evidence `tr_57548fb318c3`:

```
<tool_result id="tr_57548fb318c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_57548fb318c3>
```

> Evidence `tr_78d1da2c5f95`:

```
<tool_result id="tr_78d1da2c5f95" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_78d1da2c5f95>
```

> Evidence `tr_b2178d32c35c`:

```
<tool_result id="tr_b2178d32c35c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_b2178d32c35c>
```

> Evidence `tr_be0aa7d04972`:

```
<tool_result id="tr_be0aa7d04972" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no changes recorded for adservice over this window
</tool_result:tr_be0aa7d04972>
```

## Conclusion

productcatalogservice consults featureflagservice on the GetProduct path. From 08:30:29 onward a fraction of GetProduct calls fast-fail, and the failing chains are exactly the ones that make a GetFlag call. The mechanism is the configuration value itself: a failure-simulation flag was switched on in a production path, and the wrongness of that value is precisely what makes the request fail. Severity was critical because the edge was affected, but the blast radius was a partial degradation — roughly 11% at productcatalogservice, 13% at frontend — not an outage. Confidence high. Remediation class is a config revert of FAULTLINE_ENABLED_FLAGS on featureflagservice.

> Evidence `tr_07167402dd7b`:

```
<tool_result id="tr_07167402dd7b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
service: featureflagservice
1 changes
  2026-08-27T08:30:29.272653+00:00  platform-automation  environment updated: FAULTLINE_ENABLED_FLAGS updated on featureflagservice
      None  ->  FAULTLINE_ENABLED_FLAGS=productCatalogFailure
</tool_result:tr_07167402dd7b>
```

> Evidence `tr_3e7f1d8f4665`:

```
<tool_result id="tr_3e7f1d8f4665" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
service: frontend
200 spans
  5580013145f0229e loadgenerator/HTTP GET 17.8ms
  5580013145f0229e loadgenerator/HTTP GET 15.5ms
  5580013145f0229e frontend/HTTP GET 11.0ms
```

> Evidence `tr_3bcb172ff367`:

```
<tool_result id="tr_3bcb172ff367" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1105 n=61
</tool_result:tr_3bcb172ff367>
```

> Evidence `tr_5135d50e2665`:

```
<tool_result id="tr_5135d50e2665" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1304 n=57
</tool_result:tr_5135d50e2665>
```

## Dead ends and things worth keeping

The productcatalogservice log query returned zero lines — not zero error lines, zero lines of any severity — over the incident window. That is implausible for a running service, and the label selector used hyphens (product-catalog-service) where the service name has none. Treat this as a query-shape problem, not evidence of silence. Do not conclude from it that the pipeline is healthy and the service was quiet, and do not conclude the opposite either; an empty result cannot distinguish a wrong label from a dropped pipeline from a crashed pod. The next responder should re-query on the correct label, or enumerate the label set first.

cartservice and adservice returned no metric series at all: not just the error-filtered numerator but the unfiltered total-calls denominator matched nothing. Prometheus itself was fine — it answered successfully with an explicit empty match. So this is a genuine observability gap for those two service identities, and it cuts both ways: they are neither implicated nor cleared by metrics. Only traces speak for them, and traces say they were clean.

Every change query covered only 08:23:30–08:38:30, not the ~2h lookback that was asked for. An earlier change on frontend, productcatalogservice, cartservice or adservice is entirely unexamined.

> Evidence `tr_102d3edfcc22`:

```
<tool_result id="tr_102d3edfcc22" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_102d3edfcc22>
```

> Evidence `tr_7ba72dab164d`:

```
<tool_result id="tr_7ba72dab164d" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_7ba72dab164d>
```

> Evidence `tr_191641c59b56`:

```
<tool_result id="tr_191641c59b56" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))' over this window
</tool_result:tr_191641c59b56>
```

> Evidence `tr_57548fb318c3`:

```
<tool_result id="tr_57548fb318c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_57548fb318c3>
```

> Evidence `tr_78d1da2c5f95`:

```
<tool_result id="tr_78d1da2c5f95" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_78d1da2c5f95>
```

## Still open

No direct confirmation from productcatalogservice's own logs that it read the flag and returned an error on that basis. The causal loop closes only with a corrected log query.

The onset timestamp at productcatalogservice was never pinned. We have the minimum and maximum of the error ratio but not the per-timestamp series, so the 08:30:29 activation is correlated with the pages but not yet proven to precede the first error sample. Pull the series, not the aggregate.

Why only ~11% of GetProduct calls fail rather than all of them is unexplained. Probabilistic flag evaluation, specific product IDs, or a subset of replicas are all live possibilities; three of four fan-out calls in one trace succeeded, which is consistent with any of them.

Triage counted seven services in the blast radius and one unmeasured edge crossed. The featureflagservice hop appears only as a client-side span emitted under productcatalogservice (and separately under recommendationservice); no server-side featureflagservice spans exist in these traces, which is why the dependency is invisible in a service graph built from measured callees. featureflagservice's own health was never measured, and whether recommendationservice's separate GetFlag calls are also affected is unknown.

Finally: the change was made by automation. Whether that automation is on a schedule and will re-apply the flag after a revert is unknown. Check before declaring the incident closed.

> Evidence `tr_102d3edfcc22`:

```
<tool_result id="tr_102d3edfcc22" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_102d3edfcc22>
```

> Evidence `tr_3bcb172ff367`:

```
<tool_result id="tr_3bcb172ff367" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1105 n=61
</tool_result:tr_3bcb172ff367>
```

> Evidence `tr_3e7f1d8f4665`:

```
<tool_result id="tr_3e7f1d8f4665" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
service: frontend
200 spans
  5580013145f0229e loadgenerator/HTTP GET 17.8ms
  5580013145f0229e loadgenerator/HTTP GET 15.5ms
  5580013145f0229e frontend/HTTP GET 11.0ms
```

> Evidence `tr_07167402dd7b`:

```
<tool_result id="tr_07167402dd7b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T08:23:30.583000+00:00..2026-08-27T08:38:30.583000+00:00">
service: featureflagservice
1 changes
  2026-08-27T08:30:29.272653+00:00  platform-automation  environment updated: FAULTLINE_ENABLED_FLAGS updated on featureflagservice
      None  ->  FAULTLINE_ENABLED_FLAGS=productCatalogFailure
</tool_result:tr_07167402dd7b>
```
