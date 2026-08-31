# paymentservice alert with a clean payment path and an exporter endpoint pointed at nothing

## What the responder saw first

The page named paymentservice and carried critical severity with a blast radius of three services. That framing set an expectation that never materialised: that paymentservice was erroring, slow, or down. The alert marker sits at roughly T+0 (05:21). Everything below is measured relative to that marker, and the first thing worth saying plainly is that the two other services in the blast radius were never reached from this chair. No dispatch left paymentservice. If you are reading this because the same alert fired again, start by looking outward, not inward.

## The one substantiated abnormality

About six minutes before the alert (T-6m, 05:15:10), an automated actor applied an environment-variable update to paymentservice. It set the OTLP traces exporter endpoint to a loopback address on port 4317. Previously no such variable was set, and nothing listens on that port inside the pod. This was the only change recorded against paymentservice in the queried window.

Two properties of this change matter. It was automation-driven, not a human release. And it touched only telemetry export configuration — where traces are sent — not payment business logic and not any upstream or datastore endpoint. So it can plausibly explain degraded observability and a pod replacement to pick up the new variable. It cannot, by itself, explain a critical three-service impact.

> Evidence `tr_0523b5288237`:

```
<tool_result id="tr_0523b5288237" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
service: paymentservice
1 changes
  2026-08-31T05:15:10.246431+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_0523b5288237>
```

## The payment path was clean, on four independent lines of evidence

The error ratio for paymentservice (errored calls over total calls) is flat zero at every sample point across roughly T-10m to T+5m. Two separate queries returned this independently, one with 59 points and one with 61. Min equals max equals zero, so there is no burst hiding between the peaks. The ratio being defined at all also tells you the denominator was non-zero: the service was receiving and completing traffic the whole time, not silent, not scrape-gapped.

Logs agree. Every returned line is info level and consists of charge-request-received / transaction-complete pairs, each pair closing in about a millisecond, across multiple card types and both USD and CAD. This holds at both ends of the window.

Traces agree too. The trace query hit its 200-span cap, so the pod was plainly still exporting. Every paymentservice span is a Charge server span with its child charge span, sub-millisecond, none error-marked. paymentservice appears as a healthy child of checkoutservice PlaceOrder in complete end-to-end traces, and checkout continues past the Charge call into ShipOrder, EmptyCart and email spans. Where PlaceOrder time is spent, it is spent on the item-preparation and shipping-quote leg, not on payment.

> Evidence `tr_785dc1362a64`:

```
<tool_result id="tr_785dc1362a64" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
1 series
  {service_name=paymentservice} min=0 max=0 n=59
</tool_result:tr_785dc1362a64>
```

> Evidence `tr_524fff9f82ca`:

```
<tool_result id="tr_524fff9f82ca" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
1 series
  {service_name=paymentservice} min=0 max=0 n=61
</tool_result:tr_524fff9f82ca>
```

> Evidence `tr_004671248776`:

```
<tool_result id="tr_004671248776" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-08-31T05:11:01.780855+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-08-31T05:11:01.781305+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","transactionId":"bd0b53d0-b723-41b5-8b36-07f3c806183e","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-08-31T05:11:05.925300+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-08-31T05:11:05.925714+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","transactionId":"69d88c23-15c0-441f-8353-330691d1502e","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_05d27c7b7cdc`:

```
<tool_result id="tr_05d27c7b7cdc" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
service: paymentservice
200 spans
  503a5441aa79e5a2 currencyservice/CurrencyService/Convert 0.0ms
  503a5441aa79e5a2 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.2ms
  503a5441aa79e5a2 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

## The container was replaced, and we cannot say why

Log lines before the gap carry one hostname; lines after carry a different one, with the process id unchanged. That is a container replacement somewhere between T-10m and T+3m. It is consistent with a rolling restart to adopt the new environment variable, and that is the reading I lean toward — but it is inference from a hostname string, not from a restart counter.

No restart-count, memory, CPU, or latency-percentile series was ever returned. So a crash or memory-driven kill was never actually excluded, only made less likely: a restart violent enough to drop in-flight work would usually leave error-status calls behind, and there are none.

> Evidence `tr_a2a5e76337b4`:

```
<tool_result id="tr_a2a5e76337b4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-08-31T05:11:01.780855+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-08-31T05:11:01.781305+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","transactionId":"bd0b53d0-b723-41b5-8b36-07f3c806183e","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-08-31T05:11:05.925300+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-08-31T05:11:05.925714+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","transactionId":"69d88c23-15c0-441f-8353-330691d1502e","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_524fff9f82ca`:

```
<tool_result id="tr_524fff9f82ca" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
1 series
  {service_name=paymentservice} min=0 max=0 n=61
</tool_result:tr_524fff9f82ca>
```

## The hole in the evidence — read this before trusting the all-clear

Both log queries were truncated by design: oldest eight lines and newest thirty-two kept, middle discarded. The discarded middle in one query runs from about T-10m to T+1m, and in the other from about T-10m to T+3m. The alert neighbourhood falls entirely inside the elided region in both cases.

This matters more than it sounds. No exporter error, no connection-refused line, no OTLP failure message was ever actually observed. The mechanism for the exporter endpoint pointing at nothing is reasoned from the configuration value, not from a log line saying so. The absence of errors near the alert is an artifact of truncation, not a finding. A narrowed re-query with an explicit line limit over the alert window is the single highest-value next step.

Similarly, the trace result carried no per-span timestamps and was truncated at 200 spans, so it cannot place any span relative to the change or the alert, and cannot confirm or deny an export gap around the container replacement.

> Evidence `tr_004671248776`:

```
<tool_result id="tr_004671248776" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-08-31T05:11:01.780855+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-08-31T05:11:01.781305+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","transactionId":"bd0b53d0-b723-41b5-8b36-07f3c806183e","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-08-31T05:11:05.925300+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-08-31T05:11:05.925714+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","transactionId":"69d88c23-15c0-441f-8353-330691d1502e","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_a2a5e76337b4`:

```
<tool_result id="tr_a2a5e76337b4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-08-31T05:11:01.780855+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-08-31T05:11:01.781305+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","transactionId":"bd0b53d0-b723-41b5-8b36-07f3c806183e","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-08-31T05:11:05.925300+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-08-31T05:11:05.925714+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","transactionId":"69d88c23-15c0-441f-8353-330691d1502e","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_05d27c7b7cdc`:

```
<tool_result id="tr_05d27c7b7cdc" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
service: paymentservice
200 spans
  503a5441aa79e5a2 currencyservice/CurrencyService/Convert 0.0ms
  503a5441aa79e5a2 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.2ms
  503a5441aa79e5a2 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

## Dead ends worth keeping

A code deploy or image rollout: no such record exists for paymentservice in the window; the sole entry is an environment update.

A feature flag flip: no flag-change record present.

A credential or secret rotation — an expired gateway key or database password: no rotation event recorded. The one variable touched governs telemetry, not authentication.

An upstream or datastore endpoint being repointed at an unhealthy backend: the modified variable is the traces exporter endpoint only.

"Nothing changed, so this is purely external": also wrong — a change did land six minutes before the alert, so a change-driven path stayed open.

paymentservice down, crash-looping, or blacked out on telemetry: contradicted by the continuous metric series, the healthy log tail, and the trace result hitting its truncation cap.

paymentservice as the latency source behind checkout degradation: contradicted by sub-millisecond Charge spans and by where PlaceOrder time actually sits.

> Evidence `tr_0523b5288237`:

```
<tool_result id="tr_0523b5288237" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
service: paymentservice
1 changes
  2026-08-31T05:15:10.246431+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_0523b5288237>
```

> Evidence `tr_785dc1362a64`:

```
<tool_result id="tr_785dc1362a64" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
1 series
  {service_name=paymentservice} min=0 max=0 n=59
</tool_result:tr_785dc1362a64>
```

> Evidence `tr_05d27c7b7cdc`:

```
<tool_result id="tr_05d27c7b7cdc" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
service: paymentservice
200 spans
  503a5441aa79e5a2 currencyservice/CurrencyService/Convert 0.0ms
  503a5441aa79e5a2 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.2ms
  503a5441aa79e5a2 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

> Evidence `tr_004671248776`:

```
<tool_result id="tr_004671248776" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-08-31T05:11:01.780855+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-08-31T05:11:01.781305+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","transactionId":"bd0b53d0-b723-41b5-8b36-07f3c806183e","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-08-31T05:11:05.925300+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-08-31T05:11:05.925714+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","transactionId":"69d88c23-15c0-441f-8353-330691d1502e","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Where this landed, and confidence

The only mechanism I can name is the misconfigured exporter endpoint: a value pointed at a port nothing listens on, degrading telemetry and prompting a container replacement. The suggested remediation is a revert of that configuration value. Confidence is low, and deliberately so — this explains a telemetry problem and a restart, not a critical multi-service incident.

Three things remain open. Which two other services are in the blast radius, and how did they behave? Was the container replacement configuration-driven or a crash? And what was actually logged in the four and a half minutes bracketing the alert, which no query ever returned? Until the two uncrossed edges are walked, treat the critical severity as unexplained rather than resolved.

> Evidence `tr_0523b5288237`:

```
<tool_result id="tr_0523b5288237" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
service: paymentservice
1 changes
  2026-08-31T05:15:10.246431+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
</tool_result:tr_0523b5288237>
```

> Evidence `tr_524fff9f82ca`:

```
<tool_result id="tr_524fff9f82ca" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
1 series
  {service_name=paymentservice} min=0 max=0 n=61
</tool_result:tr_524fff9f82ca>
```

> Evidence `tr_a2a5e76337b4`:

```
<tool_result id="tr_a2a5e76337b4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-31T05:11:00.583000+00:00..2026-08-31T05:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-08-31T05:11:01.780855+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-08-31T05:11:01.781305+00:00  {"level":30,"time":1788153061780,"pid":17,"hostname":"c77b045085fd","trace_id":"3b0684a5038fb2086738a6bffe9ea534","span_id":"69faf3720bae2333","trace_flags":"01","transactionId":"bd0b53d0-b723-41b5-8b36-07f3c806183e","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":3588,"high":0,"unsigned":false},"nanos":499999990,"currencyCode":"USD"},"msg":"Transaction complete."}
2026-08-31T05:11:05.925300+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996},"creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardCvv":793,"creditCardExpirationYear":2039,"creditCardExpirationMonth":6}},"msg":"Charge request received."}
2026-08-31T05:11:05.925714+00:00  {"level":30,"time":1788153065925,"pid":17,"hostname":"c77b045085fd","trace_id":"c179e2c9c2960e409f726739845971b3","span_id":"e100bba3f8cf93eb","trace_flags":"01","transactionId":"69d88c23-15c0-441f-8353-330691d1502e","cardType":"visa","lastFourDigits":"5647","amount":{"units":{"low":10916,"high":0,"unsigned":false},"nanos":249999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```
