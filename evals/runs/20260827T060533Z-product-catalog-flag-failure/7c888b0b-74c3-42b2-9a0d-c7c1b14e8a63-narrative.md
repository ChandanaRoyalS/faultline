# Bursty partial errors at the storefront, origin near the product catalog tier — cause not established

## What was visible, in order

Three alerts arrived together: frontend, loadgenerator, and productcatalogservice. Blast radius was seven services with the entry point at frontend, and triage noted one edge leaving frontend that was never instrumented in this investigation.

Set loadgenerator aside first. It is the synthetic client; when the storefront errors, the generator errors. It restated frontend's condition and carried no independent information.

The two real signals had the same silhouette. Frontend's span error ratio was intermittent, peaking near 16.4% in one query and near 10.4% in another, with a floor of zero in both. productcatalogservice showed the same pattern on its own spans — a peak near 20% in one query, near 12.5% in another, floor at zero, with a non-zero call denominator at every point. The service stayed up and served the large majority of its traffic throughout, and the errors were completed-but-failed RPCs attributed to its own spans rather than relayed from elsewhere.

That closes several doors: no total outage, no crashloop, no routing or discovery drop, no flat background error rate, and no broken metrics pipeline — both frontend series returned populated and untruncated. Frontend is also not an innocent bystander; its own spans carry errors.

> Evidence `tr_002b87d7ee68`:

```
<tool_result id="tr_002b87d7ee68" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1636 n=59
</tool_result:tr_002b87d7ee68>
```

> Evidence `tr_105c48f50895`:

```
<tool_result id="tr_105c48f50895" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1036 n=61
</tool_result:tr_105c48f50895>
```

> Evidence `tr_4ca828b27368`:

```
<tool_result id="tr_4ca828b27368" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.2 n=58
</tool_result:tr_4ca828b27368>
```

> Evidence `tr_6eae261bb752`:

```
<tool_result id="tr_6eae261bb752" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.125 n=61
</tool_result:tr_6eae261bb752>
```

## The dead ends — read these before repeating them

Logs. Two attempts to pull productcatalogservice logs returned zero lines. Both used a hyphenated label value that does not match the service name under investigation. The first is easy to misread as "the service logged nothing" — it did not. The response was empty of all lines, not just error lines, and was empty rather than truncated. An active service serving traffic does not emit zero lines across fifteen minutes. The backend and window are fine; the response was well-formed, not an error. Try the unhyphenated service value, or a different key entirely — app, job, container — before concluding anything about log content.

Change history. Queries for frontend and productcatalogservice all returned empty: no deploys, rollbacks, config edits, or flag flips. Taken narrowly that rules out a release or flag change landing close to onset, and it means a rollback has no target. But each query was asked for the preceding hour and actually executed from roughly T-10m to T+5m. The fifty minutes before that were never examined, and two specialists flagged it independently. The results are also scoped to changes owned by these two services, so shared platform config and upstream dependency changes remain unexamined.

Attribution. Both frontend metric queries aggregated by service name only, with no downstream dimension. The per-dependency breakdown was never produced. The frontend-to-productcatalogservice link rests entirely on two curves sharing a shape over the same window — suggestive, not attribution.

> Evidence `tr_a7ff783ab63f`:

```
<tool_result id="tr_a7ff783ab63f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_a7ff783ab63f>
```

> Evidence `tr_5181276312c4`:

```
<tool_result id="tr_5181276312c4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_5181276312c4>
```

> Evidence `tr_b402eb55a949`:

```
<tool_result id="tr_b402eb55a949" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_b402eb55a949>
```

> Evidence `tr_f623b72d8d9d`:

```
<tool_result id="tr_f623b72d8d9d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f623b72d8d9d>
```

> Evidence `tr_d9c25c5802bc`:

```
<tool_result id="tr_d9c25c5802bc" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_d9c25c5802bc>
```

## What we did not conclude, and what to do next

Confidence is low and no fix class is proposed. Every metric query issued was an error-ratio query. No latency percentiles were retrieved, no CPU, memory, GC or pool saturation series, and no logs at all. Bursty partial errors with the service staying up is consistent with several quite different mechanisms, and the measurements that would separate them were never taken. Naming one on error-ratio curves alone would be a guess wearing a conclusion's clothes. One inconsistency is also unreconciled: the two catalog error-ratio queries disagree on peak, roughly 20% against 12.5%, which changes how severe the bursts actually were.

Pick this up in roughly this order. First, productcatalogservice p50/p95/p99 plotted against the burst timestamps — the single measurement most likely to separate a slow downstream from something internal. Second, that service's CPU, memory, GC and connection/thread-pool saturation across the window and the twenty minutes before it. Third, fix the Loki selector, then re-run change history over a genuinely wider window including shared platform and dependency owners, and re-issue frontend's metrics with a downstream-destination dimension. Also identify the unmeasured edge from frontend and establish per-service onset times, which no dispatch produced.

> Evidence `tr_4ca828b27368`:

```
<tool_result id="tr_4ca828b27368" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.2 n=58
</tool_result:tr_4ca828b27368>
```

> Evidence `tr_6eae261bb752`:

```
<tool_result id="tr_6eae261bb752" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.125 n=61
</tool_result:tr_6eae261bb752>
```

> Evidence `tr_002b87d7ee68`:

```
<tool_result id="tr_002b87d7ee68" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1636 n=59
</tool_result:tr_002b87d7ee68>
```

> Evidence `tr_105c48f50895`:

```
<tool_result id="tr_105c48f50895" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:59:00.583000+00:00..2026-08-27T06:14:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1036 n=61
</tool_result:tr_105c48f50895>
```
