# Cart-anchored investigation closes without a mechanism; frontend inferred but never observed

## What was visible first

The page arrived as a warning-severity event with five services firing at the same second: cart, checkout, frontend, frontend-proxy, and load-generator. The blast radius was recorded as fourteen services, with fourteen edges between them that nobody had measurements for. The starting point handed to the responder was cart, and that framing stuck: every dispatch that followed targeted cart and only cart.

Worth saying plainly at the top, because it is the single most useful thing in this record: we never established what signal tripped the alert. No latency series and no saturation series was returned for any service, at any point, by any dispatch. The alert fired on something; we closed without identifying what.

> Evidence `tr_7f64a0cb0538`:

```
<tool_result id="tr_7f64a0cb0538" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_6696564ceed5`:

```
<tool_result id="tr_6696564ceed5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

## The change-history thread (dead end, but instructive)

The first substantial lead was cart's change record. Eight entries in the window, all from the same automation actor, all image-reference changes — no configuration edits, no flag toggles of any kind. That alone retired several hypotheses a responder would reasonably reach for.

The shape of the eight was the interesting part: four identical apply/revert pairs cycling the same hotfix tag on and off cart, each pair lasting roughly eight to twelve minutes, running from about two and a half hours before onset down to about fifty-seven minutes before. That is a flapping deployment, not a rollout.

And then it stops mattering. The last entry before onset is a revert, meaning the pre-hotfix reference was the live one when the incident began, and the fifty-seven minutes immediately preceding onset contain no change at all. Nothing landed with the start. The flap is a real operational oddity someone should chase separately, but it is not the mechanism here.

> Evidence `tr_02e67517a613`:

```
<tool_result id="tr_02e67517a613" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T01:13:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" radius="seed" hops="0">
service: cart
8 changes, ranked by suspicion
  #1  57m before onset  2026-10-14T00:15:38.172165+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  1.1h before onset  2026-10-14T00:06:53.846025+00:00  platform-automation  image updated: image reference updated on cart
```

## Cart metrics: clean, twice over

Two separate metric dispatches landed on the same conclusion. Cart's span-derived error ratio is identically zero — mean, min, max, standard deviation all zero — across 128 incident-window samples, and equally zero across the 108 baseline samples. There is no onset signature, no late escalation, no carried-over elevation. Cart was not emitting the errors.

There is also no gap: every sampling interval in the incident window produced a defined value, so cart was serving traffic continuously throughout. A crash or stall would have left holes, and there are none. Curiously the baseline has twenty intervals with no defined value at all, meaning cart traffic was patchier *before* the incident than during it. That makes the baseline a weak comparator for anything rate-derived, and the responder should hold any cart-metric comparison loosely for that reason.

The serious limitation: only the error-ratio template was ever evaluated. The latency percentiles, CPU and memory, GC and connection-pool series were all requested in spirit and none came back. Saturation and latency on cart are unmeasured, not clean.

> Evidence `tr_6696564ceed5`:

```
<tool_result id="tr_6696564ceed5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_7f64a0cb0538`:

```
<tool_result id="tr_7f64a0cb0538" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

## Cart logs: normal at the edges, blind in the middle

The log pull on cart returned only info-level Valkey store operations — GetCart, AddItem, EmptyCart — at both ends of the window. No exceptions, no timeouts, no connection failures. Cart was still serving multiple distinct users with sub-second spacing roughly two minutes past the onset second, so the service was alive and logging after the fact. That retires the idea of a crash, a restart, or a lost connection to its backing store.

The catch, and it is a real one: the result was truncated to the oldest eight and newest thirty-two lines. The onset second falls entirely inside the dropped middle. We did not observe cart's logs at the moment of interest. The absence of errors there is unverified, not demonstrated, and the record should not be read as if we looked.

> Evidence `tr_185f3cb170bc`:

```
<tool_result id="tr_185f3cb170bc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-14T00:43:33.165585+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T00:43:33.165617+00:00        GetCartAsync called with userId=
2026-10-14T00:43:38.965290+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T00:43:38.965335+00:00        GetCartAsync called with userId=
```

## Traces: the one directional hint, from the wrong minutes

The trace dispatch is where the only forward-pointing evidence came from, and also where the sharpest caveat lives. Ten cart traces existed across the roughly thirty-two-minute window, and the newest starts about fourteen minutes before the onset second. There is a sixteen-minute trace gap running up to the end of the window. Nothing in this result can characterise cart at the moment of interest.

Within the traces we did get, cart is uniformly fast: handler spans of roughly 0.2–5ms, Valkey operations sub-millisecond to a few milliseconds and a small minority of end-to-end time, flag resolution under 2ms round trip with the evaluation itself around a tenth of a millisecond. In the longest sampled trace, a 93ms checkout flow, the two cart calls together account for under 4ms while the bulk sits in load-generator self-time and downstream checkout work.

The hint: in every sampled trace, the degrading hop sits outside cart — load-generator self-time, frontend route execution, or frontend-proxy to frontend. Never a cart call. Combined with the alert set firing together, that is consistent with one caller-chain propagation originating at or below frontend.

Unresolved tension worth flagging for whoever picks this up: Tempo shows no cart traces after a point fourteen minutes pre-onset, yet span metrics report defined cart values in every incident interval. Those two cannot both be a complete picture. Nobody reconciled them.

> Evidence `tr_326259fa9793`:

```
<tool_result id="tr_326259fa9793" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2250d04f43556509  root load-generator/user_checkout_multi  93.3ms  started 2026-10-14T00:58:58.534511+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 93.3ms [self 29.2ms]
```

> Evidence `tr_7f64a0cb0538`:

```
<tool_result id="tr_7f64a0cb0538" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

## Where it landed, and what it is worth

Conclusion: not established. Confidence low. Fix class: none.

Cart is clean on all three signal types we actually obtained — zero error ratio with no gaps, normal store operations at both window boundaries, sub-5ms spans in the sampled traces. Cart is where the investigation began, not where the failure is. I name frontend as the likely locus, but that is inference from cart-side traces during minutes that precede onset, nothing more. The mechanism is unidentified.

> Evidence `tr_6696564ceed5`:

```
<tool_result id="tr_6696564ceed5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_7f64a0cb0538`:

```
<tool_result id="tr_7f64a0cb0538" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_185f3cb170bc`:

```
<tool_result id="tr_185f3cb170bc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-14T00:43:33.165585+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T00:43:33.165617+00:00        GetCartAsync called with userId=
2026-10-14T00:43:38.965290+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T00:43:38.965335+00:00        GetCartAsync called with userId=
```

> Evidence `tr_326259fa9793`:

```
<tool_result id="tr_326259fa9793" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2250d04f43556509  root load-generator/user_checkout_multi  93.3ms  started 2026-10-14T00:58:58.534511+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 93.3ms [self 29.2ms]
```

## Still open for the next responder

First and largest: no dispatch ever examined frontend, frontend-proxy, checkout, or any of the fourteen unmeasured edges. The service I named is inferred, never observed. Start there.

Second: identify what signal actually tripped the alert. No latency or saturation series was retrieved for any service in this entire investigation, which means the alerting condition itself remains uncharacterised.

Third: reconcile the Tempo trace gap against the span-metric coverage, and re-pull cart logs around the onset second without truncation so that the blind middle is actually read.

Fourth, lower priority but real: the four-cycle image flap on cart is an operational problem independent of this incident and deserves its own look.

Process note for the record: the single biggest shaping force on this investigation was that the starting service became the only investigated service. Every dispatch went to cart, cart kept coming back clean, and the clean results were mistaken for progress rather than for exhaustion of a cleared subject.

> Evidence `tr_7f64a0cb0538`:

```
<tool_result id="tr_7f64a0cb0538" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" template="error-ratio" baseline="2026-10-14T00:11:38.604783+00:00..2026-10-14T00:43:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=108 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_326259fa9793`:

```
<tool_result id="tr_326259fa9793" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2250d04f43556509  root load-generator/user_checkout_multi  93.3ms  started 2026-10-14T00:58:58.534511+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 93.3ms [self 29.2ms]
```

> Evidence `tr_185f3cb170bc`:

```
<tool_result id="tr_185f3cb170bc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T00:43:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-14T00:43:33.165585+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T00:43:33.165617+00:00        GetCartAsync called with userId=
2026-10-14T00:43:38.965290+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-14T00:43:38.965335+00:00        GetCartAsync called with userId=
```

> Evidence `tr_02e67517a613`:

```
<tool_result id="tr_02e67517a613" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T01:13:31.664000+00:00..2026-10-14T01:15:24.723217+00:00" radius="seed" hops="0">
service: cart
8 changes, ranked by suspicion
  #1  57m before onset  2026-10-14T00:15:38.172165+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  1.1h before onset  2026-10-14T00:06:53.846025+00:00  platform-automation  image updated: image reference updated on cart
```

