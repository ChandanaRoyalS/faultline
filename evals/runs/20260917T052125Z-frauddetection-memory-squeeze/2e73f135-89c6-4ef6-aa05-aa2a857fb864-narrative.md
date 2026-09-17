# Fraud detection service stuck in a silent restart loop after an automated memory-limit edit

## What the alert looked like from the chair

The page named a single service, frauddetectionservice, at critical severity. Blast radius as recorded was one service, and no unmeasured edges were crossed on the way to it, so there was no upstream trail to walk backwards. The first instinct — that the alert marked the moment something broke — turned out to be wrong, and correcting that was the first useful step of the investigation. The alert time was a sampling artefact of an already-running loop, not an event.

## First look: the service's own logs

Pulling the raw log stream for the workload was the single most informative move and should be the first move next time. The stream shows the service healthy early in the queried window — normal order-record consumption lines appear at roughly T-3h50m and T-3h20m relative to the page. Then, starting around T-6m, the stream degenerates into a repeating three-line startup banner: the JVM picking up JAVA_TOOL_OPTIONS, an OpenJDK class-sharing warning, and the OpenTelemetry javaagent version line. Nothing follows. No application output, no consumption lines, no exception, no stack trace, no shutdown or lifecycle-stop message.

The cadence is the tell. Early restarts sit a few seconds apart, then the gaps lengthen — roughly 5s, 9s, 15s, 28s, 53s — and settle on a flat ~62s interval that holds through and past the alert. That ramp-then-cap pattern is a supervisor backoff policy doing exactly what it is designed to do. The process is being started, dying before it finishes initialising, and being started again.

> Evidence `tr_5f3879330cbb`:

```
<tool_result id="tr_5f3879330cbb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-17T01:37:20.492724+00:00  Consumed record with orderId: 52f2221b-b238-11f1-9e86-f6da017d94e3, and updated total count to: 775
2026-09-17T01:37:22.286291+00:00  Consumed record with orderId: 5403fbb4-b238-11f1-9e86-f6da017d94e3, and updated total count to: 776
2026-09-17T01:37:23.509046+00:00  Consumed record with orderId: 54bc0c16-b238-11f1-9e86-f6da017d94e3, and updated total count to: 777
2026-09-17T01:37:26.719985+00:00  Consumed record with orderId: 56a7b996-b238-11f1-9e86-f6da017d94e3, and updated total count to: 778
```

## The change record

Change history for the workload over a full 24 hours contains exactly one entry, and the result was not truncated: an automated actor, platform-automation, applied a resource_limits update setting the container memory limit to 200m. It landed roughly six minutes before the page and about twelve seconds before the first restart banner in the loop.

Two caveats a later reader should carry. First, the before-value in the record is null, so the magnitude of the reduction cannot be established from change history at all — it has to come from the workload manifest or a longer-horizon lookup. Second, '200m' is a suspicious string for a memory field; it reads like a CPU-style millivalue and may be a units error where 200Mi was intended. Neither question was resolved.

> Evidence `tr_3bab1fb1c90a`:

```
<tool_result id="tr_3bab1fb1c90a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_3bab1fb1c90a>
```

> Evidence `tr_4f33e9a9e848`:

```
<tool_result id="tr_4f33e9a9e848" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4f33e9a9e848>
```

## Dead ends worth keeping

Two separate attempts were made to get a metrics view of the service, over a four-hour and a two-hour baseline. Both returned nothing. The error-ratio series derived from call counts has zero samples under the queried service_name label in the incident window *and* in the baseline before it. That symmetry is the important part: because the silence predates the page, it cannot be read as the service going dark at onset, and any story built on 'error rate spiked' or 'telemetry stopped' has no data behind it. The most likely reading is that span-derived metrics for this service either are not scraped or live under a different label. Further span-based queries on this name are unlikely to repay the effort.

The more consequential gap: no container-level evidence was ever retrieved. No termination reason, no exit code, no memory working-set series, no restart count from the orchestrator. Those were the queries that would have closed the case and they were never run.

Also ruled out along the way: this was not a code deploy or a release — no deployment event exists in the window. Not a flag flip. Not a human edit; the actor is automation. Not a stack of changes making attribution murky; there is precisely one. Not a rolling deploy or operator-initiated restart, because a rollout leaves graceful shutdown messages and does not ramp its interval. Not a service that is up but degraded, because it never stays up. And not something that began at the top of the queried window, because healthy work was still logging hours in.

> Evidence `tr_8e1013d8852e`:

```
<tool_result id="tr_8e1013d8852e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" template="error-ratio" baseline="2026-09-16T21:25:36.775068+00:00..2026-09-17T01:27:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_07952637945a`:

```
<tool_result id="tr_07952637945a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T03:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" template="error-ratio" baseline="2026-09-17T01:25:36.775068+00:00..2026-09-17T03:27:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3bab1fb1c90a`:

```
<tool_result id="tr_3bab1fb1c90a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_3bab1fb1c90a>
```

> Evidence `tr_4f33e9a9e848`:

```
<tool_result id="tr_4f33e9a9e848" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4f33e9a9e848>
```

> Evidence `tr_5f3879330cbb`:

```
<tool_result id="tr_5f3879330cbb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-17T01:37:20.492724+00:00  Consumed record with orderId: 52f2221b-b238-11f1-9e86-f6da017d94e3, and updated total count to: 775
2026-09-17T01:37:22.286291+00:00  Consumed record with orderId: 5403fbb4-b238-11f1-9e86-f6da017d94e3, and updated total count to: 776
2026-09-17T01:37:23.509046+00:00  Consumed record with orderId: 54bc0c16-b238-11f1-9e86-f6da017d94e3, and updated total count to: 777
2026-09-17T01:37:26.719985+00:00  Consumed record with orderId: 56a7b996-b238-11f1-9e86-f6da017d94e3, and updated total count to: 778
```

## Where it landed

The reading, held at medium confidence: the memory ceiling was tightened, and roughly twelve seconds later the process began dying mid-startup on a backoff cadence and never recovered. A JVM plus javaagent that vanishes before writing a single application line, with no diagnostic of its own, is the signature of the container runtime killing it for exceeding its memory allowance — the process does not get to write its own obituary. The limit edit is how this started; the inability to acquire enough memory to finish JVM initialisation is what is happening now. Order consumption has been stopped since the loop began.

The fix class is a revert of the configuration. Note the caution: the change came from automation, and if a recommender, a policy default, or a template is what produced it, a manual revert may be re-applied within minutes.

> Evidence `tr_5f3879330cbb`:

```
<tool_result id="tr_5f3879330cbb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-17T01:37:20.492724+00:00  Consumed record with orderId: 52f2221b-b238-11f1-9e86-f6da017d94e3, and updated total count to: 775
2026-09-17T01:37:22.286291+00:00  Consumed record with orderId: 5403fbb4-b238-11f1-9e86-f6da017d94e3, and updated total count to: 776
2026-09-17T01:37:23.509046+00:00  Consumed record with orderId: 54bc0c16-b238-11f1-9e86-f6da017d94e3, and updated total count to: 777
2026-09-17T01:37:26.719985+00:00  Consumed record with orderId: 56a7b996-b238-11f1-9e86-f6da017d94e3, and updated total count to: 778
```

> Evidence `tr_3bab1fb1c90a`:

```
<tool_result id="tr_3bab1fb1c90a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_3bab1fb1c90a>
```

> Evidence `tr_4f33e9a9e848`:

```
<tool_result id="tr_4f33e9a9e848" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4f33e9a9e848>
```

## Open when this record was closed

The memory-exhaustion mechanism is inferred from log shape and timing, not observed. Nobody pulled a termination reason, a 137 exit, a memory series, or a restart count [tr_07952637945a].

The prior memory limit remains unknown, so the size of the cut is unknown, and the possible units error in '200m' is unexamined [tr_4f33e9a9e848].

Why the automation issued the change at all was never investigated. That is the loop that decides whether a revert holds.

Blast radius is recorded as one service, but nothing checked the consumers of the topic this service reads, nor any downstream caller. Order processing has been halted for the duration of the loop and the customer-facing consequence of that is genuinely unmeasured.

Finally, the total absence of span-derived telemetry under this service name may be a pre-existing instrumentation gap rather than anything to do with this incident. It was noticed and not chased [tr_8e1013d8852e].

> Evidence `tr_07952637945a`:

```
<tool_result id="tr_07952637945a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T03:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" template="error-ratio" baseline="2026-09-17T01:25:36.775068+00:00..2026-09-17T03:27:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_4f33e9a9e848`:

```
<tool_result id="tr_4f33e9a9e848" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" radius="seed" hops="0">
service: frauddetectionservice
1 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T05:21:30.114255+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_4f33e9a9e848>
```

> Evidence `tr_8e1013d8852e`:

```
<tool_result id="tr_8e1013d8852e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T01:27:30.583000+00:00..2026-09-17T05:29:24.390932+00:00" template="error-ratio" baseline="2026-09-16T21:25:36.775068+00:00..2026-09-17T01:27:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

