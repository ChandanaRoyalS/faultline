# frauddetectionservice crash-restart loop after a memory ceiling change

## What the page said, and what it didn't

The alert named exactly one service, frauddetectionservice, at severity critical, and the blast radius stayed at one service for the whole investigation. The page fired at roughly T+10m into the window we ended up examining. That timestamp is the first thing to distrust: it is not when the trouble started. Treat the page as a sample of an ongoing condition, not as an onset marker.

Be aware, too, that the single-service blast radius may be an artifact of how we looked. Every change query we ran was scoped to frauddetectionservice alone, so "only one service affected" is really "only one service asked about." If you are reading this months later and the same pattern recurs, widen the change scope before you accept containment.

> Evidence `tr_c492396179a0`:

```
<tool_result id="tr_c492396179a0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_c492396179a0>
```

## First look: the metrics were a dead end, twice

The instinct was to characterize the incident from span metrics — error ratio over call volume for the service. That query returned no series at all across the fifteen-minute window. Not a high ratio, not a zero ratio: nothing.

This is worth dwelling on because it burned time. An empty ratio means at least one side of the expression has no data, and the result cannot tell you which. It is equally consistent with a service that is dead and emitting nothing, and with a service that is fine but whose telemetry pipeline is broken. We ran the metrics path a second time, nominally to ask about container memory, and got the same span-metrics answer back — a different metric family than the one the question needed. So the memory side of the story was never directly measured.

What the empty result did rule out is useful: there was no error spike to chase. A partial-failure signature, where the service still serves traffic but returns errors, would have produced a non-empty denominator. It did not. Whatever this was, it was not degradation-while-serving.

> Evidence `tr_3d03a8a90a35`:

```
<tool_result id="tr_3d03a8a90a35" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_3d03a8a90a35>
```

> Evidence `tr_e8cc3a6a0af7`:

```
<tool_result id="tr_e8cc3a6a0af7" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_e8cc3a6a0af7>
```

## The logs are where the shape appeared

Logs did what metrics could not. Through roughly T+0.75m the service was writing ordinary Kafka order-consumption lines with a steadily incrementing counter — healthy, boring, working.

Then consumption stops. From about T+4m onward the entire log stream is one repeating three-line JVM startup sequence: the tool-options pickup, a VM class-sharing warning, and the OpenTelemetry agent version banner. Three tightly spaced starts cluster near T+4m, then the sequence settles into a near-regular cadence of roughly 62 seconds and repeats at least nine times through T+12m. No consumption lines appear anywhere after the break. The process never reaches steady-state work before it starts over.

Two negatives from the logs mattered more than the positives. First, there are no ERROR lines, no exception class names, no stack frames — the process dies without saying anything about why. A JVM that crashes on its own terms usually leaves something behind. Silence points at something killing the process from outside the application. Second, the OpenTelemetry agent logs its banner successfully on every single restart, so agent attachment completes; whatever kills the process happens after that point, not during it.

Caveat on the evidence: retrieval covered only the newest ~32 lines. A kill-reason or exit-status line sitting just outside that slice has not been excluded.

> Evidence `tr_159a8f48dfb0`:

```
<tool_result id="tr_159a8f48dfb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-30T04:27:22.286793+00:00  Consumed record with orderId: 1840db91-a42b-11f1-991c-6ae17e511705, and updated total count to: 1977
2026-08-30T04:27:30.315211+00:00  Consumed record with orderId: 1d095ebb-a42b-11f1-991c-6ae17e511705, and updated total count to: 1978
2026-08-30T04:27:36.741386+00:00  Consumed record with orderId: 20dddb9d-a42b-11f1-991c-6ae17e511705, and updated total count to: 1979
2026-08-30T04:27:39.349946+00:00  Consumed record with orderId: 226c2b2b-a42b-11f1-991c-6ae17e511705, and updated total count to: 1980
```

## The change

The change history for the service across the window contains exactly one entry. At approximately T+4m — the same minute the restart loop begins — an automation actor applied a resource-limits update setting the container memory limit on frauddetection-service to 200m.

The timing is the strongest single piece of evidence in this record: healthy consumption before, restart loop from that minute forward, one change and nothing else in between.

Two gaps in the change record shaped what we could and could not conclude. The before-value field is empty, so the previous limit is not recoverable from the change log and the magnitude of the reduction is unknown. And the literal value is ambiguous — in Kubernetes resource syntax the trailing letter is the milli-suffix, so this may be a malformed unit rather than a deliberate small ceiling. That distinction matters for remediation and we never resolved it.

> Evidence `tr_47c33dae0689`:

```
<tool_result id="tr_47c33dae0689" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_47c33dae0689>
```

> Evidence `tr_c492396179a0`:

```
<tool_result id="tr_c492396179a0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_c492396179a0>
```

## Where we landed

Reading the three streams together: the runtime's actual startup footprint does not fit inside the ceiling that was applied, so from that minute the container cannot complete initialization within its allowance. It is terminated during or shortly after startup and restarted, which is the ~62-second loop. Because the process never reaches the point of serving work, it emits no span metrics, which is why the canonical error-ratio expression returns nothing. That is the link between the two halves of the evidence, and it is the reason the empty metric result is a symptom rather than a tooling problem.

This is a total loss of the instance, not a partial failure. Confidence is medium. The remediation class is a config revert.

> Evidence `tr_159a8f48dfb0`:

```
<tool_result id="tr_159a8f48dfb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-30T04:27:22.286793+00:00  Consumed record with orderId: 1840db91-a42b-11f1-991c-6ae17e511705, and updated total count to: 1977
2026-08-30T04:27:30.315211+00:00  Consumed record with orderId: 1d095ebb-a42b-11f1-991c-6ae17e511705, and updated total count to: 1978
2026-08-30T04:27:36.741386+00:00  Consumed record with orderId: 20dddb9d-a42b-11f1-991c-6ae17e511705, and updated total count to: 1979
2026-08-30T04:27:39.349946+00:00  Consumed record with orderId: 226c2b2b-a42b-11f1-991c-6ae17e511705, and updated total count to: 1980
```

> Evidence `tr_c492396179a0`:

```
<tool_result id="tr_c492396179a0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_c492396179a0>
```

> Evidence `tr_3d03a8a90a35`:

```
<tool_result id="tr_3d03a8a90a35" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_3d03a8a90a35>
```

## Dead ends, kept deliberately

These consumed effort and produced nothing. They are here so you do not repeat them.

A code deploy or image rollout just before onset — no. The change log holds one entry and it is not a deploy.

A feature flag flip — no flag change is recorded for the service in the window.

A dependency or library version bump — none recorded.

A human operator making a manual maintenance edit — the recorded actor is platform automation, which changes both the remediation path and the odds that other services were touched by the same run.

A limit that flapped or was adjusted repeatedly, producing intermittent effects — only one such event exists, at a single timestamp.

The OpenTelemetry agent failing to attach and killing the JVM — ruled out cleanly, the banner appears on every restart.

A single one-off restart explaining the gap — at least nine distinct startup sequences on a fixed interval is a loop, not an event.

A visible error burst in span metrics — the query returns no series, so there is no error signal to point at.

And the tempting framing that nothing changed and this must be purely external, traffic-driven or upstream: a change did land minutes before, so the change-driven explanation deserves to be tested first.

> Evidence `tr_47c33dae0689`:

```
<tool_result id="tr_47c33dae0689" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_47c33dae0689>
```

> Evidence `tr_c492396179a0`:

```
<tool_result id="tr_c492396179a0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_c492396179a0>
```

> Evidence `tr_159a8f48dfb0`:

```
<tool_result id="tr_159a8f48dfb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-30T04:27:22.286793+00:00  Consumed record with orderId: 1840db91-a42b-11f1-991c-6ae17e511705, and updated total count to: 1977
2026-08-30T04:27:30.315211+00:00  Consumed record with orderId: 1d095ebb-a42b-11f1-991c-6ae17e511705, and updated total count to: 1978
2026-08-30T04:27:36.741386+00:00  Consumed record with orderId: 20dddb9d-a42b-11f1-991c-6ae17e511705, and updated total count to: 1979
2026-08-30T04:27:39.349946+00:00  Consumed record with orderId: 226c2b2b-a42b-11f1-991c-6ae17e511705, and updated total count to: 1980
```

> Evidence `tr_3d03a8a90a35`:

```
<tool_result id="tr_3d03a8a90a35" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_3d03a8a90a35>
```

## Still open when this was written

No container-memory telemetry was ever queried. Working-set bytes, memory failure counters, out-of-memory kill counters, and pod restart counts were all left unmeasured. The mechanism is inferred from timing and log shape, not observed directly. Query them first if this recurs; it should take a minute and would convert medium confidence into high.

The prior memory limit is not in the change record, so the correct value to restore must come from the deployment manifest or a prior revision, not from the change log.

The unit ambiguity in the applied value is unresolved. If the value is malformed rather than merely small, the framing shifts toward a wrong-value problem and "revert" means something different.

Whether the same automation run touched other services was never asked. Verify before declaring containment.

Instrumentation health for this service was never independently confirmed. The logs favor the dead-instance reading over a broken pipeline, but the metrics evidence alone cannot separate them.

Log retrieval may be truncated at the newest ~32 lines.

> Evidence `tr_e8cc3a6a0af7`:

```
<tool_result id="tr_e8cc3a6a0af7" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))' over this window
</tool_result:tr_e8cc3a6a0af7>
```

> Evidence `tr_c492396179a0`:

```
<tool_result id="tr_c492396179a0" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00">
service: frauddetectionservice
1 changes
  2026-08-30T04:31:01.425054+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
</tool_result:tr_c492396179a0>
```

> Evidence `tr_159a8f48dfb0`:

```
<tool_result id="tr_159a8f48dfb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:27:00.583000+00:00..2026-08-30T04:42:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-08-30T04:27:22.286793+00:00  Consumed record with orderId: 1840db91-a42b-11f1-991c-6ae17e511705, and updated total count to: 1977
2026-08-30T04:27:30.315211+00:00  Consumed record with orderId: 1d095ebb-a42b-11f1-991c-6ae17e511705, and updated total count to: 1978
2026-08-30T04:27:36.741386+00:00  Consumed record with orderId: 20dddb9d-a42b-11f1-991c-6ae17e511705, and updated total count to: 1979
2026-08-30T04:27:39.349946+00:00  Consumed record with orderId: 226c2b2b-a42b-11f1-991c-6ae17e511705, and updated total count to: 1980
```
