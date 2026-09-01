# paymentservice telemetry blackout following an automated exporter endpoint update

## What we saw first

The page named paymentservice, and the clock on it read 06:05:15Z. Triage put the blast radius at three services with two edges we had no measurement across; in practice only paymentservice and checkoutservice were ever dispatched, so treat the third service as unexamined rather than cleared.

The first thing a responder reaches for on a payment alert is the error ratio. That query came back with nothing — not a flat zero, but no matching series at all, over 05:55:15 to 06:10:15. Both halves of the expression were missing: the error-status numerator and the total-call denominator. That distinction is the whole incident in miniature. A healthy service still emits a denominator. An absent denominator means either the service stopped taking traffic, or its span metrics stopped arriving at the metrics backend.

> Evidence `tr_49317493f4cb`:

```
<tool_result id="tr_49317493f4cb" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_49317493f4cb>
```

> Evidence `tr_e17e6b32c055`:

```
<tool_result id="tr_e17e6b32c055" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_e17e6b32c055>
```

## The one change in the window

The change history for paymentservice returned exactly one entry: at 05:59:13Z, roughly six minutes before the alert, platform automation updated an environment variable, setting the OTLP traces exporter endpoint — previously unset — to a loopback address on the pod itself, 127.0.0.1:4317.

Worth noting what this entry was not. No image rollout or version bump. No feature flag flip. No credential, secret, or certificate rotation. No library or dependency upgrade. And it was applied by an automated actor rather than a human release. So the tempting early theory that "something must have changed externally because nothing changed here" is wrong — something did change here, minutes ahead of the alert, and it touched the telemetry path specifically.

The reading that holds together is that the new endpoint value is simply wrong: it names a local collector address, and if nothing in the pod listens on that port, trace export begins failing the moment the variable takes effect. That would starve the span-derived metrics and produce exactly the empty result we opened with.

> Evidence `tr_d12626f5a460`:

```
<tool_result id="tr_d12626f5a460" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
1 changes
  2026-09-01T05:59:13.301840+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_d12626f5a460>
```

## Evidence the service itself was fine

Against the telemetry story, we needed to know whether paymentservice was actually broken. It was not.

Traces over the window that straddles 05:59:13Z came back non-empty — 200 spans, capped. paymentservice appears as a participant in several independent checkout traces, handling Charge server-side with a child charge operation, sub-millisecond, no error rows. One trace is paymentservice's own OTLP metrics export RPC, so its export calls are themselves instrumented. That rules out a process that was down, crash-looping, or refusing requests, and rules out payment as the slow or failing element. It also rules out the trace backend being unavailable and thereby faking a gap — the backend served a full capped result on request.

Logs agree. Every returned line is informational: a charge request followed about a millisecond later by a completed transaction, across varied amounts and multiple distinct cards, both before and after the alert minute. No errors, exceptions, warnings, or rejections anywhere. That kills the theory of a sustained error stream spanning the window, the theory that the service was still failing afterwards, and the theory that the charge-handling code path itself was broken.

From upstream, checkoutservice's aggregate error ratio is continuously sampled — 44 samples, min and max both zero — straight through 06:05:15. Continuous non-empty sampling also means checkoutservice did not itself go quiet or crash and hide the failure. A hard downstream failure would have surfaced as error-status spans on its outbound calls; it never did.

> Evidence `tr_387f51d86c3e`:

```
<tool_result id="tr_387f51d86c3e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
200 spans
  38af5fcae191cd7f quoteservice/calculate-quote 0.0ms
  38af5fcae191cd7f checkoutservice/hipstershop.CurrencyService/Convert 1.0ms
  38af5fcae191cd7f currencyservice/CurrencyService/Convert 0.0ms
```

> Evidence `tr_4cf361da961c`:

```
<tool_result id="tr_4cf361da961c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-01T05:55:25.883739+00:00  {"level":30,"time":1788242125883,"pid":17,"hostname":"3635a7a8daee","trace_id":"9173cc17a69efa592a2cf03bdad5a6ac","span_id":"da6f0e8b600f88c8","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3132,"high":0,"unsigned":false},"nanos":49999976},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-01T05:55:25.884201+00:00  {"level":30,"time":1788242125883,"pid":17,"hostname":"3635a7a8daee","trace_id":"9173cc17a69efa592a2cf03bdad5a6ac","span_id":"da6f0e8b600f88c8","trace_flags":"01","transactionId":"af356216-af77-40c3-ab74-aa0a8bd428d9","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":3132,"high":0,"unsigned":false},"nanos":49999976,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-01T05:55:32.918241+00:00  {"level":30,"time":1788242132918,"pid":17,"hostname":"3635a7a8daee","trace_id":"2b0ef56217f194d45de576c2c971d706","span_id":"ec951207fa5569e3","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1435,"high":0,"unsigned":false},"nanos":399999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-01T05:55:32.918749+00:00  {"level":30,"time":1788242132918,"pid":17,"hostname":"3635a7a8daee","trace_id":"2b0ef56217f194d45de576c2c971d706","span_id":"ec951207fa5569e3","trace_flags":"01","transactionId":"1b1d116a-1d01-4b0a-851e-839bcf20c971","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":1435,"high":0,"unsigned":false},"nanos":399999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_2dc47bce9707`:

```
<tool_result id="tr_2dc47bce9707" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0 n=44
</tool_result:tr_2dc47bce9707>
```

## Dead ends and the shape of the gaps

Several lines of inquiry cost time and returned nothing usable. Recording them so the next responder does not repeat them.

The log query was truncated in the middle. It kept the oldest eight lines (05:55:25–05:56:04) and the newest thirty-two (06:06:07–06:07:38), and discarded exactly the interval containing 06:05:15. The incident minute itself was never read. Whatever error text or dependency name was emitted at that moment is unknown, and this result eliminates candidates rather than identifying one.

Inside that unread gap, the emitting hostname changes — pre-05:56 lines come from one host, post-06:06 lines from another, same process id. That is consistent with the instance being replaced around 06:05. But no container restart counter, OOM-kill counter, CPU throttling, or memory working-set series was ever queried, so a restart is neither confirmed nor attributed. Do not let the hostname change harden into a restart narrative on its own.

The trace result carries no per-span timestamps and is truncated. It proves spans exist somewhere in the window; it cannot show whether export continued, thinned, or stopped after 05:59:13Z. The ordering shown is not a timeline.

Latency was never measured on either side — no percentiles for paymentservice, none for the checkoutservice→paymentservice edge. And checkoutservice's error ratio has no peer dimension, so it reflects that service's overall call outcomes rather than its calls to payment specifically.

Both metrics dispatches also queried a narrower window (05:55:15–06:10:15) than the range asked about, leaving the edges of the period uncovered even where series had existed.

> Evidence `tr_4cf361da961c`:

```
<tool_result id="tr_4cf361da961c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-01T05:55:25.883739+00:00  {"level":30,"time":1788242125883,"pid":17,"hostname":"3635a7a8daee","trace_id":"9173cc17a69efa592a2cf03bdad5a6ac","span_id":"da6f0e8b600f88c8","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3132,"high":0,"unsigned":false},"nanos":49999976},"creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardCvv":672,"creditCardExpirationYear":2039,"creditCardExpirationMonth":1}},"msg":"Charge request received."}
2026-09-01T05:55:25.884201+00:00  {"level":30,"time":1788242125883,"pid":17,"hostname":"3635a7a8daee","trace_id":"9173cc17a69efa592a2cf03bdad5a6ac","span_id":"da6f0e8b600f88c8","trace_flags":"01","transactionId":"af356216-af77-40c3-ab74-aa0a8bd428d9","cardType":"visa","lastFourDigits":"0454","amount":{"units":{"low":3132,"high":0,"unsigned":false},"nanos":49999976,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-01T05:55:32.918241+00:00  {"level":30,"time":1788242132918,"pid":17,"hostname":"3635a7a8daee","trace_id":"2b0ef56217f194d45de576c2c971d706","span_id":"ec951207fa5569e3","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1435,"high":0,"unsigned":false},"nanos":399999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-09-01T05:55:32.918749+00:00  {"level":30,"time":1788242132918,"pid":17,"hostname":"3635a7a8daee","trace_id":"2b0ef56217f194d45de576c2c971d706","span_id":"ec951207fa5569e3","trace_flags":"01","transactionId":"1b1d116a-1d01-4b0a-851e-839bcf20c971","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":1435,"high":0,"unsigned":false},"nanos":399999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_e17e6b32c055`:

```
<tool_result id="tr_e17e6b32c055" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_e17e6b32c055>
```

> Evidence `tr_387f51d86c3e`:

```
<tool_result id="tr_387f51d86c3e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
200 spans
  38af5fcae191cd7f quoteservice/calculate-quote 0.0ms
  38af5fcae191cd7f checkoutservice/hipstershop.CurrencyService/Convert 1.0ms
  38af5fcae191cd7f currencyservice/CurrencyService/Convert 0.0ms
```

> Evidence `tr_49317493f4cb`:

```
<tool_result id="tr_49317493f4cb" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_49317493f4cb>
```

> Evidence `tr_2dc47bce9707`:

```
<tool_result id="tr_2dc47bce9707" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0 n=44
</tool_result:tr_2dc47bce9707>
```

## Where we landed

Most consistent reading, at medium confidence: the exporter endpoint value set at 05:59:13Z points at a local address nothing is listening on, trace export breaks, and paymentservice's span-derived metrics vanish. The result is an observability blackout on paymentservice, not a request-path failure — the service kept charging cards correctly throughout, and its upstream never saw an error. Fix class is a revert of the config value.

> Evidence `tr_d12626f5a460`:

```
<tool_result id="tr_d12626f5a460" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
1 changes
  2026-09-01T05:59:13.301840+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_d12626f5a460>
```

> Evidence `tr_49317493f4cb`:

```
<tool_result id="tr_49317493f4cb" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_49317493f4cb>
```

> Evidence `tr_387f51d86c3e`:

```
<tool_result id="tr_387f51d86c3e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
200 spans
  38af5fcae191cd7f quoteservice/calculate-quote 0.0ms
  38af5fcae191cd7f checkoutservice/hipstershop.CurrencyService/Convert 1.0ms
  38af5fcae191cd7f currencyservice/CurrencyService/Convert 0.0ms
```

## What would settle it

The causal link from the endpoint value to the missing metrics is inferred, never demonstrated. A single look at the pod's sidecar spec — is anything listening on 127.0.0.1:4317 — either confirms or breaks this verdict outright. Do that first.

Second highest value: re-run the trace query split into pre- and post-05:59:13Z windows. That directly tests whether export stopped at the change, which is the one thing the current trace evidence cannot say.

The uncomfortable open item is that nobody identified what actually fired at 06:05:15. No dispatch surfaced the alerting condition, and none of the returned signals — checkout errors, payment errors, payment latency — is elevated. If that alert was a request-path alert rather than a no-data or telemetry alert, this whole record is explaining the wrong symptom. Check the alert rule before acting on the conclusion.

Also outstanding: whether an instance replacement occurred near 06:05 and what drove it; latency percentiles on both sides, since an exporter that blocks rather than fails fast would put a latency mechanism in play and shift the classification; a per-peer breakdown of checkoutservice's call outcomes to fully exclude partial downstream failure; and the third service plus both unmeasured edges from triage, which nobody looked at.

> Evidence `tr_d12626f5a460`:

```
<tool_result id="tr_d12626f5a460" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
1 changes
  2026-09-01T05:59:13.301840+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_d12626f5a460>
```

> Evidence `tr_387f51d86c3e`:

```
<tool_result id="tr_387f51d86c3e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
service: paymentservice
200 spans
  38af5fcae191cd7f quoteservice/calculate-quote 0.0ms
  38af5fcae191cd7f checkoutservice/hipstershop.CurrencyService/Convert 1.0ms
  38af5fcae191cd7f currencyservice/CurrencyService/Convert 0.0ms
```

> Evidence `tr_e17e6b32c055`:

```
<tool_result id="tr_e17e6b32c055" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_e17e6b32c055>
```

> Evidence `tr_2dc47bce9707`:

```
<tool_result id="tr_2dc47bce9707" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T05:55:15.583000+00:00..2026-09-01T06:10:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0 n=44
</tool_result:tr_2dc47bce9707>
```
