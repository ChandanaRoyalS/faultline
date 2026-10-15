# Checkout order failures traced to an unreachable cart backend

## What this was, in one paragraph

Orders began failing intermittently at the front door. The paging services were checkout, frontend, frontend-proxy and the load-generator, and the seed for the investigation was checkout. Checkout turned out to be a messenger, not the patient: it was alive, answering, and failing only on the subset of requests that required a cart round-trip. The best-supported reading is that the cart endpoint dropped off the network and off the service-discovery plane, so two independent callers — frontend's own client and checkout's cart client — failed at connection-establishment time rather than on a deadline. Confidence is medium, and the reason it is only medium is written out at the end: nobody ever looked at cart directly.

> Evidence `tr_213f84c62d86`:

```
<tool_result id="tr_213f84c62d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T22:33:25.730687+00:00  Error: 5 NOT_FOUND: Product Not Found: 0PUK6V6EV0
2026-10-13T22:33:25.732583+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-10-13T22:33:25.732590+00:00      at new Promise (<anonymous>) {
2026-10-13T22:33:25.732592+00:00    code: 5,
```

> Evidence `tr_b25e9b250796`:

```
<tool_result id="tr_b25e9b250796" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 24240c16ac2bdb2f  root load-generator/user_checkout_multi  62.2ms  started 2026-10-13T22:44:14.259879+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 62.2ms [self 24.8ms]
```

## The first hour, in the order it appeared

Checkout's span error ratio was the cleanest early signal. Over the half hour before onset it sat at exactly zero — not low, zero, across 128 consecutive samples with no variance at all. It stepped off that floor at roughly T+1m and thereafter spiked to about two thirds of calls failing in the worst bucket while the window mean stayed near four percent. That shape mattered more than the magnitude: a step, not a ramp, and partial, not total. Most buckets stayed at or near zero throughout, which is what you expect when only the requests that touch one particular dependency fail. A second pass over a wider baseline hour agreed on the partial-and-spiky character and put the crossing of its own detection threshold near T+2m; the peak had no precedent anywhere in the preceding hour.

> Evidence `tr_acd19f2db44a`:

```
<tool_result id="tr_acd19f2db44a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" template="error-ratio" baseline="2026-10-13T21:47:39.080008+00:00..2026-10-13T22:19:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.03814 min=0 max=0.6667 sd=0.1254
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_85cfd0120a9a`:

```
<tool_result id="tr_85cfd0120a9a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T21:49:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" template="error-ratio" baseline="2026-10-13T20:47:39.080008+00:00..2026-10-13T21:49:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=248 mean=0.01969 min=0 max=0.6667 sd=0.09192
  baseline window: n=248 mean=0.01047 min=0 max=0.09697 sd=0.02483
```

## Dead end: checkout's change history

The obvious first move was to ask what shipped. Two separate queries against the change log came back explicitly empty for checkout — no deploys, no config pushes, no flag flips. Both queries ran cleanly, so the emptiness is a real answer and not a broken pipeline. Two caveats are worth preserving, because they cost time to notice. First, both lookups were scoped to the seed service only, zero hops out, so they say nothing about cart or any other dependency. Second, both windows opened *after* the onset reference time and ran forward roughly a day, meaning the hours immediately preceding onset were never actually covered. What these results genuinely rule out is a mid-incident change on checkout — including an attempted rollback — prolonging things. They do not rule out a pre-onset change anywhere, and they never spoke to cart at all.

> Evidence `tr_5ec324b65a06`:

```
<tool_result id="tr_5ec324b65a06" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T22:49:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_5ec324b65a06>
```

> Evidence `tr_045921c00b65`:

```
<tool_result id="tr_045921c00b65" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T22:49:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_045921c00b65>
```

## Dead end: checkout's own logs

A completely unfiltered query for checkout log lines across the incident window returned nothing. Not zero errors — zero lines of any severity, from a service that metrics show was serving traffic the whole time. That is itself a finding about the logging path for checkout (label mismatch, agent down, or an ingest gap) rather than evidence of a quiet healthy service, and it is worth fixing before the next time. The practical consequence for the responder is simple: do not expect checkout to name its own downstream here. Attribution had to come from somewhere else.

> Evidence `tr_2fb471319f1f`:

```
<tool_result id="tr_2fb471319f1f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_2fb471319f1f>
```

## Dead end: reading the traces as if checkout were broken

Traces actively pointed away from the hypothesis we started with. Every complete checkout trace in the sample showed the full fan-out — cart, product-catalog, currency, shipping quote, payment, email, flagd — finishing in single-digit milliseconds, with whole PlaceOrder spans around thirty-odd milliseconds and no checkout span flagged as an error. Cart's Redis operations in those traces were sub-millisecond. The one failing trace in the sample had only five spans and never reached checkout at all: the error chain ran load-generator to proxy ingress to proxy egress to the frontend handler and stopped there. Its alarming multi-second duration was almost entirely self-time in the load-generator root before the request was even issued; the downstream segment lasted about eight milliseconds. So the apparent latency was client-side, and the apparent checkout failure was a frontend-level failure. One honest limitation: the trace view was truncated, four of ten matching traces shown, so an error-bearing checkout subtree could in principle be hiding in what we did not see.

> Evidence `tr_b25e9b250796`:

```
<tool_result id="tr_b25e9b250796" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 24240c16ac2bdb2f  root load-generator/user_checkout_multi  62.2ms  started 2026-10-13T22:44:14.259879+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 62.2ms [self 24.8ms]
```

## The turn: frontend's logs

The only explicit attribution anywhere on the board came from frontend. Two distinct signatures appear there. Late in the window, repeated gRPC UNAVAILABLE errors describe a backend at 172.18.0.24:7070 that frontend cannot reach at the transport layer — host unreachable, with a recorded last-error stamp around T+4m being replayed on each subsequent attempt through to T+5m. Separately, and from a different frontend call path, a checkout call returns gRPC INTERNAL whose message attributes the failure to a cart lookup whose name resolver produced zero addresses. Two independent clients, two code paths, both failing to establish a connection rather than timing out. There is also an unrelated-looking band of gRPC NOT_FOUND errors for specific product IDs earlier in the window, around T-14m; it is noise relative to this incident and should not be chased. Errors were still being emitted in the final seconds of the queried range, so nothing self-resolved.

> Evidence `tr_213f84c62d86`:

```
<tool_result id="tr_213f84c62d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T22:33:25.730687+00:00  Error: 5 NOT_FOUND: Product Not Found: 0PUK6V6EV0
2026-10-13T22:33:25.732583+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-10-13T22:33:25.732590+00:00      at new Promise (<anonymous>) {
2026-10-13T22:33:25.732592+00:00    code: 5,
```

## Why we landed on cart

The chain is: checkout's errors are partial and step-onset, which fits one dependency failing rather than checkout itself; checkout's complete traces are clean, which rules checkout out as the originator; checkout has no change of its own to blame; and the only text naming a component names cart, reached via a resolver that returned no addresses. Connection-establishment failures from two callers at once, rather than deadlines, is the signature of an endpoint leaving the network and the discovery plane together. The indicated fix class is reconnection — restore the endpoint and let the callers re-resolve — but see the open items before acting on that.

> Evidence `tr_213f84c62d86`:

```
<tool_result id="tr_213f84c62d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T22:33:25.730687+00:00  Error: 5 NOT_FOUND: Product Not Found: 0PUK6V6EV0
2026-10-13T22:33:25.732583+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-10-13T22:33:25.732590+00:00      at new Promise (<anonymous>) {
2026-10-13T22:33:25.732592+00:00    code: 5,
```

> Evidence `tr_b25e9b250796`:

```
<tool_result id="tr_b25e9b250796" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 24240c16ac2bdb2f  root load-generator/user_checkout_multi  62.2ms  started 2026-10-13T22:44:14.259879+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 62.2ms [self 24.8ms]
```

> Evidence `tr_acd19f2db44a`:

```
<tool_result id="tr_acd19f2db44a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" template="error-ratio" baseline="2026-10-13T21:47:39.080008+00:00..2026-10-13T22:19:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.03814 min=0 max=0.6667 sd=0.1254
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Open items a future responder should close first

Three gaps, in priority order. First, no dispatch ever examined cart itself: its logs, metrics, process state and change history are all unexamined. Cart is named purely by inference from two callers' error text. Start there. Second, 172.18.0.24:7070 was never resolved to a service name. We assumed it was cart; it could just as easily be a second affected backend, which would change the blast picture. Resolve the address before assuming. Third, and this is the main risk to the conclusion: we do not know whether cart was running-but-isolated or simply gone — crashed, scaled to zero, or a rollout that never came up. 'Zero resolved addresses' fits both readings equally well, and the right remediation differs between them. Also unresolved: no request-rate or latency-percentile series were ever pulled for checkout, so the possibility that the error ratio was inflated by a traffic dip was never tested, and no per-status-code or per-target breakdown was ever queried — every metric query collapsed to one series per service.

> Evidence `tr_213f84c62d86`:

```
<tool_result id="tr_213f84c62d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T22:33:25.730687+00:00  Error: 5 NOT_FOUND: Product Not Found: 0PUK6V6EV0
2026-10-13T22:33:25.732583+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-10-13T22:33:25.732590+00:00      at new Promise (<anonymous>) {
2026-10-13T22:33:25.732592+00:00    code: 5,
```

> Evidence `tr_85cfd0120a9a`:

```
<tool_result id="tr_85cfd0120a9a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T21:49:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" template="error-ratio" baseline="2026-10-13T20:47:39.080008+00:00..2026-10-13T21:49:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=248 mean=0.01969 min=0 max=0.6667 sd=0.09192
  baseline window: n=248 mean=0.01047 min=0 max=0.09697 sd=0.02483
```

> Evidence `tr_acd19f2db44a`:

```
<tool_result id="tr_acd19f2db44a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T22:19:31.664000+00:00..2026-10-13T22:51:24.247992+00:00" template="error-ratio" baseline="2026-10-13T21:47:39.080008+00:00..2026-10-13T22:19:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.03814 min=0 max=0.6667 sd=0.1254
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

