# Checkout failures traced to a silent cart dependency after an image roll-forward

## What was visible, and the first dead end

Three alerts arrived together at T+0: checkoutservice, frontend, loadgenerator. Severity critical, blast radius eventually twelve services, with the investigation seeded at checkoutservice and four edges crossed unmeasured.

The first move was to look for a change on the alerting service. The change log over a full 24-hour window returned nothing at all for checkoutservice — no deploys, no config pushes, no flag flips. That cleanly removed an in-window checkout rollout, a config or flag change, a half-completed release leaving a mixed fleet, and the tempting remediation of reverting checkout's last change. There was nothing to revert. Two caveats cost us later: the query was scoped to the seed service only, so checkout's dependencies were untouched by it, and the window opened at the onset timestamp rather than before it, so a change landing minutes prior would have fallen outside.

Checkout's own error metrics confirmed the symptom was real — roughly 8.4% error ratio against a 0.2% baseline, far outside baseline spread, so not noise and not a silent degradation. But the shape misled: standard deviation exceeded the mean, most intervals were clean, and failure came in bursts of near-total error on low volume. That burstiness argued against a hard dependency outage and pulled us sideways. No latency series came back, so every p95 claim about checkout here is unsupported either way.

> Evidence `tr_c4e64bbd7e43`:

```
<tool_result id="tr_c4e64bbd7e43" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T09:19:15.583000+00:00..2026-09-17T09:21:08.222795+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_c4e64bbd7e43>
```

> Evidence `tr_21a7db79662b`:

```
<tool_result id="tr_21a7db79662b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T08:49:15.583000+00:00..2026-09-17T09:21:08.222795+00:00" template="error-ratio" baseline="2026-09-17T08:17:22.943205+00:00..2026-09-17T08:49:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08415 min=0 max=0.6667 sd=0.222
  baseline window: n=46 mean=0.002023 min=0 max=0.01887 sd=0.005169
```

## Logs and traces: the pivot

Checkout's logs offered no error text at all — every line informational, nothing above info severity near the page, so no downstream call was named. A second dead end for anyone hoping logs would hand over the culprit. What they did show was an amputated flow: early orders logged request start, payment confirmation, confirmation email and message-write; late orders logged only the request start. Intake stayed healthy at a few-second cadence, so checkout had not crashed, lost traffic, or begun refusing requests at admission. The break sat downstream of admission and upstream of payment. The result was truncated, leaving about half an hour unobserved, so onset could not be timed from here.

Traces resolved it. Ten sampled failing traces were structurally identical: frontend POST, frontend PlaceOrder, checkout PlaceOrder, order-item and shipping-quote preparation, then a CartService GetCart call as the deepest and sole erroring leaf, with the error status propagating upward to the frontend root. That explains the three-way page with no checkout-side error logs. It also killed a large candidate set at once: productcatalog, shipping, payment, currency, email, recommendation, ad and accounting appeared in no failing trace, so fan-out degradation and each of those services were out; checkout's own spans carried a tenth of a millisecond of self time and only inherited error status, so its own logic and GC were out; the frontend was propagating, not originating. Most importantly the failures were fast — three to six milliseconds end to end — which rules out timeouts and deadline expiry and points at a fast rejection with nothing listening.

> Evidence `tr_80f38a065db3`:

```
<tool_result id="tr_80f38a065db3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T08:49:15.583000+00:00..2026-09-17T09:21:08.222795+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T08:49:15.771527+00:00  {"message":"[PlaceOrder] user_id=\"a9a4cb76-b274-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T08:49:15.771317548Z"}
2026-09-17T08:49:15.789644+00:00  {"message":"payment went through (transaction_id: 8cdf89a4-0171-4938-bb93-e5993e6c73ad)","severity":"info","timestamp":"2026-09-17T08:49:15.789525465Z"}
2026-09-17T08:49:15.794045+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-17T08:49:15.793908132Z"}
2026-09-17T08:49:15.795390+00:00  {"message":"Successful to write message. offset: 62446","severity":"info","timestamp":"2026-09-17T08:49:15.795322715Z"}
```

> Evidence `tr_256fa1231c8e`:

```
<tool_result id="tr_256fa1231c8e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T08:49:15.583000+00:00..2026-09-17T09:21:08.222795+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace 649fc5895c046667  root frontend/HTTP POST  3.1ms  started 2026-09-17T09:19:27.952010+00:00  5 spans
  +0.0ms frontend/HTTP POST 3.1ms [self 0.1ms]  ERROR
```

## Cart: an orderly stop, the change, and the red herrings

Cart's log stream was routine to the end — ordinary add/get/empty-cart handler entries, normal cadence in the final minute, no warnings building, nothing naming a cache backend or connection timeout. Then, at about T-4m, a graceful hosting-lifetime shutdown notice, and nothing afterward, in a window running six minutes past the page. That ruled out a crash or out-of-memory kill (the last record is an orderly stop, not a truncated mid-request line), ruled out cache-connection failures at page time (there were no lines at all), and ruled out a running-but-degraded process. The symptom was unavailability.

Cart metrics could not corroborate the timing. The error-ratio query returned no samples in the incident window or the baseline, and because total calls were missing too, it cannot be read as healthy-and-serving; because the baseline is equally empty, it cannot be read as caused by onset. Most likely an instrumentation or label mismatch. Dead end for timing.

Cart's change log held the change: the image reference updated to a hotfix build about four minutes before the page, by automation, with no subsequent revert — the same offset as the shutdown line. The same reference had been rolled forward and reverted twice earlier that morning, so this was a flapping rollout, not a first exposure. Three entries looked promising and were not: a redis endpoint change on a non-default port, reverted about two hours before onset; a traffic-shaping sidecar applying a fixed 300ms egress delay, removed about four and a half hours before onset and never re-attached; and no flag toggle exists in the window at all.

Conclusion, medium confidence: the artifact now deployed for cart is not a working one. Fix class is rollback. Still open — no pod or container state, restart count, exit code or readiness data was gathered, and no logs from the replacement process were seen, so silence is equally consistent with a failed start, a crash loop before logging, an image-pull failure, or a log-label change. Also unresolved: why checkout's error ratio is only ~8.4% and bursty if cart has been down since T-4m; no gRPC status code or message was extracted from the GetCart span, so unavailable-versus-application-error is unsettled; and the last-known-good cart image reference was never established.

> Evidence `tr_2dd6158680cc`:

```
<tool_result id="tr_2dd6158680cc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T08:49:15.583000+00:00..2026-09-17T09:21:08.222795+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T08:49:15.759718+00:00  AddItemAsync called with userId=a9a4cb76-b274-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=5
2026-09-17T08:49:15.762336+00:00  GetCartAsync called with userId=a9a4cb76-b274-11f1-b359-b6ed2071a170
2026-09-17T08:49:15.773329+00:00  GetCartAsync called with userId=a9a4cb76-b274-11f1-b359-b6ed2071a170
2026-09-17T08:49:15.791216+00:00  EmptyCartAsync called with userId=a9a4cb76-b274-11f1-b359-b6ed2071a170
```

> Evidence `tr_3a8525a625b7`:

```
<tool_result id="tr_3a8525a625b7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T08:49:15.583000+00:00..2026-09-17T09:21:08.222795+00:00" template="error-ratio" baseline="2026-09-17T08:17:22.943205+00:00..2026-09-17T08:49:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_b71528ba01fb`:

```
<tool_result id="tr_b71528ba01fb" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T09:19:15.583000+00:00..2026-09-17T09:21:08.222795+00:00" radius="candidate_cause" hops="1">
service: cartservice
9 changes, ranked by suspicion
  #1  4m before onset  2026-09-17T09:14:53.941493+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
  #2  4.1h before onset  2026-09-17T05:10:57.619093+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

