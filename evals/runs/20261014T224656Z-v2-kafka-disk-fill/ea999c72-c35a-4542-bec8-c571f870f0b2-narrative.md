# Checkout orders stall on unresolvable message-broker host; accounting goes silent

## What we saw first

Two alerts opened close together: checkout and accounting. The user-visible complaint was failing purchases. Blast radius at the time of triage was reported as ten services reachable from checkout, with eight edges we had no direct measurement on — so most of the graph was inferred, not observed.

The first instinct, at roughly T+0 to T+3m, was to treat checkout as a service throwing errors. That framing was wrong and cost us time; see the dead ends below.

## The error-rate dead end (T+3m to T+10m)

We pulled checkout's error ratio against its immediately preceding baseline. It came back *lower* during the incident — roughly a third of the baseline mean, with a lower peak too, and the comparison flagged no sustained departure. Sample counts were equal in both windows, so this was not thin data. We ran the same comparison twice from different angles and got the same answer.

The lesson a future responder should take: a service can be the epicentre and still look quieter than usual on error ratio, because requests that hang never resolve into error-status spans within the scrape interval. The ratio also told us nothing about throughput or p95/p99 — only the error series was returned, so any statement about checkout latency from this source would have been invented.

What this did usefully kill: checkout was not crash-looping, not in a high-5xx failure mode, and the alert was not explainable by checkout error telemetry alone.

> Evidence `tr_0b9e77631f73`:

```
<tool_result id="tr_0b9e77631f73" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" template="error-ratio" baseline="2026-10-14T21:51:25.273862+00:00..2026-10-14T22:23:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=129 mean=0.01037 min=0 max=0.06686 sd=0.02168
  baseline window: n=129 mean=0.02984 min=0 max=0.1141 sd=0.03327
```

> Evidence `tr_7b1e6a99853b`:

```
<tool_result id="tr_7b1e6a99853b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" template="error-ratio" baseline="2026-10-14T21:51:25.273862+00:00..2026-10-14T22:23:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=129 mean=0.01037 min=0 max=0.06686 sd=0.02168
  baseline window: n=129 mean=0.02984 min=0 max=0.1141 sd=0.03327
```

## The logging dead end (T+10m to T+18m)

We went looking for a stack trace or an upstream-error line. Checkout returned zero log lines over the 32-minute window — not zero errors, zero records of any level. We then tried frontend for a transport-level characterisation (timeout vs. refused vs. 5xx) and got the same total silence.

We briefly treated this as the finding itself and started chasing a stopped process or a broken shipping path. That was a detour. The result was marked not truncated, so partial retrieval was not the explanation, but we could not distinguish "emitted nothing" from "label selector doesn't match how these services tag their streams" from "pipeline dropped." Traces, when we finally got to them, showed checkout was very much alive and instrumented — which strongly suggests the log gap was a labeling or ingestion problem, not evidence about the incident. Do not spend twenty minutes here again; if traces are rich and logs are empty, believe the traces.

> Evidence `tr_60dbf48dd206`:

```
<tool_result id="tr_60dbf48dd206" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_60dbf48dd206>
```

> Evidence `tr_65bc5802ce4c`:

```
<tool_result id="tr_65bc5802ce4c" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_65bc5802ce4c>
```

## The change-history dead ends (T+18m to T+26m)

Standard move: look for a release to roll back. Checkout's change log over the window was completely empty — no deployments, no config edits, no flag flips. There is nothing on checkout to revert. Note the scope limit: that query covered only the seed service at zero hops, so changes on checkout's immediate dependencies were never inspected and remain unknown.

We then looked at payment, which had six entries, all from platform automation, all attach/remove operations for a traffic-shaping container on payment's network namespace. These landed as three clean create/remove pairs of about six to seven minutes each; nothing was left attached. The last removal was roughly 5.6 hours before onset. No human actor appears anywhere in payment's history. Payment is clean, and residual shaping is ruled out.

> Evidence `tr_d427856fe00c`:

```
<tool_result id="tr_d427856fe00c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T22:53:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_d427856fe00c>
```

> Evidence `tr_9f69d07de633`:

```
<tool_result id="tr_9f69d07de633" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T22:53:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" radius="candidate_cause" hops="1">
service: payment
6 changes, ranked by suspicion
  #1  5.6h before onset  2026-10-14T17:17:31.637496+00:00  platform-automation  container removed: traffic-shaping container removed from payment's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  5.9h before onset  2026-10-14T16:57:44.196924+00:00  platform-automation  container created: traffic-shaping container attached to payment's network namespace
```

## The trace that answered it (T+26m)

Tempo had ten traces and two hundred spans for checkout in the window — richly instrumented, which immediately retired the "telemetry is the blind spot" theory.

Inside a PlaceOrder trace, every dependency behaved: cart with its Redis operations, product-catalog with its SQL query, currency, payment, shipping and quote, email, and the flag-evaluation service all completed in single-digit to low-tens of milliseconds with no error status. The catalog SQL and the cart Redis calls were sub-millisecond. Payment's charge succeeded.

The one span that mattered was checkout's `orders publish` to Kafka. It carried an error reporting that the broker hostname could not be resolved by DNS, leaving no reachable brokers — and then it hung for roughly 112 to 126 seconds, consuming essentially the entire trace. That is the whole shape of the incident: one messaging-infrastructure connectivity failure holding the order path open.

Above it, the load-generator POST and the frontend-proxy ingress span both ended in error at a consistent ~15.0s ceiling while the publish span was still outstanding tens of seconds later. The proxy spans have near-zero self time, so the proxy was enforcing a deadline on a genuinely stuck backend, not misbehaving itself. Several traces show unattached spans and a frontend POST with ~15s of self time and no checkout child — the expected signature of a backend call outliving the ingress deadline.

This also rules out a broker-overload reading. The error is name resolution, not backpressure, so scaling brokers or chasing consumer lag would have been wasted effort.

> Evidence `tr_b29b080110da`:

```
<tool_result id="tr_b29b080110da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00">
service: checkout
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 8277b84a46499a1e  root load-generator/user_checkout_multi  15022.0ms  started 2026-10-14T22:53:46.925291+00:00  51 spans
  +0.0ms load-generator/user_checkout_multi 15022.0ms [self 17.4ms]
```

## Why accounting alerted

Accounting's error ratio is flat at exactly zero across both baseline and incident windows — it emitted no failing spans at all. The real signal is traffic: 53 of 76 incident samples have no defined ratio, meaning no calls at all in those intervals, against 0 such gaps in a 129-sample baseline. Accounting went quiet, it did not break.

Two readings of that zero are both wrong and worth naming. It does not mean accounting is healthy and droppable — the zero is uninformative when most intervals had no traffic to compute from. And it does not mean reduced volume; undefined means zero calls, not fewer. The baseline's clean sample count also rules out a chronic scrape artifact.

Caveat on ordering: the summary gives aggregate counts, not per-sample timestamps, so we could not pin the first gapped interval against checkout's onset. The checkout-then-accounting direction is inferred from topology — accounting is downstream of the order stream that stopped flowing — not measured.

> Evidence `tr_6689c9f9341a`:

```
<tool_result id="tr_6689c9f9341a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" template="error-ratio" baseline="2026-10-14T21:51:25.273862+00:00..2026-10-14T22:23:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=76 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

## Conclusion and fix class

Checkout cannot reach its message brokers because the broker hostname does not resolve. The publish call hangs for ~2 minutes; callers are cut off at the ~15s proxy deadline, so users see a timeout on a stuck backend. Accounting's silence is the downstream consequence of the order stream stopping. Fix class is reconnect: restore name resolution or the broker endpoint and let checkout re-establish its producer.

Confidence is medium, deliberately. We never dispatched on the broker infrastructure itself.

> Evidence `tr_b29b080110da`:

```
<tool_result id="tr_b29b080110da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00">
service: checkout
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 8277b84a46499a1e  root load-generator/user_checkout_multi  15022.0ms  started 2026-10-14T22:53:46.925291+00:00  51 spans
  +0.0ms load-generator/user_checkout_multi 15022.0ms [self 17.4ms]
```

> Evidence `tr_6689c9f9341a`:

```
<tool_result id="tr_6689c9f9341a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" template="error-ratio" baseline="2026-10-14T21:51:25.273862+00:00..2026-10-14T22:23:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=76 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

## Still open

Three gaps a follow-up should close.

First, *why* the broker hostname fails to resolve. Cluster DNS failure, a deleted Service object for the brokers, and brokers scaled to zero all produce the same span error. Nobody looked at the Kafka side at all.

Second, whether checkout's configured broker address is still correct. We established only that checkout's change log is empty; no one read the live config value. An empty change log is not the same as a verified setting.

Third, the exact onset of accounting's traffic gaps relative to checkout's. The ordering is currently an inference from topology and should be confirmed with per-sample data if the causal chain matters for remediation.

> Evidence `tr_b29b080110da`:

```
<tool_result id="tr_b29b080110da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00">
service: checkout
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 8277b84a46499a1e  root load-generator/user_checkout_multi  15022.0ms  started 2026-10-14T22:53:46.925291+00:00  51 spans
  +0.0ms load-generator/user_checkout_multi 15022.0ms [self 17.4ms]
```

> Evidence `tr_d427856fe00c`:

```
<tool_result id="tr_d427856fe00c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T22:53:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_d427856fe00c>
```

> Evidence `tr_6689c9f9341a`:

```
<tool_result id="tr_6689c9f9341a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T22:23:31.664000+00:00..2026-10-14T22:55:38.054138+00:00" template="error-ratio" baseline="2026-10-14T21:51:25.273862+00:00..2026-10-14T22:23:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=76 mean=0 min=0 max=0 sd=0
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

