# Partial error bursts across frontend and productcatalogservice — cause not established

## What the page said, and what we could see first

The page arrived naming four services: frontend, loadgenerator, productcatalogservice, and checkoutservice. The first three alerted together; checkoutservice followed about fifteen seconds later, which at the time read as ordinary propagation delay and was not treated as a signal. The declared blast radius was twelve services. Ten of those twelve were never dispatched to at any point during this investigation — that is the single largest gap in this record, and a responder picking it up should start there rather than re-reading what follows.

From the responder's chair the immediate picture was: user-facing service erroring, catalog service erroring, load generator complaining. The obvious hypothesis was a catalog failure bleeding upward into frontend. That hypothesis was never confirmed and never eliminated.

## First reads: metrics on the two front-line services

Around T+3m we pulled the frontend error ratio for the window. It came back non-zero but nowhere near total: it peaked at roughly 10.7% of calls and touched zero at other points in the same window. Two things fell out of that immediately. Frontend was not down — nine in ten calls were succeeding even at the worst moment — and the errors were bursty rather than a flat elevated plateau. A second pull of the same series with continuous sampling confirmed uninterrupted telemetry across the whole window, sixty-one points, no gaps. So we could also discard the idea that we were looking at a visibility hole rather than a real event.

What that series could not do, and this cost us time: it was aggregated by service name only. One series, no downstream, route, or upstream dimension, and no latency at all. It was therefore structurally incapable of telling us which dependency the errors were coming from, and we should have recognised that before pulling it a second time.

Productcatalogservice looked like a near-mirror. Error ratio peaked around 12%, floor of zero, fifty-eight samples, denominator non-zero throughout — meaning the service was continuously receiving and mostly serving traffic. Same shape, same intermittency, same lack of attribution. Note carefully what this symmetry does not buy us: two services showing similar bursty error curves over the same window does not establish which one is upstream of the problem. Nothing collected had the dimensionality to answer that.

> Evidence `tr_4ebe6206b86b`:

```
<tool_result id="tr_4ebe6206b86b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1067 n=59
</tool_result:tr_4ebe6206b86b>
```

> Evidence `tr_daca9f7e265e`:

```
<tool_result id="tr_daca9f7e265e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1067 n=61
</tool_result:tr_daca9f7e265e>
```

> Evidence `tr_12e2b1ea0143`:

```
<tool_result id="tr_12e2b1ea0143" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1206 n=58
</tool_result:tr_12e2b1ea0143>
```

## The change-history line of inquiry — a clean dead end

The next move was the cheap one: had anything shipped? We queried change history for frontend across the fifteen minutes bracketing onset. Empty — no deploys, no config edits, no flag flips, no rollbacks. We ran the same query against productcatalogservice, twice, over the same span. Empty both times.

This was genuinely useful and genuinely a dead end at once. It removed the simplest available story: this was not a straightforward regression that could be reverted, because there was nothing to revert. It also removed a subtler worry — that an in-window remediation attempt had itself perturbed the services — since such an attempt would have appeared in the same log.

Two caveats a future responder must not inherit uncritically. First, both queries covered only the trailing fifteen-minute span; the fifty minutes preceding it were never examined. A change that landed forty minutes before onset and degraded slowly would be invisible here. Second, these queries were scoped by service key. They attest to frontend-owned and catalog-owned changes only. Ingress, service mesh, base images, node pool — anything shared and platform-level — is not addressed by this evidence unless it happens to be recorded under one of those two keys, which we did not verify.

> Evidence `tr_3b5877322382`:

```
<tool_result id="tr_3b5877322382" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_3b5877322382>
```

> Evidence `tr_05b147cb267b`:

```
<tool_result id="tr_05b147cb267b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_05b147cb267b>
```

> Evidence `tr_969733dc3889`:

```
<tool_result id="tr_969733dc3889" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_969733dc3889>
```

## The log attempts — the most instructive failure in this record

With metrics unable to attribute and changes empty, logs were the obvious next source. We needed to know whether productcatalogservice was failing internally (a panic, an unhandled exception) or failing on something downstream (an RPC or database timeout). Those two readings point in opposite directions and the log text would have separated them.

We queried twice. Both queries returned zero lines. Both used the label selector value "product-catalog-service", hyphenated. The service name everywhere else in this investigation is "productcatalogservice", no hyphens. The empty result is therefore almost certainly a selector mismatch, not silence from the service.

The trap here is real and worth naming, because the second query repeated the first mistake: an empty log response invites the reading that the service crashed or stopped emitting. It does not mean that. We already knew from metrics that the service was serving traffic and emitting call telemetry continuously through the window. A crash-loop reading would have contradicted evidence already in hand. Whatever productcatalogservice's logs say, we never read a single line of them.

Both log queries also covered only 05:39–05:54Z, six minutes short of the interval we intended to examine.

> Evidence `tr_3eab28a379bb`:

```
<tool_result id="tr_3eab28a379bb" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_3eab28a379bb>
```

> Evidence `tr_94c6b6cd6baf`:

```
<tool_result id="tr_94c6b6cd6baf" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_94c6b6cd6baf>
```

## What we concluded, and how far that goes

Not established. Confidence low. No fix class identified.

What we can state: a partial, intermittent failure affected both frontend and productcatalogservice over the same window, with error ratios oscillating between zero and roughly 10.7% and 12% respectively. Both services stayed up, kept serving, and kept emitting telemetry throughout. No change of any kind was recorded against either service in the fifteen minutes bracketing onset.

What we cannot state: the causal direction between the two alerting services, the failure signature inside productcatalogservice, whether latency was involved anywhere in the call graph, whether any service was saturated in memory, CPU, descriptors, or pool capacity, and what was happening in the ten unexamined services.

One temptation should be flagged explicitly. The overall shape — bursty errors, no proximate change, possibly a culprit the page never named — resembles a memory-squeeze pattern documented elsewhere in the corpus. That is a resemblance and nothing more. We measured no memory, no threads, no connections, and no latency on any service in this investigation. Treating that resemblance as a finding would be substituting a remembered story for evidence we never gathered.

> Evidence `tr_4ebe6206b86b`:

```
<tool_result id="tr_4ebe6206b86b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1067 n=59
</tool_result:tr_4ebe6206b86b>
```

> Evidence `tr_daca9f7e265e`:

```
<tool_result id="tr_daca9f7e265e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1067 n=61
</tool_result:tr_daca9f7e265e>
```

> Evidence `tr_12e2b1ea0143`:

```
<tool_result id="tr_12e2b1ea0143" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1206 n=58
</tool_result:tr_12e2b1ea0143>
```

> Evidence `tr_3b5877322382`:

```
<tool_result id="tr_3b5877322382" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_3b5877322382>
```

> Evidence `tr_05b147cb267b`:

```
<tool_result id="tr_05b147cb267b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_05b147cb267b>
```

## Open threads, in the order worth pulling

1. Re-run the productcatalogservice log query with the hyphen-free label value "productcatalogservice", and extend the window to the full 05:39–06:00Z so the uncovered 05:54–06:00 tail is closed. This is the cheapest unclaimed evidence in the whole record.

2. Get a per-dependency or per-route breakdown of frontend errors. Without a dimension that names the upstream, the alignment between frontend's bursts and the catalog's bursts is untested, and so is the direction of causation.

3. Dispatch to the ten untouched services in the blast radius, starting with checkoutservice — its fifteen-second lag may be meaningful ordering rather than noise. The service actually responsible may be one the page never named.

4. Four unmeasured edges were crossed during triage and none were subsequently measured. The failure may be propagating across a hop that no dispatch ever observed.

5. Collect latency series somewhere in the call graph. Nothing collected measured latency at all, so a slow-dependency reading is neither supported nor excluded.

6. Collect saturation signals — memory, CPU, file descriptors, connection and thread pools — for at least frontend and productcatalogservice. This is untested despite being the pattern the shape most resembles.

7. Extend the change query backward to cover the fifty minutes preceding the examined span, and widen it beyond the two service keys to shared platform components.

8. Establish onset time properly. The frontend series returned only min/max summaries with no per-timestamp values, so we never determined when the error elevation actually began relative to the alert.

> Evidence `tr_94c6b6cd6baf`:

```
<tool_result id="tr_94c6b6cd6baf" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_94c6b6cd6baf>
```

> Evidence `tr_4ebe6206b86b`:

```
<tool_result id="tr_4ebe6206b86b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1067 n=59
</tool_result:tr_4ebe6206b86b>
```

> Evidence `tr_969733dc3889`:

```
<tool_result id="tr_969733dc3889" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T05:39:15.583000+00:00..2026-08-27T05:54:15.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_969733dc3889>
```
