# Cart path slowdown traced to egress delay on cartservice's interface

## What the responder saw first

The page arrived as a warning-severity event with cartservice named as the origin and a blast radius of twelve services. Four of those had their own alerts firing: cartservice, frontend, loadgenerator and checkoutservice. Four edges in the dependency map were crossed without measurement, so the early picture was a wide fan-out with no obvious broken component in the middle of it. Nothing in the alert set suggested an outage: no service was reported down, and checkout traffic was still flowing.

> Evidence `tr_8cd345d44250`:

```
<tool_result id="tr_8cd345d44250" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T04:17:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" template="error-ratio" baseline="2026-09-17T03:45:14.315130+00:00..2026-09-17T04:17:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=130 mean=0.08711 min=0 max=0.475 sd=0.1375
  baseline window: n=130 mean=0.02803 min=0 max=0.1013 sd=0.03494
```

## Ruling out the obvious: cartservice health

The first instinct was that cartservice had crashed, restarted, or was crash-looping behind a load balancer. The log stream said otherwise. Under the service="cart-service" selector, lines were present at both ends of the window at a steady several-per-second cadence, running continuously through the final second at T+2m, all of them routine handler entries for add-item, get-cart and empty-cart. No panics, no stack traces, no startup banners, no dependency-connection errors. A batch of get-cart calls with an empty user identifier looked suspicious until the same pattern showed up in the oldest retained lines too, which made it baseline noise rather than a signal.

One important caveat for anyone re-running this: the log result was truncated to the oldest eight and newest thirty-two lines. The minutes immediately around onset were never actually returned. Two separate queries, one over four hours and one over the last half hour, both truncated the same way, so onset itself is not covered by log evidence. What the logs do establish is that the process was alive and serving normally at both window open and window close.

> Evidence `tr_eb19ac22327d`:

```
<tool_result id="tr_eb19ac22327d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T01:07:55.755898+00:00  AddItemAsync called with userId=3712082a-b234-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=4
2026-09-17T01:07:55.758458+00:00  GetCartAsync called with userId=3712082a-b234-11f1-b359-b6ed2071a170
2026-09-17T01:07:56.335344+00:00  GetCartAsync called with userId=
2026-09-17T01:07:58.806912+00:00  GetCartAsync called with userId=
```

> Evidence `tr_8ae72b281f61`:

```
<tool_result id="tr_8ae72b281f61" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T04:17:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T04:17:33.397843+00:00  AddItemAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=1
2026-09-17T04:17:33.400029+00:00  GetCartAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170
2026-09-17T04:17:33.409576+00:00  GetCartAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170
2026-09-17T04:17:33.428129+00:00  EmptyCartAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170
```

## A metrics dead end

The natural next move was to pull cartservice's error ratio from span-metrics in Prometheus. It returned nothing — no samples in the incident window and none in the four-hour baseline either. The empty baseline is what saved time here: had only the incident window been blank, it would have read as traffic stopping at onset. Because both are equally empty, the series simply was never populated for this service, most likely missing or mislabelled instrumentation. This source cannot confirm or deny inbound traffic, error rate, or latency percentiles for cartservice, and cart-side error rate remains unobserved.

> Evidence `tr_f0b0f3d1b9e8`:

```
<tool_result id="tr_f0b0f3d1b9e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" template="error-ratio" baseline="2026-09-16T20:45:14.315130+00:00..2026-09-17T00:47:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Traces: where the time actually went

Traces are what broke the case open. Samples taken before onset, at roughly T-2h and T-1h50m, show cartservice server spans of 0.2-5.7ms with Redis children of 0.2-5.1ms — entirely normal. Samples from T+2m onward are elevated, and the shape of the elevation is the clue. GetCart (one HGET) and EmptyCart (one HMSET) each land around 302-307ms. AddItem, which issues HGET then HMSET in sequence, lands around 603ms. The penalty scales per Redis round trip, not per request.

This killed the theory of a fixed per-request penalty such as an added handshake or admission delay, which would have made all three endpoints roughly equal. It also killed the idea of cartservice burning CPU: self-time excluding Redis children stayed sub-millisecond, 0.3-1.1ms, in the slow traces. A read-path story — cold cache, key scan — didn't survive either, since HMSET writes were delayed by the same quantum as HGET reads.

The same increment appeared above cartservice: frontend gRPC GetCart/AddItem spans and checkoutservice's CartService client spans each carried roughly 302ms beyond the server span they wrapped, with checkoutservice showing 904-907ms of self-time around ~302ms server spans. So the client hop in was delayed as well as the work inside. A shared platform-wide problem was ruled out by the same slow checkout trace: currencyservice and productcatalogservice were effectively zero, paymentservice 0.4ms, shippingservice GetQuote ~16ms, emailservice ~6ms. The 2.47s root latency was almost entirely the two cart hops. Checkoutservice was briefly a suspect on the strength of its ~1.2s client spans, but those are wait time on cart, not its own work.

> Evidence `tr_f503592247fe`:

```
<tool_result id="tr_f503592247fe" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00">
service: cartservice
17 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace ce2e21cbdfb96ce8  root frontend/HTTP POST  31.1ms  started 2026-09-17T02:38:12.306019+00:00  36 spans
  +0.0ms frontend/HTTP POST 31.1ms [self 0.4ms]
```

## The change that fits

Five changes landed on cartservice inside the window, all of them attributed to platform-automation rather than any individual operator. Four were two identical image-reference update/revert pairs for the same hotfix tag — one pair about 1.2 hours before onset, one pair 13-24 minutes before. Both cycles completed and returned to the prior value, so the image reference at onset matched the pre-window baseline. This is the most seductive dead end in the record: repeated deploy-and-rollback churn immediately before an incident reads like a failed rollout, and it isn't one. The hotfix image was not the active reference when latency appeared.

The fifth change, about three minutes before onset, is the one that matches the trace evidence: platform-automation attached a traffic-shaping container to cartservice's network namespace, configuring a fixed 300ms egress delay with zero jitter on eth0. Applied at namespace level, that penalty lands on every packet leaving the interface — each Redis round trip and each gRPC response — which is exactly the per-round-trip quantum the traces measure, and exactly why the delay is flat rather than bursty. Notably, the change history for this window contains no configuration or environment-variable edits at all; only container creation and image reference events.

> Evidence `tr_3a465198ab35`:

```
<tool_result id="tr_3a465198ab35" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T04:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" radius="seed" hops="0">
service: cartservice
5 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T04:44:13.066469+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-17T04:33:36.812523+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_f503592247fe`:

```
<tool_result id="tr_f503592247fe" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00">
service: cartservice
17 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace ce2e21cbdfb96ce8  root frontend/HTTP POST  31.1ms  started 2026-09-17T02:38:12.306019+00:00  36 spans
  +0.0ms frontend/HTTP POST 31.1ms [self 0.4ms]
```

## Why frontend and checkoutservice alerted

Both alerted because they block on inflated cart hops, not because of anything wrong in their own code paths. frontend's error ratio rose about 3.1x between baseline and incident windows, roughly 2.8% to 8.7% mean with a peak near 47.5%. It was not a total outage — the minimum was zero and most requests still succeeded — and variance was around four times baseline, so failure was bursty rather than uniform. The series is aggregated by service name with no dependency dimension, so no cart-specific attribution is possible from it.

> Evidence `tr_8cd345d44250`:

```
<tool_result id="tr_8cd345d44250" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T04:17:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" template="error-ratio" baseline="2026-09-17T03:45:14.315130+00:00..2026-09-17T04:17:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=130 mean=0.08711 min=0 max=0.475 sd=0.1375
  baseline window: n=130 mean=0.02803 min=0 max=0.1013 sd=0.03494
```

> Evidence `tr_f503592247fe`:

```
<tool_result id="tr_f503592247fe" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00">
service: cartservice
17 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace ce2e21cbdfb96ce8  root frontend/HTTP POST  31.1ms  started 2026-09-17T02:38:12.306019+00:00  36 spans
  +0.0ms frontend/HTTP POST 31.1ms [self 0.4ms]
```

## Conclusion and fix class

The cause is the 300ms fixed egress delay attached to cartservice's network namespace roughly three minutes before onset. Remedy class is a configuration revert: detach the shaping container and restore the interface to its prior state. Confidence is medium — the mechanism and the measured quantum agree closely, but onset is not directly pinned to the change (see below).

> Evidence `tr_3a465198ab35`:

```
<tool_result id="tr_3a465198ab35" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T04:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" radius="seed" hops="0">
service: cartservice
5 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T04:44:13.066469+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-17T04:33:36.812523+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_f503592247fe`:

```
<tool_result id="tr_f503592247fe" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00">
service: cartservice
17 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace ce2e21cbdfb96ce8  root frontend/HTTP POST  31.1ms  started 2026-09-17T02:38:12.306019+00:00  36 spans
  +0.0ms frontend/HTTP POST 31.1ms [self 0.4ms]
```

## Left open for the next responder

Four loose ends, in rough order of how much they should bother you.

First, frontend's error-ratio change point sits at T-22m, roughly nineteen minutes before the shaping container was created. That earlier elevation is unexplained and may be a separate concurrent problem; do not assume it belongs to this record.

Second, no trace samples exist between T-1h48m and T+2m. Latency onset is bracketed only to that interval and is therefore not itself pinned to the change; the correlation rests on the size and shape of the delay matching, not on timing precision.

Third, log truncation left the minutes around onset uncovered. A narrower time range on the cart-service stream should surface any error-level companions to the handler entries.

Fourth, cartservice span-metrics are empty in both windows, so cart-side error rate is simply unobserved. And nobody established whether the shaping container is still attached, or why automation created it in the first place — that second question is the one that prevents a recurrence.

> Evidence `tr_8cd345d44250`:

```
<tool_result id="tr_8cd345d44250" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T04:17:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" template="error-ratio" baseline="2026-09-17T03:45:14.315130+00:00..2026-09-17T04:17:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=130 mean=0.08711 min=0 max=0.475 sd=0.1375
  baseline window: n=130 mean=0.02803 min=0 max=0.1013 sd=0.03494
```

> Evidence `tr_f503592247fe`:

```
<tool_result id="tr_f503592247fe" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00">
service: cartservice
17 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace ce2e21cbdfb96ce8  root frontend/HTTP POST  31.1ms  started 2026-09-17T02:38:12.306019+00:00  36 spans
  +0.0ms frontend/HTTP POST 31.1ms [self 0.4ms]
```

> Evidence `tr_eb19ac22327d`:

```
<tool_result id="tr_eb19ac22327d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T01:07:55.755898+00:00  AddItemAsync called with userId=3712082a-b234-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=4
2026-09-17T01:07:55.758458+00:00  GetCartAsync called with userId=3712082a-b234-11f1-b359-b6ed2071a170
2026-09-17T01:07:56.335344+00:00  GetCartAsync called with userId=
2026-09-17T01:07:58.806912+00:00  GetCartAsync called with userId=
```

> Evidence `tr_8ae72b281f61`:

```
<tool_result id="tr_8ae72b281f61" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T04:17:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T04:17:33.397843+00:00  AddItemAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=1
2026-09-17T04:17:33.400029+00:00  GetCartAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170
2026-09-17T04:17:33.409576+00:00  GetCartAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170
2026-09-17T04:17:33.428129+00:00  EmptyCartAsync called with userId=b4ae308c-b24e-11f1-b359-b6ed2071a170
```

> Evidence `tr_f0b0f3d1b9e8`:

```
<tool_result id="tr_f0b0f3d1b9e8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T00:47:30.583000+00:00..2026-09-17T04:49:46.850870+00:00" template="error-ratio" baseline="2026-09-16T20:45:14.315130+00:00..2026-09-17T00:47:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

