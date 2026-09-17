# Cart path latency step cascading to checkout and frontend

## What we saw first

The page named four services: cartservice, checkoutservice, frontend, and loadgenerator. Blast radius counted twelve services, severity warning, with cartservice nominated as the origin. Four edges in the graph were unmeasured, so part of the picture was inference from the start.

The first useful shape came from traces rather than dashboards. Whole carts-path traces sat at a few milliseconds up to roughly T-3m30s (last clean trace, 5.9ms). By T-2m the same path was taking 1526.7ms. That bracket — clean, then more than a thousand milliseconds — was the tightest onset boundary we obtained anywhere, and it was tighter than any metric could give us.

> Evidence `tr_7a16a78fc77e`:

```
<tool_result id="tr_7a16a78fc77e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00">
service: cartservice
15 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 161dacf8ee7b6d81  root frontend/HTTP POST  32.8ms  started 2026-09-17T21:06:00.905012+00:00  36 spans
  +0.0ms frontend/HTTP POST 32.8ms [self 0.4ms]
```

## The shape of the added time

Every cartservice Redis client span from T-2m onward carried about 300ms of self time. The observed values clustered between 300.6ms and 310.3ms — a few milliseconds of spread and no long tail. That distribution matters: queueing or contention produces a tail, a fixed additive offset does not.

The penalty repeated once per outbound operation. AddItem, which issues two Redis calls in sequence, showed a handler span of roughly 604ms; single-operation GetCart and EmptyCart handlers landed at 301-306ms. Meanwhile cartservice's own in-process work was untouched: handler self time stayed at 0.5-1.1ms in the slow traces, identical to baseline. All of the added time lived in spans representing calls leaving the process.

Non-cart dependencies in the same slow traces were at baseline throughout — currencyservice 2.4-4.2ms, productcatalogservice 0-3.0ms, paymentservice 0.4ms, emailservice 6-9ms, shippingservice 17-22ms. Total trace inflation of 1513-2494ms was fully accounted for by repeated cart-path increments. Callers inherited the same fixed step per cart RPC: frontend's cart RPCs showed ~302-305ms of self time, checkoutservice's showed ~905-910ms, consistent with waiting on cart calls until deadlines expired.

> Evidence `tr_7a16a78fc77e`:

```
<tool_result id="tr_7a16a78fc77e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00">
service: cartservice
15 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 161dacf8ee7b6d81  root frontend/HTTP POST  32.8ms  started 2026-09-17T21:06:00.905012+00:00  36 spans
  +0.0ms frontend/HTTP POST 32.8ms [self 0.4ms]
```

## The change that lines up

The change log for cartservice held 29 entries, all attributed to platform-automation, cycling roughly every four hours over the preceding eighteen hours through a consistent sequence: image update, image revert, traffic-shaping attach, traffic-shaping remove, environment edit, environment revert.

The entry closest to onset — about T-3m — attached a traffic-shaping container to cart-service's network namespace, applying a fixed 300ms egress delay with zero jitter on eth0. It was still in place at onset with no matching removal recorded afterward. The magnitude, the absence of jitter, and the per-outbound-operation recurrence all match the trace evidence exactly.

> Evidence `tr_260016376ca5`:

```
<tool_result id="tr_260016376ca5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T21:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" radius="seed" hops="0">
service: cartservice
29 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T21:10:07.237282+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T20:59:30.055223+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_7a16a78fc77e`:

```
<tool_result id="tr_7a16a78fc77e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00">
service: cartservice
15 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 161dacf8ee7b6d81  root frontend/HTTP POST  32.8ms  started 2026-09-17T21:06:00.905012+00:00  36 spans
  +0.0ms frontend/HTTP POST 32.8ms [self 0.4ms]
```

## Dead ends, in the order we walked them

An image tag change. A cartservice hotfix image had been applied roughly T-22m and reverted roughly T-14m. It was tempting because it was recent and it was a deploy. It was not running at onset, so it is not the cause.

A Redis address. An environment edit pointing cartservice at a non-default Redis port existed in the history, which would have been a clean story for cache trouble. It was reverted about 3.2 hours before onset and no later environment edit landed.

A human operator. Every recorded change in the window was automation. There was nothing ad hoc to find.

Scaling or resource limits. No scaling, replica-count, or resource-limit changes appear among the 29 entries; they are confined to image references, one environment variable, and traffic-shaping containers.

cartservice's own code or CPU. Ruled out by self time staying sub-2ms in affected traces.

cartservice crashing. The logs we could see showed dense, ordinary cart operations at both ends of the window with no restart banner, no exception, no connection failure, and no deadline wording. The service was serving normally at window close.

A red herring worth naming: several cart reads carry an empty user identifier. This appears in both the earliest and latest retained log lines, so it is routine and not a symptom.

> Evidence `tr_260016376ca5`:

```
<tool_result id="tr_260016376ca5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T21:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" radius="seed" hops="0">
service: cartservice
29 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T21:10:07.237282+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T20:59:30.055223+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_7a16a78fc77e`:

```
<tool_result id="tr_7a16a78fc77e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00">
service: cartservice
15 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 161dacf8ee7b6d81  root frontend/HTTP POST  32.8ms  started 2026-09-17T21:06:00.905012+00:00  36 spans
  +0.0ms frontend/HTTP POST 32.8ms [self 0.4ms]
```

> Evidence `tr_ece83ebae4c4`:

```
<tool_result id="tr_ece83ebae4c4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T20:43:34.182234+00:00  GetCartAsync called with userId=
2026-09-17T20:43:35.298656+00:00  AddItemAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=1
2026-09-17T20:43:35.301553+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
2026-09-17T20:43:35.313595+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
```

> Evidence `tr_de1a3b1a5524`:

```
<tool_result id="tr_de1a3b1a5524" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T20:43:34.182234+00:00  GetCartAsync called with userId=
2026-09-17T20:43:35.298656+00:00  AddItemAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=1
2026-09-17T20:43:35.301553+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
2026-09-17T20:43:35.313595+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
```

## Where the instruments failed us

Two things cost real time and should be fixed before the next one.

First, cartservice has no request, error, or latency metrics at all. The templated error-ratio query returned nothing for the incident window and nothing for the four-hour baseline either. The emptiness is symmetric, which is what told us it was a data-availability problem — no matching calls_total series — rather than traffic stopping at onset. The consequence is that the entire cart-side picture rests on roughly 30 sampled traces. Pod restart and readiness counts were never covered by that query and remain unanswered from this source.

Second, both log queries were truncated to the oldest eight and newest thirty-two lines, dropping everything between roughly T-30m and T+2m. The onset neighbourhood is simply unobserved in logs. Crucially, that gap also means no removal of the shaping rule is recorded anywhere; we do not know when or whether it came off. Any claim of log silence at onset is a truncation artifact, not evidence.

> Evidence `tr_ffcabdbd7c2d`:

```
<tool_result id="tr_ffcabdbd7c2d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T17:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" template="error-ratio" baseline="2026-09-17T13:11:16.658749+00:00..2026-09-17T17:13:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ece83ebae4c4`:

```
<tool_result id="tr_ece83ebae4c4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T20:43:34.182234+00:00  GetCartAsync called with userId=
2026-09-17T20:43:35.298656+00:00  AddItemAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=1
2026-09-17T20:43:35.301553+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
2026-09-17T20:43:35.313595+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
```

> Evidence `tr_de1a3b1a5524`:

```
<tool_result id="tr_de1a3b1a5524" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T20:43:34.182234+00:00  GetCartAsync called with userId=
2026-09-17T20:43:35.298656+00:00  AddItemAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=1
2026-09-17T20:43:35.301553+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
2026-09-17T20:43:35.313595+00:00  GetCartAsync called with userId=73eba572-b2d8-11f1-b359-b6ed2071a170
```

> Evidence `tr_260016376ca5`:

```
<tool_result id="tr_260016376ca5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T21:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" radius="seed" hops="0">
service: cartservice
29 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T21:10:07.237282+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T20:59:30.055223+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## The residual we did not close

checkoutservice's error ratio moved from a baseline mean near 0.2% to 15.6% across the window, a ~74.5x shift, with peaks where two-thirds of requests failed. Errors were bursty, not sustained — the ratio still touched zero and its standard deviation (0.27) exceeded its mean (0.16) — so this was partial failure, not an outage. The 32-minute baseline immediately prior was healthy, so this is not a long-running condition that merely became visible.

But the detected change point puts checkout error onset at about T-21m — roughly eighteen minutes before the shaping container existed. That is the largest unexplained piece of this record. Either a second, earlier condition was in play, or the change-point detector latched onto an earlier burst in a noisy series. We could not distinguish these. Note also that this query returned error ratio only; there are no p95/p99 figures here, so the ~300ms step cannot be confirmed or denied from checkout metrics.

A responder picking this up should treat the checkout timing as open, not settled.

> Evidence `tr_3148065f7a49`:

```
<tool_result id="tr_3148065f7a49" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" template="error-ratio" baseline="2026-09-17T20:11:16.658749+00:00..2026-09-17T20:43:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1562 min=0 max=0.6667 sd=0.2747
  baseline window: n=129 mean=0.002097 min=0 max=0.05172 sd=0.008385
```

> Evidence `tr_260016376ca5`:

```
<tool_result id="tr_260016376ca5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T21:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" radius="seed" hops="0">
service: cartservice
29 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T21:10:07.237282+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T20:59:30.055223+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## Conclusion and confidence

The failing mechanism is delay introduced into a call path, not a semantically wrong value and not a wrong artifact. A fixed 300ms egress delay with no jitter was applied at cartservice's network namespace about three minutes before onset and was still present at onset. Traces corroborate the magnitude, the lack of spread, and the once-per-outbound-operation recurrence. Callers degraded by blocking on cart RPCs until their deadlines expired.

Confidence: medium. The mechanism is well supported by traces and by a timing-aligned change record, but cartservice has no metrics to cross-check against, the log record has a hole over the onset period, no removal of the change is recorded, and the checkout timing discrepancy is unresolved.

Fix class: revert the configuration — remove the traffic-shaping attachment and confirm removal. Independently, instrument cartservice so that calls_total exists under the expected service label, and stop issuing log queries that truncate the middle of the window.

> Evidence `tr_260016376ca5`:

```
<tool_result id="tr_260016376ca5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T21:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" radius="seed" hops="0">
service: cartservice
29 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T21:10:07.237282+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T20:59:30.055223+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_7a16a78fc77e`:

```
<tool_result id="tr_7a16a78fc77e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00">
service: cartservice
15 trace(s) shown of 30 found, 200 spans; offsets are from each trace's root

trace 161dacf8ee7b6d81  root frontend/HTTP POST  32.8ms  started 2026-09-17T21:06:00.905012+00:00  36 spans
  +0.0ms frontend/HTTP POST 32.8ms [self 0.4ms]
```

> Evidence `tr_ffcabdbd7c2d`:

```
<tool_result id="tr_ffcabdbd7c2d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T17:13:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" template="error-ratio" baseline="2026-09-17T13:11:16.658749+00:00..2026-09-17T17:13:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3148065f7a49`:

```
<tool_result id="tr_3148065f7a49" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:43:30.583000+00:00..2026-09-17T21:15:44.507251+00:00" template="error-ratio" baseline="2026-09-17T20:11:16.658749+00:00..2026-09-17T20:43:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1562 min=0 max=0.6667 sd=0.2747
  baseline window: n=129 mean=0.002097 min=0 max=0.05172 sd=0.008385
```

