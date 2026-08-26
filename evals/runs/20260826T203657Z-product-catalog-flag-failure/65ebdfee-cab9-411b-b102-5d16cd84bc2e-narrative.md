# Partial error elevation across frontend and productcatalogservice — mechanism not established

## What was visible at the start

The page arrived naming three services: frontend, loadgenerator, and productcatalogservice. Triage put the blast radius at seven services with critical severity, entry point at frontend, and flagged one edge in the call graph as unmeasured. That unmeasured edge is worth holding onto — nobody ever went and looked at it, and it is one of the few places a path could hide.

The observation window everyone worked in ran from T-10m to T+5m around the declared onset. Everything below sits inside that fifteen minutes, which turns out to matter more than it first appears.

## The error-ratio series, and what they actually said

The first solid ground was the error ratio on frontend: a real, partial elevation peaking around 12.5% of calls. Not a false alarm, not an observability artifact — server-side error status was genuinely being recorded. Equally clearly, not an outage: seven calls in eight still succeeded. The series minimum was zero, meaning there were clean intervals inside the window, so onset happened partway through it rather than before the window opened.

productcatalogservice was queried twice and told the same story both times: a populated series (57 points on one read, 61 on the other) ranging from zero up to roughly 12.3–12.7%. Same shape, same partial character, same zero floor.

The magnitude agreement between the two — about an eighth of traffic on each — is the single most suggestive thing in this record. It is consistent with frontend passing through failures that originate at productcatalogservice. It is not proof. The frontend series is a single service-level aggregate with no per-peer breakdown, so it cannot attribute its errors to any specific downstream, and nothing that was dispatched established onset ordering between the two services. Both summaries exposed only min and max, not per-timestamp values, so neither could localize the transition to the declared onset moment or say whether it was a step or a spike.

> Evidence `tr_020e4345a61c`:

```
<tool_result id="tr_020e4345a61c" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1246 n=58
</tool_result:tr_020e4345a61c>
```

> Evidence `tr_1519bf8dc8f3`:

```
<tool_result id="tr_1519bf8dc8f3" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1269 n=57
</tool_result:tr_1519bf8dc8f3>
```

> Evidence `tr_3e264b463d25`:

```
<tool_result id="tr_3e264b463d25" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1231 n=61
</tool_result:tr_3e264b463d25>
```

## Dead end: the log queries

Two separate attempts were made to read productcatalogservice logs, and both came back with zero lines over the full window. The first return was clean — not truncated, not errored, covering the window end to end. It would be easy for a later reader to conclude the service went silent.

It did not. Both queries used a hyphenated spelling of the service label, which does not match the service name in the incident scope. The second attempt was supposed to be a re-run against the un-hyphenated spelling and was not — it reproduced the same hyphenated selector and the same empty result. So what was actually established is narrow: that hyphenated label value does not carry this service's stream in this window. The retry did confirm the emptiness is a stable selector mismatch rather than a flaky query.

The cost of this dead end is the whole record. No error text, no panic text, no named downstream, no configuration key, no named saturated resource was ever read. Every mechanism hypothesis died here, unread rather than disproved. If you pick this up again, fix the label convention first — it is the cheapest path to a named mechanism.

> Evidence `tr_3b027425dc30`:

```
<tool_result id="tr_3b027425dc30" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_3b027425dc30>
```

> Evidence `tr_31f3bd9d347e`:

```
<tool_result id="tr_31f3bd9d347e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_31f3bd9d347e>
```

## Dead end: the change log, and the lookback that never ran

Change history was pulled for frontend once and for productcatalogservice twice. All three came back empty — no deploys, no configuration pushes, no flag flips, no routing or ingress edits for either service.

Read carefully, that closes some doors. A release landing in the minutes before onset is excluded for both services. A flag flip or dynamic push as proximate trigger is excluded, since those are in scope for the source queried. An in-flight rollout still landing during observation is excluded, because the window extends five minutes past onset and records nothing. And there is no recorded change to roll back, so rollback was never an available remediation.

But the door that matters stayed open. The lookback that was requested spanned roughly two hours; the query that actually executed covered only the final fifteen minutes of it. About 1h45m before the window remains unqueried. A limit adjustment or a settings edit that lands quietly and only surfaces under load minutes later would sit exactly in that unexamined span. Do not read these three empty results as "no change was involved."

> Evidence `tr_5fa6d0ff2117`:

```
<tool_result id="tr_5fa6d0ff2117" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_5fa6d0ff2117>
```

> Evidence `tr_83e1ea23919c`:

```
<tool_result id="tr_83e1ea23919c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_83e1ea23919c>
```

> Evidence `tr_f6fb170e42bd`:

```
<tool_result id="tr_f6fb170e42bd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f6fb170e42bd>
```

## cartservice: an empty denominator, not a clean bill of health

cartservice was queried to see whether it was degrading independently. Nothing came back — and critically, the unfiltered denominator was empty too, not just the error-filtered numerator. That is an absence of data, not a measured zero.

Three readings fit: cartservice received no traced traffic in the window, its telemetry export stopped, or the service label used does not match how it is actually labeled. The first of those would be a significant finding in its own right — a service that stopped receiving traffic during an incident is a lead, not noise. Nobody resolved which reading is correct, so the tempting conclusion that cartservice was fine is unsupported: a healthy service would still produce a non-empty total call rate.

> Evidence `tr_321f127c5f10`:

```
<tool_result id="tr_321f127c5f10" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_321f127c5f10>
```

## What was never measured

For completeness, so the next responder does not mistake silence for exclusion. No latency percentiles were retrieved for any service, so downstream slowness is untested, not ruled out. No CPU, memory, restart, throttling, or OOM series were retrieved for any service, so saturation and crash-looping are untested, not ruled out. The unmeasured edge triage flagged was never investigated, and the service pair it spans was never identified. adservice and the remaining services in the seven-service radius were never dispatched at all — the investigation touched three of seven.

> Evidence `tr_1519bf8dc8f3`:

```
<tool_result id="tr_1519bf8dc8f3" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1269 n=57
</tool_result:tr_1519bf8dc8f3>
```

> Evidence `tr_3e264b463d25`:

```
<tool_result id="tr_3e264b463d25" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1231 n=61
</tool_result:tr_3e264b463d25>
```

> Evidence `tr_321f127c5f10`:

```
<tool_result id="tr_321f127c5f10" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_321f127c5f10>
```

## Where it stands

No cause established. Confidence low. No fix class identified, and no remediation was applied.

What the evidence supports is a shape, not a mechanism: two services showing partial, non-continuous error elevation at closely matching magnitudes, both with a zero floor indicating onset inside the observation window. Everything beyond that is inference from magnitude coincidence on an unattributed aggregate.

I declined to name a class of failure on error-ratio summaries alone. Naming one here would have been a guess dressed as a finding, and the next responder would have inherited the guess instead of the question.

Priority order if this recurs: (1) find the real label convention for productcatalogservice and read its logs — that is the most likely source of a named mechanism; (2) run the full earlier lookback on the change log for both services and any shared dependency; (3) pull latency percentiles and restart/saturation series for productcatalogservice; (4) break frontend's error ratio down by downstream peer to test the pass-through ordering; (5) resolve why cartservice has no denominator; (6) identify and measure the flagged edge; (7) dispatch the four untouched services.

> Evidence `tr_020e4345a61c`:

```
<tool_result id="tr_020e4345a61c" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1246 n=58
</tool_result:tr_020e4345a61c>
```

> Evidence `tr_1519bf8dc8f3`:

```
<tool_result id="tr_1519bf8dc8f3" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1269 n=57
</tool_result:tr_1519bf8dc8f3>
```

> Evidence `tr_3e264b463d25`:

```
<tool_result id="tr_3e264b463d25" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1231 n=61
</tool_result:tr_3e264b463d25>
```

> Evidence `tr_3b027425dc30`:

```
<tool_result id="tr_3b027425dc30" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_3b027425dc30>
```

> Evidence `tr_31f3bd9d347e`:

```
<tool_result id="tr_31f3bd9d347e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_31f3bd9d347e>
```

> Evidence `tr_f6fb170e42bd`:

```
<tool_result id="tr_f6fb170e42bd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f6fb170e42bd>
```

> Evidence `tr_321f127c5f10`:

```
<tool_result id="tr_321f127c5f10" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T20:30:45.583000+00:00..2026-08-26T20:45:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_321f127c5f10>
```
