# frauddetectionservice restart loop after memory ceiling applied

## What the responder saw first

The page named a single service, frauddetectionservice, at critical severity, and the blast radius never grew beyond it. No unmeasured edges were crossed, so there was no adjacent service to chase. The alert itself fired at roughly T+6m relative to what turned out to be the real onset — by the time anyone looked, the failure had already been cycling for six minutes. Treat the alert time as a discovery timestamp, not a start time.

> Evidence `tr_7f4414adda74`:

```
<tool_result id="tr_7f4414adda74" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T02:44:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T02:44:23.165319+00:00  Consumed record with orderId: de193c9c-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 562
2026-09-06T02:44:25.701105+00:00  Consumed record with orderId: df9c9783-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 563
2026-09-06T02:44:41.028569+00:00  Consumed record with orderId: e8be9f46-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 564
2026-09-06T02:44:44.458341+00:00  Consumed record with orderId: eaca81eb-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 565
```

## Timeline as reconstructed from logs

Log traffic about twenty-four minutes before onset (T-24m) is unremarkable: the service is consuming Kafka records and the processed counter climbs monotonically. That is the last evidence of the service doing work.

At T+0 a memory resource limit of 200m was applied to the frauddetection-service workload by the platform-automation actor, where previously no explicit limit had been set.

About thirteen seconds later the consumption lines stop entirely. From that point the log stream contains nothing but an identical three-line startup block repeated over and over: a JAVA_TOOL_OPTIONS pickup notice, an OpenJDK class-sharing warning, and an OpenTelemetry javaagent version banner. Triplets land at roughly T+13s, T+18s, T+27s, T+42s, then T+69s, and thereafter on a steady ~60–62 second cadence out to T+7m14s, which is the end of the captured window. The tightening-then-settling interval is the shape of a restart backoff or a liveness schedule, not of application behaviour.

Two details from the log shape did most of the work. First, every cycle gets far enough for the JVM to start and the agent to attach — the banner is emitted each time — but never far enough for a single application-level line. Second, no cycle emits an exception, an ERROR record, or a stack trace. The process is not deciding to exit; something outside it is ending it.

> Evidence `tr_7f4414adda74`:

```
<tool_result id="tr_7f4414adda74" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T02:44:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T02:44:23.165319+00:00  Consumed record with orderId: de193c9c-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 562
2026-09-06T02:44:25.701105+00:00  Consumed record with orderId: df9c9783-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 563
2026-09-06T02:44:41.028569+00:00  Consumed record with orderId: e8be9f46-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 564
2026-09-06T02:44:44.458341+00:00  Consumed record with orderId: eaca81eb-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 565
```

> Evidence `tr_df7b11a4e684`:

```
<tool_result id="tr_df7b11a4e684" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T03:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  6m before onset  2026-09-06T03:08:08.737147+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  1.5h before onset  2026-09-06T01:42:34.926782+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## Change history

Three changes to this service appear in the window, all of the same kind: memory limit adjustments on the frauddetection-service workload, all attributed to platform-automation. The nearest to onset is the one described above. The same lowering had been applied once about 1.7 hours earlier and reverted roughly eight minutes after that — so this is a recurring automated apply/revert cycle, not a one-off. Critically, the second application has no recorded revert inside the window, meaning the constraint was still in force while the restart loop ran.

The change log also closes several doors cleanly. There is no deployment or release event, no image-tag bump or rollback, no application config or feature-flag or environment-variable change, and no dependency version change. Nor was there a human operator acting ad hoc — every entry carries the automation actor. And the limit is not a long-standing setting that merely happened to be present; the history shows it absent, applied, reverted, and re-applied within the window.

> Evidence `tr_df7b11a4e684`:

```
<tool_result id="tr_df7b11a4e684" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T03:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  6m before onset  2026-09-06T03:08:08.737147+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  1.5h before onset  2026-09-06T01:42:34.926782+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## Dead ends worth keeping

Metrics were the biggest time sink and produced nothing usable. The error-ratio series for this service returned zero samples across the incident window — and, importantly, zero samples across the three-hour baseline before it. The tempting reading is that telemetry went dark when the service started dying; that reading is wrong, because the silence predates the incident. This is an instrumentation or label gap (likely a service_name mismatch or a collection gap) that existed before anything went wrong, so it neither anchors an onset time nor demonstrates an error spike nor shows stability. Two separate metric passes hit the same empty answer.

The second metric pass was supposed to fetch container memory working-set, the configured limit, kill events, and restart counts. It returned the same call-based error-ratio query instead. So the container-level view was never actually obtained. If you are working a similar case, go straight to kubelet/cAdvisor series and do not accept the call-counter template as an answer.

Four log-side hypotheses were raised and discarded. There is no exception at alert time naming a cause — the newest lines cover the whole loop continuously and contain only startup output. The process is not hung on a poison-pill record; repeated JVM banners prove it is being re-executed from scratch, not stuck inside one long-lived run. It is not consuming records slowly; consumption lines appear only in the pre-onset segment and nowhere in the loop. The observability agent is not failing to load; its banner completes every cycle. And the failure is not earlier than JVM start — no bad image, no missing entrypoint, no unreadable agent jar — because initialisation demonstrably succeeds before the process dies.

> Evidence `tr_ac818489bbfe`:

```
<tool_result id="tr_ac818489bbfe" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T00:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" template="error-ratio" baseline="2026-09-05T21:12:08.315621+00:00..2026-09-06T00:14:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_91870d5f5a59`:

```
<tool_result id="tr_91870d5f5a59" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T00:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" template="error-ratio" baseline="2026-09-05T21:12:08.315621+00:00..2026-09-06T00:14:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_7f4414adda74`:

```
<tool_result id="tr_7f4414adda74" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T02:44:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T02:44:23.165319+00:00  Consumed record with orderId: de193c9c-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 562
2026-09-06T02:44:25.701105+00:00  Consumed record with orderId: df9c9783-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 563
2026-09-06T02:44:41.028569+00:00  Consumed record with orderId: e8be9f46-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 564
2026-09-06T02:44:44.458341+00:00  Consumed record with orderId: eaca81eb-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 565
```

## Conclusion and fix class

Silent, repeated, externally-driven termination of a JVM shortly after start, beginning thirteen seconds after a hard memory ceiling was imposed where none existed, is the container being stopped for exceeding its memory allowance. The process needs more memory than it is now permitted and cannot obtain it; because the kill comes from outside, the application never gets a chance to log anything. The fix class is a revert of the applied limit (or raising it to a value the workload can actually start under).

Confidence is medium, and the reason is stated plainly below rather than buried: the kill mechanism is inferred from timing and log shape alone.

> Evidence `tr_df7b11a4e684`:

```
<tool_result id="tr_df7b11a4e684" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T03:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  6m before onset  2026-09-06T03:08:08.737147+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  1.5h before onset  2026-09-06T01:42:34.926782+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_7f4414adda74`:

```
<tool_result id="tr_7f4414adda74" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T02:44:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T02:44:23.165319+00:00  Consumed record with orderId: de193c9c-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 562
2026-09-06T02:44:25.701105+00:00  Consumed record with orderId: df9c9783-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 563
2026-09-06T02:44:41.028569+00:00  Consumed record with orderId: e8be9f46-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 564
2026-09-06T02:44:44.458341+00:00  Consumed record with orderId: eaca81eb-a99c-11f1-b9ca-5e77bdcfc91c, and updated total count to: 565
```

## Still open

No container-level memory, kill-event, or restart-count series were ever collected, so the mechanism remains inferred rather than observed. Anyone revisiting this should pull those first.

The empty error-ratio series is an instrumentation or labelling defect that predates the incident and should be fixed independently — as things stand, this service has no usable call-based signal at all.

Why platform-automation repeatedly applies and then reverts this particular limit is unknown, and that loop is the real hazard: it will recur.

Finally, the downstream consequence of Kafka consumption stopping for at least seven minutes was never investigated. Consumer lag and whatever depends on fraud decisions during that gap are unexamined.

> Evidence `tr_91870d5f5a59`:

```
<tool_result id="tr_91870d5f5a59" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T00:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" template="error-ratio" baseline="2026-09-05T21:12:08.315621+00:00..2026-09-06T00:14:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ac818489bbfe`:

```
<tool_result id="tr_ac818489bbfe" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T00:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" template="error-ratio" baseline="2026-09-05T21:12:08.315621+00:00..2026-09-06T00:14:15.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_df7b11a4e684`:

```
<tool_result id="tr_df7b11a4e684" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T03:14:15.583000+00:00..2026-09-06T03:16:22.850379+00:00" radius="seed" hops="0">
service: frauddetectionservice
3 changes, ranked by suspicion
  #1  6m before onset  2026-09-06T03:08:08.737147+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  1.5h before onset  2026-09-06T01:42:34.926782+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

