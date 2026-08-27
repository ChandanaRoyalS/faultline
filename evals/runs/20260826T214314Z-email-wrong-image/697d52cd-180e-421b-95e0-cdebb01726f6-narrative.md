# Checkout confirmation-email step failing at name resolution

## What the page said

The alert fired on checkoutservice and nothing else, even though nine services sat inside the blast radius and four edges into that radius were never instrumented well enough to measure. From the responder's chair at T+0 the only fact in hand was that checkout was erroring. Severity was called critical because checkout is the money path, not because anything yet suggested a total outage. That distinction turned out to matter a great deal.

## First look: how bad, really

The first thing worth establishing was whether checkout was down or merely bleeding. The error ratio at the checkoutservice boundary climbed from a clean zero to a peak near 7.8% across the window, sampled at 57 points. Over 92% of calls succeeded even at the worst moment, and the series touched zero inside the window, so there was both a genuine excursion from a clean baseline and evidence the service kept serving and kept emitting call metrics throughout. That ruled out a crash loop, a hard down, and the opposite reading too — this was not a pre-existing error floor someone had simply noticed for the first time. It also ruled out a purely latency-shaped event: there was a real, measurable error-side symptom.

> Evidence `tr_3377e25035db`:

```
<tool_result id="tr_3377e25035db" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.07843 n=57
</tool_result:tr_3377e25035db>
```

## The change-history dead end

Standard reflex second step: look for something that shipped. The change-history query for checkoutservice came back empty — no deploys, no config edits, no flag flips in the queried interval. A second pass produced the same empty result. Worth recording honestly: the query covered only about fifteen minutes around the incident and only the checkoutservice component itself, so it did not satisfy the intended two-hour lookback and never touched the six direct dependencies. What it does support is narrow but real — no same-service change coincided with onset, and there is no in-flight rollout on checkoutservice to blame or roll back. A responder reaching for a rollback button here would have wasted the window. The broader lookback across dependencies was never run, and that gap is the reason the initiating act is still unnamed.

> Evidence `tr_7a44508803f5`:

```
<tool_result id="tr_7a44508803f5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_7a44508803f5>
```

> Evidence `tr_5ec6c6704874`:

```
<tool_result id="tr_5ec6c6704874" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_5ec6c6704874>
```

## Traces: locating the single red span

Five failing checkout traces all told the same story. In each one, exactly one span carried ERROR status: an outbound HTTP POST emitted by checkoutservice near the end of PlaceOrder, after EmptyCart and before the orders send. Everything else was clean. Payment Charge, cartservice/Redis, currencyservice, productcatalogservice, ShipOrder — all present, all sub-millisecond to low-millisecond, none erroring.

Two tempting readings died here. First, the erroring span is short, roughly 1.7–2.6ms inside a PlaceOrder of 21–25ms; it is an error carrier, not a latency carrier, so fixing it would not have moved checkout timing at all. Second, the largest duration contributor was the ShippingService/GetQuote subtree at 7–11ms, with quoteservice/getquote at 4.7–7.3ms — but that same shape appeared in the non-erroring traces too, with no outlier and no error status, so a slow quote call timing out was not the mechanism. The async order pipeline was likewise clean: accounting and frauddetection spans landed at 0.0–0.6ms after the failing POST. Neither the frontend nor the checkoutservice PlaceOrder handler itself was marked failed.

The useful negative: the erroring POST had no server-side child span from any named downstream. Either the callee was uninstrumented or the request never reached an instrumented handler.

> Evidence `tr_6dae66117de6`:

```
<tool_result id="tr_6dae66117de6" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00">
service: checkoutservice
200 spans
  af035afcc7057e07 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 1.2ms
  af035afcc7057e07 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 1.6ms
  af035afcc7057e07 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 0.8ms
```

## Logs: what the POST actually was

The logs closed the gap the traces opened. The failing outbound call is a plaintext HTTP POST to host emailservice on port 6060, path /send_order_confirmation, and it fails at name resolution against the container's embedded resolver at 127.0.0.11:53. No TCP dial is ever attempted.

That single detail retires a whole shelf of hypotheses. Not connection-refused and not a network drop, because the failure precedes any dial to an address. Not a timeout or an overloaded email backend, because the lookup fails immediately — only a few milliseconds separate the payment log line from the failure line. Not TLS, because the scheme is plain HTTP and nothing handshakes. Not an HTTP 4xx/5xx, because no status code comes back at all. And not a misconfigured URL: the identical host, port and path succeeded roughly twelve minutes before the page, so the configuration is unchanged.

The failures are logged at warning severity and are non-fatal. For every affected order, payment records a transaction id and the message write succeeds; only the confirmation email is lost. That is exactly why the error ratio peaked around 7.8% instead of going total, and it reconciles the metric and trace views cleanly.

> Evidence `tr_d05bec9e4467`:

```
<tool_result id="tr_d05bec9e4467" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T21:36:49.845116+00:00  {"message":"[PlaceOrder] user_id=\"3ee71008-a196-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T21:36:49.845021466Z"}
2026-08-26T21:36:49.860227+00:00  {"message":"payment went through (transaction_id: 35129eb1-14ee-46c0-a1c9-5216447fe65e)","severity":"info","timestamp":"2026-08-26T21:36:49.860147966Z"}
2026-08-26T21:36:49.864949+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-26T21:36:49.864886675Z"}
2026-08-26T21:36:49.865630+00:00  {"message":"Successful to write message. offset: 13790","severity":"info","timestamp":"2026-08-26T21:36:49.865587883Z"}
```

## Where the record goes quiet

Onset is bounded, not pinned. The email step was succeeding at roughly T-12m and was failing continuously from about T+0 through T+1m across multiple distinct recipients and currencies — systemic, not per-request. The transition between those two states is invisible because the middle of the log result was truncated. Nobody went back for the missing slice.

> Evidence `tr_d05bec9e4467`:

```
<tool_result id="tr_d05bec9e4467" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T21:36:49.845116+00:00  {"message":"[PlaceOrder] user_id=\"3ee71008-a196-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T21:36:49.845021466Z"}
2026-08-26T21:36:49.860227+00:00  {"message":"payment went through (transaction_id: 35129eb1-14ee-46c0-a1c9-5216447fe65e)","severity":"info","timestamp":"2026-08-26T21:36:49.860147966Z"}
2026-08-26T21:36:49.864949+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-26T21:36:49.864886675Z"}
2026-08-26T21:36:49.865630+00:00  {"message":"Successful to write message. offset: 13790","severity":"info","timestamp":"2026-08-26T21:36:49.865587883Z"}
```

## Conclusion and what it rests on

checkoutservice is healthy. Its one failing step is the confirmation-email POST, and it fails because emailservice stopped resolving in service discovery some time in the twelve-minute blind spot. Confidence is medium, and the honest reason is that every finding above describes the caller. Nothing was ever dispatched at the callee. Fix class is a restart of emailservice, which should restore its discovery record.

What the record deliberately does not claim: why emailservice left discovery. A failed rollout, an out-of-memory kill, a scale-to-zero, or a change on the discovery side would all present identically from the checkoutservice side, and none was investigated.

> Evidence `tr_d05bec9e4467`:

```
<tool_result id="tr_d05bec9e4467" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T21:36:49.845116+00:00  {"message":"[PlaceOrder] user_id=\"3ee71008-a196-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T21:36:49.845021466Z"}
2026-08-26T21:36:49.860227+00:00  {"message":"payment went through (transaction_id: 35129eb1-14ee-46c0-a1c9-5216447fe65e)","severity":"info","timestamp":"2026-08-26T21:36:49.860147966Z"}
2026-08-26T21:36:49.864949+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-26T21:36:49.864886675Z"}
2026-08-26T21:36:49.865630+00:00  {"message":"Successful to write message. offset: 13790","severity":"info","timestamp":"2026-08-26T21:36:49.865587883Z"}
```

> Evidence `tr_6dae66117de6`:

```
<tool_result id="tr_6dae66117de6" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00">
service: checkoutservice
200 spans
  af035afcc7057e07 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 1.2ms
  af035afcc7057e07 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 1.6ms
  af035afcc7057e07 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 0.8ms
```

> Evidence `tr_3377e25035db`:

```
<tool_result id="tr_3377e25035db" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T21:36:45.583000+00:00..2026-08-26T21:51:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.07843 n=57
</tool_result:tr_3377e25035db>
```

## Open threads for the next responder

Three, in priority order. First, pull emailservice logs, container state, and change history — this is the unturned stone and it almost certainly holds the answer. Second, recover the truncated log slice between roughly T-12m and T+0 to pin the exact transition; the timestamp is the strongest correlator against any change event you find. Third, check whether the other eight services in the radius, and particularly the four unmeasured edges, experienced the same resolution condition — if the discovery layer dropped one record it may have dropped others, and nothing in this record excludes that.
