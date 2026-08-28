# Checkout failures localized to the shipping quote step

## What was visible first

Two alerts opened together: checkoutservice and the load generator. Triage reported ten affected services and four edges it could not measure, starting from checkoutservice.

The service-level metric came back first and was both useful and misleading. A single continuous series across the window, sixty-one points, so scraping was intact and checkout never stopped serving. The error share of spans peaked near twenty-nine percent and returned to zero elsewhere. That shape ruled out a hard outage — most calls succeeded — and it ruled out a clean step to a fixed elevated level, which is what a single change breaking every instance at once would look like. What remained was intermittency: either some replicas failing while others served, or all replicas failing in bursts. We never distinguished the two, and that remains the most valuable open question here. No latency percentiles or per-downstream breakdown were retrieved; that reflects queries not run, not a collection gap.

The change history for checkoutservice was empty — no deploys, config edits, flag toggles, dependency bumps, or rollbacks. The important qualifier is that the queried interval spans only about ten minutes before onset to five after. The multi-hour lookback triage implied was never run, so older changes are unqueried, not absent.

> Evidence `tr_b856c003c324`:

```
<tool_result id="tr_b856c003c324" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2857 n=61
</tool_result:tr_b856c003c324>
```

> Evidence `tr_8ec40c11c077`:

```
<tool_result id="tr_8ec40c11c077" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_8ec40c11c077>
```

## Dead ends: checkout's own logs, and cart

checkoutservice logs named nothing. Every returned record was informational severity; there was not one error or exception line. If you go looking for the culprit in checkout's own logs you will not find it. What the logs did show was a change in shape: early in the window a complete order sequence is written — request entry, payment confirmation with a transaction id, confirmation email, message write with an offset. From roughly T-13s onward, only PlaceOrder entry records appear, around twenty-eight of them, with no completion steps following. Arrivals kept a normal cadence, so this was silent stalling after entry, not a traffic collapse. That cleared crash or kill (the process kept logging), cleared upstream traffic loss, and cleared any currency-specific theory — both USD and CAD requests stalled alike. The break falls after entry and before payment. One caveat: the last returned line sits about eighty-four seconds short of the window end, and whether logging stopped or the query truncated is undetermined.

Cart absorbed two dispatches and produced nothing that advanced the investigation. Its call-count metric returned no series at all — not just an empty error numerator but an empty unfiltered denominator. That is missing or mislabelled instrumentation, not a zero error rate, and widening the status filter would not help. Anyone reading flat-zero as proof of cart health should stop: this metric could not have shown a cart problem if one existed. Cart's logs returned only the oldest eight and newest thirty-two lines, omitting the entire incident period including the stall onset; the returned lines are routine call entries at both ends with tight spacing at the tail. Enough to say cart was not permanently down, not already broken at window start, and not erroring at close — not enough to say what it did during the incident. Cart's change history was likewise empty.

> Evidence `tr_f4b6b20740ad`:

```
<tool_result id="tr_f4b6b20740ad" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-28T15:39:47.905695+00:00  {"message":"[PlaceOrder] user_id=\"b344a49a-a2f6-11f1-ac74-5e36fd0150fc\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-28T15:39:47.905595594Z"}
2026-08-28T15:39:52.613827+00:00  {"message":"[PlaceOrder] user_id=\"b612aa82-a2f6-11f1-ac74-5e36fd0150fc\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-28T15:39:52.613643221Z"}
2026-08-28T15:39:52.631373+00:00  {"message":"payment went through (transaction_id: bc399d9d-ad0c-4167-8660-c038b87b20e6)","severity":"info","timestamp":"2026-08-28T15:39:52.631246638Z"}
2026-08-28T15:39:52.635599+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-08-28T15:39:52.635514846Z"}
```

> Evidence `tr_4e23da0a85ce`:

```
<tool_result id="tr_4e23da0a85ce" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_4e23da0a85ce>
```

> Evidence `tr_663de9ef33dc`:

```
<tool_result id="tr_663de9ef33dc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T15:39:47.271087+00:00  GetCartAsync called with userId=
2026-08-28T15:39:47.876048+00:00  AddItemAsync called with userId=b344a49a-a2f6-11f1-ac74-5e36fd0150fc, productId=9SIQT8TOJO, quantity=5
2026-08-28T15:39:47.878642+00:00  GetCartAsync called with userId=b344a49a-a2f6-11f1-ac74-5e36fd0150fc
2026-08-28T15:39:47.897769+00:00  AddItemAsync called with userId=b344a49a-a2f6-11f1-ac74-5e36fd0150fc, productId=OLJCESPC7Z, quantity=5
```

> Evidence `tr_32762ea5f122`:

```
<tool_result id="tr_32762ea5f122" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_32762ea5f122>
```

## Traces resolved it; the mechanism is still unmeasured

One trace dispatch did what three log and metric dispatches could not. In every PlaceOrder trace, checkoutservice -> ShippingService/GetQuote is the last downstream span started and the only downstream span carrying an error status. That status propagates upward through checkout's PlaceOrder server span, the frontend client span, and the frontend HTTP POST. The failing shipping spans complete in roughly half a millisecond to under three milliseconds, with whole traces under about eleven milliseconds — immediate rejection, not a hang, which rules out the entire stall-and-timeout family. No payment or email spans appear at all, which explains the missing completion records in checkout's logs. Cart and its backing-store children, product catalog with its nested flag lookups, and currency conversions all complete cleanly in the same traces. The prepare step wrapping the shipping call carries no independent error, so the failure does not originate in checkout's assembly logic or the frontend.

What this record does not establish: no dispatch ever touched shippingservice — no logs, metrics, saturation data, or change history. A sub-three-millisecond rejection is equally consistent with a bad artifact on part of the fleet, a wrong configuration value, or exhausted capacity, and those lead to different fixes. I decline to infer one from the error shape.

For the next responder: query shippingservice directly with a wide lookback, and get a per-instance error breakdown — partial-fleet and time-sliced failure look identical at service level. Reconcile the twenty-nine percent peak against twenty-eight consecutive requests with no completion record; those imply different impact rates. Treat checkout emitting no error record for an errored request, and cart's absent metric series, as monitoring defects to fix independently. The four unmeasured edges were never named or closed, and the other affected services were never examined.

> Evidence `tr_4216a1a46c72`:

```
<tool_result id="tr_4216a1a46c72" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T15:39:45.583000+00:00..2026-08-28T15:54:45.583000+00:00">
service: checkoutservice
200 spans
  6cd54326546980b3 currencyservice/CurrencyService/Convert 0.0ms
  6cd54326546980b3 checkoutservice/hipstershop.ShippingService/GetQuote 2.6ms ERROR
  c4e15296cd3de191 frontend/HTTP POST 8.1ms ERROR
```
