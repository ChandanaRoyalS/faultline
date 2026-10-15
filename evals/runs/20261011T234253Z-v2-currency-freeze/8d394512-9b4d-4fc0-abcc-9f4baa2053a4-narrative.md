# Critical checkout-path degradation: triage began at currency, origin never established

## What we saw first

The page arrived as a critical, ten-service blast radius with currency named as the starting point. Seven services alerted together — accounting, currency, email, payment, quote, shipping — with fraud-detection following roughly sixty seconds behind the rest. Seven edges between the affected services carry no measurement at all, so the shape of the propagation was never directly observable; what we had was a list of names and a starting guess.

The guess was currency, and the whole first half of the response was spent there. Read the rest of this record knowing that currency turns out to be the one service we can positively say was healthy.

## The first hour: four queries, four empty answers

Starting from currency, the obvious moves were tried in order and all four came back blank.

Around T+5m the change log for currency returned nothing. Around T+10m the same query for flagd returned nothing, and was then repeated later by a second responder — also nothing. At roughly T+15m the span-metric error ratio for currency returned no samples. At roughly T+20m a completely unfiltered log query for currency returned not one line, and the same query against checkout returned not one line either.

The temptation at this point is to read five empty results as five exonerations. Do not. Three separate problems sit underneath them, and each one took time to notice.

> Evidence `tr_3b5b2c6af50d`:

```
<tool_result id="tr_3b5b2c6af50d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_3b5b2c6af50d>
```

> Evidence `tr_44946be55ff6`:

```
<tool_result id="tr_44946be55ff6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_44946be55ff6>
```

> Evidence `tr_3f0972f0bc05`:

```
<tool_result id="tr_3f0972f0bc05" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_3f0972f0bc05>
```

> Evidence `tr_5c2870e93ffb`:

```
<tool_result id="tr_5c2870e93ffb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" template="error-ratio" baseline="2026-10-11T22:48:31.009663+00:00..2026-10-11T23:20:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_6277e4836179`:

```
<tool_result id="tr_6277e4836179" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_6277e4836179>
```

> Evidence `tr_2bad76dcfe7d`:

```
<tool_result id="tr_2bad76dcfe7d" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_2bad76dcfe7d>
```

## Dead end one: the change-log window pointed the wrong way

Every change-history query — currency once, flagd twice — was run over a window that *begins* at the incident timestamp and runs about twenty-four hours forward. The question we meant to ask was "what changed before this started". The question we actually asked was "what changed during and after". The answer to the second question is genuinely nothing, and that does usefully close off a few theories: no rollout was still landing mid-incident, no config edit was sustaining the symptoms, and no quiet remediation or rollback muddied the recovery timeline. But the lead-up period remains completely uninspected for every service. If you are picking this up later, this is the cheapest open item on the list.

> Evidence `tr_3b5b2c6af50d`:

```
<tool_result id="tr_3b5b2c6af50d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_3b5b2c6af50d>
```

> Evidence `tr_44946be55ff6`:

```
<tool_result id="tr_44946be55ff6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_44946be55ff6>
```

> Evidence `tr_3f0972f0bc05`:

```
<tool_result id="tr_3f0972f0bc05" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_3f0972f0bc05>
```

## Dead end two: absence that was never evidence

The currency error-ratio query returned no samples in the incident window — and, critically, no samples in the thirty-two-minute baseline window before it either. A tool that compares two empty series will happily report "no sustained departure", and that verdict was briefly treated as a clean bill of health. It is not. It is an empty comparison. The equal emptiness of the baseline also kills the more interesting reading, that currency went silent *because* it broke: the silence predates the incident by at least half an hour. The likeliest explanation is that the span-metrics series simply does not exist under that service name.

The logs tell the same story twice. Both the currency and checkout log queries were unfiltered by level and both returned zero lines across the full window. Thirty-two minutes of total silence from two busy services is not what a healthy logging path looks like. Loosening the severity filter will not help — there was no filter. Treat the telemetry pipeline, or the service label used by it, as a live suspect in its own right, and treat every absence-based conclusion in this record as provisional.

> Evidence `tr_5c2870e93ffb`:

```
<tool_result id="tr_5c2870e93ffb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" template="error-ratio" baseline="2026-10-11T22:48:31.009663+00:00..2026-10-11T23:20:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_6277e4836179`:

```
<tool_result id="tr_6277e4836179" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_6277e4836179>
```

> Evidence `tr_2bad76dcfe7d`:

```
<tool_result id="tr_2bad76dcfe7d" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_2bad76dcfe7d>
```

## Dead end three: flagd

flagd was pulled in on suspicion of a flag-evaluation change and spent most of the investigation as a secondary thread. Its span error ratio across the incident window averaged slightly *below* its own prior baseline — roughly 0.3% against 0.36% — with an in-window maximum of 0.7% and a dense, continuous sample series of about 129 points in each window. That density matters: a step change at or just before onset would have been visible here, and none is. flagd was not down, was not partially failing, and was not already degraded going in. Combined with the empty change log, nothing on this thread paid off.

> Evidence `tr_30d3f3ec0d37`:

```
<tool_result id="tr_30d3f3ec0d37" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" template="error-ratio" baseline="2026-10-11T22:48:31.009663+00:00..2026-10-11T23:20:31.664000+00:00">
service: flagd
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd"}[5m]))
  incident window: n=129 mean=0.00298 min=0 max=0.007194 sd=0.0017
  baseline window: n=129 mean=0.003619 min=0.0008333 max=0.009836 sd=0.002079
```

> Evidence `tr_44946be55ff6`:

```
<tool_result id="tr_44946be55ff6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_44946be55ff6>
```

> Evidence `tr_3f0972f0bc05`:

```
<tool_result id="tr_3f0972f0bc05" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_3f0972f0bc05>
```

## The one signal that did something

Tracing, pulled around T+30m, was the only query that returned data — and it pointed away from where we were standing.

Currency appears in every sampled trace as a single span, Currency/Convert, always a child of checkout's client call. Every one of those spans completed successfully in roughly 0.3 to 1.5 milliseconds. No errors, no timeouts, no truncated children. Requests are arriving at currency and being served normally, so it is neither unreachable nor dropping work, and the naming is consistent and singular, so nothing was hiding under a second label.

Where latency actually shows up is elsewhere. Cart's Redis operations — HGET, HMSET, EXPIRE — each sit at around 300ms. Load-generator root spans carry most of the wall time as self-time. One trace shows checkout's PlaceOrder holding roughly 620ms of self-time with no downstream currency call implicated, and that trace ends without its usual payment, email and cart-empty legs.

The caveat on all of this: the four traces returned are timestamped between roughly thirty and twenty-six minutes *before* onset, and the result was truncated at four of ten. The actual onset minute was never sampled.

> Evidence `tr_80287145255b`:

```
<tool_result id="tr_80287145255b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-11T22:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00">
service: currency
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 916c23b02364cf69  root load-generator/user_checkout_multi  5913.0ms  started 2026-10-11T23:21:51.146049+00:00  65 spans
  +0.0ms load-generator/user_checkout_multi 5913.0ms [self 4881.7ms]
```

## Where it stands

Nothing was established. The only firm finding is a negative one: currency, the service we were pointed at, is the service the evidence clears. The leading unconfirmed theory is a slow dependency in the cart-to-Redis path dragging checkout past its deadlines, with checkout's fan-out explaining why payment, email, shipping, accounting and quote all alerted together.

For whoever picks this up: nothing dispatched ever looked at cart or its Redis store, which is precisely where the only observed latency sits — go there first with metrics, logs and traces around the onset minute. Re-run the change history with the window pointing backwards from onset rather than forwards. Settle whether currency and checkout are genuinely silent or merely mislabelled in the telemetry backends, because if it is the latter, everything in the two dead-end sections above needs redoing. Get a trace sampled at or after onset. And find out what the seven unmeasured edges carry, and why fraud-detection lagged the others by a minute — that delay is the only timing structure in the whole incident and nobody explained it.

> Evidence `tr_80287145255b`:

```
<tool_result id="tr_80287145255b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-11T22:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00">
service: currency
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 916c23b02364cf69  root load-generator/user_checkout_multi  5913.0ms  started 2026-10-11T23:21:51.146049+00:00  65 spans
  +0.0ms load-generator/user_checkout_multi 5913.0ms [self 4881.7ms]
```

> Evidence `tr_5c2870e93ffb`:

```
<tool_result id="tr_5c2870e93ffb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-11T23:20:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" template="error-ratio" baseline="2026-10-11T22:48:31.009663+00:00..2026-10-11T23:20:31.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3b5b2c6af50d`:

```
<tool_result id="tr_3b5b2c6af50d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T23:50:31.664000+00:00..2026-10-11T23:52:32.318337+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_3b5b2c6af50d>
```

