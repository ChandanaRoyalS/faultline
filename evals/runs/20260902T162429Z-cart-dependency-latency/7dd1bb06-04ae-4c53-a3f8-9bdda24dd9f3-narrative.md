# Constant ~300ms penalty on every cartservice network round trip

## What we saw first

The page arrived as a warning, not a pager-melting outage: cartservice, checkoutservice, frontend and loadgenerator all alerted at once, and the declared blast radius was twelve services with four edges we had no measurements for. The starting point handed to us was cartservice.

The shape of the alerts was the first useful clue and it pointed away from the obvious reading. Nothing was erroring. Frontend's error ratio was flat zero for every sample in the incident window and equally flat across the preceding baseline window, with zero variance in both — so the pre-incident reference was clean and the alerting was not about failed requests. Checkoutservice looked the same: forty-six samples in-window, mean, min and max all zero. Both services were serving traffic and serving it successfully. Whatever we were chasing was a waiting problem, not a breaking one.

> Evidence `tr_daef75001ab0`:

```
<tool_result id="tr_daef75001ab0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" template="error-ratio" baseline="2026-09-02T15:26:08.337512+00:00..2026-09-02T15:58:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=47 mean=0 min=0 max=0 sd=0
  baseline window: n=9 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_79187b226011`:

```
<tool_result id="tr_79187b226011" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" template="error-ratio" baseline="2026-09-02T15:26:08.337512+00:00..2026-09-02T15:58:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=46 mean=0 min=0 max=0 sd=0
  baseline window: n=8 mean=0 min=0 max=0 sd=0
```

## The dead end that cost the most time: cartservice metrics

The natural next move was to ask Prometheus what cartservice itself was doing. That returned nothing. The error-ratio series for the cartservice service name was empty in the incident window — and, crucially, empty in the baseline window too.

This is the part a future responder should read twice. The tooling reported "no sustained departure" for cartservice, and that phrasing is actively misleading here: there was no departure because there was no data on either side of the comparison. It is not an all-clear. We briefly entertained the idea that the emptiness itself was the signal — that cartservice traffic had collapsed to zero — but the identical emptiness in the pre-incident baseline rules that out. The gap predates the incident and is best explained by missing or mislabeled span-metrics coverage for this service name. It is an observability defect that degraded this investigation and deserves its own follow-up; it is not a symptom of the failure.

Note also what that query did not cover: no latency percentiles, no CPU or memory, no cache-call timing. Those dimensions were never queried for any service during this incident.

> Evidence `tr_4d25d6568bf2`:

```
<tool_result id="tr_4d25d6568bf2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" template="error-ratio" baseline="2026-09-02T15:26:08.337512+00:00..2026-09-02T15:58:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Logs: partially useful, badly truncated

Loki did have cartservice's stream, so the label was right and ingestion was working. What came back were routine request-handling lines — cart reads, add-item, empty-cart — with no error-level entries and no mention of a downstream backend or cache.

The result was over-full and got trimmed from the middle: roughly eight lines from the early part of the window survived, plus the newest thirty-two from the last forty-odd seconds. The minute we most wanted to inspect fell entirely inside the discarded middle, so these logs can neither confirm nor deny error activity at onset. What they do establish is that in the final stretch cartservice was still serving several operations per second for many distinct user ids, all completing normally. That kills the crash-loop and the dead-instance hypotheses, and it kills the idea of a sustained ongoing stream of cache errors running past the end of the window.

> Evidence `tr_bd15542f04f8`:

```
<tool_result id="tr_bd15542f04f8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-02T16:18:07.587820+00:00  GetCartAsync called with userId=
2026-09-02T16:18:09.238055+00:00  GetCartAsync called with userId=
2026-09-02T16:18:09.894056+00:00  AddItemAsync called with userId=e371c5ac-a6e9-11f1-ae7b-9eef0fcf8acb, productId=66VCHSJNUP, quantity=1
2026-09-02T16:18:09.896684+00:00  GetCartAsync called with userId=e371c5ac-a6e9-11f1-ae7b-9eef0fcf8acb
```

## Traces: where the answer actually was

Jaeger settled it. Every cartservice server span in the window sat at a flat floor: GetCart and EmptyCart around 301–306ms, AddItem around 603–609ms because it makes two serial cache calls. The spread across dozens of independent spans was a few milliseconds — no long tail, no jitter.

Inside each span, almost the whole duration belonged to the child cache client span (HGET and HMSET both ~300–307ms), leaving something under 1.5ms of handler and serialization work. Handler code, garbage collection and CPU starvation are therefore off the table; there is no self-time to hide them in. Queuing and pool contention are off the table too — those produce a heavy right tail and wide variance, not a knife-edge constant on both reads and writes. A payload-size explanation fails for the same reason: the penalty does not scale with operation type or cart size.

The increment is additive per network round trip, which is why the blast radius looked large. Frontend's GetCart client spans ran ~604–614ms against a ~301ms cartservice server span, leaving ~300ms unaccounted on the wire. Checkoutservice's GetCart and EmptyCart client spans ran ~1206–1213ms against ~302ms server spans — roughly three increments' worth. Peer services in those same traces were untouched: productcatalog, currency, payment, shipping/quote, email and the async orders path all finished between 0 and 21ms. That containment is what ruled out a slow dependency elsewhere and made it clear the penalty attaches to cartservice's own network path and its inbound hops.

One limitation to carry forward: the result was truncated at two hundred spans and contained no pre-onset comparison spans. Every cartservice span we retrieved already carried the floor, so the step change is inferred from the near-zero handler self-time rather than measured against a clean before-picture.

> Evidence `tr_97be6bef850b`:

```
<tool_result id="tr_97be6bef850b" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-02T15:28:00.583000+00:00..2026-09-02T16:29:52.828488+00:00">
service: cartservice
200 spans
  0959dd3fe1c54682 checkoutservice/hipstershop.CheckoutService/PlaceOrder 2462.3ms
  0959dd3fe1c54682 checkoutservice/prepareOrderItemsAndShippingQuoteFromCart 1241.5ms
  0959dd3fe1c54682 checkoutservice/hipstershop.CartService/GetCart 1209.4ms
```

## The cause

The change history for cartservice contained exactly one entry in the minutes before onset: a traffic-shaping container attached to the cart-service pod's network namespace at about T-3m, applying a fixed egress delay on eth0 with zero jitter. The stated magnitude was a constant 300ms per packet — which predicts precisely the flat, tightly-clustered shift the traces show, and rules out bursty congestion or packet loss as an explanation for anything erratic.

Several candidate causes died against the same record. A code rollout was ruled out: the most recent image activity was a revert completing roughly 2.8 hours before onset, with nothing in the preceding minutes. The v1.2.1-cartservice-hotfix.2 tag had been applied and reverted twice earlier in the day and was not the running reference at incident time. No cache endpoint or connection-string change appears, no environment variable, resource limit or replica change appears. And the latency is not organic — an explicit, sufficient cause was attached three minutes ahead of onset.

The service was up and correct throughout. It was simply blocked ~300ms per call, which is why the alerts fired on latency and not on errors.

> Evidence `tr_6aaaaa80dd6a`:

```
<tool_result id="tr_6aaaaa80dd6a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T16:28:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" radius="seed" hops="0">
service: cartservice
5 changes, ranked by suspicion
  #1  3m before onset  2026-09-02T16:24:37.005358+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  2.8h before onset  2026-09-02T13:42:04.682894+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_97be6bef850b`:

```
<tool_result id="tr_97be6bef850b" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-02T15:28:00.583000+00:00..2026-09-02T16:29:52.828488+00:00">
service: cartservice
200 spans
  0959dd3fe1c54682 checkoutservice/hipstershop.CheckoutService/PlaceOrder 2462.3ms
  0959dd3fe1c54682 checkoutservice/prepareOrderItemsAndShippingQuoteFromCart 1241.5ms
  0959dd3fe1c54682 checkoutservice/hipstershop.CartService/GetCart 1209.4ms
```

## Fix and what remains unverified

Fix class is a config revert: remove the shaping rule from the pod's network namespace.

Open items, in rough order of how much they'd bother me on the next call:

Whether the rule is still active. Nobody checked the pod's current queueing discipline state or whether the container was detached. Trace and log coverage stops at the window edge, so persistence is unverified.

Whether this was an authorized experiment. The change record attributes all five entries in the window to a platform-automation actor with no human-initiated change recorded — which is why an ad-hoc human change was ruled out — but it names no owning experiment or ticket, and that record came from an untrusted source with no corroborating dispatch.

cartservice's own error and saturation behaviour at onset is genuinely unmeasured, for the two reasons described above: the metric series was empty in both windows and the log query dropped the relevant minute.

Exact onset inside the pod is not pinned, since no pre-onset spans were captured.

The declared radius named twelve services, but only cartservice, checkoutservice and frontend were examined. Whether loadgenerator or the remaining services saw anything beyond inherited waiting is unestablished.

User-facing severity is unquantified. No frontend latency percentiles or per-route data were returned, so we cannot say whether any client-side timeout budget was breached despite zero server-side errors.

> Evidence `tr_6aaaaa80dd6a`:

```
<tool_result id="tr_6aaaaa80dd6a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-01T16:28:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" radius="seed" hops="0">
service: cartservice
5 changes, ranked by suspicion
  #1  3m before onset  2026-09-02T16:24:37.005358+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  2.8h before onset  2026-09-02T13:42:04.682894+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_4d25d6568bf2`:

```
<tool_result id="tr_4d25d6568bf2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" template="error-ratio" baseline="2026-09-02T15:26:08.337512+00:00..2026-09-02T15:58:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_bd15542f04f8`:

```
<tool_result id="tr_bd15542f04f8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-02T16:18:07.587820+00:00  GetCartAsync called with userId=
2026-09-02T16:18:09.238055+00:00  GetCartAsync called with userId=
2026-09-02T16:18:09.894056+00:00  AddItemAsync called with userId=e371c5ac-a6e9-11f1-ae7b-9eef0fcf8acb, productId=66VCHSJNUP, quantity=1
2026-09-02T16:18:09.896684+00:00  GetCartAsync called with userId=e371c5ac-a6e9-11f1-ae7b-9eef0fcf8acb
```

> Evidence `tr_daef75001ab0`:

```
<tool_result id="tr_daef75001ab0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-02T15:58:00.583000+00:00..2026-09-02T16:29:52.828488+00:00" template="error-ratio" baseline="2026-09-02T15:26:08.337512+00:00..2026-09-02T15:58:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=47 mean=0 min=0 max=0 sd=0
  baseline window: n=9 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_97be6bef850b`:

```
<tool_result id="tr_97be6bef850b" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-02T15:28:00.583000+00:00..2026-09-02T16:29:52.828488+00:00">
service: cartservice
200 spans
  0959dd3fe1c54682 checkoutservice/hipstershop.CheckoutService/PlaceOrder 2462.3ms
  0959dd3fe1c54682 checkoutservice/prepareOrderItemsAndShippingQuoteFromCart 1241.5ms
  0959dd3fe1c54682 checkoutservice/hipstershop.CartService/GetCart 1209.4ms
```
