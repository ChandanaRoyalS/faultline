# Frontend handlers stall to a fixed client deadline with no downstream work

## What we saw first

The page came from frontend-proxy and load-generator together. The visible symptom was client-side: callers hanging and then giving up. Nothing in the first look pointed at a specific backend — no error text, no crash signal, no obvious slow dependency.

The cleanest early anchor was the proxy's error ratio. Its baseline hour was not merely low but exactly flat — every sample zero, no variance at all — and it stepped off that floor roughly two minutes before the alert time (call it T-2m), peaking near 25% and averaging about 1.2% through the window. That shape matters: a zero-variance baseline cannot throw a 25% excursion as noise, and there was exactly one crossing rather than a ramp, so this was a step onset, not something creeping up over hours. The errors were bursty rather than continuous, with the minimum still touching zero, so the proxy was never fully down.

> Evidence `tr_4bfa31fa6797`:

```
<tool_result id="tr_4bfa31fa6797" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" template="error-ratio" baseline="2026-10-09T00:25:44.293515+00:00..2026-10-09T01:27:46.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=249 mean=0.01225 min=0 max=0.248 sd=0.0486
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

## The trace picture, which is where the answer lives

Ten sampled traces across the window; eight of them tell the same story. A frontend GET span (a POST in the checkout trace) runs about 15 seconds, and that 15 seconds is entirely its own self-time. It emits no child spans at all. The ERROR marks are not on the frontend span — they sit on the wrapping frontend-proxy ingress span and the load-generator client span, both of which contribute roughly 0ms of self-time. In other words the proxy and the client are reporting the failure they experienced; the frontend is the thing they were waiting on.

Two details sharpen this. First, the stalled spans cluster on one near-identical ~15.000s value rather than spreading across a range of elevated durations. That is a deadline being hit, not a queue draining slowly. Second, the frontend work that does complete in the same window completes fine: AdService/GetAds around 4ms, CartService AddItem and GetCart in the 1-3ms range, /api/cart and /api/data in single-digit milliseconds. So the service is answering some requests normally while others never get answered at all.

The affected routes are the browser-facing page/GET paths (product browse, recommendations, the opening GET of add-to-cart) plus the checkout POST.

> Evidence `tr_838e5c9acc04`:

```
<tool_result id="tr_838e5c9acc04" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00">
service: frontend
10 trace(s) shown of 10 found, 117 spans; offsets are from each trace's root

trace 81acaddc87d00d48  root load-generator/user_add_to_cart  15271.4ms  started 2026-10-09T02:26:05.732492+00:00  19 spans
  +0.0ms load-generator/user_add_to_cart 15271.4ms [self 265.9ms]
```

## Dead ends worth keeping

**A slow downstream dependency.** The natural first guess, and wrong. Every cart, ad and cart-store operation observed in the same traces finishes well under 3ms. More decisively, the stalled frontend spans have no children — no outbound call was even attempted during the 15 seconds. You cannot blame a dependency that was never called.

**The proxy itself adding latency.** Also wrong. Envoy's ingress and router egress spans show ~0ms self-time and merely wrap the long frontend span; on healthy requests the proxy adds fractions of a millisecond.

**The frontend being down or failing everything.** Ruled out by the ad trace and the POST /api/cart legs completing normally inside the same window.

**The checkout cart lookup being the bottleneck.** In the multi-item checkout trace, checkout-to-cart GetCart returns in under 1ms; the 15 seconds is consumed by a frontend POST span that is all self-time.

**Frontend throwing errors.** Its own error ratio is identically zero across 249 samples in both the baseline and the incident window, with zero variance. There is no inflection point there to anchor a start time. The service is not failing requests — it is not answering them. A corollary worth remembering: error-rate alerting on frontend would never have fired for this.

**A recent change.** The change log returned nothing for frontend, and nothing for frontend or its one-hop neighbours, across a full 24-hour window — no deploys, no config edits, no flag flips. Caveat on that below.

> Evidence `tr_838e5c9acc04`:

```
<tool_result id="tr_838e5c9acc04" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00">
service: frontend
10 trace(s) shown of 10 found, 117 spans; offsets are from each trace's root

trace 81acaddc87d00d48  root load-generator/user_add_to_cart  15271.4ms  started 2026-10-09T02:26:05.732492+00:00  19 spans
  +0.0ms load-generator/user_add_to_cart 15271.4ms [self 265.9ms]
```

> Evidence `tr_4bec7214ac16`:

```
<tool_result id="tr_4bec7214ac16" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" template="error-ratio" baseline="2026-10-09T00:25:44.293515+00:00..2026-10-09T01:27:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=249 mean=0 min=0 max=0 sd=0
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_6ab4975b4cff`:

```
<tool_result id="tr_6ab4975b4cff" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-08T02:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" radius="candidate_cause" hops="1">
no changes recorded for frontend over this window
</tool_result:tr_6ab4975b4cff>
```

> Evidence `tr_5e7448476208`:

```
<tool_result id="tr_5e7448476208" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-08T02:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" radius="candidate_cause" hops="1">
no changes recorded for frontend over this window
</tool_result:tr_5e7448476208>
```

## The log silence, and why we stopped leaning on it

Both frontend and frontend-proxy returned zero log lines over the ~62-minute window — not zero error lines, zero lines of any level, against a bare service selector. It is tempting to read frontend's silence as the process having stopped writing. We did not, because the same emptiness covers the entire pre-incident baseline hour, when both services were demonstrably serving traffic, and because frontend-proxy is equally empty. A label mismatch, a different tenant or stream, or a collection-path outage explains this exactly as well as a hung process. The proxy's silence in particular cannot be read as a crash signature: it extends backward an hour before onset and so does not correlate with anything.

Consequence for the investigation: no upstream attribution from proxy access logs, no 5xx accounting from that source, and frontend cannot serve as the timeline anchor. Everything had to come from traces and metrics.

> Evidence `tr_c665ffa355cd`:

```
<tool_result id="tr_c665ffa355cd" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_c665ffa355cd>
```

> Evidence `tr_4020e752193a`:

```
<tool_result id="tr_4020e752193a" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00">
no log lines matched {service="frontend-proxy"} over this window
</tool_result:tr_4020e752193a>
```

## Where we landed

The socket is still accepting. Callers hang to their own deadline. No outbound work is attempted. Nothing changed in the recorded history. The most consistent reading is that frontend request handlers are stuck — a stalled process — and most likely only on a subset of replicas, since some ad and /api/cart requests continue to complete in milliseconds through the same window. Fix class: restart. Confidence medium, for the reasons in the next section.

> Evidence `tr_838e5c9acc04`:

```
<tool_result id="tr_838e5c9acc04" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00">
service: frontend
10 trace(s) shown of 10 found, 117 spans; offsets are from each trace's root

trace 81acaddc87d00d48  root load-generator/user_add_to_cart  15271.4ms  started 2026-10-09T02:26:05.732492+00:00  19 spans
  +0.0ms load-generator/user_add_to_cart 15271.4ms [self 265.9ms]
```

> Evidence `tr_4bec7214ac16`:

```
<tool_result id="tr_4bec7214ac16" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" template="error-ratio" baseline="2026-10-09T00:25:44.293515+00:00..2026-10-09T01:27:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=249 mean=0 min=0 max=0 sd=0
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_4bfa31fa6797`:

```
<tool_result id="tr_4bfa31fa6797" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" template="error-ratio" baseline="2026-10-09T00:25:44.293515+00:00..2026-10-09T01:27:46.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=249 mean=0.01225 min=0 max=0.248 sd=0.0486
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

## Still open — read this before trusting the conclusion

**Unmeasured signals at frontend.** CPU, memory, restart counts, thread-pool and file-descriptor saturation, and request rate were never queried. Only the error ratio was. A pegged CPU or a deadlocked thread pool would produce an identical trace signature — long self-time spans, no children, no errors — and would reclassify this entirely. If you are re-walking this, measure those first.

**One unmeasured edge.** Triage flagged an edge out of frontend that carries no instrumentation. If frontend makes an uninstrumented outbound call, then "no child spans" is an artefact of what we can see, not proof that no downstream work was attempted. That single gap is the weakest joint in the whole chain.

**Change-history window placement.** Both change queries ran forward from the incident timestamp for about 24 hours. They cover during and after onset well; they do not actually cover the hours *preceding* it. A pre-onset change would not have appeared. The empty result is good evidence against a concurrent or post-onset release, and weak evidence about anything earlier.

**Proxy breakdown by route and upstream.** The proxy metric aggregated by service name only — no route, span-name or upstream dimension, and no latency or request-rate series was returned. Whether volume collapsed or spiked, and whether latency degraded alongside errors, is simply unknown from what was gathered.

> Evidence `tr_4bec7214ac16`:

```
<tool_result id="tr_4bec7214ac16" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" template="error-ratio" baseline="2026-10-09T00:25:44.293515+00:00..2026-10-09T01:27:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=249 mean=0 min=0 max=0 sd=0
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_6ab4975b4cff`:

```
<tool_result id="tr_6ab4975b4cff" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-08T02:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" radius="candidate_cause" hops="1">
no changes recorded for frontend over this window
</tool_result:tr_6ab4975b4cff>
```

> Evidence `tr_5e7448476208`:

```
<tool_result id="tr_5e7448476208" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-08T02:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" radius="candidate_cause" hops="1">
no changes recorded for frontend over this window
</tool_result:tr_5e7448476208>
```

> Evidence `tr_4bfa31fa6797`:

```
<tool_result id="tr_4bfa31fa6797" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-09T01:27:46.664000+00:00..2026-10-09T02:29:49.034485+00:00" template="error-ratio" baseline="2026-10-09T00:25:44.293515+00:00..2026-10-09T01:27:46.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=249 mean=0.01225 min=0 max=0.248 sd=0.0486
  baseline window: n=249 mean=0 min=0 max=0 sd=0
```

