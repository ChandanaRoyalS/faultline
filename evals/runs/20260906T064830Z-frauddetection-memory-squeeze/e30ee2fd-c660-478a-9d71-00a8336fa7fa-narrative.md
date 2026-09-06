# Fraud detection service in a restart loop after an unreverted container memory limit

## What the responder saw first

The page named a single service, frauddetectionservice, at critical severity, with no other service in the blast radius and no unmeasured edges crossed to get there. That framing held up: nothing in the investigation ever pulled the story outward to a caller or a dependency. The starting picture was one service, alone, and an alert clock we will call T+0.

The first instinct was to look at the service's own golden signals. That is where the record starts, and it is also the first dead end.

## Dead end one: the metrics were never there

The error-ratio query for this service — errored calls over total calls, derived from span telemetry — returned nothing for the alert window. Widening to the preceding half hour returned nothing. Widening again to a six-hour baseline before T+0 returned nothing. Twelve continuous hours, zero samples on both sides of the comparison.

The trap here is subtle and worth remembering. The tooling reported "no sustained departure from baseline," which reads like a clean bill of health. It is not. Both windows were empty, so the comparison was undefined; absent series cannot demonstrate a flat error rate any more than they can demonstrate a spike. Two hypotheses were briefly entertained and both had to be dropped: that the service was throwing a rising share of errors into T+0 (no signal to support it), and that it had been emitting normally and then went dark at onset (the baseline was equally empty, so the gap predates the incident entirely).

What that emptiness actually points at is the metric source — either the call counter is not scraped for this service, or it is not labelled with the exact service name that was queried. Either way, span telemetry was unusable as a primary signal, and the responder had to abandon it and go to logs. Roughly a third of the investigation's effort went into this branch and produced no evidence about the incident. Note also that only the error-ratio template was ever run: request rate, latency, CPU, memory working-set, and restart counts were never queried at all.

> Evidence `tr_95266ef8ea3d`:

```
<tool_result id="tr_95266ef8ea3d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T06:24:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" template="error-ratio" baseline="2026-09-06T05:52:32.100014+00:00..2026-09-06T06:24:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_785453d21099`:

```
<tool_result id="tr_785453d21099" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T00:54:30.583000+00:00..2026-09-06T06:54:30.583000+00:00" template="error-ratio" baseline="2026-09-05T18:54:30.583000+00:00..2026-09-06T00:54:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The logs: a restart loop, and a conspicuous silence

Logs for the service told a much clearer story, and it was not the story anyone expected.

At the start of the sampled window the service is doing normal work — Kafka record consumption with incrementing order counts, visible through roughly T-29m. That output then stops and never returns.

From about T-5m45s onward the log stream becomes a repeating three-line JVM and OpenTelemetry-agent startup sequence: the JAVA_TOOL_OPTIONS pickup, a benign class-sharing VM warning, and the agent version banner. It repeats at least nine times through the end of the window. From roughly T-4m it settles into a near-constant ~62-second cadence — a fresh start about every minute, on the minute-ish, which is the fingerprint of a supervisor or liveness probe killing and restarting on a fixed interval rather than randomly timed crashes. One of those iterations lands at ~T+16s, which is why the alert fired when it did; it is one turn of an ongoing loop, not the beginning of anything.

Several plausible readings died here. There is no exception, no ERROR line, no stack trace anywhere in the sample, including the newest lines bracketing T+0 — so an application-level crash reason being written to stdout can be ruled out. The repeated JVM banners mean the process is genuinely dying and being started fresh, not hanging on a slow dependency inside one long-lived process. And there are no broker, consumer-group, or connection messages: consumption simply ceases, which gives no support to a Kafka-side explanation and instead sharpens the question to why the process exits before it ever consumes anything.

The most useful detail is where in the lifecycle death occurs: after the agent version banner, before any application readiness or first business log line. The process never reaches steady state.

> Evidence `tr_8b2593c1ccb0`:

```
<tool_result id="tr_8b2593c1ccb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T06:24:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T06:24:35.244991+00:00  Consumed record with orderId: a119fdd8-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 588
2026-09-06T06:24:39.329142+00:00  Consumed record with orderId: a38c7749-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 589
2026-09-06T06:24:49.679583+00:00  Consumed record with orderId: a9b74f0b-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 590
2026-09-06T06:24:51.155141+00:00  Consumed record with orderId: aa983db7-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 591
```

## The change history

With logs pointing at a process that cannot finish starting, the change record was the next place to look, and it was unusually tidy.

Only five changes exist for this service in the window, all of the same kind — container resource limits — and all made by the same actor, platform-automation. No code deploys. No image rollouts. No feature-flag flips. No individual human operator. Each of those was considered and each is ruled out by the simple fact that the corresponding entry type does not appear at all.

The most recent of the five landed at T-6m and lowered the container memory limit from unset to 200m. Two earlier applications of the same limit had occurred that day — about 5.3 hours and 3.8 hours before T+0 — and each was reverted within eight to eleven minutes. The final one was not reverted. The 200m limit was in effect going into onset and stayed in effect.

That repeating apply/revert pattern cuts both ways and the record should be honest about it. Because the two earlier applications were rolled back quickly and no incident is associated with them, the limit alone is a plausible but not self-evidently sufficient trigger. The distinguishing factor is duration: this one persisted long enough for the consequence to accumulate.

> Evidence `tr_998ab37c8a91`:

```
<tool_result id="tr_998ab37c8a91" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T06:54:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  5m before onset  2026-09-06T06:48:34.890045+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.6h before onset  2026-09-06T03:19:42.593426+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## How the pieces were put together

Change timing and log behaviour line up within about a minute: the limit lands at T-6m, and the earliest restart visible in the log sample is at T-5m45s. A JVM whose heap plus native footprint does not fit inside a 200m cgroup allowance will be terminated by the platform for exceeding its allowance, without the application ever getting a chance to log a reason — which matches exactly what the logs show: death between agent initialisation and the first business line, no exception, no stack trace, supervisor restarts, repeat.

The failing mechanism is memory exhaustion against the enforced limit. The automation edit is how it started, not what is happening. The fix class is a revert of the change.

Confidence in this is medium, not high, and the next section explains why.

> Evidence `tr_998ab37c8a91`:

```
<tool_result id="tr_998ab37c8a91" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T06:54:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  5m before onset  2026-09-06T06:48:34.890045+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.6h before onset  2026-09-06T03:19:42.593426+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_8b2593c1ccb0`:

```
<tool_result id="tr_8b2593c1ccb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T06:24:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T06:24:35.244991+00:00  Consumed record with orderId: a119fdd8-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 588
2026-09-06T06:24:39.329142+00:00  Consumed record with orderId: a38c7749-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 589
2026-09-06T06:24:49.679583+00:00  Consumed record with orderId: a9b74f0b-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 590
2026-09-06T06:24:51.155141+00:00  Consumed record with orderId: aa983db7-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 591
```

## What was never measured, and what stays open

The central weakness of this record: no container memory working-set series, no terminated-reason or OOMKilled indicator, and no restart-count series was ever queried. The termination mechanism is inferred from restart cadence plus change timing, not directly observed. A responder revisiting this should pull those three series first — they would either confirm the story in one query or break it.

Onset is bounded only from above. Restart activity is already present in the oldest line of the newest-lines block, so the true start could be earlier than T-5m45s, possibly at or even slightly before the limit change at T-6m. The untruncated gap in the middle of the log window was never examined.

It is unknown whether the service was already impaired before the change landed, because the span telemetry gap covers the whole preceding twelve hours and the cause of that gap — label mismatch versus genuine scrape failure — was never determined.

No callers of this service were dispatched, so downstream user impact is unmeasured, and it is not known whether the fraud path fails open or fails closed when this service is unavailable. For a critical-severity page that is a significant hole.

Finally, and operationally the most important open item: nobody established why the automation applied this limit three times and reverted it twice. If the automation re-applies on its own schedule, a manual revert will not hold, and the incident will recur. Find the automation's trigger before declaring this closed.

> Evidence `tr_785453d21099`:

```
<tool_result id="tr_785453d21099" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T00:54:30.583000+00:00..2026-09-06T06:54:30.583000+00:00" template="error-ratio" baseline="2026-09-05T18:54:30.583000+00:00..2026-09-06T00:54:30.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_8b2593c1ccb0`:

```
<tool_result id="tr_8b2593c1ccb0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T06:24:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-06T06:24:35.244991+00:00  Consumed record with orderId: a119fdd8-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 588
2026-09-06T06:24:39.329142+00:00  Consumed record with orderId: a38c7749-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 589
2026-09-06T06:24:49.679583+00:00  Consumed record with orderId: a9b74f0b-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 590
2026-09-06T06:24:51.155141+00:00  Consumed record with orderId: aa983db7-a9bb-11f1-ad3b-badd4c11dd2b, and updated total count to: 591
```

> Evidence `tr_998ab37c8a91`:

```
<tool_result id="tr_998ab37c8a91" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T06:54:30.583000+00:00..2026-09-06T06:56:29.065986+00:00" radius="seed" hops="0">
service: frauddetectionservice
5 changes, ranked by suspicion
  #1  5m before onset  2026-09-06T06:48:34.890045+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  3.6h before onset  2026-09-06T03:19:42.593426+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

