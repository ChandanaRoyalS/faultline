# Checkout errors at two-thirds of traffic, origin unestablished

## What was visible, in order

Offsets anchor at T+0 = the moment checkoutservice, frontend and loadgenerator alerted together. The queried window runs T-10m to T+5m. Blast radius was tallied at twelve services with checkout named as the start point, and four edges in that graph had no measurement behind them.

The first solid look was checkout's own error ratio: errored spans over all spans, two-minute rate, fifty-eight sampled points, rising from zero to a peak near sixty-seven percent. Two details carry weight. The series minimum is zero inside the window, so the transition from clean to degraded happened during the interval we were already watching rather than predating it. And the peak sits well below 1.0 — a substantial share of requests still succeeded at the worst moment.

Next, checkout's logs over the same window, unfiltered by severity. Info-level PlaceOrder entries recording a user id and currency, and nothing else: no error lines, no exceptions, no stack traces, no RPC-failure messages. The returned tail is contiguous from T-1m48s to T+2m32s, covering the alert squarely, and the PlaceOrder cadence holds steady every five to twenty seconds — the process stayed up and kept taking work. Two caveats: the result was truncated to the oldest eight and newest thirty-two lines, leaving roughly T-9m to T-1m48s unobserved, and the last line lands at T+2m32s though the window runs to T+5m.

So: a caller erroring on two thirds of its traffic, alive, and silent about it in its own logs. That shape reads as a service propagating someone else's failure on a subset of call paths rather than originating one. That is a reading, not a finding — and it is where the evidence stops.

> Evidence `tr_a96ac556b459`:

```
<tool_result id="tr_a96ac556b459" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=58
</tool_result:tr_a96ac556b459>
```

> Evidence `tr_9c75fb07b9cf`:

```
<tool_result id="tr_9c75fb07b9cf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T04:26:32.927364+00:00  {"message":"[PlaceOrder] user_id=\"51278b3e-a106-11f1-86d7-1e4ac5f08d0c\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-08-26T04:26:32.927257129Z"}
2026-08-26T04:26:35.709814+00:00  {"message":"[PlaceOrder] user_id=\"52d46704-a106-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T04:26:35.709626589Z"}
2026-08-26T04:26:37.970141+00:00  {"message":"[PlaceOrder] user_id=\"542d7546-a106-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T04:26:37.969916006Z"}
2026-08-26T04:27:05.277319+00:00  {"message":"[PlaceOrder] user_id=\"6473d1de-a106-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T04:27:05.277150922Z"}
```

## Dead ends — the useful part

Three dispatches were meant to close the gap between 'checkout is erroring' and 'why'. All three returned nothing usable, and none of the three failures tell you anything about the system under investigation.

The trace query never produced a span set — the backend answered with a server-side 500. That is a broken result, not an empty one, and the distinction matters twice. No span-level attribution is available, and the silence carries no information about instrumentation: you cannot conclude checkout stopped emitting spans when the query path failed first. Re-scoping window or service will not help until the backend is healthy. Whether that 500 is a second, independent failure or a symptom of the same condition is itself unanswered.

The dependency error-ratio query returned no matching series because the service_name selector was an exact-match literal containing the entire prose list of service names rather than any single name. A selector that cannot match any label value returns empty regardless of the underlying data. It does not indicate a metrics outage either — the query evaluated cleanly and returned a well-formed no-match, which is what a live backend with a bad filter looks like. No per-service error ratio, request rate or latency was obtained; no dependency is implicated or exonerated.

The dependency log query has the same disease: four service names comma-joined into one literal label value instead of a regex or alternation matcher. The empty return is indistinguishable from a no-op. It does not show those four services were silent and healthy, and it is not evidence of a store-wide data gap.

> Evidence `tr_d7c5f0e96cd3`:

```
<tool_result id="tr_d7c5f0e96cd3" tool="trace_query" trust="untrusted" source="jaeger" empty="true" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00" error="HTTP Error 500: Internal Server Error">
query failed: HTTP Error 500: Internal Server Error
</tool_result:tr_d7c5f0e96cd3>
```

> Evidence `tr_79945d6a9c52`:

```
<tool_result id="tr_79945d6a9c52" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="all checkoutservice dependencies (sync edges first: cartservice, productcatalogservice, shippingservice, recommendationservice, adservice, emailservice)",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="all checkoutservice dependencies (sync edges first: cartservice, productcatalogservice, shippingservice, recommendationservice, adservice, emailservice)"}[2m]))' over this window
</tool_result:tr_79945d6a9c52>
```

> Evidence `tr_c8b247b0f008`:

```
<tool_result id="tr_c8b247b0f008" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00">
no log lines matched {service="cartservice, paymentservice, currencyservice, productcatalogservice"} over this window
</tool_result:tr_c8b247b0f008>
```

## Change history, what was ruled out, and what is still open

Both change-history queries — one for checkoutservice, one for all nine dependencies — came back empty. Within the interval they cover, that cleanly excludes a checkout release, config edit or flag flip at or just before onset, an in-flight checkout rollout mid-window, a dependency deploy in the ten minutes before T+0, and any concurrent operator rollback confounding the signal. The catch: both covered only about fifteen minutes, not the ninety-minute lookback that was asked for. The earlier seventy-five minutes are unexamined for all ten services. The corpus analogues matching this signature both involved a dependency image change that would sit outside the queried interval — a reason to widen the lookback, not to assume one happened.

Also closed and not worth re-treading: checkout is not merely a bystander (it errors on two thirds of its own traffic); it is not hard-down (no restarts, no panics, PlaceOrder continues past the alert, ratio peaks below 1.0); this is not latency-only (spans carry error status); and checkout's own logs will not solve it — the selector was unfiltered and returned only info lines.

Still open, in priority order. Re-run the dependency metrics query with one selector per service or a proper regex matcher; no dependency can be named until that exists. Re-run the dependency log query with a corrected matcher. Extend both change queries to the full lookback before T-10m. Separately: check the tracing backend's 500 on its own terms and re-query for span attribution once healthy; explain why the error ratio plateaus below 1.0 — which subset of checkout call paths still succeeds is the strongest discriminator available; and compare onset times across frontend, loadgenerator and checkout, bearing in mind that per the corpus, loadgenerator's signal only restates the storefront's.

No cause is established. Confidence low. No fix class named.

> Evidence `tr_f031982de448`:

```
<tool_result id="tr_f031982de448" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_f031982de448>
```

> Evidence `tr_f0e152f2896f`:

```
<tool_result id="tr_f0e152f2896f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00">
no changes recorded for all checkoutservice dependencies (adservice, cartservice, productcatalogservice, recommendationservice, shippingservice, emailservice, paymentservice, currencyservice, accountingservice) over this window
</tool_result:tr_f0e152f2896f>
```

> Evidence `tr_a96ac556b459`:

```
<tool_result id="tr_a96ac556b459" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T04:26:30.583000+00:00..2026-08-26T04:41:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=58
</tool_result:tr_a96ac556b459>
```
