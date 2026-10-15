# Frontend cart calls refused after a config value was re-applied

## What was visible, in order

Frontend alerted first; frontend-proxy, checkout and the load generator followed. That ordering was the story in miniature — the failure started at frontend and was inherited outward by everything calling it. The thirteen-service blast radius reflects propagation of error status, not thirteen independent problems.

Anchor T+0 at the frontend error-ratio change point: the ratio crossed the ~0.12 threshold, reached ~0.19 and peaked near 0.27, roughly 3.5x anything in the preceding half-hour baseline. A trap for later readers: the incident-window mean was *below* baseline, because this is a narrow late spike rather than a plateau. Judging the service by window averages shows nothing wrong.

Sampled traces put every error span on one branch — frontend's gRPC client calls to CartService (GetCart, AddItem) behind /api/cart — with the status inherited upward through the proxy and load generator. Recommendations, ads, product-catalog and product-reviews traces completed cleanly under ~36ms, and all SQL leaf spans were 0.3-1.1ms. The failing cart client spans lasted only 0.3-2.1ms with no matching server-side span at all: the signature of a call that never reached a listener, not a slow callee and not a saturated database.

Frontend logs moved real onset earlier than the metric. No frontend lines exist for the first half of the window; the first entry is a clean start at T-3m13s, ready in ~200ms, with the first gRPC error one second later. Every error was the same: status 14 UNAVAILABLE, connection refused, to one resolved address and port (172.18.0.24:7071), one stack frame. A resolved IP being refused is not DNS; an immediate refusal is not a timeout; a clean start with no internal exception types is not a crash loop; failure at TCP connect is before any handshake, so credentials were never in play. A single target address rules out a cluster-wide outage.

Frontend's change history contains exactly three entries, all the same key: CART_ADDR. The most recent pointed it at cart on port 7071 about three minutes before T+0, applied by platform automation, and the restart lines up. The identical value had been applied ~3.9h earlier and reverted ~3.7h earlier — this was a re-application of something already backed out. No deploy, image bump or toggle appears for frontend anywhere in the window.

> Evidence `tr_caa1c51c6bda`:

```
<tool_result id="tr_caa1c51c6bda" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" template="error-ratio" baseline="2026-10-14T07:25:46.575629+00:00..2026-10-14T07:57:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=129 mean=0.02197 min=0 max=0.2711 sd=0.06342
  baseline window: n=129 mean=0.02916 min=0 max=0.07758 sd=0.03106
```

> Evidence `tr_36d896dacae9`:

```
<tool_result id="tr_36d896dacae9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00">
service: frontend
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace 1e95ab3208c35b7f  root load-generator/user_get_recommendations  27.0ms  started 2026-10-14T08:25:00.905177+00:00  25 spans
  +0.0ms load-generator/user_get_recommendations 27.0ms [self 0.5ms]
```

> Evidence `tr_ffd09da66365`:

```
<tool_result id="tr_ffd09da66365" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T08:24:33.302535+00:00  ▲ Next.js 16.1.1
2026-10-14T08:24:33.302582+00:00  - Local:         http://8ce29f6dd882:8080
2026-10-14T08:24:33.302636+00:00  - Network:       http://8ce29f6dd882:8080
2026-10-14T08:24:33.302702+00:00  
```

> Evidence `tr_8b2c437c958a`:

```
<tool_result id="tr_8b2c437c958a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T08:27:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" radius="seed" hops="0">
service: frontend
3 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T08:24:32.568719+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
      None  ->  CART_ADDR=cart:7071
  #2  3.7h before onset  2026-10-14T04:43:01.757364+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
```

## Dead end: suspecting cart

Most of the effort went into cart, and none of it changed the conclusion — which is exactly why it belongs here. Cart is the obvious suspect and it is innocent.

Cart's error ratio was flat at exactly zero for every sample, identical to baseline in mean, min, max and deviation, with complete sample coverage across the restart and onset interval. Since the ratio is only defined when the denominator is non-zero, cart was continuously serving successful calls; a crash would have left gaps. Note the inference chain: no direct request-rate, restart or pod-availability metric was retrieved, so continuity of that one series is the entire basis for the availability claim.

Cart's logs agreed — steady info-level cart-store work (add item, get cart, empty cart) with no errors, warnings, timeouts or retries, continuing to within seconds of window close. No wedge, no backend store trouble.

Cart's change history looked alarming and was irrelevant: twelve entries from the same automation actor, six apply/revert pairs flapping a hotfix image reference over about seven hours. None touches a listening port, service spec or deployment field; the last pair completed ~2.6h before onset, and the final action was a revert *away* from the hotfix. No cart-side change coincides with onset.

> Evidence `tr_170c77c4641d`:

```
<tool_result id="tr_170c77c4641d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" template="error-ratio" baseline="2026-10-14T07:25:46.575629+00:00..2026-10-14T07:57:46.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=129 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_81299862b448`:

```
<tool_result id="tr_81299862b448" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-14T07:57:49.654758+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T07:57:49.654840+00:00        AddItemAsync called with userId=f358b774-c7a4-11f1-acc9-ba1d51da3ea9, productId=LS4PSXUNUM, quantity=10
2026-10-14T07:57:49.656745+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T07:57:49.656776+00:00        GetCartAsync called with userId=f358b774-c7a4-11f1-acc9-ba1d51da3ea9
```

> Evidence `tr_2a12a40350e5`:

```
<tool_result id="tr_2a12a40350e5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T08:27:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" radius="candidate_cause" hops="1">
service: cart
12 changes, ranked by suspicion
  #1  2.6h before onset  2026-10-14T05:51:55.080689+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  2.7h before onset  2026-10-14T05:43:37.162806+00:00  platform-automation  image updated: image reference updated on cart
```

## Conclusion and what remains open

Frontend's CART_ADDR was re-applied by platform automation about three minutes before onset, pointing at cart on port 7071 where nothing is listening. Frontend restarted a second later, picked up the wrong endpoint, and every outbound call to CartService failed immediately against the resolved address. The wrongness of the value is the failure: cart is healthy and serving other callers, so only the frontend paths that dial that endpoint break, and the errors propagate outward — which is why the other services alerted after frontend. Confidence high; the fix is to revert the configuration value.

Still open. Cart's actual listening port was never directly observed: its logs carry no bind or listener lines and no deployment or service spec was pulled, so "7071 is wrong" is inferred from the frontend-side refusal plus cart's continued healthy service, not confirmed from cart's own config. Confirm from the spec before trusting the revert target. Why automation re-applied a value already backed out twice is unexplained — without that, reverting may buy only hours. Both log queries were truncated (frontend 8 oldest / 32 newest; cart roughly a half-hour unobserved mid-window), so the ~3 minutes between restart and the metric change point is not directly characterised on either side; rate-window smoothing or cached channel state is the likely explanation but was not demonstrated. No frontend latency percentiles, CPU, memory or connection-pool data were returned, so a concurrent resource problem on frontend is unmeasured, though nothing in logs or traces hints at one. Finally, checkout also calls cart; whether it uses a separate, correct endpoint — which would explain cart's uninterrupted zero-error traffic — was never investigated, as no dispatch touched checkout.

> Evidence `tr_ffd09da66365`:

```
<tool_result id="tr_ffd09da66365" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T08:24:33.302535+00:00  ▲ Next.js 16.1.1
2026-10-14T08:24:33.302582+00:00  - Local:         http://8ce29f6dd882:8080
2026-10-14T08:24:33.302636+00:00  - Network:       http://8ce29f6dd882:8080
2026-10-14T08:24:33.302702+00:00  
```

> Evidence `tr_8b2c437c958a`:

```
<tool_result id="tr_8b2c437c958a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T08:27:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" radius="seed" hops="0">
service: frontend
3 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T08:24:32.568719+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
      None  ->  CART_ADDR=cart:7071
  #2  3.7h before onset  2026-10-14T04:43:01.757364+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
```

> Evidence `tr_caa1c51c6bda`:

```
<tool_result id="tr_caa1c51c6bda" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T07:57:46.664000+00:00..2026-10-14T08:29:46.752371+00:00" template="error-ratio" baseline="2026-10-14T07:25:46.575629+00:00..2026-10-14T07:57:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=129 mean=0.02197 min=0 max=0.2711 sd=0.06342
  baseline window: n=129 mean=0.02916 min=0 max=0.07758 sd=0.03106
```

