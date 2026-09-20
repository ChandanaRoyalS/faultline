# Checkout fails uniformly at the shipping quote hop

## What we saw first

The page came from two places at once: checkoutservice and the load generator. That pairing is worth noting up front, because it told us the failure was user-visible and continuous rather than a sampling artifact — the synthetic traffic was failing the same way real traffic was. Blast radius was scored across ten services with checkoutservice as the seed, and four of the edges we ended up reasoning across had no measurements behind them at all. Keep that number in mind when reading the confidence at the bottom.

The first honest description of the symptom, before any theory: orders were being accepted and then going nowhere.

## The first look at checkout logs (T+0 to T+8m)

We pulled the checkoutservice log stream for the half hour leading into the page. The early part of the window looked completely normal: each order-entry line was followed by a payment authorization carrying a transaction id, a confirmation email dispatch, and a successful message write with a monotonically increasing offset.

The late part of the window had only the first of those lines. Order entry, then nothing. No payment line, no email line, no write line — and, critically, no error line either. Severity across everything returned was info. The service was plainly alive: order-entry lines kept arriving at a steady cadence right up to the edge of the window, with distinct users and a mix of USD and CAD.

That shaped the early hypothesis badly. A silent truncation with no logged error reads like a hang, and we spent the next stretch looking for something that was blocking. It was not blocking. Also worth flagging for the next reader: this result was truncated to the oldest eight and newest thirty-two lines, so roughly a half-hour in the middle was never observed and we could not pin the transition moment from the logs. We never went back for it, and it would not have changed the answer.

> Evidence `tr_a8397fd91134`:

```
<tool_result id="tr_a8397fd91134" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T04:26:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-20T04:26:46.525412+00:00  {"message":"[PlaceOrder] user_id=\"7d9b1de4-b4ab-11f1-bde0-b2c1b7dd3a95\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-20T04:26:46.525319542Z"}
2026-09-20T04:26:46.540397+00:00  {"message":"payment went through (transaction_id: 348b711b-dd90-4a8b-86a2-85559cd6a203)","severity":"info","timestamp":"2026-09-20T04:26:46.540288083Z"}
2026-09-20T04:26:46.544318+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-20T04:26:46.544191625Z"}
2026-09-20T04:26:46.544964+00:00  {"message":"Successful to write message. offset: 78993","severity":"info","timestamp":"2026-09-20T04:26:46.544877042Z"}
```

## Dead end: the change log

Standard reflex — ask what changed. We queried change history for checkoutservice twice, and both times the answer was an empty window. No deploys, no config edits, no flag flips, no dependency bumps.

This legitimately cleared a few things: no checkout deploy at onset caused it, no flag flip triggered it, no churn kept it going, and no quiet remediation explains any recovery. But the queries had two defects that the reader should not repeat. First, both were scoped to the seed service only, radius zero, so the sync dependencies — cart, product catalog, shipping, email — were never covered. Second, both windows began at the incident timestamp and ran forward about twenty-four hours, which means the hours *before* onset, the interval where a triggering change would actually live, were never looked at. One of the queries was also dated a day off from the traces we later read.

So the change log is not evidence of absence here. It is evidence that we asked the wrong window of the wrong service, twice.

> Evidence `tr_1012f421e75f`:

```
<tool_result id="tr_1012f421e75f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:56:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_1012f421e75f>
```

> Evidence `tr_433e204c696d`:

```
<tool_result id="tr_433e204c696d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:56:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_433e204c696d>
```

## Dead end: metrics, on two services

We reached for span-derived error ratios on checkoutservice next, comparing the incident window against a six-hour baseline. Zero samples in both. The same query against cartservice, same result — nothing on either side of the boundary.

The temptation at this point is to read empty as healthy. It is not. The symmetry of the absence — baseline as empty as incident — says the series was already missing before anything went wrong, which points at collection (the service_name label, the calls_total series, or span-metric generation) rather than at anything that happened at onset. It specifically does *not* support the tidy story that checkout crashed or went silent at onset; that would have shown healthy baseline samples and then a cliff.

Only the error-ratio template was run. Request rate, latency percentiles, CPU and memory, and any downstream-call breakdown were never returned, so none of those questions are answered either way. Roughly fifteen minutes of investigation went into metrics and produced no usable signal. Fix the collection gap before the next incident; it cost us real time.

> Evidence `tr_4b32d21df915`:

```
<tool_result id="tr_4b32d21df915" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-19T04:56:45.583000+00:00..2026-09-19T10:56:45.583000+00:00" template="error-ratio" baseline="2026-09-18T22:56:45.583000+00:00..2026-09-19T04:56:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_c98110ffa106`:

```
<tool_result id="tr_c98110ffa106" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-20T04:26:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" template="error-ratio" baseline="2026-09-20T03:53:58.042017+00:00..2026-09-20T04:26:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Dead end: cartservice

With checkout stalling before payment, cart was a reasonable suspect — it sits early in the order-preparation path. Its logs were routine throughout: steady request-handling lines to within seconds of the window end, no errors, no timeouts, no retries, no backend or Redis client messages at all, and write-then-read pairs completing within milliseconds of each other.

One small detail pointed the right way before we understood it: a cart-emptying operation, which a completed checkout normally triggers, appeared early in the window and not once in the most recent minute of lines. That is downstream confirmation that checkouts were not finishing, not an indication cart was at fault. Same truncation caveat as the checkout logs — most of the window is unobserved.

Cart was cleared: not crashed, not disconnected from its backend, not erroring to callers, and still receiving traffic.

> Evidence `tr_389225343923`:

```
<tool_result id="tr_389225343923" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T04:26:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-20T04:26:46.506412+00:00  AddItemAsync called with userId=7d9b1de4-b4ab-11f1-bde0-b2c1b7dd3a95, productId=OLJCESPC7Z, quantity=3
2026-09-20T04:26:46.507810+00:00  GetCartAsync called with userId=7d9b1de4-b4ab-11f1-bde0-b2c1b7dd3a95
2026-09-20T04:26:46.519122+00:00  AddItemAsync called with userId=7d9b1de4-b4ab-11f1-bde0-b2c1b7dd3a95, productId=9SIQT8TOJO, quantity=3
2026-09-20T04:26:46.520219+00:00  GetCartAsync called with userId=7d9b1de4-b4ab-11f1-bde0-b2c1b7dd3a95
```

## The trace that settled it

Traces were what we should have opened first. Ten checkout traces in the window, and all ten failed identically. The root frontend HTTP POST, the frontend PlaceOrder call, and the checkoutservice PlaceOrder span all carry error status, and the deepest error sits on the checkoutservice-side call to ShippingService/GetQuote.

Several things fell out at once. The call is not hanging — each GetQuote span completes in about three to four milliseconds and the whole trace closes inside twelve. Our hang theory, built on the silent logs, was simply wrong; this is a fast, uniform error return. The call does cross the network: a shippingservice server span and its downstream HTTP client span are present in every trace and both complete cleanly. The error is recorded only on the caller's span. Within the quote-preparation step, GetQuote is consistently the last child to start, after the cart, currency and product-catalog children — all of which are healthy, with cart's Redis read well under a millisecond and currency conversions returning essentially instantly. And no payment, email, or broker spans exist anywhere in the 163 spans, which is exactly why the logs looked truncated.

Callee succeeds, caller rejects, every single request. That is a response-contract break.

> Evidence `tr_c195f3e496d9`:

```
<tool_result id="tr_c195f3e496d9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-20T03:56:45.583000+00:00..2026-09-20T04:59:33.123983+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 163 spans; offsets are from each trace's root

trace 3dfcc183fadf4d2a  root frontend/HTTP POST  10.3ms  started 2026-09-20T04:57:52.503018+00:00  13 spans
  +0.0ms frontend/HTTP POST 10.3ms [self 0.2ms]  ERROR
```

## Conclusion and what remains open

All checkout requests fail at one hop: checkoutservice calling ShippingService/GetQuote. The shipping side completes its work and returns; checkout cannot accept what comes back, and aborts before payment, email, and the broker write — which reconciles the trace picture with the log picture exactly. The most likely mechanism is shippingservice running an artifact whose response shape no longer matches what its caller expects. Fix class is rollback of shippingservice.

Confidence is medium, not high, and the reasons are specific. We never queried shippingservice's change history, logs, or metrics — every change lookup was scoped to checkoutservice, so no record confirms shippingservice actually changed. Our change windows all started at onset and ran forward, so pre-incident changes to any service remain unobserved. And the gRPC status code and error text on the failing client span were never reported, which means a deserialization or contract break cannot be cleanly distinguished from a validation or authorization rejection at the caller.

For whoever picks this up: pull shippingservice's deploy record for the hours *before* onset, and get the status code off that client span. Those two facts would move this to high confidence or overturn it.

> Evidence `tr_c195f3e496d9`:

```
<tool_result id="tr_c195f3e496d9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-20T03:56:45.583000+00:00..2026-09-20T04:59:33.123983+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 163 spans; offsets are from each trace's root

trace 3dfcc183fadf4d2a  root frontend/HTTP POST  10.3ms  started 2026-09-20T04:57:52.503018+00:00  13 spans
  +0.0ms frontend/HTTP POST 10.3ms [self 0.2ms]  ERROR
```

> Evidence `tr_a8397fd91134`:

```
<tool_result id="tr_a8397fd91134" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-20T04:26:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-20T04:26:46.525412+00:00  {"message":"[PlaceOrder] user_id=\"7d9b1de4-b4ab-11f1-bde0-b2c1b7dd3a95\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-20T04:26:46.525319542Z"}
2026-09-20T04:26:46.540397+00:00  {"message":"payment went through (transaction_id: 348b711b-dd90-4a8b-86a2-85559cd6a203)","severity":"info","timestamp":"2026-09-20T04:26:46.540288083Z"}
2026-09-20T04:26:46.544318+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-20T04:26:46.544191625Z"}
2026-09-20T04:26:46.544964+00:00  {"message":"Successful to write message. offset: 78993","severity":"info","timestamp":"2026-09-20T04:26:46.544877042Z"}
```

> Evidence `tr_1012f421e75f`:

```
<tool_result id="tr_1012f421e75f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:56:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_1012f421e75f>
```

> Evidence `tr_433e204c696d`:

```
<tool_result id="tr_433e204c696d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-19T04:56:45.583000+00:00..2026-09-20T04:59:33.123983+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_433e204c696d>
```

