# Partial, intermittent order-flow errors at checkoutservice with unidentified mechanism

## What the responder saw first

The page named checkoutservice as origin, with a critical severity and a claimed blast radius of fourteen services. Seven services were on the alert list alongside checkoutservice: loadgenerator, frontend, quoteservice, accountingservice, emailservice and frauddetectionservice. That breadth set the initial expectation of a broad outage, and it was misleading. Nothing in the evidence gathered afterwards established that any of the co-alerted services were measurably degraded; they were listed, not measured. Treat the fan-out as a symptom of shared alert routing until someone actually queries those services.

The alert timestamp itself also turned out to be a red herring for onset. Work anchored on it for the first stretch of the investigation before the metric baseline showed the regime had already shifted long before.

## The one thing that was actually measured

The error-ratio baseline for checkoutservice is the only positive measurement in this record. Comparing the incident window against the four hours before it, the mean error ratio roughly doubled, from about 0.043 to about 0.079. The peak did not move at all: the maximum ratio was the same value, about 0.667, in both windows. Read that carefully, because it is the shape of the whole incident. The bursts did not get deeper; they got more frequent. Whatever went wrong made an existing intermittent failure mode fire more often rather than introducing a new, more severe one.

Two change points fall at 15:30:30 and 16:07:30 UTC. Both are more than ninety minutes before the alert fired. The elevated regime was established and running well before anyone was told about it.

Also in this series: two intervals in the incident window where the ratio is undefined, meaning checkoutservice served no traffic at all. The baseline window had no such gaps. Nobody chased this. It is one of the more promising loose threads left behind, and it is not the same thing as a healthy zero-error interval.

The series is aggregated by service name only. There is no outbound target dimension, no status-code split beyond a single error bucket, and no latency. It can tell you that checkoutservice is losing a minority of requests. It cannot tell you to whom.

> Evidence `tr_5aad0ca7eb90`:

```
<tool_result id="tr_5aad0ca7eb90" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" template="error-ratio" baseline="2026-09-10T09:42:38.878705+00:00..2026-09-10T13:46:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=975 mean=0.07867 min=0 max=0.6667 sd=0.1745
  baseline window: n=977 mean=0.04326 min=0 max=0.6667 sd=0.1575
```

## Dead end: was it something checkoutservice did to itself

The obvious first hypothesis was a release or a config change on checkoutservice. Two separate passes over the change log came back completely empty for the service: no deploys, no rollbacks, no config edits, no flag flips, no repointing of a dependency endpoint, and no operator remediation recorded as a change. That closes off the tidy answer — there is nothing to roll back here, and the investigation has to move to the runtime or to something checkoutservice calls.

One caveat a future responder must not skip. The change window used begins at the alert timestamp and runs forward about twenty-four hours. It covers during and after onset, but not the hours immediately preceding it. Since onset is now known to sit at 15:30 and 16:07, the pre-onset change surface was never genuinely looked at. The second pass claimed coverage of the 15:00-16:15 period, but the window bounds do not support that claim. Re-query the change log backwards from 14:00 before concluding there was no change.

No service other than checkoutservice and cartservice was ever queried for changes at all.

> Evidence `tr_7fd73c0fee57`:

```
<tool_result id="tr_7fd73c0fee57" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T17:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_7fd73c0fee57>
```

> Evidence `tr_04984ffc214e`:

```
<tool_result id="tr_04984ffc214e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T17:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_04984ffc214e>
```

## Dead end: the logs

The checkoutservice log selector returned nothing but info-severity order-flow lines: order placements with user id and currency, payment confirmations, confirmation-email sends, message-write successes. No errors, no warnings, no stack traces, in either the oldest or the newest segment kept. Order placement continues at a steady few-second cadence right through 17:50:45, so the process was alive and doing work on both sides of the alert.

Two things make this less conclusive than it looks. First, the result was truncated: only the oldest eight and newest thirty-two lines survived, and the omitted middle spans 13:47:27 to 17:47:49 — which swallows the alert instant entirely. The four-hour query window is what caused the truncation. A narrow re-query around 17:44-17:48 is the correct next move and was never run. Second, none of the visible lines names a downstream host, address, endpoint, or gRPC status, so the logs as selected cannot attribute the loss to any dependency. Expecting them to was a wasted assumption.

What the logs do rule out: checkoutservice did not crash or stall, no error stream persisted past 17:47:49, and the service was demonstrably healthy at the start of the four-hour window.

> Evidence `tr_4a1494514241`:

```
<tool_result id="tr_4a1494514241" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T13:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T13:46:55.058197+00:00  {"message":"[PlaceOrder] user_id=\"15b5f72e-ad1e-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T13:46:55.058091595Z"}
2026-09-10T13:46:55.076677+00:00  {"message":"payment went through (transaction_id: 0640a905-f0f3-4946-b959-af5d02a7072a)","severity":"info","timestamp":"2026-09-10T13:46:55.07659697Z"}
2026-09-10T13:46:55.082737+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T13:46:55.082603137Z"}
2026-09-10T13:46:55.083837+00:00  {"message":"Successful to write message. offset: 32136","severity":"info","timestamp":"2026-09-10T13:46:55.083782928Z"}
```

## Dead end: cartservice

Exactly one downstream was probed. The cartservice error-ratio query returned no samples in the incident window and, importantly, no samples in the preceding baseline window either. Because both are empty, the most defensible reading is that cartservice is not emitting the span-derived call counter under that service label — absent or differently-labelled instrumentation — rather than traffic having stopped at onset.

So cartservice is neither implicated nor cleared. Do not record it as healthy. Empty is not zero. Also note the interval queried was only 17:16-17:50, which does not touch the 15:30-16:10 onset period at all, so even the shape of cartservice's behaviour at the moment that matters is unobserved.

> Evidence `tr_1530bdbebf59`:

```
<tool_result id="tr_1530bdbebf59" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T17:16:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" template="error-ratio" baseline="2026-09-10T16:42:38.878705+00:00..2026-09-10T17:16:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where it was left

The locus of loss is checkoutservice: an intermittent, partial error regime, roughly eight percent of calls in aggregate, established around 15:30-16:07 and still running at the end of the observed window. The service shows no self-inflicted signature and no distress in its own logs. A live, unchanged service dropping a steady minority of requests points at something beneath or downstream of it, but five edges out of checkoutservice were never measured and the one that was probed returned nothing usable.

Mechanism unidentified. Confidence low. No fix class assigned, because there is nothing yet to fix against.

> Evidence `tr_5aad0ca7eb90`:

```
<tool_result id="tr_5aad0ca7eb90" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" template="error-ratio" baseline="2026-09-10T09:42:38.878705+00:00..2026-09-10T13:46:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=975 mean=0.07867 min=0 max=0.6667 sd=0.1745
  baseline window: n=977 mean=0.04326 min=0 max=0.6667 sd=0.1575
```

> Evidence `tr_04984ffc214e`:

```
<tool_result id="tr_04984ffc214e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T17:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_04984ffc214e>
```

> Evidence `tr_4a1494514241`:

```
<tool_result id="tr_4a1494514241" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T13:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T13:46:55.058197+00:00  {"message":"[PlaceOrder] user_id=\"15b5f72e-ad1e-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T13:46:55.058091595Z"}
2026-09-10T13:46:55.076677+00:00  {"message":"payment went through (transaction_id: 0640a905-f0f3-4946-b959-af5d02a7072a)","severity":"info","timestamp":"2026-09-10T13:46:55.07659697Z"}
2026-09-10T13:46:55.082737+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T13:46:55.082603137Z"}
2026-09-10T13:46:55.083837+00:00  {"message":"Successful to write message. offset: 32136","severity":"info","timestamp":"2026-09-10T13:46:55.083782928Z"}
```

## What to do first next time

Three concrete gaps, in the order I would attack them.

One: get a per-target breakdown of checkoutservice's outbound calls — RPC target, status code, and latency — across 15:00 to 18:00. Everything about the current record is blocked on the absence of that dimension. The existing error-ratio series is service-aggregated and structurally cannot answer which call fails.

Two: look at the hours before 15:30. Both the change-log passes and the cartservice probe used windows that start after onset. Widen backwards and re-run, and extend the change query to the other alerted services, none of which have been examined.

Three: explain the two intervals where checkoutservice served no traffic. Restarts, out-of-memory kills, and CPU and memory series were never sampled. Those gaps are the strongest hint that the answer is in the runtime beneath the service rather than in its call graph, and they cost nothing to check.

> Evidence `tr_5aad0ca7eb90`:

```
<tool_result id="tr_5aad0ca7eb90" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" template="error-ratio" baseline="2026-09-10T09:42:38.878705+00:00..2026-09-10T13:46:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=975 mean=0.07867 min=0 max=0.6667 sd=0.1745
  baseline window: n=977 mean=0.04326 min=0 max=0.6667 sd=0.1575
```

> Evidence `tr_1530bdbebf59`:

```
<tool_result id="tr_1530bdbebf59" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T17:16:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" template="error-ratio" baseline="2026-09-10T16:42:38.878705+00:00..2026-09-10T17:16:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_7fd73c0fee57`:

```
<tool_result id="tr_7fd73c0fee57" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T17:46:45.583000+00:00..2026-09-10T17:50:52.287295+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_7fd73c0fee57>
```

