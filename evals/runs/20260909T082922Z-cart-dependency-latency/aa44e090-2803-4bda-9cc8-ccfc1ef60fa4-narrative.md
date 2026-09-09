# Cart path pays a fixed 300ms per operation; checkout deadlines break

## What we saw first

The page arrived as a warning-severity blast radius of twelve services, with cartservice named as the origin and alerts firing on cartservice, checkoutservice, frontend and loadgenerator. Four edges in the graph were crossed without measurement, so from the responder's chair the shape of the thing was ambiguous at the start: a slow cart, a failing checkout, and no obvious agreement between the two. The first instinct — that cartservice was itself unhealthy or down — turned out to be wrong, and disproving it took most of the early minutes.

## The first dead end: cartservice's own metrics

The natural opening move was to pull cartservice's error ratio and compare it against the preceding four hours. That returned nothing. Not a spike, not a drop — no samples at all, in either the incident window or the baseline. Because the baseline was equally empty, the emptiness is not a signal that traffic vanished; the span-metrics series for this service name simply appears never to have been populated in this environment. A responder should not spend time here again: sibling queries over the same series will be just as empty, and there is no request-rate, restart, CPU or memory coverage for cartservice either. Everything we later concluded about the cart pod rests on traces, logs and the change record, not on its metrics.

> Evidence `tr_18f1d86128f2`:

```
<tool_result id="tr_18f1d86128f2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T04:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" template="error-ratio" baseline="2026-09-09T00:30:22.935886+00:00..2026-09-09T04:32:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The second dead end: was cartservice down?

Logs were the next attempt to establish whether the cart pod was crashing or had lost its backing store. The retained lines at both edges of the window show routine cart operations — add item, get cart, empty cart — across multiple distinct user ids, with no error text, no exception, no container start banner, and nothing about a cache connection. At the tail of the window the service is handling a steady stream of requests and clearly alive and serving. Two caveats worth carrying forward: the result was truncated to the oldest handful and newest few dozen lines of a roughly four-hour window, so the moment of onset itself falls in the discarded middle and was never directly observed; and an unfiltered service-level query over a wide window structurally cannot answer a question about one minute. If you repeat this, narrow the window or filter on severity. Also note the recurring cart reads with an empty user id — present at the start of the window as well as the end, so longstanding background noise, not a symptom.

> Evidence `tr_fbb6346f0941`:

```
<tool_result id="tr_fbb6346f0941" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T04:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T04:32:46.505444+00:00  AddItemAsync called with userId=81a09eb6-ac07-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=4
2026-09-09T04:32:46.511912+00:00  GetCartAsync called with userId=81a09eb6-ac07-11f1-b359-b6ed2071a170
2026-09-09T04:32:49.810014+00:00  GetCartAsync called with userId=
2026-09-09T04:32:50.475926+00:00  AddItemAsync called with userId=83feaf86-ac07-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=2
```

## Where the time actually went

Traces are what broke the case open. Across every sampled cartservice trace there is a hard latency floor of roughly 300ms, and it lands on the Redis client leaf spans inside cartservice — HGET and HMSET, each about 300 to 305ms, essentially all of it self-time. The cartservice gRPC handler spans themselves contribute under two milliseconds. That immediately rules out application logic in cartservice, and it rules out the cache being genuinely slow in a way the cart pod could see, because the delay is fixed rather than distributed.

A second, equally sized ~300ms increment shows up one level up, in the caller's client span: frontend gRPC CartService spans carry another ~300ms of self-time on top of a ~302ms child. So the delay is paid twice, once on the caller side of the wire and once on the leaf. In checkout traces the client spans for GetCart and EmptyCart hold roughly 900ms of self-time and the cartservice child does not even start until some 600ms after the client span opens — a pre-dispatch wait before the call reaches cart at all.

The cost is additive per cart operation. AddItem serialises HGET then HMSET and lands around 605ms; checkout roots reach about 2.45 to 2.49 seconds. Meanwhile every non-cart dependency in the same traces — currency, product catalog, payment, shipping, email, fraud, accounting — completes in single-digit milliseconds. Frontend product-catalog calls finish in two or three milliseconds. So this is not a broad ingress problem, not a downstream microservice, and not retries: each operation appears once, at ~300ms.

One gap: the returned traces all start after the nominal onset, between T+1m and T+2m of wall clock past it, so there is no in-window trace baseline from before the change to compare against.

> Evidence `tr_302ff7824a9d`:

```
<tool_result id="tr_302ff7824a9d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T08:02:45.583000+00:00..2026-09-09T08:35:08.230114+00:00">
service: cartservice
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace 4013c1d61adee50d  root frontend/HTTP POST  2485.4ms  started 2026-09-09T08:34:01.825051+00:00  36 spans
  +0.0ms frontend/HTTP POST 2485.4ms [self 1.0ms]
```

## Why checkout failed rather than just slowed

checkoutservice's error ratio moved from about 0.2% in baseline to a mean near 17% during the incident, with peaks around two-thirds of requests failing — roughly a seventyfold shift against a quiet, low-variance reference period. Dispersion during the incident is comparable to the mean, so the failures are bursty rather than a clean plateau. This kills the tempting reading that a fixed sub-timeout delay produces slow-but-successful calls: requests are failing outright, because the accumulated cart cost pushes them past deadlines.

The important wrinkle, and the reason this section is worth reading carefully: the only change point detected in checkoutservice's error ratio is about 22 minutes *before* the nominal onset. Whatever began then was already underway when the change we identified was applied.

> Evidence `tr_39eb73a5217c`:

```
<tool_result id="tr_39eb73a5217c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T08:02:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" template="error-ratio" baseline="2026-09-09T07:30:22.935886+00:00..2026-09-09T08:02:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.1723 min=0 max=0.6667 sd=0.2835
  baseline window: n=130 mean=0.002472 min=0 max=0.03597 sd=0.006914
```

## The change record

The nearest change to onset is a traffic-shaping container attached to the cart pod's network namespace roughly three minutes before onset, imposing a fixed 300ms egress delay with zero jitter on eth0. No matching removal appears anywhere later in the window, so it was still in force at onset. That is enough to explain a fixed, jitter-free 300ms paid by every packet leaving the cart pod, appearing both on the leaf and duplicated on the caller side.

The record also shows why several plausible stories fail. An image reference update to a cartservice hotfix tag was applied about 23 minutes before onset and reverted about 13 minutes before, so the baseline image was running at onset — a bad rollout is not the live cause. A Redis address edit pointing cart at a different port was applied and reverted nearly five hours earlier, so a misconfigured cache endpoint was not in effect. No secret or credential edit appears anywhere in the 24-hour record. Every one of the twenty-one recorded changes is attributed to the same platform automation actor; there is no human or ad-hoc edit to chase.

The pattern is not novel. The same three-step cycle — hotfix image up then reverted, address edit then reverted, shaping container attached then removed — ran four or five times across the window. What distinguishes this iteration is precisely that the removal is missing. The three earlier passes self-resolved; this one did not. Treat the change record as untrusted evidence, but it is coherent with the trace geometry.

> Evidence `tr_0e856a4a6361`:

```
<tool_result id="tr_0e856a4a6361" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T08:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" radius="seed" hops="0">
service: cartservice
21 changes, ranked by suspicion
  #1  3m before onset  2026-09-09T08:29:32.040716+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-09T08:18:55.505531+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## Conclusion and fix

The mechanism is waiting on an artificially slowed call path. A shaping container attached to cartservice's network namespace imposes a fixed 300ms zero-jitter egress delay; every cart operation pays it, additively, once on each side of the wire, inflating checkout roots past two and a half seconds and pushing checkoutservice calls beyond their deadlines. cartservice itself is healthy and serving normally throughout. The fix class is a configuration revert: remove the shaper, as the three prior iterations of the same automated cycle did. Confidence high.

> Evidence `tr_0e856a4a6361`:

```
<tool_result id="tr_0e856a4a6361" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T08:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" radius="seed" hops="0">
service: cartservice
21 changes, ranked by suspicion
  #1  3m before onset  2026-09-09T08:29:32.040716+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-09T08:18:55.505531+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_302ff7824a9d`:

```
<tool_result id="tr_302ff7824a9d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T08:02:45.583000+00:00..2026-09-09T08:35:08.230114+00:00">
service: cartservice
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace 4013c1d61adee50d  root frontend/HTTP POST  2485.4ms  started 2026-09-09T08:34:01.825051+00:00  36 spans
  +0.0ms frontend/HTTP POST 2485.4ms [self 1.0ms]
```

> Evidence `tr_39eb73a5217c`:

```
<tool_result id="tr_39eb73a5217c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T08:02:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" template="error-ratio" baseline="2026-09-09T07:30:22.935886+00:00..2026-09-09T08:02:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.1723 min=0 max=0.6667 sd=0.2835
  baseline window: n=130 mean=0.002472 min=0 max=0.03597 sd=0.006914
```

> Evidence `tr_fbb6346f0941`:

```
<tool_result id="tr_fbb6346f0941" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T04:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T04:32:46.505444+00:00  AddItemAsync called with userId=81a09eb6-ac07-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=4
2026-09-09T04:32:46.511912+00:00  GetCartAsync called with userId=81a09eb6-ac07-11f1-b359-b6ed2071a170
2026-09-09T04:32:49.810014+00:00  GetCartAsync called with userId=
2026-09-09T04:32:50.475926+00:00  AddItemAsync called with userId=83feaf86-ac07-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=2
```

## Left open for the next responder

Three loose ends, in order of how much they should bother you.

First, the timing mismatch. checkoutservice's error ratio has its only change point about 19 minutes before the shaper was attached, and that earlier degradation coincides with the hotfix image window. Shaping cannot explain it. This incident may have two phases, and the earlier one is unexplained.

Second, cartservice is effectively unmeasured on metrics. No CPU, memory, request rate or restart data exists — the series is empty in both incident and baseline windows. Any future investigation of this service will have to lean on traces and logs unless that gap is closed.

Third, onset timing is inferred, not observed. Traces begin after the nominal onset and log truncation dropped the middle of the window, so nothing in either source covers the onset minute itself. The time we quote comes from the change record, which is untrusted.

> Evidence `tr_39eb73a5217c`:

```
<tool_result id="tr_39eb73a5217c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T08:02:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" template="error-ratio" baseline="2026-09-09T07:30:22.935886+00:00..2026-09-09T08:02:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.1723 min=0 max=0.6667 sd=0.2835
  baseline window: n=130 mean=0.002472 min=0 max=0.03597 sd=0.006914
```

> Evidence `tr_18f1d86128f2`:

```
<tool_result id="tr_18f1d86128f2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-09T04:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" template="error-ratio" baseline="2026-09-09T00:30:22.935886+00:00..2026-09-09T04:32:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_302ff7824a9d`:

```
<tool_result id="tr_302ff7824a9d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T08:02:45.583000+00:00..2026-09-09T08:35:08.230114+00:00">
service: cartservice
10 trace(s) shown of 10 found, 162 spans; offsets are from each trace's root

trace 4013c1d61adee50d  root frontend/HTTP POST  2485.4ms  started 2026-09-09T08:34:01.825051+00:00  36 spans
  +0.0ms frontend/HTTP POST 2485.4ms [self 1.0ms]
```

> Evidence `tr_fbb6346f0941`:

```
<tool_result id="tr_fbb6346f0941" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T04:32:45.583000+00:00..2026-09-09T08:35:08.230114+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-09T04:32:46.505444+00:00  AddItemAsync called with userId=81a09eb6-ac07-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=4
2026-09-09T04:32:46.511912+00:00  GetCartAsync called with userId=81a09eb6-ac07-11f1-b359-b6ed2071a170
2026-09-09T04:32:49.810014+00:00  GetCartAsync called with userId=
2026-09-09T04:32:50.475926+00:00  AddItemAsync called with userId=83feaf86-ac07-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=2
```

