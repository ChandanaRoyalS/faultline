# Checkout failures traced to an unreachable cart backing store

## What the responder saw first

Three alerts arrived together at T+0: checkoutservice, frontend and loadgenerator. Blast radius was assessed at twelve services, severity critical, with checkoutservice named as the starting point. That framing is worth flagging up front, because it pointed the first hour of work at the wrong service. checkoutservice was the caller that noticed, not the origin. Four edges in the dependency graph were never measured during this incident and remain unmeasured.

> Evidence `tr_8338f7487f5d`:

```
<tool_result id="tr_8338f7487f5d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00">
service: checkoutservice
6 trace(s) shown of 6 found, 30 spans; offsets are from each trace's root

trace 377928dd15998e11  root frontend/HTTP POST  1.2ms  started 2026-09-09T08:50:48.891012+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.2ms [self 0.1ms]  ERROR
```

## Clearing the alerting service

The first three probes all pointed away from checkoutservice. Its change record over a 24-hour window came back empty: no deploys, no config edits, no flag flips, no rollbacks — and, because of how the window was bounded, the emptiness also tells us nobody applied a remediation change to checkoutservice during or after the event. Its aggregate error ratio in the incident window was roughly 2.5x *lower* than its own immediately preceding baseline, with the same peak value and the same high variance in both windows, i.e. spiky errors on low volume that predate the alert rather than a step change at T+0. And its self time in traces was around 0.1ms per span. Nothing about checkoutservice was internally unwell.

> Evidence `tr_a7140baea402`:

```
<tool_result id="tr_a7140baea402" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T08:50:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_a7140baea402>
```

> Evidence `tr_28c109c65274`:

```
<tool_result id="tr_28c109c65274" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T08:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" template="error-ratio" baseline="2026-09-09T07:47:57.472949+00:00..2026-09-09T08:20:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.0675 min=0 max=0.6667 sd=0.1905
  baseline window: n=129 mean=0.1724 min=0 max=0.6667 sd=0.2849
```

> Evidence `tr_8338f7487f5d`:

```
<tool_result id="tr_8338f7487f5d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00">
service: checkoutservice
6 trace(s) shown of 6 found, 30 spans; offsets are from each trace's root

trace 377928dd15998e11  root frontend/HTTP POST  1.2ms  started 2026-09-09T08:50:48.891012+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.2ms [self 0.1ms]  ERROR
```

## The shape of the stall in checkout logs

The checkoutservice log stream contained no error or warn lines at all in the window — every retained line was info severity, and none named a failing target. What it did show was a change in shape at roughly T-2m30s (about 08:47:31 wall clock). Before that point, each order-start line was followed within 20-30ms by payment, confirmation-email and message-write lines. From that point onward, only order-start lines appear, at a steady one every 5-20 seconds, straight through the end of the window. So the process was alive and still accepting work; orders simply stopped completing, and they stopped at or before the payment step, not after it. There was no restart banner. This log view read as hanging work rather than fast rejection, which turned out to be misleading — see below.

> Evidence `tr_0ec22ffb17fe`:

```
<tool_result id="tr_0ec22ffb17fe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T08:20:35.615736+00:00  {"message":"[PlaceOrder] user_id=\"550bee26-ac27-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T08:20:35.615592128Z"}
2026-09-09T08:20:35.635346+00:00  {"message":"payment went through (transaction_id: f1b81d64-db84-4e29-922c-767f8139cae0)","severity":"info","timestamp":"2026-09-09T08:20:35.63525167Z"}
2026-09-09T08:20:35.640780+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-09T08:20:35.640710712Z"}
2026-09-09T08:20:35.641738+00:00  {"message":"Successful to write message. offset: 20801","severity":"info","timestamp":"2026-09-09T08:20:35.641648462Z"}
```

## Traces pin the leaf

Six traces were available in the window, all complete, all five spans, none truncated or left open, and all finishing in 1.2-1.6ms. Six of six failed at the same leaf: the checkoutservice call to the cart service's GetCart, invoked from prepareOrderItemsAndShippingQuoteFromCart. The error status propagated up through checkoutservice's PlaceOrder span, the frontend gRPC PlaceOrder client span and the frontend HTTP POST root — which is exactly the alert triple that fired. No payment span exists in any trace, because execution never got that far. The traces cluster after T+0, within about seventy seconds. This corrected the earlier reading: the failure is a fast error, not a stall, and it is consistent rather than sporadic.

> Evidence `tr_8338f7487f5d`:

```
<tool_result id="tr_8338f7487f5d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00">
service: checkoutservice
6 trace(s) shown of 6 found, 30 spans; offsets are from each trace's root

trace 377928dd15998e11  root frontend/HTTP POST  1.2ms  started 2026-09-09T08:50:48.891012+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.2ms [self 0.1ms]  ERROR
```

## The cause: cartservice never finishes starting

cartservice logs resolve it. Early in the window (around T-30m) cartservice was healthy, completing add-item and get-cart operations back to back in a few milliseconds. From roughly T+0 (08:50:22) onward it is in a startup loop: it attempts to connect to its Redis backing store, fails, and terminates with an unhandled exception thrown from the cart-store initialization path called directly from program startup, restarting every 1-30 seconds. In the retained late-window lines there are no request-handling entries at all — only startup, connect, and crash lines — so the process never reaches the point of accepting cart RPCs. The connection target named in each attempt is the redis-cart host on port 6380. 6380 is not Redis's default port. The best-supported mechanism is therefore a wrong endpoint value in the cart backing-store connection configuration; the fix class is a config revert to the correct port. Confidence is medium, for the reasons in the open items.

> Evidence `tr_7c90a77b1763`:

```
<tool_result id="tr_7c90a77b1763" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T08:20:11.666079+00:00  AddItemAsync called with userId=46c8e134-ac27-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=10
2026-09-09T08:20:11.669092+00:00  GetCartAsync called with userId=46c8e134-ac27-11f1-b359-b6ed2071a170
2026-09-09T08:20:12.043846+00:00  AddItemAsync called with userId=4700f92a-ac27-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=10
2026-09-09T08:20:12.046364+00:00  GetCartAsync called with userId=4700f92a-ac27-11f1-b359-b6ed2071a170
```

## Dead ends worth keeping

Three lines of inquiry cost time and produced nothing usable.

First, productcatalogservice change history looked like a hit and was not. Two records exist, both from platform-automation, both attaching and then detaching a traffic-shaping container on the service's network namespace. The applied effect was a fixed 300ms egress delay on eth0 with zero jitter, active for about eight and a half minutes and explicitly withdrawn roughly 2.7 hours before onset. It was not in effect when the incident began, and its zero-jitter parameterisation rules out erratic network behaviour on that interface anyway. It is a real deliberate manipulation of that dependency the same morning, so it should not be dismissed as noise — but it is not the cause here.

Second, cartservice error-rate metrics were unavailable rather than informative. The span-derived error-ratio query returned no samples in either the incident window or the baseline. Because both windows are equally empty, the right reading is that the series does not exist for this service, not that traffic dropped to zero. Anyone tempted to treat that gap as the incident signal should not.

Third, the checkoutservice log read (hanging orders, no error lines) suggested a slow or timing-out downstream and pulled attention toward latency. The traces contradicted that: everything completed in under 2ms with an error status. Trust the traces over the log shape here.

> Evidence `tr_443caba87a56`:

```
<tool_result id="tr_443caba87a56" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T08:50:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" radius="candidate_cause" hops="1">
service: productcatalogservice
2 changes, ranked by suspicion
  #1  2.7h before onset  2026-09-09T06:09:03.403533+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  2.8h before onset  2026-09-09T06:00:32.130376+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

> Evidence `tr_6c8f032b5bde`:

```
<tool_result id="tr_6c8f032b5bde" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" template="error-ratio" baseline="2026-09-09T05:47:57.472949+00:00..2026-09-09T07:20:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_0ec22ffb17fe`:

```
<tool_result id="tr_0ec22ffb17fe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T08:20:35.615736+00:00  {"message":"[PlaceOrder] user_id=\"550bee26-ac27-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T08:20:35.615592128Z"}
2026-09-09T08:20:35.635346+00:00  {"message":"payment went through (transaction_id: f1b81d64-db84-4e29-922c-767f8139cae0)","severity":"info","timestamp":"2026-09-09T08:20:35.63525167Z"}
2026-09-09T08:20:35.640780+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-09T08:20:35.640710712Z"}
2026-09-09T08:20:35.641738+00:00  {"message":"Successful to write message. offset: 20801","severity":"info","timestamp":"2026-09-09T08:20:35.641648462Z"}
```

> Evidence `tr_8338f7487f5d`:

```
<tool_result id="tr_8338f7487f5d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00">
service: checkoutservice
6 trace(s) shown of 6 found, 30 spans; offsets are from each trace's root

trace 377928dd15998e11  root frontend/HTTP POST  1.2ms  started 2026-09-09T08:50:48.891012+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.2ms [self 0.1ms]  ERROR
```

## Still open when this was written

No change history was ever pulled for cartservice or for the redis-cart deployment. Nothing here shows who set the port to 6380 or when; the config reading rests entirely on 6380 being non-default, not on a recorded edit. Relatedly, nobody confirmed that redis-cart is currently listening on 6379, or on anything. If Redis itself is down or was moved, 6380 could be the correct value and the endpoint reading is wrong — check that before reverting.

There is a timeline gap of about three minutes that is unexplained: checkout orders stop completing at roughly T-2m30s, but the cartservice restart loop is only visible from T+0 and the traces cluster after that. Something happened to cartservice before the loop began — plausibly a slower degradation — and it was never characterised.

The per-attempt connect failure latencies range from sub-second to about 30 seconds. A pure closed-port rejection would be uniformly fast; the spread hints at a network-path or DNS component that nobody looked at.

No cartservice resource metrics (memory, CPU, connection counts) and no redis-cart-side evidence were collected at all. The four unmeasured edges flagged at triage are still unmeasured. Past incidents were not available for comparison, so no corpus check informed this verdict.

> Evidence `tr_7c90a77b1763`:

```
<tool_result id="tr_7c90a77b1763" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T08:20:11.666079+00:00  AddItemAsync called with userId=46c8e134-ac27-11f1-b359-b6ed2071a170, productId=66VCHSJNUP, quantity=10
2026-09-09T08:20:11.669092+00:00  GetCartAsync called with userId=46c8e134-ac27-11f1-b359-b6ed2071a170
2026-09-09T08:20:12.043846+00:00  AddItemAsync called with userId=4700f92a-ac27-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=10
2026-09-09T08:20:12.046364+00:00  GetCartAsync called with userId=4700f92a-ac27-11f1-b359-b6ed2071a170
```

> Evidence `tr_0ec22ffb17fe`:

```
<tool_result id="tr_0ec22ffb17fe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T08:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-09T08:20:35.615736+00:00  {"message":"[PlaceOrder] user_id=\"550bee26-ac27-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-09T08:20:35.615592128Z"}
2026-09-09T08:20:35.635346+00:00  {"message":"payment went through (transaction_id: f1b81d64-db84-4e29-922c-767f8139cae0)","severity":"info","timestamp":"2026-09-09T08:20:35.63525167Z"}
2026-09-09T08:20:35.640780+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-09T08:20:35.640710712Z"}
2026-09-09T08:20:35.641738+00:00  {"message":"Successful to write message. offset: 20801","severity":"info","timestamp":"2026-09-09T08:20:35.641648462Z"}
```

> Evidence `tr_8338f7487f5d`:

```
<tool_result id="tr_8338f7487f5d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00">
service: checkoutservice
6 trace(s) shown of 6 found, 30 spans; offsets are from each trace's root

trace 377928dd15998e11  root frontend/HTTP POST  1.2ms  started 2026-09-09T08:50:48.891012+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.2ms [self 0.1ms]  ERROR
```

> Evidence `tr_6c8f032b5bde`:

```
<tool_result id="tr_6c8f032b5bde" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T07:20:00.583000+00:00..2026-09-09T08:52:03.693051+00:00" template="error-ratio" baseline="2026-09-09T05:47:57.472949+00:00..2026-09-09T07:20:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

