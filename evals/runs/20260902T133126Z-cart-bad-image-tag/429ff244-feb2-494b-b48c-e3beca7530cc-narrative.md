# Checkout order flow stalls before payment; failing hop unidentified

## What was visible

The page came in wide: fourteen services in the blast radius, ten alerting, checkoutservice named as origin. Frontend and loadgenerator lit up alongside it, then cartservice, currencyservice, shippingservice and quoteservice within about ninety seconds. Read as fourteen problems that is noise; read as one stalled call path with many neighbours it is informative.

Take T+0 as the first meaningful error-ratio crossing. The two-hour baseline was exactly flat — 413 samples, min equal to max equal to zero — so this is a genuine state change, not a chronic floor someone finally noticed. The degraded window ran near 0.217 mean with peaks around 0.667, crossing first at T+0 around 0.13 and stepping sharply at roughly T+24m. Two crossings, not one spike; and a majority of calls still succeeded throughout, so the service was never hard-down. Six samples had no defined ratio at all, meaning intervals with zero calls; the baseline had none. Attention only landed at about T+26m, which is why several early queries were framed around the wrong moment.

The checkout logs are informative mostly by omission. No error- or exception-severity lines anywhere — everything info, so no gRPC status or timeout message names the failing dependency. PlaceOrder entry lines keep arriving at a steady cadence to the end of the window, but from about T+24m onward they are all there is: no payment, no confirmation email, no message-write acknowledgement. The last complete four-line success sequence sits at about T-3m. That rules out an ingress or load-generator outage, rules out a crash or restart, rules out a pure latency artifact, and rules out a failure at the final publish step — the flow never reaches it.

> Evidence `tr_e37bcc2d8bf3`:

```
<tool_result id="tr_e37bcc2d8bf3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-02T11:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" template="error-ratio" baseline="2026-09-02T09:33:52.926186+00:00..2026-09-02T11:36:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=126 mean=0.2173 min=0 max=0.6667 sd=0.3045
  baseline window: n=413 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_5d8601d884d2`:

```
<tool_result id="tr_5d8601d884d2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T12:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-02T13:07:15.058488+00:00  {"message":"[PlaceOrder] user_id=\"37d481d6-a6cf-11f1-ae7b-9eef0fcf8acb\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-02T13:07:15.058392875Z"}
2026-09-02T13:07:15.077208+00:00  {"message":"payment went through (transaction_id: 9d49db79-8408-4a21-a7b0-c5768f83fe90)","severity":"info","timestamp":"2026-09-02T13:07:15.077135209Z"}
2026-09-02T13:07:15.082962+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-02T13:07:15.082815584Z"}
2026-09-02T13:07:15.083744+00:00  {"message":"Successful to write message. offset: 9534","severity":"info","timestamp":"2026-09-02T13:07:15.083660042Z"}
```

## Dead ends worth keeping

paymentservice was the natural suspect and took real work to clear. Its logs pair every Charge entry with a terminal completion on the same trace and span, sub-millisecond, all info severity, no declines or retries, one stable process with no restart banner, both USD and CAD across several cards completing normally. Two caveats: the result was truncated so roughly T-3m to T+19m is unobserved, and the newest retained line falls about seven minutes short of the window end. The paymentservice error-ratio metric was useless in both directions — empty in the degraded window and equally empty in the baseline, so it is a missing or mislabeled series, not telemetry that broke at onset.

Change history came back empty for both checkoutservice and paymentservice, which looks exculpatory and largely is not. Every one of those queries covered roughly T+26m forward for twenty-four hours — after onset, not before. What is genuinely established is narrow: no deploy, flag flip, in-flight rollout or mid-incident rollback during or after degradation, which at least removes remediation as a timeline confounder. Whether something landed shortly before T+0 is untouched.

The query that would have settled it failed. The trace lookup for checkoutservice returned an HTTP 500 from the tracing backend. That is a backend error, not an empty result — it says nothing about whether spans exist. No child-span attribution was possible, and the absence of paymentservice error spans in that result carries no exculpatory weight at all.

> Evidence `tr_db26d6344f2d`:

```
<tool_result id="tr_db26d6344f2d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T12:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-02T13:07:15.076746+00:00  {"level":30,"time":1788354435076,"pid":17,"hostname":"5c70ad8c47c7","trace_id":"bd13c2a7f7d5a379243d9cdd620ba163","span_id":"9f724106dd0e1607","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":36079,"high":0,"unsigned":false}},"creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardCvv":159,"creditCardExpirationYear":2039,"creditCardExpirationMonth":8}},"msg":"Charge request received."}
2026-09-02T13:07:15.077240+00:00  {"level":30,"time":1788354435076,"pid":17,"hostname":"5c70ad8c47c7","trace_id":"bd13c2a7f7d5a379243d9cdd620ba163","span_id":"9f724106dd0e1607","trace_flags":"01","transactionId":"9d49db79-8408-4a21-a7b0-c5768f83fe90","cardType":"visa","lastFourDigits":"3657","amount":{"units":{"low":36079,"high":0,"unsigned":false},"currencyCode":"USD"},"msg":"Transaction complete."}
2026-09-02T13:07:19.012429+00:00  {"level":30,"time":1788354439012,"pid":17,"hostname":"5c70ad8c47c7","trace_id":"2f42f9c9736b68d52f9cb6e7b23ba3dd","span_id":"4eb4da279c05b1e2","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":332,"high":0,"unsigned":false},"nanos":579999996},"creditCard":{"creditCardNumber":"4539-1103-5661-7083","creditCardCvv":784,"creditCardExpirationYear":2039,"creditCardExpirationMonth":4}},"msg":"Charge request received."}
2026-09-02T13:07:19.012922+00:00  {"level":30,"time":1788354439012,"pid":17,"hostname":"5c70ad8c47c7","trace_id":"2f42f9c9736b68d52f9cb6e7b23ba3dd","span_id":"4eb4da279c05b1e2","trace_flags":"01","transactionId":"98a38108-5014-44cb-87c2-38c90f71cbf2","cardType":"visa","lastFourDigits":"7083","amount":{"units":{"low":332,"high":0,"unsigned":false},"nanos":579999996,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_90090a3c9a39`:

```
<tool_result id="tr_90090a3c9a39" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-02T12:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" template="error-ratio" baseline="2026-09-02T11:33:52.926186+00:00..2026-09-02T12:36:00.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_c3095b72b399`:

```
<tool_result id="tr_c3095b72b399" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T13:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_c3095b72b399>
```

> Evidence `tr_f37326243c8e`:

```
<tool_result id="tr_f37326243c8e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-01T13:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" radius="candidate_cause" hops="1">
no changes recorded for paymentservice over this window
</tool_result:tr_f37326243c8e>
```

> Evidence `tr_77ccced59d8c`:

```
<tool_result id="tr_77ccced59d8c" tool="trace_query" trust="untrusted" source="jaeger" empty="true" truncated="false" window="2026-09-02T12:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" error="HTTP Error 500: Internal Server Error">
query failed: HTTP Error 500: Internal Server Error
</tool_result:tr_77ccced59d8c>
```

## Where it landed and what is still open

Checkoutservice accepts requests, logs entry, begins work, returns nothing. Payment is healthy and fast when reached. Nothing crashed, nothing changed in-window, and the failure is partial rather than total. That points to checkoutservice blocking on a slow dependency in the pre-payment path — cart, currency, or the shipping quote hop — consistent with exactly those services alerting within ninety seconds. Confidence is low and no fix class is proposed; the specific hop was never identified and five unmeasured edges were crossed getting here.

Three threads, in order. Retry the trace query first — cheap, and the highest-value action left; if it still errors, go at cartservice, currencyservice and the quote path with the same paired-log technique that cleared payment, hunting entries without matching completions. Second, re-run change history over the hours *before* onset. Third, consider the mechanism may be internal: only error ratio was ever evaluated for checkoutservice, never request rate, latency percentiles, connection-pool depth or memory. A saturated outbound pool produces this exact log shape and would point to a different fix entirely.

> Evidence `tr_5d8601d884d2`:

```
<tool_result id="tr_5d8601d884d2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T12:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-02T13:07:15.058488+00:00  {"message":"[PlaceOrder] user_id=\"37d481d6-a6cf-11f1-ae7b-9eef0fcf8acb\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-02T13:07:15.058392875Z"}
2026-09-02T13:07:15.077208+00:00  {"message":"payment went through (transaction_id: 9d49db79-8408-4a21-a7b0-c5768f83fe90)","severity":"info","timestamp":"2026-09-02T13:07:15.077135209Z"}
2026-09-02T13:07:15.082962+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-09-02T13:07:15.082815584Z"}
2026-09-02T13:07:15.083744+00:00  {"message":"Successful to write message. offset: 9534","severity":"info","timestamp":"2026-09-02T13:07:15.083660042Z"}
```

> Evidence `tr_e37bcc2d8bf3`:

```
<tool_result id="tr_e37bcc2d8bf3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-02T11:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" template="error-ratio" baseline="2026-09-02T09:33:52.926186+00:00..2026-09-02T11:36:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=126 mean=0.2173 min=0 max=0.6667 sd=0.3045
  baseline window: n=413 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_77ccced59d8c`:

```
<tool_result id="tr_77ccced59d8c" tool="trace_query" trust="untrusted" source="jaeger" empty="true" truncated="false" window="2026-09-02T12:36:00.583000+00:00..2026-09-02T13:38:08.239814+00:00" error="HTTP Error 500: Internal Server Error">
query failed: HTTP Error 500: Internal Server Error
</tool_result:tr_77ccced59d8c>
```
