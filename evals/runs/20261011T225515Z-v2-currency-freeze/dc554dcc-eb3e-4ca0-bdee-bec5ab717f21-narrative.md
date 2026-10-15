# Checkout requests stall at a uniform 15-second ceiling with currency silent

## What was visible, in order

The page arrived broad rather than deep: seven services alerting at once (accounting, currency, email, fraud-detection, payment, quote, shipping), a blast radius of ten, critical severity, seed at currency. Seven of the edges crossed had no measurements behind them, so much of this record is reasoning across gaps.

The trace store was the first source with substance. Ten checkout traces in the half hour before cutoff all terminated at almost exactly 15.00s wall clock — a flat ceiling, not a distribution, which reads as a budget being enforced rather than work taking time. The whole duration sat as self time on a childless frontend POST span, and ERROR markers appeared only on the load-generator and frontend-proxy hops, the two places a caller marks a request it abandoned. Nothing downstream reported an error of its own.

The decisive detail was an absence: no currency-conversion span appeared anywhere in the ten traces. The only downstream calls under checkout were cart GetCart and product-catalog GetProduct, finishing in roughly 0.6–4.7ms with Redis and SQL children under ~2ms. Checkout's own spans were sub-millisecond to 4ms and done within ~50ms of trace start.

> Evidence `tr_a4f76ff99b8e`:

```
<tool_result id="tr_a4f76ff99b8e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-11T22:32:31.664000+00:00..2026-10-11T23:04:33.979298+00:00">
service: checkout
10 trace(s) shown of 10 found, 110 spans; offsets are from each trace's root

trace ade0ea7f6c0d8517  root load-generator/user_checkout_single  15013.0ms  started 2026-10-11T23:00:39.184773+00:00  11 spans, 2 unattached
  +0.0ms load-generator/user_checkout_single 15013.0ms [self 7.3ms]
```

## Dead ends worth inheriting

Currency's own telemetry produced nothing. A query for every log line across a ~62-minute window returned zero records of any severity, and the span-metrics error ratio returned no samples in the incident window. The expensive part: the baseline window two hours earlier was equally empty. The attractive inference — telemetry stopped when the service stopped — does not hold, because the silence predates onset by hours and may simply mean currency never emitted under that service name. Request rate and latency percentiles were never pulled and remain uncovered.

The flag-service detour closed cleanly and taught the main lesson. flagd's logs were just as empty, but its metrics showed a dense unbroken series (129 samples in each window), an error ratio below baseline with roughly half the mean, and error rates a fraction of a percent of calls. flagd was alive and healthier than usual while checkout failed. Log silence alone proves nothing — read currency's silence with the same caution.

Both change-history queries came back empty for currency and flagd, but both ran forward from the onset timestamp for about twenty-four hours. They close only in-incident and post-incident changes. The hours before onset were never searched. If this recurs, search backwards first.

> Evidence `tr_6684ce4716c9`:

```
<tool_result id="tr_6684ce4716c9" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T22:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_6684ce4716c9>
```

> Evidence `tr_eda8554af50c`:

```
<tool_result id="tr_eda8554af50c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-11T21:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00" template="error-ratio" baseline="2026-10-11T19:00:29.348702+00:00..2026-10-11T21:02:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_da87be3320ed`:

```
<tool_result id="tr_da87be3320ed" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T22:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00">
no log lines matched {service="flagd"} over this window
</tool_result:tr_da87be3320ed>
```

> Evidence `tr_5012373073f3`:

```
<tool_result id="tr_5012373073f3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T22:32:31.664000+00:00..2026-10-11T23:04:33.979298+00:00" template="error-ratio" baseline="2026-10-11T22:00:29.348702+00:00..2026-10-11T22:32:31.664000+00:00">
service: flagd
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd"}[5m]))
  incident window: n=129 mean=0.002819 min=0 max=0.00722 sd=0.001871
  baseline window: n=129 mean=0.005202 min=0 max=0.0274 sd=0.007008
```

> Evidence `tr_0991d4e1e55f`:

```
<tool_result id="tr_0991d4e1e55f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_0991d4e1e55f>
```

> Evidence `tr_6636625dc1d7`:

```
<tool_result id="tr_6636625dc1d7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_6636625dc1d7>
```

## Where it landed, and what is still open

The surviving reconstruction: callers of currency hang until their own deadline fires and mark the request failed client-side, while currency produces no error, no rejection, and no reachability complaint. Checkout's own work is fast, the conversion step is simply missing, and the time is charged as self time because nothing downstream ever answered — the shape of a stopped process whose socket still accepts. Confidence medium; fix class is a restart.

Three things were never established. There is no independent onset anchor for currency, since its silence begins hours early. Change history before onset is unsearched. And there is no direct process-state evidence at all — no restarts, liveness, CPU or memory, no traces pulled against currency or the frontend, and frontend trace assembly was known incomplete (11 spans with 2 unattached per trace). The blocking span was inferred from the shape of a hole; it was never seen.

Fastest disambiguators next time: query change history backwards from onset, pull currency's liveness and restart history directly, and confirm whether currency emits under a different service label before treating its silence as signal.

> Evidence `tr_a4f76ff99b8e`:

```
<tool_result id="tr_a4f76ff99b8e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-11T22:32:31.664000+00:00..2026-10-11T23:04:33.979298+00:00">
service: checkout
10 trace(s) shown of 10 found, 110 spans; offsets are from each trace's root

trace ade0ea7f6c0d8517  root load-generator/user_checkout_single  15013.0ms  started 2026-10-11T23:00:39.184773+00:00  11 spans, 2 unattached
  +0.0ms load-generator/user_checkout_single 15013.0ms [self 7.3ms]
```

> Evidence `tr_eda8554af50c`:

```
<tool_result id="tr_eda8554af50c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-11T21:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00" template="error-ratio" baseline="2026-10-11T19:00:29.348702+00:00..2026-10-11T21:02:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_6684ce4716c9`:

```
<tool_result id="tr_6684ce4716c9" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T22:02:31.664000+00:00..2026-10-11T23:04:33.979298+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_6684ce4716c9>
```

