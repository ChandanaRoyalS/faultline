# paymentservice alert with no underlying payment failure: telemetry export path pointed at a dead loopback receiver

## What we saw first

The page named paymentservice and nothing else. Severity was set critical, and the recorded blast radius was three services, reached across two edges that were never actually probed with a measurement. From the responder's chair the alert arrived cold: no accompanying customer report, no queue backlog, just a service name.

The first instinct was to quantify it. That instinct cost the most time and produced the least, and the reason is worth carrying forward: in this environment the alert surface and the metric surface for this service are fed from the same pipe, so when the pipe is broken the alert is loud and the metrics are silent.

## T+0 to T+8m: the metric dead end

The obvious move was an error-ratio query on paymentservice — error-status call counts over total call counts, two-minute rate. It returned nothing. Not zero: nothing. No samples in the incident window at all.

At that point the tempting reading was "the service fell over at alert time and stopped emitting." To test that, the same query was run against a three-hour baseline ending just before the alert. That window was equally empty. So there was no emission to lose; the series simply does not exist under the queried service name and metric. That single comparison killed the crash hypothesis and, more importantly, retired this entire metric path as a way to size the incident. It also means no onset shape — step versus ramp — can be recovered from here, and no latency percentiles were ever in scope, since the query only counts calls by status code.

Worth flagging for the next responder: an empty result is not a clean bill of health. Nobody should read "no samples" as "error ratio was zero."

> Evidence `tr_2763aaff5c6f`:

```
<tool_result id="tr_2763aaff5c6f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T19:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" template="error-ratio" baseline="2026-09-17T16:11:29.834290+00:00..2026-09-17T19:13:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## T+8m to T+20m: traces, also empty, and a window mistake

Next stop was the trace backend, looking for a pre-incident latency baseline. Six hours of paymentservice spans came back empty. That ruled out any afternoon latency ramp being visible in spans, and it ruled out the idea that the gap was a narrow outage confined to the minutes around the alert — the absence stretches back at least six hours.

The dead end here is an operator error worth preserving: the query window was built ending roughly an hour *before* the alert. So this result says nothing about whether spans exist at or after the config change that later turned out to matter. It also cannot, on its own, separate "no spans emitted" from "spans emitted but never ingested." Two useful exclusions, one unanswered question, and an hour of coverage missed.

> Evidence `tr_9c11b97d7914`:

```
<tool_result id="tr_9c11b97d7914" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T15:13:15.583000+00:00..2026-09-17T21:13:15.583000+00:00">
no traces for paymentservice over this window
</tool_result:tr_9c11b97d7914>
```

## T+20m to T+35m: logs say the service is fine

With both telemetry-derived surfaces dark, the log path was the first source that actually carried signal — and it is the one path that does not depend on the export configuration.

Every returned line is info-level charge lifecycle logging: request received, transaction complete. No error, warn or fatal lines, no exceptions, no stack traces. At the exact alert timestamp a charge was received and completed within about a millisecond, with a transaction id returned. Requests arrive and complete every few seconds on both sides of the alert, through roughly three minutes past it, with no gap and no startup or listening output that would mark a process restart at that moment.

This collapsed several candidate stories at once: not a crash, not a restart at onset, not rejected charges, not slow in-service processing, not a throughput blackout. In-service handling time is sub-millisecond for every returned transaction, including the large-amount charges in the minutes around the alert.

One loose thread that turned out not to matter: the emitting container hostname differs between the early and late parts of the log window while the process id stays constant. That is consistent with a replica replacement somewhere in the unreturned middle of the window — not at the alert moment — and it never connected to anything else in the record.

> Evidence `tr_29d582524105`:

```
<tool_result id="tr_29d582524105" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T21:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T21:13:20.154951+00:00  {"level":30,"time":1789679600154,"pid":17,"hostname":"0b3de0a9873e","trace_id":"e29d9167f054b2db0177b227ff71d01c","span_id":"33b214dd90e81535","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":133,"high":0,"unsigned":false},"nanos":399999998},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-17T21:13:20.155647+00:00  {"level":30,"time":1789679600154,"pid":17,"hostname":"0b3de0a9873e","trace_id":"e29d9167f054b2db0177b227ff71d01c","span_id":"33b214dd90e81535","trace_flags":"01","transactionId":"0f98931a-ce53-4c93-99b1-7d92547a7061","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":133,"high":0,"unsigned":false},"nanos":399999998,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T21:13:24.804726+00:00  {"level":30,"time":1789679604804,"pid":17,"hostname":"0b3de0a9873e","trace_id":"4ce49a06a86e28ea25482783e10d3ad8","span_id":"45b559c45e23af72","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":666,"high":0,"unsigned":false},"nanos":999999990},"creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardCvv":397,"creditCardExpirationYear":2039,"creditCardExpirationMonth":5}},"msg":"Charge request received."}
2026-09-17T21:13:24.805578+00:00  {"level":30,"time":1789679604804,"pid":17,"hostname":"0b3de0a9873e","trace_id":"4ce49a06a86e28ea25482783e10d3ad8","span_id":"45b559c45e23af72","trace_flags":"01","transactionId":"e552ef05-482a-422b-b0a0-1f213c68d7f6","cardType":"visa","lastFourDigits":"7968","amount":{"units":{"low":666,"high":0,"unsigned":false},"nanos":999999990,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## T+35m to T+50m: the change log, and why novelty was the wrong test

The change history for paymentservice in the window contains nine entries, and all nine are the same thing: automated toggles of a single environment variable, the OTLP traces endpoint, alternating between unset and a loopback address. Every one is attributed to platform automation. No deploys, no releases, no new images, no flag flips, no library version bumps, no human operator.

The pattern repeats on a roughly three-to-five-hour cadence across the day — set, then reverted about eleven or twelve minutes later, four times over. The final set landed roughly six minutes before the alert and was never reverted.

The dead end here is subtle and it is the most instructive part of the record. The first reading was "a unique mutation immediately before onset, therefore the cause." That is wrong: the identical mutation had already been applied and backed out at least four times the same day with no incident. The mutation is routine. What is novel about this instance is only that it persisted. Causality rests on the missing revert, not on the change itself.

> Evidence `tr_3eec73fcdc8a`:

```
<tool_result id="tr_3eec73fcdc8a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T22:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T22:07:07.257703+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.4h before onset  2026-09-17T18:47:48.063750+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## T+50m to T+65m: checking the caller

To test whether anything user-visible was actually broken, the upstream caller was checked with an aggregate error-ratio query over four hours. Its error ratio during the incident window was *lower* than in the preceding baseline — mean falling from roughly 0.083 to roughly 0.062 across nearly a thousand samples. The metric is bursty in both windows, with standard deviation exceeding the mean, and the maximum burst severity is identical on both sides, so nothing of a new magnitude appeared. Two change points show up inside the incident window, but both are late and both are discrete bursts at the pre-existing maximum, not a step at onset. The caller served traffic continuously; the only no-traffic intervals are in the baseline.

That rules out sustained caller elevation, a new failure class, and a caller-side blackout. It does *not* clear the downstream edge: the query has no downstream dimension, so a localized problem on the paymentservice edge could be diluted by healthy traffic to other dependencies and stay invisible. This check narrows the picture; it does not close it.

> Evidence `tr_7fa6ab3c7e72`:

```
<tool_result id="tr_7fa6ab3c7e72" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T18:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" template="error-ratio" baseline="2026-09-17T14:11:29.834290+00:00..2026-09-17T18:13:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=968 mean=0.06222 min=0 max=0.6667 sd=0.1634
  baseline window: n=787 mean=0.08322 min=0 max=0.6667 sd=0.186
```

## Where we landed

paymentservice is functionally healthy. What broke is its telemetry export path. The traces endpoint was pointed at a loopback address — an address that names a receiver which is not there — so spans never reach the trace backend, and the span-derived call-count series never materialises in the metric store. That single condition explains all three silent surfaces: empty traces, empty metrics in both windows, and a live, clean, sub-millisecond log stream from a service that is plainly still taking payments.

The wrong endpoint value is itself the mechanism. Read the page as "paymentservice telemetry is absent," not "payments are failing." Fix class is a config revert: restore the variable to the state the automation has restored four times already today.

Confidence is medium, and the reason is the gap in coverage rather than disagreement between sources.

> Evidence `tr_3eec73fcdc8a`:

```
<tool_result id="tr_3eec73fcdc8a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T22:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" radius="seed" hops="0">
service: paymentservice
9 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T22:07:07.257703+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.4h before onset  2026-09-17T18:47:48.063750+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_9c11b97d7914`:

```
<tool_result id="tr_9c11b97d7914" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T15:13:15.583000+00:00..2026-09-17T21:13:15.583000+00:00">
no traces for paymentservice over this window
</tool_result:tr_9c11b97d7914>
```

> Evidence `tr_2763aaff5c6f`:

```
<tool_result id="tr_2763aaff5c6f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T19:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" template="error-ratio" baseline="2026-09-17T16:11:29.834290+00:00..2026-09-17T19:13:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_29d582524105`:

```
<tool_result id="tr_29d582524105" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T21:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T21:13:20.154951+00:00  {"level":30,"time":1789679600154,"pid":17,"hostname":"0b3de0a9873e","trace_id":"e29d9167f054b2db0177b227ff71d01c","span_id":"33b214dd90e81535","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":133,"high":0,"unsigned":false},"nanos":399999998},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-17T21:13:20.155647+00:00  {"level":30,"time":1789679600154,"pid":17,"hostname":"0b3de0a9873e","trace_id":"e29d9167f054b2db0177b227ff71d01c","span_id":"33b214dd90e81535","trace_flags":"01","transactionId":"0f98931a-ce53-4c93-99b1-7d92547a7061","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":133,"high":0,"unsigned":false},"nanos":399999998,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T21:13:24.804726+00:00  {"level":30,"time":1789679604804,"pid":17,"hostname":"0b3de0a9873e","trace_id":"4ce49a06a86e28ea25482783e10d3ad8","span_id":"45b559c45e23af72","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":666,"high":0,"unsigned":false},"nanos":999999990},"creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardCvv":397,"creditCardExpirationYear":2039,"creditCardExpirationMonth":5}},"msg":"Charge request received."}
2026-09-17T21:13:24.805578+00:00  {"level":30,"time":1789679604804,"pid":17,"hostname":"0b3de0a9873e","trace_id":"4ce49a06a86e28ea25482783e10d3ad8","span_id":"45b559c45e23af72","trace_flags":"01","transactionId":"e552ef05-482a-422b-b0a0-1f213c68d7f6","cardType":"visa","lastFourDigits":"7968","amount":{"units":{"low":666,"high":0,"unsigned":false},"nanos":999999990,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Still open

Three things a later responder should pick up.

First: which alert rule actually fired, and whether its condition was an absence-of-data check rather than an error-rate threshold. Nothing on the board identifies the firing signal, and this matters because an absence-of-data rule makes the whole picture self-consistent while a threshold rule would demand a different explanation.

Second: whether paymentservice spans exist at or after the final config change. The trace query never covered that period — see the window error above. Re-run it forward through the alert.

Third: why telemetry was also missing during the long stretch when the variable was reportedly unset, between the previous revert and the final set. An unset endpoint should not produce the same silence, and that inconsistency is unexplained. Related: whether any real user impact occurred on the two edges that were never measured. The caller-side query had no downstream dimension and cannot answer it.

> Evidence `tr_9c11b97d7914`:

```
<tool_result id="tr_9c11b97d7914" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T15:13:15.583000+00:00..2026-09-17T21:13:15.583000+00:00">
no traces for paymentservice over this window
</tool_result:tr_9c11b97d7914>
```

> Evidence `tr_7fa6ab3c7e72`:

```
<tool_result id="tr_7fa6ab3c7e72" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T18:13:15.583000+00:00..2026-09-17T22:15:01.331710+00:00" template="error-ratio" baseline="2026-09-17T14:11:29.834290+00:00..2026-09-17T18:13:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=968 mean=0.06222 min=0 max=0.6667 sd=0.1634
  baseline window: n=787 mean=0.08322 min=0 max=0.6667 sd=0.186
```

