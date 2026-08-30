# Checkout order failures traced to the shipping quote call

## Summary for the responder

Checkout was failing for roughly a quarter of orders at peak, with eleven services in the blast radius and alerts firing on checkout, accounting, email, fraud detection and quote. The investigation started at checkoutservice and, after several honest dead ends, ended one hop downstream: every failing checkout dies at checkoutservice's client span for the ShippingService/GetQuote call.

The shape matters. The shipping server span completes in about two milliseconds and carries no error flag; the caller's span for the same call is ERROR, and that status rides up through PlaceOrder to the frontend. The callee answers quickly and believes it is fine while the caller treats the answer as unusable. That is a fast error return, not a stall and not saturation. Our reading is a wrong or incompatible shipping artifact, but be clear about the standing of that claim: it is inferred from trace shape and elimination. Confidence is low. Fix class is rollback of shippingservice.

> Evidence `tr_c49390dc4046`:

```
<tool_result id="tr_c49390dc4046" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
service: checkoutservice
200 spans
  7c1d7000ca29ca72 checkoutservice/hipstershop.CartService/GetCart 1.3ms
  7c1d7000ca29ca72 cartservice/hipstershop.CartService/GetCart 0.3ms
  7c1d7000ca29ca72 cartservice/HGET 0.2ms
```

> Evidence `tr_35b8ab805d0d`:

```
<tool_result id="tr_35b8ab805d0d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2778 n=61
</tool_result:tr_35b8ab805d0d>
```

## What was visible, in order

First look was checkoutservice's own error ratio. It was populated across the whole fifteen-minute window (61 points), ranging from zero up to about 27.8%. That single series answered more than it looked like it would: the service was up, scraping fine, serving the majority of traffic, and failing intermittently rather than at a flat elevated rate. Total outage, crashloop, and broken telemetry all fell away here. It also meant checkoutservice could not be waved off as a healthy bystander — it was emitting error spans itself, so it sat on the failing path even if it was not the origin.

Logs came next and were more suggestive than conclusive. At the start of the window each order logged a complete pipeline: order start, payment success, confirmation email, message write with an incrementing offset. From roughly T+1m to T+4m only order-start lines remain — the follow-ups vanish. Orders were still arriving at a steady cadence, so the process never restarted or stopped listening. Not one returned line was above info severity; there were no timeouts, no exceptions, no named downstream. Whatever was breaking, checkoutservice did not consider it worth complaining about.

> Evidence `tr_cfa0cde017ad`:

```
<tool_result id="tr_cfa0cde017ad" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2778 n=61
</tool_result:tr_cfa0cde017ad>
```

> Evidence `tr_35b8ab805d0d`:

```
<tool_result id="tr_35b8ab805d0d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2778 n=61
</tool_result:tr_35b8ab805d0d>
```

> Evidence `tr_fc2ccaca02d1`:

```
<tool_result id="tr_fc2ccaca02d1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-30T05:06:05.397987+00:00  {"message":"[PlaceOrder] user_id=\"80e9a44c-a430-11f1-8c4e-9e12df7a2593\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-30T05:06:05.397883261Z"}
2026-08-30T05:06:05.416191+00:00  {"message":"payment went through (transaction_id: c7d196e6-a480-41ad-bf59-c1c296a1ea9d)","severity":"info","timestamp":"2026-08-30T05:06:05.416126302Z"}
2026-08-30T05:06:05.420543+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-08-30T05:06:05.420481719Z"}
2026-08-30T05:06:05.421293+00:00  {"message":"Successful to write message. offset: 25444","severity":"info","timestamp":"2026-08-30T05:06:05.421189594Z"}
```

## The evidence that settled it

Traces closed the case. In two hundred sampled spans, every trace containing PlaceOrder ended the same way: cart fetch, the Redis HGET behind it, product catalog lookups, the feature-flag check and repeated currency conversions all complete cleanly in sub-millisecond to low-millisecond time, then the shipping quote client span goes ERROR and the trace unwinds. No payment span exists anywhere. No email span. No broker or queue write. Execution never reaches them, which explains the log pattern exactly — the missing payment/email/write lines are downstream of a step that aborts before them.

End-to-end the failing requests finish in about 8 to 15 milliseconds at the frontend. Nothing hangs. The shipping server span and its own outbound HTTP client span are both present and complete, so the request reached shippingservice and was handled; it was not unreachable and was not crashing before the handler. The disagreement is entirely at the caller's boundary.

> Evidence `tr_c49390dc4046`:

```
<tool_result id="tr_c49390dc4046" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
service: checkoutservice
200 spans
  7c1d7000ca29ca72 checkoutservice/hipstershop.CartService/GetCart 1.3ms
  7c1d7000ca29ca72 cartservice/hipstershop.CartService/GetCart 0.3ms
  7c1d7000ca29ca72 cartservice/HGET 0.2ms
```

## Dead ends worth keeping

These are the branches that cost time and returned nothing, which is precisely why they belong in the record.

Change history on checkoutservice: empty. No deploys, no config edits, no flag flips, no version bumps. That killed the natural first hypothesis — that checkout had shipped something bad — and killed the natural first remediation of rolling checkout back, because there was nothing to roll back to.

Change history on paymentservice: also empty, same window. Given that traces later showed payment is never even invoked, this query was answering a question the incident had already made irrelevant.

cartservice error ratio: flat zero for all 61 points, before and after onset, continuous with no gaps. Not the origin, not a quiet precursor, not a crash.

productcatalogservice error ratio: identically flat zero across all callers. Same three conclusions.

The broker write path looked implicated for a while because the successful-write log lines disappeared. They disappeared because the write is the last step of the pipeline and the payment and email lines ahead of it were missing too. The stall was upstream of the write, and the broker was never in the picture.

Currency also looked plausible from the log gap, and was cleared by traces: Convert spans appear repeatedly, complete with near-zero server duration, no error flag, and are always followed by the shipping call.

> Evidence `tr_eb8fbdfb53a8`:

```
<tool_result id="tr_eb8fbdfb53a8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_eb8fbdfb53a8>
```

> Evidence `tr_448f1cc832db`:

```
<tool_result id="tr_448f1cc832db" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
no changes recorded for paymentservice over this window
</tool_result:tr_448f1cc832db>
```

> Evidence `tr_4e15d7efe181`:

```
<tool_result id="tr_4e15d7efe181" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
1 series
  {service_name=cartservice} min=0 max=0 n=61
</tool_result:tr_4e15d7efe181>
```

> Evidence `tr_7161353dc65d`:

```
<tool_result id="tr_7161353dc65d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_7161353dc65d>
```

> Evidence `tr_fc2ccaca02d1`:

```
<tool_result id="tr_fc2ccaca02d1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-30T05:06:05.397987+00:00  {"message":"[PlaceOrder] user_id=\"80e9a44c-a430-11f1-8c4e-9e12df7a2593\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-30T05:06:05.397883261Z"}
2026-08-30T05:06:05.416191+00:00  {"message":"payment went through (transaction_id: c7d196e6-a480-41ad-bf59-c1c296a1ea9d)","severity":"info","timestamp":"2026-08-30T05:06:05.416126302Z"}
2026-08-30T05:06:05.420543+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-08-30T05:06:05.420481719Z"}
2026-08-30T05:06:05.421293+00:00  {"message":"Successful to write message. offset: 25444","severity":"info","timestamp":"2026-08-30T05:06:05.421189594Z"}
```

> Evidence `tr_c49390dc4046`:

```
<tool_result id="tr_c49390dc4046" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
service: checkoutservice
200 spans
  7c1d7000ca29ca72 checkoutservice/hipstershop.CartService/GetCart 1.3ms
  7c1d7000ca29ca72 cartservice/hipstershop.CartService/GetCart 0.3ms
  7c1d7000ca29ca72 cartservice/HGET 0.2ms
```

## What is still open

Three gaps that the next responder should close before trusting the conclusion.

No dispatch ever touched shippingservice itself. Its change history, its own error rate, and its logs are entirely unobserved. The mechanism we name — a wrong or incompatible artifact — is elimination plus trace shape, nothing more. A bad config value or a request/response contract mismatch on shippingservice would look identical from the caller's chair. Start there.

The change queries covered only a fifteen-minute band around onset (about T-10m to T+5m) despite asking for two hours. Roughly T-2h to T-10m is unexamined for every service. A change landing in that earlier stretch would not have appeared in either the checkout or payment result.

Saturation is unruled-out rather than excluded. No latency percentiles, throughput, CPU, memory, connection or thread pool, or queue depth series were ever returned for checkoutservice, and its logs were truncated across roughly T-10m to T+1m — the oldest eight and newest thirty-two lines were kept and the middle dropped. If error lines existed at onset, they are in the omitted portion.

The partial error ratio, peaking near 27.8% with dips back to zero, is consistent with only part of the shipping replica set serving the bad artifact. That is a hypothesis about the distribution of the problem, not an observation of it.

> Evidence `tr_eb8fbdfb53a8`:

```
<tool_result id="tr_eb8fbdfb53a8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_eb8fbdfb53a8>
```

> Evidence `tr_448f1cc832db`:

```
<tool_result id="tr_448f1cc832db" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
no changes recorded for paymentservice over this window
</tool_result:tr_448f1cc832db>
```

> Evidence `tr_fc2ccaca02d1`:

```
<tool_result id="tr_fc2ccaca02d1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-30T05:06:05.397987+00:00  {"message":"[PlaceOrder] user_id=\"80e9a44c-a430-11f1-8c4e-9e12df7a2593\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-30T05:06:05.397883261Z"}
2026-08-30T05:06:05.416191+00:00  {"message":"payment went through (transaction_id: c7d196e6-a480-41ad-bf59-c1c296a1ea9d)","severity":"info","timestamp":"2026-08-30T05:06:05.416126302Z"}
2026-08-30T05:06:05.420543+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-08-30T05:06:05.420481719Z"}
2026-08-30T05:06:05.421293+00:00  {"message":"Successful to write message. offset: 25444","severity":"info","timestamp":"2026-08-30T05:06:05.421189594Z"}
```

> Evidence `tr_35b8ab805d0d`:

```
<tool_result id="tr_35b8ab805d0d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2778 n=61
</tool_result:tr_35b8ab805d0d>
```

> Evidence `tr_cfa0cde017ad`:

```
<tool_result id="tr_cfa0cde017ad" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2778 n=61
</tool_result:tr_cfa0cde017ad>
```

## Note on the victim service

Do not let the alert list mislead you. checkoutservice alerted loudest and appears on every failing trace, but it stayed up, kept accepting orders, logged no errors, and had no recorded change in the window. It is downstream of the alert noise and upstream of the actual break — a carrier of the error status, not its source. The same reasoning applies to accounting, email, fraud detection and quote: they alerted because orders stopped reaching them, not because they misbehaved.

> Evidence `tr_fc2ccaca02d1`:

```
<tool_result id="tr_fc2ccaca02d1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-30T05:06:05.397987+00:00  {"message":"[PlaceOrder] user_id=\"80e9a44c-a430-11f1-8c4e-9e12df7a2593\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-30T05:06:05.397883261Z"}
2026-08-30T05:06:05.416191+00:00  {"message":"payment went through (transaction_id: c7d196e6-a480-41ad-bf59-c1c296a1ea9d)","severity":"info","timestamp":"2026-08-30T05:06:05.416126302Z"}
2026-08-30T05:06:05.420543+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-08-30T05:06:05.420481719Z"}
2026-08-30T05:06:05.421293+00:00  {"message":"Successful to write message. offset: 25444","severity":"info","timestamp":"2026-08-30T05:06:05.421189594Z"}
```

> Evidence `tr_eb8fbdfb53a8`:

```
<tool_result id="tr_eb8fbdfb53a8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_eb8fbdfb53a8>
```

> Evidence `tr_c49390dc4046`:

```
<tool_result id="tr_c49390dc4046" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T05:06:00.583000+00:00..2026-08-30T05:21:00.583000+00:00">
service: checkoutservice
200 spans
  7c1d7000ca29ca72 checkoutservice/hipstershop.CartService/GetCart 1.3ms
  7c1d7000ca29ca72 cartservice/hipstershop.CartService/GetCart 0.3ms
  7c1d7000ca29ca72 cartservice/HGET 0.2ms
```
