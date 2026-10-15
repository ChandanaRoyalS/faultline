# Cart slow-but-successful: ~300ms per backing-store command, 14 services touched

## What was visible, in order

Five services alerted together — cart, frontend, frontend-proxy, load-generator, checkout — at warning severity, with cart named as origin and fourteen services in the blast radius. Nothing was hard down; the symptom was edge latency around 1.2s plus a minority of outright failures at the proxy. The first signal we chased was the change log: cart had exactly two entries in a full day, both image-reference edits on the same deployment by the same automated actor, an apply at T+3m and a revert at T+13m, leaving roughly eleven minutes of exposure. At T+5m frontend-proxy's error ratio stepped — a single detected change point, baseline mean ~0.47% to ~9.3%, about twentyfold — and stayed elevated with no detected return to baseline. It was bursty: the series still touches zero and peaks near 29%, so most requests kept succeeding and this was never a total outage. Note the trigger is at T+5m, not at the top of the window.

> Evidence `tr_87ae34783661`:

```
<tool_result id="tr_87ae34783661" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-11T02:02:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" radius="seed" hops="0">
service: cart
2 changes, ranked by suspicion
  #1  16m before onset  2026-10-12T01:45:33.026721+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  27m before onset  2026-10-12T01:35:13.836745+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_f4bcda3c9058`:

```
<tool_result id="tr_f4bcda3c9058" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T01:32:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" template="error-ratio" baseline="2026-10-12T01:00:30.822801+00:00..2026-10-12T01:32:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=129 mean=0.09283 min=0 max=0.2879 sd=0.119
  baseline window: n=129 mean=0.004658 min=0 max=0.02715 sd=0.009217
```

## Where the time actually went

Traces settled it. Cart has inbound server spans throughout, each parented by a frontend or checkout client span, so requests were reaching its instrumentation. Around T+25m cart handler spans complete in 0.3–1.9ms with store-command children at tenths of a millisecond. From T+26m onward they balloon: ~300ms for GetCart, up to ~900ms for AddItem. The time is self-time inside individual store command spans — HGET, HMSET and EXPIRE each around 300ms — and AddItem, issuing three sequentially, accumulates the ~900ms. Handler self-time stays sub-millisecond, the flag-evaluation subtree is about 1ms, and product-catalog and other dependencies in the same traces stay under a millisecond. No span carries an error status. Cart is slow-but-successful; the latency propagates intact up through frontend, frontend-proxy and checkout, which is what drove the proxy's error step as callers hit deadlines and dropped connections. Cart's own logs agree and are unhelpfully calm: only info-level store operations, distinct user ids arriving through the final seconds, no warnings or stack traces. Its error ratio is flat zero with zero variance in both baseline and incident window.

> Evidence `tr_f3ad7f93f89a`:

```
<tool_result id="tr_f3ad7f93f89a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T01:32:31.664000+00:00..2026-10-12T02:04:32.505199+00:00">
service: cart
7 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 3a01d11989f8f074  root load-generator/user_checkout_multi  40.8ms  started 2026-10-12T01:57:29.382655+00:00  49 spans
  +0.0ms load-generator/user_checkout_multi 40.8ms [self 14.3ms]
```

> Evidence `tr_2f1a6581d4c2`:

```
<tool_result id="tr_2f1a6581d4c2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T01:32:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-12T01:32:32.768246+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T01:32:32.768343+00:00        GetCartAsync called with userId=
2026-10-12T01:32:34.977375+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T01:32:34.977405+00:00        AddItemAsync called with userId=cd19beba-c5dc-11f1-9e56-ba3679c5fcbe, productId=OLJCESPC7Z, quantity=5
```

> Evidence `tr_36196ebbba0f`:

```
<tool_result id="tr_36196ebbba0f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T01:32:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" template="error-ratio" baseline="2026-10-12T01:00:30.822801+00:00..2026-10-12T01:32:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=101 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

## Dead ends and what is still open

The longest dead end was frontend's logs between T+3.5m and T+14m: gRPC 13 wrapping Unavailable on a dial timeout to cart's address on port 7070, gRPC 14 with host-unreachable, and — dominating — resolver-produced-zero-addresses. Read alone that says cart is gone, and it sent us hunting reachability and discovery problems. It describes the churn around the image transitions, not the condition still degrading requests half an hour later. The rollback-as-trigger theory also failed: the revert landed well before the measured latency signature. Ruled out along the way: a config or flag change on cart (only image references exist), a human out-of-band deploy (both entries are automation), a slow-burn change (a full day holds nothing else), cart as an error source, and latency originating in the frontend or proxy layers. Still open: cart's latency percentiles, request rate and saturation were never measured — only error ratio was queried, which also surfaced 28 intervals with no cart spans at all, new to this window. The backing store itself was never inspected, so whether the ~300ms lives in the store, the network hop, or client-side code is unsettled. Both cart and frontend log results were truncated through the middle ~30 minutes. And each change record shows one side of the image transition as unset, so what cart runs now, and whether the revert fully took, is not established. Confidence medium; fix class restart.

> Evidence `tr_d0d2cb41a0aa`:

```
<tool_result id="tr_d0d2cb41a0aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T01:32:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-12T01:36:04.107383+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 172.18.0.24:7070: i/o timeout"
2026-10-12T01:36:04.112742+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-12T01:36:04.112752+00:00      at new Promise (<anonymous>) {
2026-10-12T01:36:04.112754+00:00    code: 13,
```

> Evidence `tr_36196ebbba0f`:

```
<tool_result id="tr_36196ebbba0f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T01:32:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" template="error-ratio" baseline="2026-10-12T01:00:30.822801+00:00..2026-10-12T01:32:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=101 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_87ae34783661`:

```
<tool_result id="tr_87ae34783661" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-11T02:02:31.664000+00:00..2026-10-12T02:04:32.505199+00:00" radius="seed" hops="0">
service: cart
2 changes, ranked by suspicion
  #1  16m before onset  2026-10-12T01:45:33.026721+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  27m before onset  2026-10-12T01:35:13.836745+00:00  platform-automation  image updated: image reference updated on cart
```

