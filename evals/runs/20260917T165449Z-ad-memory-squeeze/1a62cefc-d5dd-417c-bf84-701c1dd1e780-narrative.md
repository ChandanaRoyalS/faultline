# adservice restart loop under a lowered memory ceiling

## What the page looked like

Three alerts arrived within a couple of minutes of each other, around T+2m: loadgenerator, adservice, and frontend. Blast radius was scored at seven services, severity critical, with adservice named as the origin. From the responder's chair the useful shape was immediately narrow: only one of the three alerting services had anything local to explain, and the other two are its callers.

The conclusion we reached, at medium confidence, is that adservice was in a crash/restart loop because its container was being killed for exceeding a memory ceiling that had been lowered to 256m about four minutes before onset and, unlike four identical lowerings earlier the same day, was never put back.

> Evidence `tr_db271cd98701`:

```
<tool_result id="tr_db271cd98701" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:28:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-17T16:28:55.368339+00:00  2026-09-17 16:28:55 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=b826b35aab401c222f63bc785506cfa2 span_id=cacceaf5b84fea86 trace_flags=01 
2026-09-17T16:29:00.567604+00:00  2026-09-17 16:29:00 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=8b20562382554bcf7b078ee4c460687a span_id=9d15f3367a26d203 trace_flags=01 
2026-09-17T16:29:10.614502+00:00  2026-09-17 16:29:10 - hipstershop.AdService - received ad request (context_words=[telescopes]) trace_id=3f28558226d8701cf43147dbf5e4dc4e span_id=5f876e842b6a604a trace_flags=01 
2026-09-17T16:29:11.876766+00:00  2026-09-17 16:29:11 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=4fb15671512f5ae62189327e5c065e59 span_id=602c8aa7578c415a trace_flags=01 
```

> Evidence `tr_07df5f60a0c1`:

```
<tool_result id="tr_07df5f60a0c1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T16:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" radius="seed" hops="0">
service: adservice
9 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T16:54:55.176965+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  4.1h before onset  2026-09-17T12:50:20.405863+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

## The adservice log stream was the whole case

The log query for ad-service split cleanly in two. The early part of the window (roughly T-30m to T-18m) shows ordinary ad-request handling. From about T-3m onward there is nothing but startup output: the JAVA_TOOL_OPTIONS pickup line, an OpenJDK class-sharing warning, and the OpenTelemetry agent version banner — nine distinct startup sequences, with successive starts landing at a near-constant ~63s spacing right up to the end of the window at T+3m30s.

Two absences did more work than any of the lines present. First, no startup sequence is ever followed by an application-ready or request-handling line, so the process never reached steady-state serving. Second, there is no ERROR line, no exception class name, and no stack trace anywhere in that stretch. A JVM that dies of its own reported limits — heap or metaspace exhaustion, thread-creation failure, an exhausted pool — says so before it exits. This one said nothing, which points at an external and silent termination after bootstrap. The regular ~63s cadence reads as a fixed-interval supervisor restart rather than load-dependent crashing.

This also disposed of a launch-failure story: the JVM starts successfully every cycle and the telemetry agent loads and prints its version, so the image and entrypoint are fine. The failure is after bootstrap, not at it. And it disposed of the "adservice was merely degraded, look elsewhere" reading — startup-only with no serving lines is a hard-down participant.

> Evidence `tr_db271cd98701`:

```
<tool_result id="tr_db271cd98701" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T16:28:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-17T16:28:55.368339+00:00  2026-09-17 16:28:55 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=b826b35aab401c222f63bc785506cfa2 span_id=cacceaf5b84fea86 trace_flags=01 
2026-09-17T16:29:00.567604+00:00  2026-09-17 16:29:00 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=8b20562382554bcf7b078ee4c460687a span_id=9d15f3367a26d203 trace_flags=01 
2026-09-17T16:29:10.614502+00:00  2026-09-17 16:29:10 - hipstershop.AdService - received ad request (context_words=[telescopes]) trace_id=3f28558226d8701cf43147dbf5e4dc4e span_id=5f876e842b6a604a trace_flags=01 
2026-09-17T16:29:11.876766+00:00  2026-09-17 16:29:11 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=4fb15671512f5ae62189327e5c065e59 span_id=602c8aa7578c415a trace_flags=01 
```

## What the change record said

The full ~24h change record for adservice contains nine entries and they are all resource-limit edits by the same automation actor. No code deploys, no image rollouts, no flag flips, and no individual human operator anywhere in the list. The most recent entry is a memory limit lowered to 256m at T-4m, with no matching revert recorded afterward, so the constrained ceiling was still in force at onset.

The part worth remembering is that the same lower/revert pair had already happened four times that day — early morning, mid-morning, midday — each lowering held for roughly ten minutes and then restored. So the change value is not novel and is not, on its own, an explanation. What distinguishes this occurrence is duration: it was not reverted on the usual schedule. That is the differentiating factor, and it is what turns a routine ceiling into a service that cannot stay up.

> Evidence `tr_07df5f60a0c1`:

```
<tool_result id="tr_07df5f60a0c1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T16:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" radius="seed" hops="0">
service: adservice
9 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T16:54:55.176965+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  4.1h before onset  2026-09-17T12:50:20.405863+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

## Dead end: adservice metrics

We went looking for the obvious confirmation and found an empty room. The span-derived error-ratio series for adservice returned zero samples in the incident window and zero samples in the preceding baseline window of comparable length — twice, on two separate baseline attempts. The temptation is to read that as either a telemetry outage at onset or as a flat, healthy service. It is neither. Because the baseline is equally empty, the gap predates onset entirely and is an instrumentation or label-match problem: adservice spans are simply not in the call-count series. An empty series is not a zero-error measurement, so the service can be neither implicated nor cleared on this basis.

The second, sharper dead end: neither metric attempt touched container memory working-set, restart counts, or termination reason. The memory-ceiling story is therefore inferred from log shape, not observed. Do not let the fact that we settled on it disguise that.

> Evidence `tr_40bb35714972`:

```
<tool_result id="tr_40bb35714972" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T12:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" template="error-ratio" baseline="2026-09-17T08:54:40.928510+00:00..2026-09-17T12:58:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_73c5820de50a`:

```
<tool_result id="tr_73c5820de50a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T13:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" template="error-ratio" baseline="2026-09-17T10:54:40.928510+00:00..2026-09-17T13:58:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Dead end: productcatalogservice as an upstream origin

We tested whether something upstream had been failing ahead of adservice and propagated in. The productcatalogservice error ratio across the window is statistically indistinguishable from its own four-hour baseline — mean moved by a factor of 1.01, with incident spread and maximum both slightly lower than baseline. A single change point is flagged about two hours before onset where the ratio briefly crossed ~5.3%, but that magnitude sits below the baseline maximum and matches this service's pre-existing spiky behaviour. Nothing is flagged near onset. There is no error-side precursor here to propagate. Latency for this service was never queried, so that half is still unanswered.

> Evidence `tr_0a160e22e631`:

```
<tool_result id="tr_0a160e22e631" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T12:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" template="error-ratio" baseline="2026-09-17T08:54:40.928510+00:00..2026-09-17T12:58:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=800 mean=0.003416 min=0 max=0.09186 sd=0.01501
  baseline window: n=907 mean=0.003398 min=0 max=0.1092 sd=0.01653
```

## Dead end: the frontend traces, and an edge we never measured

This is the most useful dead end in the record. We sampled 20 frontend traces (124 spans) across the window expecting to see adservice calls erroring or hanging under frontend. No adservice span appears anywhere in the sample, and no frontend span names an ad-path RPC — not even in the healthy early part of the window. The frontend->adservice edge is unmeasured in both directions.

The one error trace, starting around T+3m50s, has the error marked on the loadgenerator root, its loadgenerator child, and a frontend HTTP GET. That failing frontend span is a childless leaf and only a few milliseconds long, with the whole trace around 35ms, which rules out a deadline expiry. A sibling frontend GET in the same trace completes normally, so the failure is per-request rather than a frontend-wide outage at that instant. Everything with visible downstream children — cart, productcatalog, and one full checkout fan-out through shipping, currency, payment, email, and fraud/accounting — completes without error and fast, the heaviest checkout totalling about 26ms. recommendationservice never appears at all. Where latency is attributed on the slow loadgenerator-driven GETs, the degrading hop is repeatedly frontend's own self-time, not a downstream call.

The consequence: the causal link from adservice being down to the frontend and loadgenerator alerts is assumed from topology, not observed. We never saw the ad call fail because we never saw the ad call.

> Evidence `tr_fa5089e6fced`:

```
<tool_result id="tr_fa5089e6fced" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T16:28:45.583000+00:00..2026-09-17T17:02:50.237490+00:00">
service: frontend
20 trace(s) shown of 20 found, 124 spans; offsets are from each trace's root

trace aca0357176b55bbb  root loadgenerator/HTTP POST  16.6ms  started 2026-09-17T16:29:01.977169+00:00  3 spans
  +0.0ms loadgenerator/HTTP POST 16.6ms [self 1.3ms]
```

## Fix and what is still open

Fix class is a config revert: restore the adservice memory ceiling to its pre-T-4m value. Whether that is a manual action or a wait depends on an open question — why this lowering was not reverted when the four previous ones were within about ten minutes. If the automation loop is merely late, it may restore itself; if it is stuck, someone has to do it.

Still open, in the order I would attack them:

First, the termination mechanism is inferred. Query container memory working-set against the 256m ceiling, container_restart_count, and the last-terminated-reason and exit code (an external kill versus a probe failure) for adservice. Any one of those settles it directly and cheaply.

Second, the frontend->adservice edge. Until a trace or a frontend-side log shows the ad call failing, the propagation path is topology-shaped reasoning.

Third, the single error-marked frontend span. Being a childless leaf with frontend self-time attributed, it could be a fallback on a degraded ad path inside frontend, or something entirely frontend-local and unrelated. Unresolved.

Fourth, the instrumentation gap on adservice spans hides its request rate and latency completely, across baseline as well as incident. Worth fixing independent of this incident, because it is why this investigation had to lean on log shape.

Fifth, the blast radius of seven services was never reconciled against per-service evidence. We have evidence for adservice, frontend, productcatalogservice, and loadgenerator by alert; the other services in that count were never examined.

> Evidence `tr_07df5f60a0c1`:

```
<tool_result id="tr_07df5f60a0c1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T16:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" radius="seed" hops="0">
service: adservice
9 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T16:54:55.176965+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  4.1h before onset  2026-09-17T12:50:20.405863+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

> Evidence `tr_73c5820de50a`:

```
<tool_result id="tr_73c5820de50a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T13:58:45.583000+00:00..2026-09-17T17:02:50.237490+00:00" template="error-ratio" baseline="2026-09-17T10:54:40.928510+00:00..2026-09-17T13:58:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_fa5089e6fced`:

```
<tool_result id="tr_fa5089e6fced" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T16:28:45.583000+00:00..2026-09-17T17:02:50.237490+00:00">
service: frontend
20 trace(s) shown of 20 found, 124 spans; offsets are from each trace's root

trace aca0357176b55bbb  root loadgenerator/HTTP POST  16.6ms  started 2026-09-17T16:29:01.977169+00:00  3 spans
  +0.0ms loadgenerator/HTTP POST 16.6ms [self 1.3ms]
```

