# Checkout failing fast inside its own order path, no change on record

## What was visible, in order

T+0 was an error-rate page on checkout, with frontend, frontend-proxy and load-generator following it up the call chain. Thirteen services sat in the blast radius, but the alerting set had the shape of one failing service plus everyone above it.

The metrics were pulled twice and disagree, which is worth knowing before anyone trusts them. The narrower pull put checkout's error ratio at roughly double baseline (about 1.5% to 2.8%), bursty, minimum still at zero, peaks at half of sampled calls, with a single change point one minute before the page — abrupt onset, not a creep, and not a total outage. The wider two-hour pull came back the other way: mean slightly below baseline, identical extremes in both windows, its one change point at T+1m and read as a brief terminal spike. The window boundaries differ, which is the likely explanation, but nobody checked. Neither pull returned request rate or p95 — both came back with only the error-ratio template — so the fast-fail versus hang question could not be answered from metrics at all.

> Evidence `tr_d6f9ed35aa55`:

```
<tool_result id="tr_d6f9ed35aa55" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:40:31.664000+00:00..2026-10-14T23:42:21.468954+00:00" template="error-ratio" baseline="2026-10-14T21:38:41.859046+00:00..2026-10-14T22:40:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=248 mean=0.02818 min=0 max=0.5 sd=0.07751
  baseline window: n=248 mean=0.01552 min=0 max=0.1141 sd=0.02823
```

> Evidence `tr_c24b7542b607`:

```
<tool_result id="tr_c24b7542b607" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T21:40:31.664000+00:00..2026-10-14T23:42:21.468954+00:00" template="error-ratio" baseline="2026-10-14T19:38:41.859046+00:00..2026-10-14T21:40:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=488 mean=0.02221 min=0 max=0.5 sd=0.05903
  baseline window: n=488 mean=0.02921 min=0 max=0.5 sd=0.109
```

## Logs and traces: the failure is checkout's own

The log store held two Go runtime panics — nil pointer dereference, SIGSEGV — at about T-41m, both on gRPC-served requests, raised in sendToPostProcessor (main.go:630) under PlaceOrder (main.go:388). That is checkout's own code. The OpenTelemetry frames are the deferred span-End unwind after the panic, not its origin. No decode errors, no connection or TLS errors, no memory-exhaustion or external kill, and no error line naming any downstream service. After the second panic checkout logged nothing for the forty-one minutes bracketing the page — so it had not quietly recovered, but whether it was restarted, crashlooping or running silent was never settled.

The traces agree. One PlaceOrder span in error around T-3m, message combining a shipping-quote failure with an email 400. That message is misleading and recognising it as such is the point: the trace is thirteen spans against fifty-seven to sixty-five in healthy comparisons, checkout aborts after a successful CartService/GetCart, and there is no email, shipping, payment, currency or product-catalog span at all. Error status propagates upward only; no child of checkout is in error. The span completes in 11.1ms inside a 49.2ms trace, far too fast for a deadline. Three clean traces in the same window confirm the failure is intermittent.

Dead ends to keep: do not go read the email service for that 400, it was never called; do not chase shipping, payment or the cart path, whose GetCart and underlying HGET both succeeded. The pull was truncated, four of ten traces, so spans nearer T+0 were never examined.

> Evidence `tr_58ffbe0e4fc5`:

```
<tool_result id="tr_58ffbe0e4fc5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T22:40:31.664000+00:00..2026-10-14T23:42:21.468954+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-14T22:59:06.483473+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-14T22:59:06.485860+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-14T22:59:06.485873+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-14T22:59:06.485879+00:00  
```

> Evidence `tr_641900452056`:

```
<tool_result id="tr_641900452056" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T23:10:31.664000+00:00..2026-10-14T23:42:21.468954+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace bed481f68c73514e  root load-generator/user_checkout_multi  625.6ms  started 2026-10-14T23:36:20.450508+00:00  65 spans
  +0.0ms load-generator/user_checkout_multi 625.6ms [self 297.7ms]
```

## The empty change log, and what it does and does not establish

Two change-history queries against checkout both returned nothing — no deploy, image tag, environment edit or runtime toggle. Both used the same window, starting at onset and running roughly twenty-four hours forward, and both were scoped to the seed service at zero hops. So what was actually established is narrow: nothing changed on checkout during or after onset, which usefully excludes a mid-incident rollback or hotfix confusing the signal. It says nothing about the hours before the page, and nothing about checkout's dependencies. Re-run it backwards from onset and widen by a hop before treating the emptiness as meaningful.

The working conclusion — low confidence — is that a runtime toggle moved checkout onto a broken branch: fast, intermittent, self-attributed errors from a code path that never made the call it reports, with no artifact shown to be wrong and no change on record. Proposed class is config_revert. But that rests on absence plus failure shape; no toggle store or daemon evidence was ever pulled, and no value was observed to change. Left open: the metric disagreement above, the unexplained email 400 in the error string, the forty-one-minute log silence, and whether an ordinary change landed just before onset or on a dependency.

> Evidence `tr_2d84fe3c5698`:

```
<tool_result id="tr_2d84fe3c5698" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T23:40:31.664000+00:00..2026-10-14T23:42:21.468954+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_2d84fe3c5698>
```

> Evidence `tr_3f2c9028e057`:

```
<tool_result id="tr_3f2c9028e057" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T23:40:31.664000+00:00..2026-10-14T23:42:21.468954+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_3f2c9028e057>
```

