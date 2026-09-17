# Fraud detection service stuck in a start-and-die loop under a tightened memory limit

## What the responder saw first

The page named a single service, frauddetectionservice, at critical severity, and the blast radius never widened: one service, zero unmeasured edges crossed. There was no multi-service fan-out to chase, which in hindsight was the most useful early signal — whatever was wrong was local.

The first instinct was to confirm the alert with metrics. That attempt is described below and it went nowhere. The logs were what actually told the story, and they should be the first stop for anyone reading this record with a similar page in hand.

## The metrics dead end (read this before repeating it)

The error-ratio series for frauddetectionservice — error-status call counts over total call counts, grouped by service name — returned nothing at all. Not zero: no samples. The natural reading at T+0 was "telemetry broke when the service broke," which would itself have been a finding. That reading is wrong. Widening to a four-hour baseline before the page showed the same emptiness, and a second pass over a shorter half-hour baseline showed it again. Eight hours of span covering both windows produced not a single sample.

So the series was already empty long before onset. Either the service is not span-instrumented under that service name, or the label does not match, or those metrics were never scraped. This was never resolved, and it matters: it means the error ratio cannot confirm the alert, cannot refute it, and cannot be used as a before/after instrument for this service until the selector or the source is fixed. Note also the trap in the other direction — an empty result is not a clean bill of health, because the denominator is missing too.

A later metrics pass was aimed explicitly at container-level questions (working set against the limit, last-terminated reason, restart counts) but came back running the same span-derived call-count query. That pass therefore contributed nothing about memory or restarts. If you are picking this up, treat the container-level questions as untouched.

> Evidence `tr_708255aaeefa`:

```
<tool_result id="tr_708255aaeefa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T14:21:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" template="error-ratio" baseline="2026-09-17T10:19:13.602199+00:00..2026-09-17T14:21:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_2354d468af15`:

```
<tool_result id="tr_2354d468af15" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T17:51:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" template="error-ratio" baseline="2026-09-17T17:19:13.602199+00:00..2026-09-17T17:51:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## What the logs showed

At the start of the log window, about T-30m, the service was plainly healthy: ordinary Kafka record-consumption lines with a counter ticking steadily upward.

From roughly T-6m that stops dead. After that point the only output is a repeating three-line startup banner — tool-options pickup, a JVM class-sharing warning, and the telemetry agent version line. Nothing else. No consumption lines, no readiness output, no application logging of any kind after each start.

The spacing is the giveaway. The first starts come fast and then stretch out — a few seconds apart, then tens of seconds — before settling onto a near-exact ~62-second cadence that was still running when the window ended, about T+1m past the last observed start. Eleven distinct startup sequences in roughly seven minutes. That is a backoff-then-fixed-interval restart loop, not a deploy, not a single blip, and not a slow-but-alive process.

Equally important is what is absent: no exception, no stack trace, no shutdown or termination message between consecutive banners. Each process vanishes silently mid-initialization. An application that kills itself usually says so; one that is killed from outside does not. That silence is the reason the cause was sought outside the application log.

> Evidence `tr_442f06575fcf`:

```
<tool_result id="tr_442f06575fcf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T17:51:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-17T17:51:11.635545+00:00  Consumed record with orderId: 5e9dbaa3-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 428
2026-09-17T17:51:17.191222+00:00  Consumed record with orderId: 61ee40b5-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 429
2026-09-17T17:51:29.712789+00:00  Consumed record with orderId: 6965426f-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 430
2026-09-17T17:51:35.779726+00:00  Consumed record with orderId: 6d02424b-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 431
```

## The change that lines up

The change log for this service in the window contains exactly seven entries, all resource-limit edits, all attributed to a platform automation actor — four lowering the container memory limit to 200m and three restoring it to unset. No deploys, no image rollouts, no flag flips, no application config edits, and no individual human operator anywhere in the list. Those alternatives can be set aside.

The most recent entry lowered the limit to 200m about six minutes before the page — which is to say, essentially at the moment the consumption logs stop and the banners begin. Unlike the three preceding cycles, it has no matching restore recorded. The constrained limit was still in effect throughout the loop.

The lower/restore pattern repeats on a roughly four-to-five hour cadence across the preceding half-day, and every earlier lowering was restored within about eleven to twelve minutes. That bound is worth holding onto: it means the constrained state is normally short-lived, and it means at the time of the page this instance was still inside the interval where a restore would normally have fired. It also means the tightened limit is not stale background state to be dismissed — it landed minutes before onset.

> Evidence `tr_a973b51e9341`:

```
<tool_result id="tr_a973b51e9341" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T18:21:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T18:14:52.840892+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  4.2h before onset  2026-09-17T14:08:37.587981+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

## Conclusion, and how firmly it rests

Reading the two together: with a 200m memory ceiling in place the JVM cannot finish initializing. Each process starts, exhausts the memory it needs before reaching steady state, and is terminated from outside without getting a chance to log anything — hence the silent exits and the restart loop under supervisor backoff. The failure is memory exhaustion against a limit that was tightened minutes earlier and, this cycle only, never put back. Fix class is a configuration restore: put the memory limit back to its prior value.

Confidence is medium, not high, and the reason is specifically the untouched container-level evidence. The external kill is inferred from silent exits plus timing, not measured.

> Evidence `tr_a973b51e9341`:

```
<tool_result id="tr_a973b51e9341" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T18:21:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T18:14:52.840892+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  4.2h before onset  2026-09-17T14:08:37.587981+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

> Evidence `tr_442f06575fcf`:

```
<tool_result id="tr_442f06575fcf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T17:51:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frauddetection-service"}
2026-09-17T17:51:11.635545+00:00  Consumed record with orderId: 5e9dbaa3-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 428
2026-09-17T17:51:17.191222+00:00  Consumed record with orderId: 61ee40b5-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 429
2026-09-17T17:51:29.712789+00:00  Consumed record with orderId: 6965426f-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 430
2026-09-17T17:51:35.779726+00:00  Consumed record with orderId: 6d02424b-b2c0-11f1-b729-7253516bbd8b, and updated total count to: 431
```

## Still open for whoever picks this up

First, measure what was inferred. Nothing container-level was ever collected: the last-terminated reason for the container, memory working set against the 200m ceiling, and the restart counter from onset forward all remain unqueried. Those three would turn the central claim from plausible to proven.

Second, why did the automation's restore not fire this cycle? Every prior lowering was undone in eleven to twelve minutes. Whether this one is merely late, failed outright, or has been disabled decides whether someone must restore the limit by hand or whether it will self-heal.

Third, the broader question: why is automation lowering memory limits on a four-to-five hour cadence at all, and is 200m ever a workable ceiling for this JVM? If the earlier lowerings also produced crash loops that simply ended when the restore landed, this is a recurring latent outage that has been hiding behind its own timer.

Fourth, fix the instrumentation gap. The error-ratio series is empty across eight hours covering both windows. Until it is known whether the service is uninstrumented under that name or whether telemetry is broken, there is no measured way to confirm caller-visible impact.

Fifth, downstream impact was never assessed — triage crossed zero unmeasured edges, so whether orders are backing up in the topic or any caller is degraded is simply unknown.

Finally, the observation window ends with the loop still cycling. There is no evidence either way about what happened afterwards.

> Evidence `tr_2354d468af15`:

```
<tool_result id="tr_2354d468af15" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T17:51:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" template="error-ratio" baseline="2026-09-17T17:19:13.602199+00:00..2026-09-17T17:51:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_708255aaeefa`:

```
<tool_result id="tr_708255aaeefa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T14:21:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" template="error-ratio" baseline="2026-09-17T10:19:13.602199+00:00..2026-09-17T14:21:00.583000+00:00">
service: frauddetectionservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frauddetectionservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frauddetectionservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_a973b51e9341`:

```
<tool_result id="tr_a973b51e9341" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T18:21:00.583000+00:00..2026-09-17T18:22:47.563801+00:00" radius="seed" hops="0">
service: frauddetectionservice
7 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T18:14:52.840892+00:00  platform-automation  resource_limits updated: memory limit lowered on frauddetection-service
      None  ->  memory=200m
  #2  4.2h before onset  2026-09-17T14:08:37.587981+00:00  platform-automation  resource_limits reverted: memory limit restored on frauddetection-service
```

