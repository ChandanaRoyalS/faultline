# Payment service paged with no telemetry while charges kept completing

## What was visible, in order

The page named paymentservice; triage called it critical across three services with two unmeasured edges. First move was an error ratio built from span-derived call counts. It came back empty — not zero, empty. The error-filtered numerator returned nothing and so did the unfiltered denominator covering all calls regardless of status. That shape matters: a failing service still populates the denominator, and so does a healthy one. This was absent data, not bad data, so I stopped querying that metric family and pivoted to logs, traces, and change history.

Logs were all info-level: paired charge-request-received and transaction-complete lines, no errors or warnings anywhere. The result was truncated in the worst possible way, keeping only the oldest few and newest thirty-odd lines and dropping the middle — which is exactly the interval containing the moment of the page. Both surviving segments show healthy processing, charge pairs completing within about a millisecond, across multiple cards and two currencies. One incidental detail carried real weight: the container hostname differs between the early and late segments, so the instance was replaced somewhere inside the missing interval.

Traces then contradicted the simplest reading. Two hundred spans (truncated) came back for the same window, including the gRPC Charge handler and its internal charge span, all sub-millisecond, all inside intact frontend→checkout→payment chains with parent spans around twenty milliseconds. Eight other services appear in the same traces. Checkoutservice's error ratio was a measured flat zero across sixty-one unbroken samples with a populated denominator — a real zero, not a gap.

> Evidence `tr_54adf3203c6c`:

```
<tool_result id="tr_54adf3203c6c" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_54adf3203c6c>
```

> Evidence `tr_636b3d98dbb2`:

```
<tool_result id="tr_636b3d98dbb2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-01T09:20:51.591889+00:00  {"level":30,"time":1788254451591,"pid":17,"hostname":"6e65d7eb9947","trace_id":"a655b473c35ad3021378e2ec75b8c14b","span_id":"75b2c4d690dc058d","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3233,"high":0,"unsigned":false},"nanos":49999991},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-01T09:20:51.592284+00:00  {"level":30,"time":1788254451591,"pid":17,"hostname":"6e65d7eb9947","trace_id":"a655b473c35ad3021378e2ec75b8c14b","span_id":"75b2c4d690dc058d","trace_flags":"01","transactionId":"d5043aeb-3536-42be-813e-902c45bdf130","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":3233,"high":0,"unsigned":false},"nanos":49999991,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-01T09:21:01.088800+00:00  {"level":30,"time":1788254461088,"pid":17,"hostname":"6e65d7eb9947","trace_id":"4372c828f2bcccfb10f1bd42f7ba962b","span_id":"c1c7f69954794e3a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1912,"high":0,"unsigned":false},"nanos":749999990},"creditCard":{"creditCardNumber":"4532-6178-2799-1951","creditCardCvv":239,"creditCardExpirationYear":2039,"creditCardExpirationMonth":3}},"msg":"Charge request received."}
2026-09-01T09:21:01.089208+00:00  {"level":30,"time":1788254461088,"pid":17,"hostname":"6e65d7eb9947","trace_id":"4372c828f2bcccfb10f1bd42f7ba962b","span_id":"c1c7f69954794e3a","trace_flags":"01","transactionId":"7183542d-7212-4215-8228-320d418d9ae3","cardType":"visa","lastFourDigits":"1951","amount":{"units":{"low":1912,"high":0,"unsigned":false},"nanos":749999990,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_e1a1eb5bf2b3`:

```
<tool_result id="tr_e1a1eb5bf2b3" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00">
service: paymentservice
200 spans
  b31d804f977a4b19 cartservice/hipstershop.CartService/GetCart 0.5ms
  b31d804f977a4b19 cartservice/HGET 0.3ms
  b31d804f977a4b19 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
```

> Evidence `tr_3efe7d0db599`:

```
<tool_result id="tr_3efe7d0db599" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0 n=61
</tool_result:tr_3efe7d0db599>
```

## The change that explains the shape

Change history returned exactly one entry: a platform-automation environment update setting the OTLP traces export endpoint variable — previously unset — to a loopback address on port 4317, about six minutes before the page. No collector listens on that in-pod loopback target, so the export path pointed at nothing. That accounts for the empty call-metric series on both numerator and denominator, and such an environment mutation rolls the pod, matching the hostname change across the unreturned log interval.

The change touches telemetry export only — not business logic, routing, or data stores — which fits everything the logs and traces showed about charge handling being healthy throughout. Working conclusion: a configuration value naming the wrong export address broke the measurement path and produced a no-data page, not a payment degradation. Fix class is a revert of that value. Confidence medium.

> Evidence `tr_eb6ff6f007ba`:

```
<tool_result id="tr_eb6ff6f007ba" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00">
service: paymentservice
1 changes
  2026-09-01T09:24:49.625960+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_eb6ff6f007ba>
```

## Dead ends and what remains open

Dead ends worth not repeating: iterating label permutations on the span-derived call metric after the first empty result (the base family yields nothing here — leave it); hunting for a deploy, image rollout, flag flip, credential rotation, or repointed dependency, none of which exist in the window; assuming nothing changed and the trigger was external; assuming an operator made an emergency manual edit, when the sole change is automation-attributed and predates the page; chasing a latency signature, since every returned request/complete pair sits within a millisecond; chasing a fleet-wide collector problem, since eight other services trace normally.

Still open. The empty series may mean no emission or a different metric/label naming — nothing distinguished these, so "telemetry broke" is inferred, not measured. At least one observed paymentservice span is itself an OTLP export call completing in a few milliseconds, and the trace listing carries no per-span timestamps and was truncated, so it is unknown whether any spans postdate the change; if export continued, the loopback target was not fully dead and this explanation weakens. The log gap covers the alert moment itself. Nothing retrieved the alert definition, so a no-data firing condition is assumed rather than confirmed. The change query covered only the final ten minutes before the reference point. The third affected service and the two unmeasured edges were never dispatched. Whether pointing the exporter at a dead target caused queue backpressure or startup blocking was never measured — no process- or container-level resource data was collected.

> Evidence `tr_eb6ff6f007ba`:

```
<tool_result id="tr_eb6ff6f007ba" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00">
service: paymentservice
1 changes
  2026-09-01T09:24:49.625960+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_eb6ff6f007ba>
```

> Evidence `tr_e1a1eb5bf2b3`:

```
<tool_result id="tr_e1a1eb5bf2b3" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00">
service: paymentservice
200 spans
  b31d804f977a4b19 cartservice/hipstershop.CartService/GetCart 0.5ms
  b31d804f977a4b19 cartservice/HGET 0.3ms
  b31d804f977a4b19 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
```

> Evidence `tr_636b3d98dbb2`:

```
<tool_result id="tr_636b3d98dbb2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-01T09:20:45.583000+00:00..2026-09-01T09:35:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-01T09:20:51.591889+00:00  {"level":30,"time":1788254451591,"pid":17,"hostname":"6e65d7eb9947","trace_id":"a655b473c35ad3021378e2ec75b8c14b","span_id":"75b2c4d690dc058d","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3233,"high":0,"unsigned":false},"nanos":49999991},"creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardCvv":114,"creditCardExpirationYear":2039,"creditCardExpirationMonth":2}},"msg":"Charge request received."}
2026-09-01T09:20:51.592284+00:00  {"level":30,"time":1788254451591,"pid":17,"hostname":"6e65d7eb9947","trace_id":"a655b473c35ad3021378e2ec75b8c14b","span_id":"75b2c4d690dc058d","trace_flags":"01","transactionId":"d5043aeb-3536-42be-813e-902c45bdf130","cardType":"visa","lastFourDigits":"1278","amount":{"units":{"low":3233,"high":0,"unsigned":false},"nanos":49999991,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-01T09:21:01.088800+00:00  {"level":30,"time":1788254461088,"pid":17,"hostname":"6e65d7eb9947","trace_id":"4372c828f2bcccfb10f1bd42f7ba962b","span_id":"c1c7f69954794e3a","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":1912,"high":0,"unsigned":false},"nanos":749999990},"creditCard":{"creditCardNumber":"4532-6178-2799-1951","creditCardCvv":239,"creditCardExpirationYear":2039,"creditCardExpirationMonth":3}},"msg":"Charge request received."}
2026-09-01T09:21:01.089208+00:00  {"level":30,"time":1788254461088,"pid":17,"hostname":"6e65d7eb9947","trace_id":"4372c828f2bcccfb10f1bd42f7ba962b","span_id":"c1c7f69954794e3a","trace_flags":"01","transactionId":"7183542d-7212-4215-8228-320d418d9ae3","cardType":"visa","lastFourDigits":"1951","amount":{"units":{"low":1912,"high":0,"unsigned":false},"nanos":749999990,"currencyCode":"USD"},"msg":"Transaction complete."}
```
