# Constant per-call delay on the cart path degrades checkout

## What was visible, in order

The page named four services at once: cartservice, checkoutservice, frontend, loadgenerator. Warning severity, twelve services in the blast radius, cartservice named as the origin, four unmeasured edges crossed. Nothing was down. Orders were still completing. The shape on arrival was "one path got slow and the slowness is propagating to whoever waits on it." Treat the alert as T+0.

The first move was to ask whether cartservice was erroring, and it was the wrong question as asked. The error-ratio expression returned no series at all over fifteen minutes — not a zero, nothing. That is ambiguous by construction: equally consistent with no span-derived call metrics existing under those labels and with calls existing but none carrying an error-status label. Since the denominator covers all statuses, a quiet-but-instrumented service would still have produced a series. Total emptiness points at a labeling or instrumentation-coverage gap, not at service health. No latency percentiles, CPU, memory, GC or pool numbers were retrieved for cartservice at all. Dead end; do not re-walk without fixing the labels first.

cartservice logs showed only ordinary cart operations — retrievals, adds, empties — with no exceptions, timeouts, or downstream component named. Healthy at roughly T-10m and again by about T+2m30s, where a dense stream of requests ran with sub-second spacing across many user ids. But the result was truncated to the oldest eight and newest thirty-two lines, so the interval containing T+0 was never read. That rules out a sustained process death or a long-running error condition bracketing the alert; it says nothing about a short burst inside the unread gap.

> Evidence `tr_4f3c96261fcf`:

```
<tool_result id="tr_4f3c96261fcf" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_4f3c96261fcf>
```

> Evidence `tr_3f1fe3ae621b`:

```
<tool_result id="tr_3f1fe3ae621b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T08:12:37.227615+00:00  GetCartAsync called with userId=
2026-08-28T08:12:38.369934+00:00  GetCartAsync called with userId=
2026-08-28T08:12:40.657245+00:00  GetCartAsync called with userId=
2026-08-28T08:12:45.312057+00:00  GetCartAsync called with userId=
```

## Where the answer was

Traces settled it. Every cache round-trip out of cartservice landed in a tight ~300–310ms band, reads and writes alike, no fast outliers and no heavy tail. cartservice server spans were essentially the sum of their cache children with negligible self-time: single-operation GetCart and EmptyCart around 301–309ms, two-operation AddItem around 603–611ms. The penalty is additive per outbound cache call, not a flat charge per request. Everything not routed through cartservice stayed fast in the same window — catalog, currency, payment, shipping, quote, email, messaging all sub-millisecond to about 20ms.

That killed several theories at once. cartservice was not CPU-starved or blocked in application code (no self-time to blame). It was not cluster-wide network or mesh trouble (every non-cart edge healthy). It was not a persistence or write-path problem (reads and writes indistinguishable). It was not tail latency (very low variance across many independent traces).

The change record supplied the trigger. Roughly T-3m30s, platform-automation attached a traffic-shaping container to the cart-service network namespace, applying a fixed 300ms delay with zero jitter on eth0 egress. The rule binds the whole pod namespace, so all outbound traffic pays it — which matches the trace band exactly, jitter included. The log shows no code deployment, no image rollout, no flag flip, no application config edit, and no change on the cache side. Nor was this organic drift: there is a discrete timestamped trigger of fixed magnitude.

From checkoutservice, the victim view was consistent. Its error ratio ran from a clean zero baseline to a peak near 7.9% across sixty samples — onset inside the window, and partial rather than total, the signature of a degraded dependency rather than an absent one. Its logs were entirely info-severity successful order flows with gap-free topic offsets, but per-order step latency grew from tens of milliseconds near T-10m to roughly 1.2 seconds per step by about T+4m. Hard-down, a stalled publish path, and a purely upstream artifact are all ruled out.

Conclusion: added constant wait on a dependency call path. cartservice never errored or crashed; it became slow and its callers absorbed the wait. Not a wrong artifact, not a wrong config value consumed by the application. High confidence. Fix by reverting the change.

> Evidence `tr_b168907e2864`:

```
<tool_result id="tr_b168907e2864" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00">
service: cartservice
200 spans
  b8690453499c6a29 cartservice/hipstershop.CartService/GetCart 303.6ms
  b8690453499c6a29 cartservice/HGET 302.3ms
  06bb9192c75f4bd7 frontend/HTTP POST 1520.1ms
```

> Evidence `tr_0a41300a4f4b`:

```
<tool_result id="tr_0a41300a4f4b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00">
service: cartservice
1 changes
  2026-08-28T08:18:53.416539+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_0a41300a4f4b>
```

> Evidence `tr_4ee611489716`:

```
<tool_result id="tr_4ee611489716" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.07895 n=60
</tool_result:tr_4ee611489716>
```

## Loose ends worth chasing

The caller-side inflation is not uniform, and this is the most interesting open item. frontend's client span for GetCart (~605ms) exceeds the matching cartservice server span (~302ms) by about 300ms, as expected. But checkoutservice's client spans for GetCart and EmptyCart (~1207–1210ms) exceed their server spans (~301–304ms) by roughly 900ms — about triple. Something on the checkout-to-cart path specifically (connection setup, retries, or queuing) is amplifying the delay and is unexplained.

Both log queries were truncated and returned nothing from roughly T-2m to T+3m, so the interval containing the alert was never read directly in either service. Any error or timeout burst confined to that gap is unobserved. Relatedly, no pre-change cartservice spans came back despite the trace window opening earlier, so the healthy cache baseline is inferred from unaffected peers rather than measured on the cart path.

Two smaller items: checkoutservice's ~7.9% error peak is aggregated by service name only, with no per-peer breakdown, so whether those errors are all cart-path timeouts or include independent payment, shipping, or email failures is unestablished. And the change record does not say whether the shaping rule is still attached, nor whether it was a deliberate experiment with a scheduled teardown or an unintended action.

> Evidence `tr_b168907e2864`:

```
<tool_result id="tr_b168907e2864" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00">
service: cartservice
200 spans
  b8690453499c6a29 cartservice/hipstershop.CartService/GetCart 303.6ms
  b8690453499c6a29 cartservice/HGET 302.3ms
  06bb9192c75f4bd7 frontend/HTTP POST 1520.1ms
```

> Evidence `tr_3f1fe3ae621b`:

```
<tool_result id="tr_3f1fe3ae621b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T08:12:37.227615+00:00  GetCartAsync called with userId=
2026-08-28T08:12:38.369934+00:00  GetCartAsync called with userId=
2026-08-28T08:12:40.657245+00:00  GetCartAsync called with userId=
2026-08-28T08:12:45.312057+00:00  GetCartAsync called with userId=
```

> Evidence `tr_4ee611489716`:

```
<tool_result id="tr_4ee611489716" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T08:12:30.583000+00:00..2026-08-28T08:27:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.07895 n=60
</tool_result:tr_4ee611489716>
```
