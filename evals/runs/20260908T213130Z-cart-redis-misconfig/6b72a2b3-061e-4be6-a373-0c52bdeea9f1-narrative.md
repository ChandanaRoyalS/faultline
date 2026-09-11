# Checkout failures traced to a cart dependency refusing connections

## What was visible, in order

Take T+0 as the page: frontend, loadgenerator and checkoutservice alerting together, critical, frontend named as entry point, twelve services in the stated blast radius and four unmeasured edges in the path we ended up walking.

The first quantitative look was frontend's error ratio against its own prior hour. Baseline near 1.9%, incident-window mean about 6.9% (roughly 3.6x), peaks around a third of calls failing. Three separate threshold crossings, the earliest about five minutes after the window opened. Crucially the window minimum was zero and the standard deviation exceeded the mean: bursty, not a step change, with most requests succeeding throughout. Anyone expecting a total outage of a required dependency would have been wrong-footed. The series carried no dependency or route label, so it could name no downstream — it only proved a real error-side regression with onset inside the window.

Traces were the turn. Failing PlaceOrder traces from about T-1m ran five spans deep — frontend HTTP POST, frontend PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, checkoutservice to CartService/GetCart — with ERROR on the whole ancestor chain and nothing recorded below GetCart, which was attributed as the degrading hop on error grounds. Durations were the tell: 1.2–1.7ms end to end for failures versus 21–27ms for healthy traces with the full fan-out completing cleanly. A failure an order of magnitude faster than success is a rejection, not a stall. One trace near T-1m was only two spans, ending at the frontend client span with no checkoutservice server span at all — connection-level failure at that hop, or a missing span; never resolved.

Frontend logs closed it: repeated gRPC code 14 UNAVAILABLE with 'no connection established', plus one detail line at about T+2m naming the checkout path's cart fetch and a refused TCP dial to a concrete address on port 7070. That single line disposed of timeouts (no DEADLINE_EXCEEDED; a connection that never established cannot be slow), of service discovery (a real IP was resolved and actively refused), of TLS and auth (no certificate or permission errors), and of frontend business logic (every frame in the gRPC client's receive-status path). Uncomfortably, the same UNAVAILABLE pattern appears roughly 38 minutes before the page — the condition was not new at the alert.

> Evidence `tr_fd630b3e661c`:

```
<tool_result id="tr_fd630b3e661c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T20:34:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" template="error-ratio" baseline="2026-09-08T19:32:11.252251+00:00..2026-09-08T20:34:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=248 mean=0.06889 min=0 max=0.333 sd=0.1047
  baseline window: n=248 mean=0.01921 min=0 max=0.06998 sd=0.02369
```

> Evidence `tr_96ee5ce2de29`:

```
<tool_result id="tr_96ee5ce2de29" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-08T20:49:00.583000+00:00..2026-09-08T21:35:49.913749+00:00">
service: checkoutservice
10 trace(s) shown of 50 found, 200 spans; offsets are from each trace's root

trace 210e46af78c41419  root frontend/HTTP POST  21.3ms  started 2026-09-08T21:24:17.629011+00:00  35 spans
  +0.0ms frontend/HTTP POST 21.3ms [self 0.3ms]
```

> Evidence `tr_0271ca85f856`:

```
<tool_result id="tr_0271ca85f856" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:49:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-08T20:56:33.716818+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-08T20:56:33.716865+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-08T20:56:33.716870+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-08T20:56:33.716872+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Dead ends worth not repeating

checkoutservice alerted, so it drew attention first, and most of that time went to clearing it. Its error ratio showed no sustained departure from baseline — the window mean was about half the baseline mean, with identical peaks and dispersion in both windows, marking its occasional spikes as background behaviour. With no sustained onset there was no timestamp to compare against frontend's, so the propagation-lag question could not be settled on error rates at all. Only the aggregate ratio was queried: no latency series, no per-downstream breakdown.

Its logs agreed. No error-severity lines in the window. The only non-info line, about half an hour before the page, blamed the email service for an HTTP 500 on an order confirmation, and never recurred. Through the T-1m to T+2m span every line was an info-level PlaceOrder entry — no dependency, no status code, no timeout, no resource message — and requests kept arriving every few seconds, so the process stayed up with no crash or restart. One weak note, from absence and possibly just coarse log level: those late PlaceOrder entries lacked the downstream completion lines (payment, email, order write) seen earlier.

The rest of the checkout fan-out was cleared from traces: payment Charge, email, currency Convert, product catalog GetProduct, shipping GetQuote and ShipOrder all completed cleanly in healthy traces and were simply never reached in failing ones. The real distractor here was the shippingservice HTTP hop to quoteservice /getquote, flagged as the degrading hop at 4.7–6.5ms (22–26% of self-time) in healthy traces — a steady-state latency contributor with no error marking, and 5–9ms cannot produce a 1.5ms error trace. File it separately. Note also that only the cart read path is implicated; cart writes appear only in healthy traces.

Change history produced nothing usable. Frontend: no deploys, config edits or flag flips across ~24h. checkoutservice: likewise empty, which also rules out a mid-incident rollback or flag flip. Both queries ran at seed radius with zero hops, so neither service's dependencies were inspected, and both windows begin at the alert time — the pre-onset interval was never searched. Productcatalogservice was the only service with records: an automation-driven traffic-shaping container attached and removed about 13.4 hours before onset, adding then clearing a fixed egress delay, with the delay reverted on removal and no deploy or config change anywhere in the window. Not active at onset, and not the cause.

> Evidence `tr_742a0e81c22a`:

```
<tool_result id="tr_742a0e81c22a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T21:04:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" template="error-ratio" baseline="2026-09-08T20:32:11.252251+00:00..2026-09-08T21:04:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.08008 min=0 max=0.6667 sd=0.2006
  baseline window: n=128 mean=0.1528 min=0 max=0.6667 sd=0.2799
```

> Evidence `tr_247ff21e0444`:

```
<tool_result id="tr_247ff21e0444" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T21:04:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T21:04:02.006069+00:00  {"message":"[PlaceOrder] user_id=\"d15b6f92-abc8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T21:04:02.00572468Z"}
2026-09-08T21:04:06.538244+00:00  {"message":"[PlaceOrder] user_id=\"d32a69e0-abc8-11f1-b359-b6ed2071a170\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-09-08T21:04:06.538070376Z"}
2026-09-08T21:04:16.757680+00:00  {"message":"[PlaceOrder] user_id=\"d84e7c90-abc8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T21:04:16.757370006Z"}
2026-09-08T21:04:28.758093+00:00  {"message":"[PlaceOrder] user_id=\"e14bdd10-abc8-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T21:04:28.75799797Z"}
```

> Evidence `tr_167ae270c816`:

```
<tool_result id="tr_167ae270c816" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T21:34:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_167ae270c816>
```

> Evidence `tr_809820cbb77d`:

```
<tool_result id="tr_809820cbb77d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T21:34:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" radius="candidate_cause" hops="1">
service: productcatalogservice
2 changes, ranked by suspicion
  #1  13.4h before onset  2026-09-08T08:11:55.405469+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  13.5h before onset  2026-09-08T08:03:24.104105+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

## Where it was left

Conclusion, medium confidence: frontend PlaceOrder requests fail because the cart dependency actively refuses connections on port 7070 for a fraction of dials. Blame sits on cartservice; it resolves but is not accepting. Frontend and checkoutservice are reporting an unreachable dependency, not their own failure. Fix class applied: restart.

Three things stay open, and they are the honest gaps. First, no cartservice evidence of any kind was ever collected — no logs, metrics, change history or process state — so the mechanism behind the refusal is unsettled: crash loop, limit kill, wrong bind address and replica loss all remain live. Second, the UNAVAILABLE pattern predates the alert by roughly 38 minutes while every change query started at or after the alert, so true onset and any pre-onset triggering act were never searched. Third, nothing distinguishes why only part of traffic fails — peak about a third, minimum zero — between partial replica loss and intermittent restarts. Start at cartservice itself and widen the window backwards.

> Evidence `tr_0271ca85f856`:

```
<tool_result id="tr_0271ca85f856" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:49:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-08T20:56:33.716818+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-08T20:56:33.716865+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-08T20:56:33.716870+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-08T20:56:33.716872+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_51c4169ff3a9`:

```
<tool_result id="tr_51c4169ff3a9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T21:34:00.583000+00:00..2026-09-08T21:35:49.913749+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_51c4169ff3a9>
```

