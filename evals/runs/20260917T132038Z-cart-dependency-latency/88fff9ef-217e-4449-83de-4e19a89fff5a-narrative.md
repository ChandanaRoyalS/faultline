# Cart path acquires a 300ms floor; slowdown propagates to checkout and frontend

## What was visible, and the two passes that yielded nothing

Four services paged within a minute: cartservice, checkoutservice, frontend and loadgenerator. Warning severity, nothing down. Blast radius reached twelve services across four unmeasured edges. cartservice sat innermost among the alerting set, so it was the starting point.

First move was an error-ratio comparison for cartservice against baseline. It came back empty — not zero, empty. No samples in the incident window and none in the baseline either. State this plainly, because it is the easiest mistake in the record: an empty series is not a flat zero, and the absence spanning the baseline rules out the other tempting reading, that the ratio vanished because cart stopped serving. The gap predates the incident and is a collection or label-matching problem in the span-derived call counter. Consequence for the reader: cartservice's error rate, request rate, latency, restarts and readiness were never measured here.

Logs were the second pass and were equally undramatic. The cart-service stream was populated across the whole window with only routine info lines — reads, adds, empties — no errors or warnings, dense and continuous through onset, no startup banner in the newest lines. That killed four candidates at once: no crash loop, no image-pull problem, no lost Redis connection, no silent service. A handful of cart reads with an empty user identifier appear at both ends of the window, so that is background, not a change. The service was healthy. It was slow, and slowness of this kind writes no log line.

> Evidence `tr_f413b29612b1`:

```
<tool_result id="tr_f413b29612b1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T12:54:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" template="error-ratio" baseline="2026-09-17T12:22:08.473290+00:00..2026-09-17T12:54:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_449b2234a1ed`:

```
<tool_result id="tr_449b2234a1ed" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:54:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T12:54:16.095850+00:00  GetCartAsync called with userId=
2026-09-17T12:54:23.323578+00:00  AddItemAsync called with userId=e808ffc8-b296-11f1-b359-b6ed2071a170, productId=9SIQT8TOJO, quantity=5
2026-09-17T12:54:23.327744+00:00  GetCartAsync called with userId=e808ffc8-b296-11f1-b359-b6ed2071a170
2026-09-17T12:54:23.340064+00:00  GetCartAsync called with userId=e808ffc8-b296-11f1-b359-b6ed2071a170
```

## Traces found the floor

Across ten traces and 188 spans, every Redis leaf out of cartservice — HGET, HMSET — landed between roughly 300.5ms and 311.6ms. Tight, almost no spread. The cartservice gRPC server spans wrapping them had 0.3–1.1ms self time, so cart's own compute was doing nothing and a CPU-bound or GC-stalled cartservice is excluded.

The penalty is not a bounded single offset. Each caller leg absorbs its own ~300ms: frontend client spans ~302–313ms self, checkout client spans ~900ms self with the cartservice child not starting until ~605ms in. Cart round trips compound to ~605ms up to ~1.21s, that last accounting for 49% of its trace. In the same traces, productcatalog, currency, shipping, payment, email, frauddetection and accounting were all sub-20ms and mostly sub-5ms — nothing systemic, the floor belongs to the cart path alone.

Upstream, checkoutservice's error ratio rose roughly seventyfold above a baseline whose maximum sat below the incident mean, with a single change point about six and a half minutes into the window. The errors were bursty — returning to zero at points, peaking near two-thirds, standard deviation above the mean — which excludes both a hard-down dependency and a smooth ramp, and fits deadline breaches on the slowest cart calls. Checkout's own logs show no error lines at all but per-order steps stretching from tens of milliseconds to roughly a second apart, with payment authorisations and gap-free queue offsets throughout, clearing both the payment and email/queue paths.

> Evidence `tr_4adfe9df6c0c`:

```
<tool_result id="tr_4adfe9df6c0c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T12:24:15.583000+00:00..2026-09-17T13:26:22.692710+00:00">
service: cartservice
10 trace(s) shown of 10 found, 188 spans; offsets are from each trace's root

trace 15c2e8762080513d  root frontend/HTTP POST  2497.0ms  started 2026-09-17T13:25:00.525048+00:00  37 spans
  +0.0ms frontend/HTTP POST 2497.0ms [self 1.0ms]
```

> Evidence `tr_c9e5a7b0bc37`:

```
<tool_result id="tr_c9e5a7b0bc37" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T12:54:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" template="error-ratio" baseline="2026-09-17T12:22:08.473290+00:00..2026-09-17T12:54:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1703 min=0 max=0.6667 sd=0.2794
  baseline window: n=94 mean=0.00244 min=0 max=0.0411 sd=0.008202
```

> Evidence `tr_5486a4f3c587`:

```
<tool_result id="tr_5486a4f3c587" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:54:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T12:54:23.338117+00:00  {"message":"[PlaceOrder] user_id=\"e808ffc8-b296-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T12:54:23.337960636Z"}
2026-09-17T12:54:23.357614+00:00  {"message":"payment went through (transaction_id: 97f42ab2-9665-4ab6-92af-43e0b2d3e307)","severity":"info","timestamp":"2026-09-17T12:54:23.357506636Z"}
2026-09-17T12:54:23.362434+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T12:54:23.362276136Z"}
2026-09-17T12:54:23.363571+00:00  {"message":"Successful to write message. offset: 64103","severity":"info","timestamp":"2026-09-17T12:54:23.363428178Z"}
```

## The change record, the dead ends in it, and what is still open

Seventeen changes on cartservice, all by the same platform-automation actor, cycling apply-then-revert through the same three mutations — an automated harness, not human deploys. Three of them are red herrings worth naming. A hotfix image tag was applied ~23 minutes before onset and reverted ~14 minutes before, so the baseline image was running. A REDIS_ADDR edit to an alternate Redis port was applied and reverted twice earlier the same day, latest ~3.4h before onset; because the symptom lives on the Redis edge this one is especially seductive and especially wrong. The null hypothesis — nothing changed locally, look upstream — also fails.

The cause: a traffic-shaping container attached to the cart-service network namespace ~3 minutes before onset, imposing a fixed 300ms zero-jitter egress delay on eth0, with no removal recorded. Zero jitter is what matches the traces; real congestion produces spread. Fix class is config_revert.

Still open. No evidence ties checkout's errors specifically to the cart edge — the error-ratio query carries no dependency dimension and not one of the 188 spans was errored; the link is inferred from timing and exclusion. Checkout logs from 13:25:19 onward show clean successful orders while traces in the same minutes still show the 300ms floor; unreconciled, and the lines around the 13:24:30 alert moment were truncated out of the result entirely. And the change record is untrusted — the container's continued attachment was never independently confirmed.

> Evidence `tr_4ba6c4f2425b`:

```
<tool_result id="tr_4ba6c4f2425b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T13:24:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" radius="seed" hops="0">
service: cartservice
17 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T13:20:48.039464+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  14m before onset  2026-09-17T13:10:10.327071+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_c9e5a7b0bc37`:

```
<tool_result id="tr_c9e5a7b0bc37" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T12:54:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" template="error-ratio" baseline="2026-09-17T12:22:08.473290+00:00..2026-09-17T12:54:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.1703 min=0 max=0.6667 sd=0.2794
  baseline window: n=94 mean=0.00244 min=0 max=0.0411 sd=0.008202
```

> Evidence `tr_5486a4f3c587`:

```
<tool_result id="tr_5486a4f3c587" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:54:15.583000+00:00..2026-09-17T13:26:22.692710+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T12:54:23.338117+00:00  {"message":"[PlaceOrder] user_id=\"e808ffc8-b296-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T12:54:23.337960636Z"}
2026-09-17T12:54:23.357614+00:00  {"message":"payment went through (transaction_id: 97f42ab2-9665-4ab6-92af-43e0b2d3e307)","severity":"info","timestamp":"2026-09-17T12:54:23.357506636Z"}
2026-09-17T12:54:23.362434+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-17T12:54:23.362276136Z"}
2026-09-17T12:54:23.363571+00:00  {"message":"Successful to write message. offset: 64103","severity":"info","timestamp":"2026-09-17T12:54:23.363428178Z"}
```

