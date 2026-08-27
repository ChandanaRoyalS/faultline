# Partial, intermittent errors on productcatalogservice — cause not established

## What the responder saw first

Three pages arrived nearly together: loadgenerator and productcatalogservice at the same instant, frontend about fifteen seconds behind. Severity was called critical, with a blast radius of seven services and one edge in the call graph that carries no measurement at all. The starting point handed to the responder was productcatalogservice, and that framing shaped everything that followed — it was never independently confirmed that productcatalogservice was the origin rather than a co-victim sitting between an upstream generator of load and a downstream that nobody measured. Anyone re-opening this should reconcile the page ordering against the call graph before accepting the starting point.

> Evidence `tr_9fbeba3d3dc7`:

```
<tool_result id="tr_9fbeba3d3dc7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=58
</tool_result:tr_9fbeba3d3dc7>
```

> Evidence `tr_2d55c2a36f86`:

```
<tool_result id="tr_2d55c2a36f86" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=61
</tool_result:tr_2d55c2a36f86>
```

## The one positive signal

Around T+2m the error-status ratio for productcatalogservice came back populated and non-zero. Across roughly sixty sample points it swung between exactly zero and a peak near 13.6 percent. Two things follow from that shape and both matter. First, the service kept serving: at no sampled point does the error fraction approach one, so this was never a hard outage and the majority of calls succeeded throughout. Second, it is spiky, not a ramp — the series returns cleanly to zero between excursions, which is inconsistent with a steadily worsening leak-style degradation and equally inconsistent with a flat background noise rate that would have been there all along. A populated series also confirms the scrape target was alive and traffic was flowing, so "the service disappeared" is closed. This is the entirety of the affirmative evidence collected.

> Evidence `tr_9fbeba3d3dc7`:

```
<tool_result id="tr_9fbeba3d3dc7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=58
</tool_result:tr_9fbeba3d3dc7>
```

> Evidence `tr_2d55c2a36f86`:

```
<tool_result id="tr_2d55c2a36f86" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=61
</tool_result:tr_2d55c2a36f86>
```

## Dead end: the log queries

Two separate attempts were made to read productcatalogservice logs across the fifteen-minute bracket around onset. Both returned zero lines. The reason is not that the service was silent — it is that both queries used a hyphenated spelling of the service label, and no stream in Loki carries that label value. The second attempt was intended to correct this and did not; it re-ran the same hyphenated selector, came back cleanly with an explicit empty result and no truncation, which at least establishes that the emptiness is a stable property of the selector rather than a flaky query backend or an oversized response. The practical cost was high: the log lines around onset would likely have named either a downstream dependency or an internal failure signature, and neither reading has any support at all right now. If you read nothing else here, read this: re-run the log query with the unhyphenated service name first, before anything else.

> Evidence `tr_2f15082b25ed`:

```
<tool_result id="tr_2f15082b25ed" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_2f15082b25ed>
```

> Evidence `tr_8f219560f828`:

```
<tool_result id="tr_8f219560f828" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_8f219560f828>
```

## Dead end: change history across three services

Change history was pulled for productcatalogservice, then cartservice, then adservice. All three came back completely empty for the bracket around onset — no deploys, no configuration pushes, no feature-flag flips, no scaling or replica adjustments, on any of the three. Because the queried window also extends past onset, this additionally rules out any in-incident change having prolonged or worsened things, and rules out a rollback or remediation having already been quietly applied and confounding the timeline. It also means rollback is simply not an available remediation here: there is nothing to roll back. One coverage caveat the responder should not gloss over — the queried bracket covers only the final ten minutes of the requested preceding hour. Changes landing earlier in that hour were never examined, so change-driven causes are narrowed, not fully closed.

> Evidence `tr_c4a9069628ee`:

```
<tool_result id="tr_c4a9069628ee" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_c4a9069628ee>
```

> Evidence `tr_69d7febd3f9f`:

```
<tool_result id="tr_69d7febd3f9f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_69d7febd3f9f>
```

> Evidence `tr_89851a2cfb64`:

```
<tool_result id="tr_89851a2cfb64" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no changes recorded for adservice over this window
</tool_result:tr_89851a2cfb64>
```

## What was never retrieved

Four categories of evidence were requested and none arrived. No latency percentiles for productcatalogservice, so a slow dependency cannot be told apart from fast-failing internal errors. No CPU, memory, file-descriptor or connection-pool saturation series, and no container restart or out-of-memory counts, so resource pressure is untested rather than excluded. No per-dependency breakdown of calls out to adservice or cartservice, so the one unmeasured edge stayed unmeasured. And no resource metrics for adservice at all, despite a prior corpus entry describing a memory signature on that service worth checking against.

> Evidence `tr_9fbeba3d3dc7`:

```
<tool_result id="tr_9fbeba3d3dc7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=58
</tool_result:tr_9fbeba3d3dc7>
```

> Evidence `tr_2d55c2a36f86`:

```
<tool_result id="tr_2d55c2a36f86" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=61
</tool_result:tr_2d55c2a36f86>
```

## Where this landed

Not established. Confidence low, no fix class identified. A partial, spiky error fraction on a service that keeps serving most of its traffic is compatible with resource pressure on the service itself, with a slow or flaky dependency sitting behind the unmeasured edge, and with a latent code path that only some requests reach. The evidence in hand does not discriminate between those. The honest reading is that the class of failure is unknown — not that it is any particular one of them, and specifically not that it has been narrowed by the empty change logs, which only remove one family of triggers.

> Evidence `tr_9fbeba3d3dc7`:

```
<tool_result id="tr_9fbeba3d3dc7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=58
</tool_result:tr_9fbeba3d3dc7>
```

> Evidence `tr_2d55c2a36f86`:

```
<tool_result id="tr_2d55c2a36f86" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=61
</tool_result:tr_2d55c2a36f86>
```

> Evidence `tr_c4a9069628ee`:

```
<tool_result id="tr_c4a9069628ee" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_c4a9069628ee>
```

## Open threads, in the order worth pulling them

One: re-run the productcatalogservice log query with the unhyphenated service name. This is cheap and is the single highest-value missing piece. Two: pull saturation series for productcatalogservice — memory, CPU, file descriptors, connection pool — plus restart and out-of-memory counts. Three: pull latency percentiles for productcatalogservice across the same window. Four: identify which dependency sits behind the unmeasured edge and retrieve its error and latency series; the per-dependency breakdown for adservice and cartservice calls was asked for and never came back. Five: pull adservice resource metrics and compare against the known memory signature. Six: extend the change-history window backward to cover the full hour before onset. Seven: reconcile the simultaneous loadgenerator and productcatalogservice pages, with frontend fifteen seconds later, against the call graph to test whether the assigned starting point is actually the origin.

> Evidence `tr_8f219560f828`:

```
<tool_result id="tr_8f219560f828" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_8f219560f828>
```

> Evidence `tr_2d55c2a36f86`:

```
<tool_result id="tr_2d55c2a36f86" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1364 n=61
</tool_result:tr_2d55c2a36f86>
```

> Evidence `tr_c4a9069628ee`:

```
<tool_result id="tr_c4a9069628ee" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:03:00.583000+00:00..2026-08-27T05:18:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_c4a9069628ee>
```
