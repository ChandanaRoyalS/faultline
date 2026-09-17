# Product catalog GetProduct errors on the flag-lookup path

## What was visible first

Alerts arrived from three places at once: loadgenerator, frontend, and productcatalogservice. Blast radius was assessed at seven services, severity critical, with productcatalogservice named as the starting point. The initial picture was therefore ambiguous in the usual way — the loadgenerator and frontend alarms are consistent both with productcatalogservice being the source and with it being a victim of something deeper.

The first quantitative look was at error ratio for productcatalogservice over the half hour leading into the report. Against a preceding half-hour baseline that was flat zero on every statistic, the window carried a mean around 1% with a peak near 9%, with the minimum still touching zero across the samples. So: real, new, and bursty rather than a wall. A single crossing of the 5% threshold was detected at roughly T-2m. That late crossing briefly pushed the working theory in the wrong direction — the shape of the series was read as propagated impact rather than origin, which traces later contradicted.

> Evidence `tr_529e7ceb35de`:

```
<tool_result id="tr_529e7ceb35de" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00" template="error-ratio" baseline="2026-09-17T09:58:49.401411+00:00..2026-09-17T10:30:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.0101 min=0 max=0.08847 sd=0.02551
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## What the traces settled

Traces were the turning point. Ten traces came back, clustered around T+1m rather than spread across the requested window. Four carried errors, and in all four the deepest error-flagged span was productcatalogservice's own GetProduct handler. Every flagged span above it was a caller — the frontend HTTP root, the frontend gRPC client span, and on the checkout path checkoutservice's PlaceOrder/prepareOrderItems and its GetProduct client span. Errors were being inherited upward, not arriving from below.

The conditionality was the second useful detail. Each errored GetProduct span had exactly one child, a FeatureFlagService/GetFlag call, and none of those children were flagged. In the same traces, GetProduct spans that made no such child call completed cleanly, and ListProducts was clean throughout. Only the subset of GetProduct calls that took the flag-lookup path failed. The errored spans returned in roughly 0.7–2.0ms, so nothing was timing out or running out of anything; the handler was deciding to fail and returning promptly.

That combination — origin at productcatalogservice, gated on a flag read, fast returns, clean callee — is the basis for the conclusion that a flag value governing the GetProduct path was set to a failing state. Reading the wrong value is what broke the request.

> Evidence `tr_fa36d7823d16`:

```
<tool_result id="tr_fa36d7823d16" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00">
service: productcatalogservice
10 trace(s) shown of 10 found, 136 spans; offsets are from each trace's root

trace 32bdd772a85d2307  root frontend/HTTP GET  2.6ms  started 2026-09-17T11:01:38.285036+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.3ms]
```

## Branches closed by the trace evidence

Several plausible lines were eliminated cheaply once the span tree was in hand, and they are worth recording so nobody re-walks them.

cartservice as the failing callee: its spans (GetCart, HGET, EmptyCart, HMSET) appear in the errored checkout traces and are all clean, and structurally it is a sibling under checkoutservice, never downstream of productcatalogservice.

adservice: absent entirely from the 136 spans across these traces, so not on the path.

featureflagservice returning errors that were merely relayed: the GetFlag child spans are unflagged; the error flag stops at productcatalogservice.

checkoutservice as origin: its flags sit on ancestors of the errored productcatalogservice span, and its sibling calls to currencyservice and cartservice in the same traces are clean. It is a propagator.

A latency or deadline story: the only spans showing meaningful slowness (shippingservice to quoteservice, around 7ms) carry no error flags at all. The slow path and the failing path do not overlap.

Total outage: six of ten traces are fully clean, and errored traces contain successful GetProduct spans alongside the failing one.

> Evidence `tr_fa36d7823d16`:

```
<tool_result id="tr_fa36d7823d16" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00">
service: productcatalogservice
10 trace(s) shown of 10 found, 136 spans; offsets are from each trace's root

trace 32bdd772a85d2307  root frontend/HTTP GET  2.6ms  started 2026-09-17T11:01:38.285036+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.3ms]
```

## Dead ends worth keeping

Two log queries were run and both returned nothing. Both used a hyphenated service label that does not index this service's stream — one over roughly three hours, one over about thirty minutes. Because the emptiness spanned the entire window rather than only the minutes around onset, it is a selector artifact, not evidence of silence or a collection outage. The consequence is that the flag name and the actual error text were never read. Anyone picking this up should re-run with the unhyphenated service identifier before doing anything else.

The change-log queries also came back empty, twice, for productcatalogservice. That is genuine emptiness — the source answered cleanly — and it does rule out a rollout, config edit, flag flip, or remediation to this service concurrent with or after onset, across roughly twenty-four hours forward. But both queries opened at the onset timestamp and ran forward. The hours immediately before onset were never queried, which is precisely where a change would sit. featureflagservice's own change history and its current flag values were never looked at either.

The two metric readings disagree and this should not be papered over. The tight window showed an exactly-zero baseline and a clear novelty. A wider six-hour comparison showed mean error ratio rising roughly 2.9x (about 2.7% to about 7.8%) but with baseline bursts already reaching near 16% and baseline variability exceeding incident variability — i.e. no sustained departure and error activity pre-dating the window. Which framing is correct depends on the baseline chosen. Separately, neither metric query returned latency percentiles or any saturation series; only the error-ratio template was evaluated, so those questions are simply unanswered rather than answered negatively.

> Evidence `tr_f3528a2a9096`:

```
<tool_result id="tr_f3528a2a9096" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T08:00:45.583000+00:00..2026-09-17T11:02:41.764589+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_f3528a2a9096>
```

> Evidence `tr_4dd8bf8248eb`:

```
<tool_result id="tr_4dd8bf8248eb" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_4dd8bf8248eb>
```

> Evidence `tr_0a067fef7256`:

```
<tool_result id="tr_0a067fef7256" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T11:00:45.583000+00:00..2026-09-17T11:02:41.764589+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_0a067fef7256>
```

> Evidence `tr_8b7434752206`:

```
<tool_result id="tr_8b7434752206" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T11:00:45.583000+00:00..2026-09-17T11:02:41.764589+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8b7434752206>
```

> Evidence `tr_b06b351638e9`:

```
<tool_result id="tr_b06b351638e9" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-16T11:00:45.583000+00:00..2026-09-16T17:00:45.583000+00:00" template="error-ratio" baseline="2026-09-16T05:00:45.583000+00:00..2026-09-16T11:00:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=83 mean=0.07798 min=0 max=0.1944 sd=0.03129
  baseline window: n=85 mean=0.02686 min=0 max=0.1607 sd=0.04715
```

> Evidence `tr_529e7ceb35de`:

```
<tool_result id="tr_529e7ceb35de" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00" template="error-ratio" baseline="2026-09-17T09:58:49.401411+00:00..2026-09-17T10:30:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.0101 min=0 max=0.08847 sd=0.02551
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Conclusion and confidence

productcatalogservice is originating the errors itself, on GetProduct, conditional on the flag-lookup path being taken. The fix class is a configuration revert of the flag value governing that path.

Confidence is medium, not high, and the reason is specific: the mechanism is inferred entirely from span structure. No log line was ever retrieved, so the flag name and the error message are unverified. No pre-onset change record was examined. One unmeasured edge was crossed in reaching this conclusion. Before acting, confirm the current flag value at featureflagservice and pull the service's logs under the correct label — either one would convert this from a structural inference into a direct observation.

> Evidence `tr_fa36d7823d16`:

```
<tool_result id="tr_fa36d7823d16" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00">
service: productcatalogservice
10 trace(s) shown of 10 found, 136 spans; offsets are from each trace's root

trace 32bdd772a85d2307  root frontend/HTTP GET  2.6ms  started 2026-09-17T11:01:38.285036+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.3ms]
```

> Evidence `tr_529e7ceb35de`:

```
<tool_result id="tr_529e7ceb35de" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T10:30:45.583000+00:00..2026-09-17T11:02:41.764589+00:00" template="error-ratio" baseline="2026-09-17T09:58:49.401411+00:00..2026-09-17T10:30:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=128 mean=0.0101 min=0 max=0.08847 sd=0.02551
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_f3528a2a9096`:

```
<tool_result id="tr_f3528a2a9096" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T08:00:45.583000+00:00..2026-09-17T11:02:41.764589+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_f3528a2a9096>
```

> Evidence `tr_0a067fef7256`:

```
<tool_result id="tr_0a067fef7256" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T11:00:45.583000+00:00..2026-09-17T11:02:41.764589+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_0a067fef7256>
```

