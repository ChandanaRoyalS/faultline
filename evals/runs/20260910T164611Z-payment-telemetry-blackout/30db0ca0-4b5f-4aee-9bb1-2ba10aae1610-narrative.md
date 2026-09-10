# Critical alert on paymentservice with no supporting signal: a telemetry endpoint pointed at loopback

## What the responder saw first

The page named paymentservice, severity critical, with a blast radius drawn across three services (paymentservice, checkoutservice, frontend). Onset was stamped at 16:52:15. Two of the edges in that radius had never been measured, which matters later.

The first instinct — open the error-ratio panel for the alerting service — produced nothing. Not a flat line: nothing. The span-derived call counter series scoped to paymentservice returned zero samples for the whole ~32-minute window. That is the single most important early observation, and it is easy to misread as "healthy".

> Evidence `tr_c051aabba503`:

```
<tool_result id="tr_c051aabba503" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The first dead end: treating the empty panel as a collection outage

The natural next move was to assume the telemetry pipeline had died at onset. That was checked by pulling the same query over the preceding baseline window, and it came back equally empty. Whatever is keeping those series from existing predates 16:52:15 by at least half an hour, so it cannot be a new-onset collection break aligned to the alert.

The same emptiness closes two opposite conclusions at once. You cannot say paymentservice spiked (no samples to spike), and you cannot say paymentservice held steady (no samples to be steady). Both readings were abandoned. A related point worth carrying forward: this query, as written, is not a usable monitoring signal for this service at all — the selector or the instrumentation does not match.

> Evidence `tr_c051aabba503`:

```
<tool_result id="tr_c051aabba503" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The second dead end: looking for the error text in the service's own logs

With metrics blind, the logs were the obvious fallback. Every returned paymentservice line was info-level. No errors, no warnings, no exceptions, no stack traces, no rejections, and no line naming a downstream dependency, credential, secret, or config value.

Charge handling looked ordinary in both the oldest and newest portions of the window: each charge request was followed within about a millisecond by a completion line carrying a transaction id, card type and last four digits — including the requests bracketing the onset timestamp. So the service was not failing charges, not rejecting on a missing credential, and not crashing or looping: the process id was stable across the contiguous late segment, with no startup, shutdown or fatal lines.

The honest conclusion from this branch is that paymentservice's own logs were the wrong place to look. Whatever tripped the alert was not something this service wrote down.

> Evidence `tr_da570bd78bc4`:

```
<tool_result id="tr_da570bd78bc4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T16:22:26.984334+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":505,"high":0,"unsigned":false},"nanos":372886330},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T16:22:26.984685+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","transactionId":"d8247068-93b4-43bc-b6f8-e9055124635d","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":505,"high":0,"unsigned":false},"nanos":372886330,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-10T16:22:30.391729+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":394,"high":0,"unsigned":false},"nanos":250000000},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-10T16:22:30.392433+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","transactionId":"97a11516-0dee-4a33-8781-636d32c6541a","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":394,"high":0,"unsigned":false},"nanos":250000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Two details in the logs that did turn out to matter

Two things in the log output survived the dead end. First, a roughly 28-second hole in output spanning the onset stamp: the last completion before it landed at 16:52:10, the next charge request at 16:52:38, nothing in between. That segment of the result was contiguous rather than truncated, so it is a genuine absence of output, not an absence of retained lines.

Second, the reporting host identifier differs between the early lines and the late lines while the process id stays the same — consistent with the service running on a different replica by 16:52 than it was at 16:22. A short output gap plus a changed host is what a replica roll looks like from the log side.

Caveat for anyone re-reading this: the log result was truncated to the oldest eight and newest thirty-two lines, so roughly 16:22:41 through 16:52:04 was never observed.

> Evidence `tr_da570bd78bc4`:

```
<tool_result id="tr_da570bd78bc4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T16:22:26.984334+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":505,"high":0,"unsigned":false},"nanos":372886330},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T16:22:26.984685+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","transactionId":"d8247068-93b4-43bc-b6f8-e9055124635d","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":505,"high":0,"unsigned":false},"nanos":372886330,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-10T16:22:30.391729+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":394,"high":0,"unsigned":false},"nanos":250000000},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-10T16:22:30.392433+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","transactionId":"97a11516-0dee-4a33-8781-636d32c6541a","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":394,"high":0,"unsigned":false},"nanos":250000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

## Third dead end: chasing the callers

If the service itself is quiet, the failure might be surfacing at the callers. Both were checked and both came back clean, in a way that also closed off some tempting stories.

checkoutservice error ratio was flat at zero across all 128 incident-window samples. Its comparison baseline, though, carried a substantial error ratio — mean around 0.17 with peaks near 0.67 — so errors went *down* entering the window, not up. There is no error onset in checkoutservice to order against paymentservice, which rules out both the "downstream failure propagating through checkout" story and the "co-primary failure" story. The earlier elevated errors sit in the pre-onset baseline and resolve during the window, so they belong to something before this incident.

frontend told the same story: identically zero across 128 samples, zero variance, against a baseline mean of ~0.082 peaking near 0.33. At roughly 15-second granularity even a sub-30-second burst would have registered above zero, so the "brief burst that self-recovered" explanation is closed too. Note that neither of these results measured latency — only the error-ratio template was evaluated.

> Evidence `tr_3264013da097`:

```
<tool_result id="tr_3264013da097" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1719 min=0 max=0.6667 sd=0.2802
```

> Evidence `tr_c1ab5ef493db`:

```
<tool_result id="tr_c1ab5ef493db" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.08247 min=0 max=0.3311 sd=0.1242
```

## Where the signal actually was: the change record

The change record for paymentservice in the window contained seven entries, and all seven were environment-variable edits to a single key: the OTLP traces endpoint. Nothing else. No deploys, no releases, no feature-flag flips, no dependency bumps, no credential rotations, and no individual human operator — every entry was attributed to the same automated actor.

The pattern is a loop. The same set-then-revert pair repeated four times over roughly eighteen hours (around 22:59, 06:42, 13:18, and 16:46), each set followed by a revert about eleven minutes later — except the last one. The 16:46 set, five minutes before onset, has no matching revert in the window, so the service was most likely running with the endpoint pointed at a loopback address at onset.

One guard worth keeping: the closeness in time is not by itself proof. The identical set-edit had already occurred three times earlier in the window without producing this page, so "it happened just before" cannot carry the argument alone.

> Evidence `tr_325c5d8c71bb`:

```
<tool_result id="tr_325c5d8c71bb" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T16:52:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" radius="seed" hops="0">
service: paymentservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-10T16:46:17.311548+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.4h before onset  2026-09-10T13:29:31.187105+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

## What we concluded, and how firmly

Reading the pieces together: the only change touching the service is a flapping automated edit to the traces endpoint, and its final state points the exporter at an address where no collector listens. With export broken, the span-derived call counters that the alert rests on have no samples in either window. The service itself is serving normally — sub-millisecond charge completions with transaction ids on both sides of the onset stamp — and both callers are error-free and trending better than baseline. The visible "onset" is the ~28-second output gap and the host change, which is what the 16:46 edit rolling the replica would look like.

So the failing mechanism is the configuration value itself: a traces endpoint naming the wrong address, which broke telemetry export and blinded the alerting path. Confidence is medium. The fix class is a configuration revert — and, separately, stopping the automation loop that keeps re-applying the value.

> Evidence `tr_325c5d8c71bb`:

```
<tool_result id="tr_325c5d8c71bb" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T16:52:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" radius="seed" hops="0">
service: paymentservice
7 changes, ranked by suspicion
  #1  5m before onset  2026-09-10T16:46:17.311548+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
      None  ->  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
  #2  3.4h before onset  2026-09-10T13:29:31.187105+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
```

> Evidence `tr_c051aabba503`:

```
<tool_result id="tr_c051aabba503" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_da570bd78bc4`:

```
<tool_result id="tr_da570bd78bc4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T16:22:26.984334+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":505,"high":0,"unsigned":false},"nanos":372886330},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T16:22:26.984685+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","transactionId":"d8247068-93b4-43bc-b6f8-e9055124635d","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":505,"high":0,"unsigned":false},"nanos":372886330,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-10T16:22:30.391729+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":394,"high":0,"unsigned":false},"nanos":250000000},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-10T16:22:30.392433+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","transactionId":"97a11516-0dee-4a33-8781-636d32c6541a","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":394,"high":0,"unsigned":false},"nanos":250000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_3264013da097`:

```
<tool_result id="tr_3264013da097" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1719 min=0 max=0.6667 sd=0.2802
```

> Evidence `tr_c1ab5ef493db`:

```
<tool_result id="tr_c1ab5ef493db" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.08247 min=0 max=0.3311 sd=0.1242
```

## Left open for whoever reads this next

Three threads were not closed.

First, we could not distinguish whether the empty call-counter series is caused by the loopback endpoint or by a naming mismatch — the logs carry the service as payment-service while the metric selector uses paymentservice. The baseline window is equally empty, which is exactly what a label mismatch would also produce.

Second, nothing was found that departed from baseline at 16:52:15 in any of the three services. What actually tripped the alert at that precise timestamp is still unexplained.

Third, latency and saturation were never measured for any of the three services, and roughly 16:22:41–16:52:04 of paymentservice logs was never observed. If this recurs, start by widening the log pull over that unobserved stretch and by adding a latency query before anything else.

> Evidence `tr_c051aabba503`:

```
<tool_result id="tr_c051aabba503" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_da570bd78bc4`:

```
<tool_result id="tr_da570bd78bc4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment-service"}
2026-09-10T16:22:26.984334+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","request":{"amount":{"currencyCode":"CAD","units":{"low":505,"high":0,"unsigned":false},"nanos":372886330},"creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardCvv":488,"creditCardExpirationYear":2039,"creditCardExpirationMonth":7}},"msg":"Charge request received."}
2026-09-10T16:22:26.984685+00:00  {"level":30,"time":1789057346984,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"ef7ea052cafb7bcd41fd34c8004dd916","span_id":"c8250ece4644795f","trace_flags":"01","transactionId":"d8247068-93b4-43bc-b6f8-e9055124635d","cardType":"visa","lastFourDigits":"8031","amount":{"units":{"low":505,"high":0,"unsigned":false},"nanos":372886330,"currencyCode":"CAD"},"msg":"Transaction complete."}
2026-09-10T16:22:30.391729+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","request":{"amount":{"currencyCode":"USD","units":{"low":394,"high":0,"unsigned":false},"nanos":250000000},"creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardCvv":682,"creditCardExpirationYear":2039,"creditCardExpirationMonth":9}},"msg":"Charge request received."}
2026-09-10T16:22:30.392433+00:00  {"level":30,"time":1789057350391,"pid":17,"hostname":"5c1ff7aa9de3","trace_id":"dc419103d40c95c63596a47b04c3c3ca","span_id":"10d8e195bdeca9fc","trace_flags":"01","transactionId":"97a11516-0dee-4a33-8781-636d32c6541a","cardType":"visa","lastFourDigits":"3547","amount":{"units":{"low":394,"high":0,"unsigned":false},"nanos":250000000,"currencyCode":"USD"},"msg":"Transaction complete."}
```

> Evidence `tr_3264013da097`:

```
<tool_result id="tr_3264013da097" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.1719 min=0 max=0.6667 sd=0.2802
```

> Evidence `tr_c1ab5ef493db`:

```
<tool_result id="tr_c1ab5ef493db" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T16:22:15.583000+00:00..2026-09-10T16:54:12.138564+00:00" template="error-ratio" baseline="2026-09-10T15:50:19.027436+00:00..2026-09-10T16:22:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.08247 min=0 max=0.3311 sd=0.1242
```

