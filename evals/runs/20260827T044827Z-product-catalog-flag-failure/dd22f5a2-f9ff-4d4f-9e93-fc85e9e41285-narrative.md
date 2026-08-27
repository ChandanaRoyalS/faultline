# Partial, intermittent errors on productcatalogservice — mechanism not established

## What was visible at the top of the incident

Three alerts arrived together: loadgenerator, frontend, and productcatalogservice. Triage put the blast radius at seven services, severity critical, with productcatalogservice named as the starting point and one edge crossed that carries no instrumentation at all. From the responder's chair, that is the entire shape of the thing at T+0: a customer-facing pair of alerts (loadgenerator and frontend, which are downstream consumers) and one backend service named as origin, with no statement yet about why.

Everything in this record hangs off a single positive signal, described next. Read the rest as a map of where the evidence is not.

## The one thing that was actually measured

An error-ratio series for productcatalogservice — spans carrying error status over all recorded calls — was retrieved twice over the same fifteen-minute window and both retrievals agree. The ratio is populated at every sample point (57 points in the first pull, 61 in the second), floors at zero, and peaks around 11.4%. The denominator is non-zero throughout.

That combination says three useful things. The service was serving continuously — requests reached its instrumentation and were handled, so nothing upstream was swallowing traffic wholesale. It was not hard-down or crash-looping; a dead process leaves a gap or a ratio pinned near one, and neither appears. And the errors are not a chronic background level, because the series returns to zero inside the window; there is a genuine excursion. What we have is recurring partial failure affecting roughly a tenth of calls at worst, oscillating rather than sustained.

That is the whole of the positive evidence. Every attempt to explain it came back empty.

> Evidence `tr_839eda652d8a`:

```
<tool_result id="tr_839eda652d8a" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1139 n=57
</tool_result:tr_839eda652d8a>
```

> Evidence `tr_1096f7dba2d7`:

```
<tool_result id="tr_1096f7dba2d7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1139 n=61
</tool_result:tr_1096f7dba2d7>
```

## Dead end: the logs were never actually read

Two separate dispatches went after productcatalogservice logs over the incident window, and both returned zero lines. The trap is that both used a hyphenated form of the service label — the hyphenated variant — while the service is named without hyphens everywhere else in the investigation scope. The second dispatch was supposed to be the corrected re-run; the result it returned still reports the hyphenated selector. So the re-run did not happen.

This matters more than it looks. An empty log result is tempting to read as silence, and silence from a service is itself a strong signal — a wedged or crashed process. That reading is not available here. A selector that matches no stream and a service that emits nothing produce byte-identical results. We know nothing about what productcatalogservice logged. There is no error signature and no first-anomalous-line timestamp anywhere in this record, and any claim otherwise would be unsupported.

Next responder: run a label-values enumeration first, then query. Do not skip the enumeration — the assumption about the label shape is exactly what cost this investigation its timeline anchor.

> Evidence `tr_223ade85cee8`:

```
<tool_result id="tr_223ade85cee8" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_223ade85cee8>
```

> Evidence `tr_f32b98c26f6e`:

```
<tool_result id="tr_f32b98c26f6e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_f32b98c26f6e>
```

## Dead end: the two peer services returned nothing at all

adservice and cartservice were each queried for error ratio over the same window. Both returned no series whatsoever — and critically, the denominators are absent too, not just the error numerators. The denominator counts calls of every status, so a healthy service with a zero error rate would still have produced a series.

This is a gap, not a measurement. Absent denominators mean either those services received no traffic in the window, or their metric emission or scraping stopped. Those two cannot be told apart from what was collected. The temptation is to record 'adservice and cartservice were clean' and move on; that would be wrong in a way that could send a later responder down the wrong branch. The correct entry is: unmeasured.

What this does close off is any timing argument built on these two. There is no onset timestamp for either service, so neither can be shown to precede or follow productcatalogservice's excursion. The window was not clipped too narrowly either — it is uniformly empty rather than partially populated, so widening it alone will not help. Find out first whether these services were emitting.

> Evidence `tr_ea2d754fc52d`:

```
<tool_result id="tr_ea2d754fc52d" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))' over this window
</tool_result:tr_ea2d754fc52d>
```

> Evidence `tr_dc3105edf015`:

```
<tool_result id="tr_dc3105edf015" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_dc3105edf015>
```

## What turned out not to matter: the change log

Two change-log dispatches ran against productcatalogservice and both came back with nothing recorded — no deployments, no config edits, no flag flips — across the queried window. Within the bounds of what was queried, this is a real negative and it does clear three hypotheses. Nothing shipped to the service at the moment of onset. No runtime config or flag mutation flipped behaviour mid-window. And no rollback or remediation edit landed during the window, so the metric timeline is not confounded by someone else's fix.

The bounds are the problem. Both dispatches covered only the fifteen minutes straddling onset — roughly T-10m to T+5m — while the question posed at the start of the investigation concerned the full hour before. That preceding hour is unqueried. Both dispatches were also scoped to productcatalogservice alone; no dependency change stream was ever pulled. So 'no change caused this' is not established, only 'no change to this one service in these fifteen minutes'.

> Evidence `tr_8c5b0d29808f`:

```
<tool_result id="tr_8c5b0d29808f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8c5b0d29808f>
```

> Evidence `tr_227ccdd76acc`:

```
<tool_result id="tr_227ccdd76acc" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_227ccdd76acc>
```

## Why no cause is named

No mechanism was established. Confidence is low and no fix class applies.

Nothing beyond the error ratio was ever retrieved for productcatalogservice: no latency percentiles, no request rate in absolute terms, no CPU, memory, GC, thread-pool or connection-pool series. Those queries were not run, or ran and returned nothing worth recording. The result is that we can see the symptom clearly and have zero visibility into the machinery behind it.

A partial error rate that oscillates while the large majority of calls succeed is compatible with at least three quite different causes. A resource ceiling — memory, connections, threads — would produce exactly this shape as the service crosses and falls back below the limit. A slow downstream call timing out on some fraction of requests produces the same shape. So does a bad artifact running on a subset of replicas, with the ratio tracking how load happens to distribute. Nothing collected discriminates among them. Naming one would be a guess wearing the clothes of a finding, and a later responder would inherit the guess as fact.

One further thing is entirely unprobed: triage flagged an edge with no measurement on it. Nothing in the dispatch set went near it, so whether the causal path runs through that edge is unknown.

> Evidence `tr_839eda652d8a`:

```
<tool_result id="tr_839eda652d8a" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1139 n=57
</tool_result:tr_839eda652d8a>
```

> Evidence `tr_1096f7dba2d7`:

```
<tool_result id="tr_1096f7dba2d7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T04:43:15.583000+00:00..2026-08-27T04:58:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1139 n=61
</tool_result:tr_1096f7dba2d7>
```

## Open questions, in the order I would work them

1. Read the logs. Enumerate label values for the service, then re-query the window with the correct unhyphenated selector. Until this is done there is no error signature and no first-anomaly timestamp, and everything else is being reasoned about in the dark.

2. Pull saturation series for productcatalogservice — memory, connection pool, thread pool, CPU, GC. A ceiling being hit and released would explain the oscillation directly.

3. Pull latency percentiles alongside the error ratio and check whether the error fraction tracks timeouts on an outbound call. This is the single measurement that separates a local problem from a slow downstream, and it was never taken.

4. Break the errors down per replica or pod. If they concentrate on a subset, that separates a bad artifact on some instances from a fleet-wide condition in one query.

5. Establish why adservice and cartservice have no call counts at all. Traffic stopped or emission stopped — either is unexplained and either could sit upstream of, downstream of, or entirely beside the productcatalogservice errors.

6. Extend the change query back a full hour before onset, and extend it to dependencies rather than productcatalogservice alone.

7. Probe past the unmeasured boundary triage flagged.
