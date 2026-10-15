# Checkout hangs to deadline; currency paged first and was innocent

## How it surfaced

The first page named currency, and within about a minute six more services were alerting: frontend-proxy, accounting, email, payment, quote and shipping. Nine services in the blast radius, severity critical. The shape of that fan-out is worth noting up front, because it set the first hour's direction wrongly: the seed of the investigation was the service that paged first, not the service that was broken. Treat the alert order here as topology, not causality — the services that lit up a minute later did so because requests stopped arriving at them, not because anything was wrong inside them.

## First line of inquiry: currency, and three empty windows

Because currency seeded the investigation, the first three queries all pointed at it, and all three came back empty.

The change log for currency over the ~24h window before the page held nothing — no release, no image swap, no config push, no runtime flag edit. That query was scoped to the seed service alone (radius zero), so it said nothing about its neighbours; that limitation mattered later and was eventually covered by a second, wider query.

The error-ratio metric for currency returned no samples at all — not in the incident window and not in the preceding baseline. The important detail is that the baseline was equally empty. A series that is absent before the trouble started is an instrumentation or label-naming gap, not an onset signal, and reading it as "currency stopped emitting" would have been wrong.

The log query for currency over the same window returned no lines. This one is genuinely ambiguous and stayed ambiguous: either the service wrote nothing, or its output is not being captured under that selector. What it does foreclose is a crash-and-restart story — no startup banner, no allocation failure, no decode errors, no exporter deadline lines.

Three empty results in a row is easy to read as "currency is dead." It was not. It was the wrong service.

> Evidence `tr_5ee898a674ba`:

```
<tool_result id="tr_5ee898a674ba" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T23:19:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_5ee898a674ba>
```

> Evidence `tr_40d57e02ea67`:

```
<tool_result id="tr_40d57e02ea67" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" template="error-ratio" baseline="2026-10-14T22:17:39.575978+00:00..2026-10-14T22:49:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_19bfe26748dc`:

```
<tool_result id="tr_19bfe26748dc" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_19bfe26748dc>
```

## The turn: reading the traces

The trace read is where the investigation actually moved. Every currency server span in the sampled traces completed in sub-millisecond to low single-digit milliseconds, none carried an error status, and — decisively — every checkout-side call to currency had a matching currency server span, with the caller span only marginally longer than the server span. There is no gap at that hop. Currency was answering, promptly, throughout.

One hop upstream the picture inverts. In three traces the frontend's gRPC call to CheckoutService/PlaceOrder accounted for 100% of trace time — 18.4s, 24.0s, 52.7s — all of it self time, with no checkout server span attached at all, while the ingress gave up at its 15s deadline. In the same traces checkout's own downstream fan-out (cart, product-catalog, payment, shipping, email, currency, the flag daemon) completed inside tens of milliseconds. The backend was healthy while the request as a whole was timing out.

Two shorter traces showed the same hop failing fast instead (108ms and 280ms, ERROR) with frontend dns.lookup and tcp.connect children present — connection-establishment behaviour on the frontend→checkout edge rather than backend work.

> Evidence `tr_6ef0d6740cf9`:

```
<tool_result id="tr_6ef0d6740cf9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00">
service: currency
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 26c04e5d8f2b5f15  root load-generator/user_checkout_single  15014.2ms  started 2026-10-14T22:58:09.613266+00:00  44 spans, 5 unattached
  +0.0ms load-generator/user_checkout_single 15014.2ms [self 0.0ms]
```

## Checkout's own numbers

Checkout's service-wide error ratio rose roughly 26x over baseline — mean near 0.0231 against a baseline near 0.00088, peaking around 0.071. The spread was an order of magnitude wider than baseline, which reads as intermittent bursts rather than a flat elevation. The single detected change point sits about 28 minutes *before* the first page (T-28m), which contradicted the working assumption at the time that trouble began a few minutes before the alert. Baseline was not spotless either — the prior window touched 0.0175 — so a low level of checkout errors predates all of this.

This query carried no operation or downstream dimension, only service_name. It neither implicates nor clears any particular call path inside checkout, and should not be read as doing either.

> Evidence `tr_e15b112d18b2`:

```
<tool_result id="tr_e15b112d18b2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" template="error-ratio" baseline="2026-10-14T22:17:39.575978+00:00..2026-10-14T22:49:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.02308 min=0 max=0.07087 sd=0.02941
  baseline window: n=128 mean=0.0008797 min=0 max=0.01751 sd=0.003528
```

## Change history, widened

The second change-log query covered checkout plus its one-hop neighbours — frontend, frontend-proxy, currency — across the full ~24h window. It returned nothing: no deploys, no image swaps, no config pushes, no runtime flag edits anywhere in scope. There is no rollback target and no configuration to restore. In this environment an empty change log is not automatically exculpatory — a runtime flag flip leaves no record here — but combined with the trace shape it argues against anything release-driven.

> Evidence `tr_4120a3f3bc24`:

```
<tool_result id="tr_4120a3f3bc24" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T23:19:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" radius="also_affected" hops="1">
no changes recorded for checkout over this window
</tool_result:tr_4120a3f3bc24>
```

## Where it landed

The pattern is callers hanging to their deadline against a peer whose requests sometimes produce no server span at all, with that peer's own downstream work fast and healthy, and with no change recorded anywhere. That reads as checkout accepting connections it never serves — a stalled checkout process — and the downstream alerts (payment, shipping, email, quote, accounting) as starvation behind a stuck caller rather than failures of their own.

Confidence is low, and deliberately so. The fix class is restart: recreate checkout's container without touching image or configuration. That action is not reversible and discards in-process state, which for these services is cache only. Callers of checkout — frontend, and the proxy behind it — will see resets for the duration of the recreate. If the resume works, expect a second burst of error-rate alerts on checkout and its callers a couple of minutes later as every hung request wakes and fails together; that wave is the recovery, not a new failure.

> Evidence `tr_6ef0d6740cf9`:

```
<tool_result id="tr_6ef0d6740cf9" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00">
service: currency
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 26c04e5d8f2b5f15  root load-generator/user_checkout_single  15014.2ms  started 2026-10-14T22:58:09.613266+00:00  44 spans, 5 unattached
  +0.0ms load-generator/user_checkout_single 15014.2ms [self 0.0ms]
```

> Evidence `tr_e15b112d18b2`:

```
<tool_result id="tr_e15b112d18b2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" template="error-ratio" baseline="2026-10-14T22:17:39.575978+00:00..2026-10-14T22:49:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.02308 min=0 max=0.07087 sd=0.02941
  baseline window: n=128 mean=0.0008797 min=0 max=0.01751 sd=0.003528
```

> Evidence `tr_4120a3f3bc24`:

```
<tool_result id="tr_4120a3f3bc24" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T23:19:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" radius="also_affected" hops="1">
no changes recorded for checkout over this window
</tool_result:tr_4120a3f3bc24>
```

## Open, and what a future responder should do differently

Four things were never closed.

No log query was run against checkout itself. That is the single cheapest piece of evidence remaining and the one that separates a stalled process (silent log) from a container cut off from its network (a repeating once-a-minute telemetry upload deadline line) from a full data directory (no space left on device). Run it first next time.

The T-28m change point against the T+0 page is unexplained. Nothing establishes whether the intermittent error elevation and the hang are the same condition or two overlapping ones.

No memory, CPU or container-restart data was gathered for checkout, so a memory squeeze producing stalls is untested. Note that if it were a squeeze, a restart would bring the container back under the same limit and the trouble would return — the proposed action would look like it failed.

Both change-history queries returned empty and the health of the change log itself was never verified. An unrecorded edit, or a runtime flag flip that by design leaves no record, cannot be excluded.

The useful dead ends to carry forward: currency's three empty windows cost real time and meant nothing; the currency metric gap predated the incident; and the alert ordering pointed at the wrong service from the first minute.

> Evidence `tr_19bfe26748dc`:

```
<tool_result id="tr_19bfe26748dc" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_19bfe26748dc>
```

> Evidence `tr_40d57e02ea67`:

```
<tool_result id="tr_40d57e02ea67" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" template="error-ratio" baseline="2026-10-14T22:17:39.575978+00:00..2026-10-14T22:49:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_e15b112d18b2`:

```
<tool_result id="tr_e15b112d18b2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:49:31.664000+00:00..2026-10-14T23:21:23.752022+00:00" template="error-ratio" baseline="2026-10-14T22:17:39.575978+00:00..2026-10-14T22:49:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.02308 min=0 max=0.07087 sd=0.02941
  baseline window: n=128 mean=0.0008797 min=0 max=0.01751 sd=0.003528
```

