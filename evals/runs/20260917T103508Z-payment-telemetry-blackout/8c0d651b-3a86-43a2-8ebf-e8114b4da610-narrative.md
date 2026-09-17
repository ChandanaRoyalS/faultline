# Payment service goes dark to telemetry while still taking charges

## What we saw first

The page named paymentservice and nothing else. Severity was set critical and the blast radius was drawn at three services, but the alert text never told us which condition tripped — that gap shaped the whole investigation and is still open at the end of it.

The first instinct was the normal one: confirm the symptom in the service's own signals before chasing neighbours. That is where the record stops behaving like a typical outage. Every place we looked for the symptom, paymentservice simply was not represented.

## The empty dashboards (T+0 to T+10m)

The span-derived error-ratio query for paymentservice returned nothing. Not a flat line near zero — no samples at all. That on its own reads like a crash, and for a few minutes we treated it that way.

The detail that killed that reading was the baseline. We pulled the same query over the three hours before onset and it was equally empty. There was no emission to lose. Whatever the absence is, it did not begin at onset, which means the metric gap cannot be used as an outage signal and cannot be anchored to the alert timestamp.

Worth recording plainly: this result only ever answered the error-ratio question. Request rate, latency, restart count and memory/CPU for paymentservice were never returned by anything we ran. Four of the five things a responder would normally check on the alerting service remain unmeasured.

> Evidence `tr_d2a97eca0742`:

```
<tool_result id="tr_d2a97eca0742" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T07:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" template="error-ratio" baseline="2026-09-17T04:39:22.832707+00:00..2026-09-17T07:41:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Traces, same hole (T+10m)

We went to the trace backend expecting a clean cutover — healthy spans up to onset, silence after — which would have pinned the timing neatly. Six hours of window, and paymentservice had no traces on either side of the onset moment. Zero before, zero after.

So there is no cutover boundary to point at. There are also no span attributes to read: no error statuses, no export-failure markers, nothing that would let tracing speak to whether requests were succeeding. Every request-outcome question had to be answered elsewhere from here on.

> Evidence `tr_7210d55f984b`:

```
<tool_result id="tr_7210d55f984b" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T04:41:15.583000+00:00..2026-09-17T10:41:15.583000+00:00">
no traces for paymentservice over this window
</tool_result:tr_7210d55f984b>
```

## Is the pipeline itself broken? (T+15m)

Before blaming paymentservice we checked whether the collection path was healthy at all. We ran the identical error-ratio shape against checkoutservice and got a densely populated series in both the incident and the baseline window — over a thousand samples in one, several hundred in the other. Span metrics exist, they are being scraped, and they arrive.

So the blackout is specific to paymentservice, not global.

The checkoutservice numbers were also examined on their own merits and turned out to be a dead end for causation. The mean error ratio was roughly 1.4x higher in the incident window, which briefly looked interesting, but the maximum was identical in both windows and the spread was wide relative to the mean — a sparse, spiky series where a handful of intervals drag the average. The three detected change points land hours before onset, around 05:03, 09:17 and 09:56. None of them sit near the alert. A few intervals had no defined ratio at all, meaning no traffic in that interval rather than no errors. Nothing here escalates beyond what the service did before the incident.

> Evidence `tr_ab73c6290b73`:

```
<tool_result id="tr_ab73c6290b73" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T04:41:15.583000+00:00..2026-09-17T10:41:15.583000+00:00" template="error-ratio" baseline="2026-09-16T22:41:15.583000+00:00..2026-09-17T04:41:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=1183 mean=0.07776 min=0 max=0.6667 sd=0.1879
  baseline window: n=638 mean=0.05482 min=0 max=0.6667 sd=0.1559
```

## The logs disagree with the page (T+20m)

This is the section to read if you are triaging something similar.

The log stream for the payment service does not go quiet at onset. It keeps emitting routine info-level request/completion pairs for charge handling every five to twenty seconds, right through the end of the collected window at 10:43:06. No error lines. No panic. No shutdown. No startup banner. Both USD and CAD charges completing, all card-present successes.

That rules out three things we had been holding open: a crash at onset, a restart loop, and paymentservice being the origin of user-visible payment failures. The service was serving.

One oddity we could not close. The emitting container hostname in the oldest returned lines differs from the hostname in the newest, while the process id stays constant. Something replaced the instance somewhere in the middle of the window, in a stretch the query truncated. It did not appear to correlate with anything else and we did not chase it further, but it is the sort of thing that bites later, so it is here.

> Evidence `tr_dca2c04cc757`:

```
<tool_result id="tr_dca2c04cc757" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T07:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T07:48:45.275730+00:00  {"level":30,"time":1789631325275,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"a2d8414745cda7e5fad4283bde85dac3","span_id":"27784b4f9e4bef0a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":2870,"high":0,"unsigned":false},"nanos":969999993},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-17T07:48:45.276113+00:00  {"level":30,"time":1789631325275,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"a2d8414745cda7e5fad4283bde85dac3","span_id":"27784b4f9e4bef0a","trace_flags":"01","transactionId":"8993fdc3-ed13-4ffc-8c99-671830f07349","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":2870,"high":0,"unsigned":false},"nanos":969999993,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T07:48:45.643322+00:00  {"level":30,"time":1789631325643,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"28a621d011a7148eab6883240d073b6f","span_id":"0006f9bab87d2821","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1094,"high":0,"unsigned":false},"nanos":249999995},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-17T07:48:45.643667+00:00  {"level":30,"time":1789631325643,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"28a621d011a7148eab6883240d073b6f","span_id":"0006f9bab87d2821","trace_flags":"01","transactionId":"0fc43b48-6fa0-4206-a520-20bab03e48c2","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":1094,"high":0,"unsigned":false},"nanos":249999995,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## The change record (T+25m)

Three changes landed on paymentservice in the window. All three were authored by platform-automation. All three touched the same single environment variable: the OTLP traces endpoint.

The most recent one, about six minutes before onset, pointed telemetry export at the pod's own loopback address. That is the closest change in time to the alert and the mechanism is plausible on its face — a service exporting spans to itself will not deliver them anywhere useful.

The part that matters most for the write-up: this same value had been applied roughly five hours earlier and backed out about twelve minutes after that. So the pre-onset event is not a novel, untested edit. It is a re-application of a setting that someone or something had already decided was wrong once. That is a flap on a single known-bad configuration value.

Things the change record positively excluded: there was no code deploy and no new image on paymentservice in the window; there was no feature flag toggle; there was no human operator acting under pressure — every entry is automation. And there was no broad configuration drift to audit, because all three entries hit the same one variable.

> Evidence `tr_79a519cb2f6e`:

```
<tool_result id="tr_79a519cb2f6e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T10:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" radius="seed" hops="0">
service: paymentservice
3 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T10:35:14.200343+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  4.8h before onset  2026-09-17T05:54:47.183904+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## Where it landed

The cause we settled on is a configuration value that is itself wrong: telemetry export on paymentservice redirected to loopback, re-applied about six minutes before onset by automation, reinstating a setting that had already been reverted once the same day. The effect is an observability blackout on a service that continued to take and complete payments normally.

Fix class is a revert of that configuration back to the working endpoint.

Confidence is medium, not high, and the reason is in the next section.

> Evidence `tr_79a519cb2f6e`:

```
<tool_result id="tr_79a519cb2f6e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T10:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" radius="seed" hops="0">
service: paymentservice
3 changes, ranked by suspicion
  #1  6m before onset  2026-09-17T10:35:14.200343+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  4.8h before onset  2026-09-17T05:54:47.183904+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_7210d55f984b`:

```
<tool_result id="tr_7210d55f984b" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T04:41:15.583000+00:00..2026-09-17T10:41:15.583000+00:00">
no traces for paymentservice over this window
</tool_result:tr_7210d55f984b>
```

> Evidence `tr_d2a97eca0742`:

```
<tool_result id="tr_d2a97eca0742" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T07:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" template="error-ratio" baseline="2026-09-17T04:39:22.832707+00:00..2026-09-17T07:41:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ab73c6290b73`:

```
<tool_result id="tr_ab73c6290b73" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T04:41:15.583000+00:00..2026-09-17T10:41:15.583000+00:00" template="error-ratio" baseline="2026-09-16T22:41:15.583000+00:00..2026-09-17T04:41:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=1183 mean=0.07776 min=0 max=0.6667 sd=0.1879
  baseline window: n=638 mean=0.05482 min=0 max=0.6667 sd=0.1559
```

> Evidence `tr_dca2c04cc757`:

```
<tool_result id="tr_dca2c04cc757" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T07:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T07:48:45.275730+00:00  {"level":30,"time":1789631325275,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"a2d8414745cda7e5fad4283bde85dac3","span_id":"27784b4f9e4bef0a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":2870,"high":0,"unsigned":false},"nanos":969999993},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-17T07:48:45.276113+00:00  {"level":30,"time":1789631325275,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"a2d8414745cda7e5fad4283bde85dac3","span_id":"27784b4f9e4bef0a","trace_flags":"01","transactionId":"8993fdc3-ed13-4ffc-8c99-671830f07349","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":2870,"high":0,"unsigned":false},"nanos":969999993,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T07:48:45.643322+00:00  {"level":30,"time":1789631325643,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"28a621d011a7148eab6883240d073b6f","span_id":"0006f9bab87d2821","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1094,"high":0,"unsigned":false},"nanos":249999995},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-17T07:48:45.643667+00:00  {"level":30,"time":1789631325643,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"28a621d011a7148eab6883240d073b6f","span_id":"0006f9bab87d2821","trace_flags":"01","transactionId":"0fc43b48-6fa0-4206-a520-20bab03e48c2","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":1094,"high":0,"unsigned":false},"nanos":249999995,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Still open — read this before you trust the conclusion

First: we never established that paymentservice was ever emitting spans to this backend. The absence in both traces and span metrics predates the endpoint edit by hours. That means a pre-existing instrumentation problem, or a service_name label that does not match what we queried, cannot be separated from the endpoint rewrite. The endpoint change is the best-supported story by timing and mechanism, but the evidence cannot distinguish it from a blackout that was already there.

Second: we still do not know what condition actually fired. If the page was tied to user-visible payment failures, the healthy log tail directly contradicts it and something we never looked at is in play.

Third: coverage. Request rate, latency, restarts and memory/CPU on paymentservice were never returned. The third service in the declared blast radius was never dispatched, and two edges crossed during the walk were never measured. If you are picking this up again, start with those four paymentservice metrics and the third service — they are the cheapest way to either confirm the blackout story or blow it up.

> Evidence `tr_7210d55f984b`:

```
<tool_result id="tr_7210d55f984b" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-09-17T04:41:15.583000+00:00..2026-09-17T10:41:15.583000+00:00">
no traces for paymentservice over this window
</tool_result:tr_7210d55f984b>
```

> Evidence `tr_d2a97eca0742`:

```
<tool_result id="tr_d2a97eca0742" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T07:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" template="error-ratio" baseline="2026-09-17T04:39:22.832707+00:00..2026-09-17T07:41:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_dca2c04cc757`:

```
<tool_result id="tr_dca2c04cc757" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T07:41:15.583000+00:00..2026-09-17T10:43:08.333293+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-17T07:48:45.275730+00:00  {"level":30,"time":1789631325275,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"a2d8414745cda7e5fad4283bde85dac3","span_id":"27784b4f9e4bef0a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":2870,"high":0,"unsigned":false},"nanos":969999993},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-17T07:48:45.276113+00:00  {"level":30,"time":1789631325275,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"a2d8414745cda7e5fad4283bde85dac3","span_id":"27784b4f9e4bef0a","trace_flags":"01","transactionId":"8993fdc3-ed13-4ffc-8c99-671830f07349","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":2870,"high":0,"unsigned":false},"nanos":969999993,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-17T07:48:45.643322+00:00  {"level":30,"time":1789631325643,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"28a621d011a7148eab6883240d073b6f","span_id":"0006f9bab87d2821","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1094,"high":0,"unsigned":false},"nanos":249999995},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-17T07:48:45.643667+00:00  {"level":30,"time":1789631325643,"pid":17,"hostname":"d2fcb542f4b0","trace_id":"28a621d011a7148eab6883240d073b6f","span_id":"0006f9bab87d2821","trace_flags":"01","transactionId":"0fc43b48-6fa0-4206-a520-20bab03e48c2","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":1094,"high":0,"unsigned":false},"nanos":249999995,"currencyCode":"USD"},"msg":"Transaction complete."}
```

