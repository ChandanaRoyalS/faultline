# Checkout Failures Traced to CartService GetCart Rejections

## What we saw first

The page arrived from three places at once: frontend, loadgenerator, and checkoutservice. The user-visible complaint was checkout failing. Blast radius was scored at twelve services, severity critical, with the frontend as the entry point for the investigation. Nothing in the initial alert text distinguished a slow path from a rejected one, and that distinction turned out to be the whole investigation.

First move was to characterise the frontend error signal rather than chase the topology. Frontend error ratio in the incident window averaged roughly 7% with peaks near 32% and a floor of zero — bursty, not a plateau. The prior comparable hour was exactly zero across every sample, zero variance. So this was a step from nothing, not a chronic floor that someone finally noticed.

Two things from that first look reshaped the timeline. The first threshold crossing was at 08:31, with further crossings at 08:43 and 09:18 — roughly forty minutes before the alerts fired. And because the frontend minimum stayed at zero and the mean sat far below the max, the service was clearly not hard-down; a substantial share of requests were still clean, which argues for one failing path among several rather than total loss of a dependency.

> Evidence `tr_ce6f2f9e7568`:

```
<tool_result id="tr_ce6f2f9e7568" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" template="error-ratio" baseline="2026-09-15T07:18:08.122055+00:00..2026-09-15T08:20:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=249 mean=0.07002 min=0 max=0.3232 sd=0.1095
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

## Following the error one hop down

checkoutservice told the same story with a sharper edge: exactly zero error ratio across the full prior-hour baseline, then a mean near 12% in the incident window with a peak around 67%. Its first crossing above 5% was 08:43:30, with a second at 09:18:30. Again, high variance, never reaching 1.0 — partial and intermittent, not a hard outage of the checkout path.

Worth noting for anyone reading a similar shape later: both of these metric results were service-level aggregates only. No per-downstream-target dimension and no latency series. They were enough to establish onset and to kill the 'chronic background errors' reading, but they could not name a culprit and it would have been a mistake to keep re-querying them hoping for one.

> Evidence `tr_632e684f9eb7`:

```
<tool_result id="tr_632e684f9eb7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" template="error-ratio" baseline="2026-09-15T07:18:08.122055+00:00..2026-09-15T08:20:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=249 mean=0.1225 min=0 max=0.6667 sd=0.2488
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_ce6f2f9e7568`:

```
<tool_result id="tr_ce6f2f9e7568" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" template="error-ratio" baseline="2026-09-15T07:18:08.122055+00:00..2026-09-15T08:20:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=249 mean=0.07002 min=0 max=0.3232 sd=0.1095
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

## Dead end: checkoutservice logs

The obvious next step was to read checkoutservice's own logs across the alert window, on the assumption a service failing at 12% would say something about why. It said nothing. Every line returned was info severity. The newest ~32 lines ran contiguously from about 09:18:48 to 09:22:11 and contained no warning or error entries at all, including straight across 09:20:30.

The only log shape emitted was the per-order PlaceOrder entry with a user id and a currency code. No message named a downstream RPC target, a pool or resource limit, or a deadline. Orders kept being handled through 09:22:11 with no silent gap and no restart banner, which ruled out a crash-loop reading of the incident. Currency mix was ordinary USD with occasional CAD, so no single pathological request pattern.

Three hypotheses died here and are worth recording as dead: checkoutservice self-reporting an exhausted resource, checkoutservice returning deadline-exceeded to its callers, and checkoutservice having crashed or stopped. None of them left a trace. One caveat: the result was truncated to the oldest 8 and newest 32 lines, so the 08:51–09:18 interior was never read. Re-running the same unfiltered query would not recover it — a severity filter or a narrower window is needed.

> Evidence `tr_b46113298aeb`:

```
<tool_result id="tr_b46113298aeb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-15T08:50:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-15T08:50:18.274147+00:00  {"message":"[PlaceOrder] user_id=\"7a1436e6-b0e2-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-15T08:50:18.274046967Z"}
2026-09-15T08:50:21.894478+00:00  {"message":"[PlaceOrder] user_id=\"7c3b1a3e-b0e2-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-15T08:50:21.894261927Z"}
2026-09-15T08:50:24.839575+00:00  {"message":"[PlaceOrder] user_id=\"7dfce4c4-b0e2-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-15T08:50:24.839405886Z"}
2026-09-15T08:50:36.182752+00:00  {"message":"[PlaceOrder] user_id=\"84baca74-b0e2-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-15T08:50:36.182655336Z"}
```

## Dead end: change history

In parallel we asked the change log whether anything had shipped. Frontend, checkoutservice, and productcatalogservice were all queried and all came back completely empty — no deploys, no config edits, no flag flips.

Two cautions on how much that buys you. The first three queries used a window starting at 09:20:15 on the previous day and running forward about 24 hours, which covers the incident and everything after it but does not cleanly cover the hours immediately preceding onset in the way the question implied. A later productcatalogservice query on effectively the same window was read as spanning roughly 23 hours before the 08:31 onset, so for that service the absence does cover a plausible change lead-time.

What this does settle: no in-incident deploy, revert, or flag flip on these three services is sustaining the failure, and rollback is not an available remediation for them. What it does not settle: cartservice, which was never queried at all.

> Evidence `tr_398163674902`:

```
<tool_result id="tr_398163674902" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T09:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_398163674902>
```

> Evidence `tr_811985784c40`:

```
<tool_result id="tr_811985784c40" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T09:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_811985784c40>
```

> Evidence `tr_269adc930139`:

```
<tool_result id="tr_269adc930139" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T09:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_269adc930139>
```

> Evidence `tr_4749cb36dd1e`:

```
<tool_result id="tr_4749cb36dd1e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T09:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_4749cb36dd1e>
```

## Dead end: productcatalogservice

productcatalogservice was a natural suspect given its fan-in. It was clean. Error ratio flat at zero across the full window from 07:20 onward, identical to the zero baseline, 489 samples each side with no variance and no departure anywhere. No spike around 08:15, no regression relative to prior behaviour.

This query returned the error-ratio series only; the p95 latency half of the question came back empty and was never re-asked. Given what traces later showed about durations, that gap did not end up mattering.

> Evidence `tr_feba44de6059`:

```
<tool_result id="tr_feba44de6059" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T07:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" template="error-ratio" baseline="2026-09-15T05:18:08.122055+00:00..2026-09-15T07:20:15.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=489 mean=0 min=0 max=0 sd=0
  baseline window: n=489 mean=0 min=0 max=0 sd=0
```

## The turn: traces

Traces resolved in one query what metrics and logs could not. Nine sampled checkoutservice traces, all with an identical five-span shape: frontend HTTP POST, frontend gRPC PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, then CartService/GetCart. Forty-five spans total.

The only downstream RPC span checkoutservice emitted was the call to CartService/GetCart, and it was error-marked in all nine traces — 9/9, with every other target at zero. GetCart was the deepest error in each trace; the error status propagated upward through checkoutservice PlaceOrder and the frontend spans. Self-time inside the checkoutservice spans was ~0.1–0.2ms and prepareOrderItems carried no error of its own, which places the origin at the leaf, not in checkout's business logic and not at the frontend or ingress layer.

The durations settled the character of the failure. Root spans ran ~1.2–2.6ms end to end, with GetCart leaves at ~0.4–1.0ms. That is far too fast for a timeout, a queueing backlog, or a saturated pool. These are immediate rejections. Any hypothesis built around slow calls or blown deadline budgets can be set aside.

It also explains why payment, shipping, email, and currency never appeared: the trace terminates in error at GetCart before checkout ever reaches them. Their absence from the spans is not evidence of health, it is evidence they were never called.

> Evidence `tr_d6827e2372a7`:

```
<tool_result id="tr_d6827e2372a7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-15T07:50:15.583000+00:00..2026-09-15T09:22:23.043945+00:00">
service: checkoutservice
9 trace(s) shown of 9 found, 45 spans; offsets are from each trace's root

trace a5fbfc62dfee5c77  root frontend/HTTP POST  1.7ms  started 2026-09-15T09:21:30.151010+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.7ms [self 0.3ms]  ERROR
```

## Where it landed, and what is still open

The failing component is cartservice, on the GetCart path. Fix class is a restart. Confidence is low, and the reason is specific: no dispatch ever reached cartservice, so we identified the component without ever examining its internals.

Four things a future responder should close.

First, the gRPC status code cartservice returns on failed GetCart calls. UNAVAILABLE versus RESOURCE_EXHAUSTED versus INTERNAL would very likely decide the class of failure outright, and it is one query away.

Second, cartservice change history was never queried, so the comfortable phrase 'no change anywhere' is not established. Its backing cache or store was likewise never looked at.

Third, the timing gap. Onset at 08:31 on the frontend and 08:43 on checkoutservice precedes the 09:20 alerts by about forty minutes and nothing in the record explains that delay. Either the alert thresholds are slow or something changed in character at 09:18.

Fourth, the sampling. All nine traces cluster in the final minute of the window, roughly 09:21:30 to 09:22:11. The 9/9 error rate is a snapshot of that minute and cannot be generalised to the whole incident — note that it sits oddly against the metric picture of a 7–12% bursty error ratio, which is precisely what you would expect if the trace sample caught one burst rather than the average.

> Evidence `tr_d6827e2372a7`:

```
<tool_result id="tr_d6827e2372a7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-15T07:50:15.583000+00:00..2026-09-15T09:22:23.043945+00:00">
service: checkoutservice
9 trace(s) shown of 9 found, 45 spans; offsets are from each trace's root

trace a5fbfc62dfee5c77  root frontend/HTTP POST  1.7ms  started 2026-09-15T09:21:30.151010+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.7ms [self 0.3ms]  ERROR
```

> Evidence `tr_632e684f9eb7`:

```
<tool_result id="tr_632e684f9eb7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" template="error-ratio" baseline="2026-09-15T07:18:08.122055+00:00..2026-09-15T08:20:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=249 mean=0.1225 min=0 max=0.6667 sd=0.2488
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_ce6f2f9e7568`:

```
<tool_result id="tr_ce6f2f9e7568" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:20:15.583000+00:00..2026-09-15T09:22:23.043945+00:00" template="error-ratio" baseline="2026-09-15T07:18:08.122055+00:00..2026-09-15T08:20:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=249 mean=0.07002 min=0 max=0.3232 sd=0.1095
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

