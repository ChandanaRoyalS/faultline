# Cart backing-store connection target broke checkout and cart paths

## What paged, and the first look

Three services alerted together: frontend, loadgenerator, checkoutservice. Call it T+0. Blast radius as first drawn covered twelve services and four edges we had no measurements across; severity critical because user-visible checkout was failing.

We pulled aggregate error ratios at the two alerting services that actually serve requests. Frontend's errored-span share peaked around a third of requests; checkoutservice peaked near two thirds. Both series dipped back to zero at points inside the same fifteen minutes. Two conclusions fell out immediately: neither service was hard down, and this was not a pre-existing error floor, since a constant background would not return to zero mid-window. The burstiness was the first real clue and, awkwardly, the one we never fully explained. Note the gap: we asked frontend only for the aggregate ratio — no p95/p99, no per-dependency breakdown. That stayed open.

> Evidence `tr_424ff96c2052`:

```
<tool_result id="tr_424ff96c2052" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3292 n=57
</tool_result:tr_424ff96c2052>
```

> Evidence `tr_4ab1a3c62db5`:

```
<tool_result id="tr_4ab1a3c62db5" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=58
</tool_result:tr_4ab1a3c62db5>
```

## Dead end: blaming checkoutservice itself

Because checkoutservice had the highest error share, the first hypothesis was self-inflicted: a deploy, config edit, or flag flip landing just before onset. Its change log over roughly T-10m to T+5m came back empty. That killed the hypothesis and also killed the remediation built on it — there was nothing to roll back. Scope limit, recorded honestly: the query covered only checkoutservice and only that fifteen-minute window. The preceding hour and checkout's six direct dependencies were not queried here.

The next natural move was to let checkoutservice's logs name the failing downstream. They do not. Every returned line was info severity — no errors, no status codes, no target names. The logs still helped indirectly: early lines show each PlaceOrder followed by payment, confirmation email, and a message-write offset; the newest lines show PlaceOrder entries alone, with longer gaps between them. Checkouts were starting and not finishing. This also ruled out a crash (entries continue steadily) and intake rejection (requests still accepted with user and currency). Both log results were truncated to oldest-eight/newest-thirty-two lines, leaving a middle stretch unobserved.

> Evidence `tr_00b04094cd40`:

```
<tool_result id="tr_00b04094cd40" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_00b04094cd40>
```

> Evidence `tr_e05bd27b0000`:

```
<tool_result id="tr_e05bd27b0000" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-28T08:29:02.915881+00:00  {"message":"[PlaceOrder] user_id=\"86767c4a-a2ba-11f1-ac74-5e36fd0150fc\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-28T08:29:02.915714Z"}
2026-08-28T08:29:02.937228+00:00  {"message":"payment went through (transaction_id: de3d1f76-0bea-4f2d-9460-6beedc478c5b)","severity":"info","timestamp":"2026-08-28T08:29:02.937150459Z"}
2026-08-28T08:29:02.942228+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-08-28T08:29:02.94212575Z"}
2026-08-28T08:29:02.942942+00:00  {"message":"Successful to write message. offset: 2988","severity":"info","timestamp":"2026-08-28T08:29:02.942856334Z"}
```

## The traces settled it

Frontend traces turned the investigation. Checkout fails at one identifiable step: frontend POST → checkoutservice PlaceOrder → prepareOrderItemsAndShippingQuoteFromCart → CartService/GetCart. The GetCart span carries the error; the enclosing prepare span is not itself errored, placing origin at the cart call. The error propagates outward, which is exactly why the alert surfaced at checkoutservice and frontend without either being at fault.

The same dependency fails outside checkout: direct frontend CartService/GetCart and repeated AddItem spans are errored, propagating to frontend parents and loadgenerator. So this was not checkout-specific logic.

Timings killed several theories at once. Errored cart and checkout spans complete in roughly 0.2–2.6ms, frontend parents under ~9ms — immediate rejection, not timeout or saturation. No payment, currency, or accounting spans appear in any checkout tree, so the cause cannot lie beyond those unmeasured edges; checkout aborts upstream of them. Product catalog, recommendation, ad, and flag spans were clean and fast in the same window, so frontend was propagating, not originating.

> Evidence `tr_a2f3dadb7f03`:

```
<tool_result id="tr_a2f3dadb7f03" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
service: frontend
200 spans
  ca14bc20a4d0eebf loadgenerator/HTTP GET 6.2ms
  ca14bc20a4d0eebf frontend/HTTP GET 1.7ms
  ca14bc20a4d0eebf loadgenerator/HTTP GET 22.4ms
```

## Dead end: cartservice's error ratio

With cart identified, we tried to quantify it. The error-ratio query returned no series at all — both the error-status numerator and the all-calls denominator empty. The empty denominator is the informative part: a service serving traffic with a high error share would still register calls, and a partially degraded one would still register successes. This pipeline could not serve as source of truth here, so we stopped using it. Request rate as an independent series, restart counters, memory signals, and connection-pool gauges were never pulled.

> Evidence `tr_0010aaceab9b`:

```
<tool_result id="tr_0010aaceab9b" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_0010aaceab9b>
```

## What cartservice's logs said

The logs explained the empty metrics. cartservice was in a crash-restart loop. Each cycle opens with a startup connection attempt to host redis-cart on port 6380 (non-SSL, abortConnect disabled), then within fifteen to thirty-five seconds logs a connection failure and throws an unhandled exception out of the Redis cart store's connection-check path during store initialization called from Main. At least five cycles appear between roughly T+1m and T+3m, each new attempt starting under a second after the prior crash, the last visible line being another attempt. No successful connection anywhere.

Because the exception is unhandled and comes out of initialization called from Main, the process dies before serving requests — which is why callers saw sub-millisecond rejections and why there were no span metrics to read. That also rules out in-process degradation, application-level rejection (no validation or quota messages at all), a transient blip (five identical cycles), and TLS trouble (the logged connection string shows SSL disabled; the unusual detail is the port). At window start cartservice was healthy, logging normal GetCartAsync and AddItemAsync invocations, so onset is later than window start. Coverage stops around T+3m.

> Evidence `tr_0972cafc180e`:

```
<tool_result id="tr_0972cafc180e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T08:29:01.171104+00:00  GetCartAsync called with userId=
2026-08-28T08:29:01.649282+00:00  GetCartAsync called with userId=
2026-08-28T08:29:01.671681+00:00  AddItemAsync called with userId=85bc21d8-a2ba-11f1-ac74-5e36fd0150fc, productId=L9ECAV7KIM, quantity=10
2026-08-28T08:29:01.673846+00:00  GetCartAsync called with userId=85bc21d8-a2ba-11f1-ac74-5e36fd0150fc
```

## The cause

cartservice's change log held exactly one entry: at T-3m an automated platform actor set an environment variable pointing cartservice at its Redis backing store on a different port than the one previously in effect. The recorded prior value is unset, so this was the first explicit setting of that variable, not an edit. The connection string cartservice then logs targets redis-cart:6380.

That single entry closed the alternatives: not organic, not a code deploy or image rollout, not a flag flip, and not an ambiguous pile of overlapping changes. The failing mechanism is the configuration value itself — it names an endpoint that does not accept the connection. Confidence high. Fix class: config revert.

> Evidence `tr_c79fcc3e7be2`:

```
<tool_result id="tr_c79fcc3e7be2" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
service: cartservice
1 changes
  2026-08-28T08:36:31.135585+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_c79fcc3e7be2>
```

> Evidence `tr_0972cafc180e`:

```
<tool_result id="tr_0972cafc180e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T08:29:01.171104+00:00  GetCartAsync called with userId=
2026-08-28T08:29:01.649282+00:00  GetCartAsync called with userId=
2026-08-28T08:29:01.671681+00:00  AddItemAsync called with userId=85bc21d8-a2ba-11f1-ac74-5e36fd0150fc, productId=L9ECAV7KIM, quantity=10
2026-08-28T08:29:01.673846+00:00  GetCartAsync called with userId=85bc21d8-a2ba-11f1-ac74-5e36fd0150fc
```

## Still open for the next responder

We never checked from the Redis side which port redis-cart actually listens on. If Redis was intentionally moved to 6380 and the automation was correcting cartservice, the fix belongs on the Redis/service side, not a revert. Relatedly, nobody established why platform-automation applied this change or whether it will re-apply after a manual revert; the unset prior value hints at a template or defaulting change upstream that no one examined.

No change query was run against checkout's other five dependencies or outside the fifteen-minute window, so a second concurrent change elsewhere is unexcluded. Frontend latency percentiles and per-dependency breakdowns were never retrieved, so a secondary degradation on a non-cart path cannot be fully excluded, though all sampled non-cart spans were clean. Finally, the bursty pattern — frontend peaking near a third, checkout near two thirds, both returning to zero — is only partly explained by a crash-restart cycle. Whether cart briefly served between restarts, or whether some replicas kept the old config, is unsettled. Log coverage after T+3m is absent, so we do not know whether the loop was still running.

> Evidence `tr_424ff96c2052`:

```
<tool_result id="tr_424ff96c2052" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3292 n=57
</tool_result:tr_424ff96c2052>
```

> Evidence `tr_4ab1a3c62db5`:

```
<tool_result id="tr_4ab1a3c62db5" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=58
</tool_result:tr_4ab1a3c62db5>
```

> Evidence `tr_0972cafc180e`:

```
<tool_result id="tr_0972cafc180e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T08:29:00.583000+00:00..2026-08-28T08:44:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T08:29:01.171104+00:00  GetCartAsync called with userId=
2026-08-28T08:29:01.649282+00:00  GetCartAsync called with userId=
2026-08-28T08:29:01.671681+00:00  AddItemAsync called with userId=85bc21d8-a2ba-11f1-ac74-5e36fd0150fc, productId=L9ECAV7KIM, quantity=10
2026-08-28T08:29:01.673846+00:00  GetCartAsync called with userId=85bc21d8-a2ba-11f1-ac74-5e36fd0150fc
```
