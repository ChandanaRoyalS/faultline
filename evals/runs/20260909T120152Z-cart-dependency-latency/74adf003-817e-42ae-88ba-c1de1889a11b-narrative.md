# Cart cache calls pinned to a 300 ms floor; checkout deadlines blown

## What was visible, and the dead ends

The page arrived warning-severity with four services alerting together — cartservice, checkoutservice, frontend, loadgenerator — and a blast radius that eventually counted twelve services across four unmeasured edges. Starting point was cartservice, and the first question was whether it was broken or merely slow.

Logs said it was up. Only routine handler lines for cart operations, sub-second spacing continuing unbroken to the end of the window, no startup banner, no crash, no connection-refused, no dependency error. A crash-loop would have punched a hole in that and did not. One thing looked suspicious and was not: a fraction of requests are handled with an empty user identifier, but that pattern runs uniformly across the whole window, so it is steady state, not a signal. Coverage caveat — only the oldest handful and newest few dozen lines came back, so roughly the middle half-hour was never inspected.

The expensive dead end was cartservice metrics. The error-ratio query returned no samples at all, in either the incident or the baseline window. Because the emptiness is symmetric, it is not a service going dark at onset; the span-derived call counter simply isn't produced or scraped for this service name. It is readable neither as an error surge nor as onset-correlated telemetry loss, and with the denominator absent it cannot even separate zero traffic from zero instrumentation. Skip it and go to traces.

> Evidence `tr_425aee5c5bc0`:

```
<tool_result id="tr_425aee5c5bc0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T11:35:15.583000+00:00..2026-09-09T12:07:15.825805+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T11:35:17.779293+00:00  AddItemAsync called with userId=882addb0-ac42-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=2
2026-09-09T11:35:17.782020+00:00  GetCartAsync called with userId=882addb0-ac42-11f1-b359-b6ed2071a170
2026-09-09T11:35:17.945234+00:00  AddItemAsync called with userId=8844326a-ac42-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=1
2026-09-09T11:35:17.948053+00:00  GetCartAsync called with userId=8844326a-ac42-11f1-b359-b6ed2071a170
```

> Evidence `tr_eb93ab5d8384`:

```
<tool_result id="tr_eb93ab5d8384" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T11:35:15.583000+00:00..2026-09-09T12:07:15.825805+00:00" template="error-ratio" baseline="2026-09-09T11:03:15.340195+00:00..2026-09-09T11:35:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The trace sample, and how it reached checkout

Traces made the mechanism plain. Every cartservice Redis client span sits just above 300 ms with almost no spread — HGET and HMSET alike in a roughly 300.5-306 ms band across all ten traces. A floor, not a distribution. The cartservice handlers themselves do essentially nothing, 0.4-1.2 ms of self-time; their total duration is just the sum of their 300 ms children. The penalty is charged per call: frontend carries ~301-306 ms of self-time on its cart call, checkoutservice carries ~903-905 ms on each of GetCart and EmptyCart, and AddItem traces total ~1.51 s. Nothing amortizes.

That kills several stories. Not queueing — queueing gives a wide right-skewed tail with fast outliers, and the sample fits a 6 ms band. Not write-specific persistence stalls — read-only HGET pays the same. Not another downstream — in the checkout trace every non-cart dependency finishes in 0-14 ms while the 2.45 s root is two cart calls at ~1.21 s each. Limitation: all ten traces fall in a single 29-second slice at the tail of the window, so the floor is confirmed but its onset is not located.

Downstream, checkoutservice's error ratio moved from a ~1.7% baseline mean to ~18.2%, peaks at two-thirds of calls failing — deadlines exceeded. It never went quiet; every incident sample had a defined ratio, so upstream removal is ruled out. Failures are bursty (sd 0.29 against mean 0.18), consistent with a fixed added wait sitting close to a deadline.

> Evidence `tr_a7d576a32ef6`:

```
<tool_result id="tr_a7d576a32ef6" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T11:05:15.583000+00:00..2026-09-09T12:07:15.825805+00:00">
service: cartservice
10 trace(s) shown of 10 found, 91 spans; offsets are from each trace's root

trace 5ec60953ce6a8594  root frontend/HTTP POST  1514.5ms  started 2026-09-09T12:06:45.516013+00:00  8 spans
  +0.0ms frontend/HTTP POST 1514.5ms [self 0.8ms]
```

> Evidence `tr_6b7bfb1ca61f`:

```
<tool_result id="tr_6b7bfb1ca61f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T11:35:15.583000+00:00..2026-09-09T12:07:15.825805+00:00" template="error-ratio" baseline="2026-09-09T11:03:15.340195+00:00..2026-09-09T11:35:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1823 min=0 max=0.6667 sd=0.2906
  baseline window: n=128 mean=0.01746 min=0 max=0.2917 sd=0.06065
```

## The change, the conclusion, and what is still open

The change log holds 27 entries in the window, all from one automated actor, repeating a fixed cycle about every five hours. The entry that matters: a traffic-shaping sidecar attached to the cart-service network namespace ~3 minutes before onset, applying a 300 ms fixed egress delay with zero jitter on eth0, with no matching removal in the window — still in effect at incident time. Zero jitter predicts a flat floor, and a flat floor is what the traces show.

Ruled out from the same cycle: a cartservice hotfix image that landed ~23 minutes before onset but was reverted ~13 minutes before, leaving the prior binary running (and which had come and gone four times before without incident); and a cache-endpoint override applied and reverted ~3.2 hours before onset, consistent with cart reads and writes succeeding throughout. No human actor appears anywhere. Also wrong was the reflex that nothing changed on cartservice — the change was local to its own network namespace.

Conclusion: induced wait on a dependency call path, high confidence, fix by reverting the configuration. Still open, and read this before trusting the timeline: checkoutservice's only error change point is at 11:43, about nineteen minutes *before* the sidecar attached, so 12:02 is not the true onset and an earlier cycle or a separate contributing failure was never measured. Trace coverage spans only ~12:06:45-12:07:14 and logs drop from ~11:35 to 12:06:45, so onset was inferred from parameter match rather than observed. And no cartservice latency or request-rate series exists, nor was it verified whether the sidecar is still attached.

> Evidence `tr_cb602d1af2c1`:

```
<tool_result id="tr_cb602d1af2c1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T12:05:15.583000+00:00..2026-09-09T12:07:15.825805+00:00" radius="seed" hops="0">
service: cartservice
27 changes, ranked by suspicion
  #1  3m before onset  2026-09-09T12:02:01.548840+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-09T11:51:24.786029+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_6b7bfb1ca61f`:

```
<tool_result id="tr_6b7bfb1ca61f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T11:35:15.583000+00:00..2026-09-09T12:07:15.825805+00:00" template="error-ratio" baseline="2026-09-09T11:03:15.340195+00:00..2026-09-09T11:35:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1823 min=0 max=0.6667 sd=0.2906
  baseline window: n=128 mean=0.01746 min=0 max=0.2917 sd=0.06065
```

> Evidence `tr_eb93ab5d8384`:

```
<tool_result id="tr_eb93ab5d8384" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T11:35:15.583000+00:00..2026-09-09T12:07:15.825805+00:00" template="error-ratio" baseline="2026-09-09T11:03:15.340195+00:00..2026-09-09T11:35:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

