# Seven services alert at once, currency named as origin — no mechanism found

## What the board showed at the start

The page came in as a critical, ten-service blast radius with currency named as the origin point. Seven services alerted together within the same second: accounting, currency, email, fraud-detection, payment, quote, shipping. Triage had crossed seven edges it had no measurements for, which is worth flagging up front — the shape of the alert set was inferred, not observed end to end.

The thing a responder should carry into this record: by the end of the investigation, the only service anyone actually dispatched a probe against was currency (plus flagd and frontend as follow-ups). Six of the seven alerting services were never queried at all. Everything below is a picture of one corner of the board.

## First moves against currency (T+0 to roughly T+10m)

Standard order: metrics, logs, change history, traces.

The error-ratio query against currency returned nothing. Not a flat line, not zeros — zero samples, in both the incident window and the pre-incident baseline. That matters. A service that broke would show a baseline and then a departure from it. A service with no samples in either window is a service whose span metrics never reached the metrics store under that label, or never reached it at all.

Logs for currency over the same 32-minute window: also empty. Not filtered-empty — the selector was broad, no filter expression, nothing matched. So this was not a case of errors being suppressed while normal chatter continued; there was no chatter either.

Change history for currency across a full day back: nothing. No deploy, no restart, no config edit, no rollback. The change-driven explanation closed cleanly here.

> Evidence `tr_442706f3c61c`:

```
<tool_result id="tr_442706f3c61c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00" template="error-ratio" baseline="2026-10-13T07:34:09.269054+00:00..2026-10-13T08:06:16.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1c2ff94d632d`:

```
<tool_result id="tr_1c2ff94d632d" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_1c2ff94d632d>
```

> Evidence `tr_b11242a221e5`:

```
<tool_result id="tr_b11242a221e5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T08:36:16.664000+00:00..2026-10-13T08:38:24.058946+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_b11242a221e5>
```

## Traces contradicted the alert

Tempo was the one source that had something to say about currency, and what it said was that currency was fine. The Convert server spans appear across every trace returned, finishing between roughly 0.3 and 2.1 milliseconds, none carrying an error status. Checkout's client spans calling into currency are equally clean. Currency was reachable, was taking traffic, and was answering fast.

Two caveats a responder should not skip. First, the result set was truncated — four of ten traces were visible, so six were never inspected. Second, the trace window reached back an hour before the alert, and nobody confirmed whether any of the four healthy samples actually fall after the alert moment or whether all four are pre-incident. That question is still open and it is the cheapest one left on the board.

> Evidence `tr_37561b9fb5d8`:

```
<tool_result id="tr_37561b9fb5d8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T07:36:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
service: currency
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 205fb90d189cf364  root load-generator/user_checkout_multi  71.2ms  started 2026-10-13T07:57:57.156410+00:00  65 spans
  +0.0ms load-generator/user_checkout_multi 71.2ms [self 27.8ms]
```

## The flagd detour (dead end, worth keeping)

When seven services break in the same second with no deploy to point at, the shared configuration service is the obvious next suspect — one toggle, seven blast radii, no per-service change record. That reasoning is sound and it is why the detour happened.

It did not hold. flagd's change history across a full day back was empty: no flag-value edits, no config changes, no rollouts. And flagd's error ratio through the incident window sat around 0.0025 mean against a baseline of 0.0018 — a 1.37x shift, which sounds like something until you notice the standard deviation is comparable to the mean in both windows. That is sporadic noise, not a regime change. Peak was around 0.008. Nothing there.

Keep this dead end. The next responder will have the same instinct and should not spend the same twenty minutes.

> Evidence `tr_3e62e639f356`:

```
<tool_result id="tr_3e62e639f356" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T08:36:16.664000+00:00..2026-10-13T08:38:24.058946+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_3e62e639f356>
```

> Evidence `tr_1f876997ef8a`:

```
<tool_result id="tr_1f876997ef8a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00" template="error-ratio" baseline="2026-10-13T07:34:09.269054+00:00..2026-10-13T08:06:16.664000+00:00">
service: flagd
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd"}[5m]))
  incident window: n=129 mean=0.002475 min=0 max=0.008048 sd=0.002292
  baseline window: n=129 mean=0.001806 min=0 max=0.006383 sd=0.002008
```

## The frontend check, and what it accidentally revealed

Frontend was queried on the theory that if currency were degraded, its caller would be logging downstream failures. Frontend produced no log lines at all over the same window — again a broad selector with no filter, so the emptiness is real rather than an artifact of how the query was written.

This was meant to be a confirmation step and instead became the most interesting result on the board. Two services with no architectural reason to go quiet together went quiet together, over the same 32 minutes. Combined with currency having no span metrics even in the *baseline* — before anything was supposed to be wrong — the simpler reading is that the observation pipeline had a hole in it during this window, not that two services independently stopped speaking.

> Evidence `tr_b302ee9e949f`:

```
<tool_result id="tr_b302ee9e949f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_b302ee9e949f>
```

> Evidence `tr_1c2ff94d632d`:

```
<tool_result id="tr_1c2ff94d632d" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_1c2ff94d632d>
```

> Evidence `tr_442706f3c61c`:

```
<tool_result id="tr_442706f3c61c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00" template="error-ratio" baseline="2026-10-13T07:34:09.269054+00:00..2026-10-13T08:06:16.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

## Where this landed

No verdict. Confidence low, no fix class, nothing to action.

The honest summary is that every probe aimed at currency either came back empty or came back healthy, and the pattern of emptiness looks more like missing telemetry than like a broken service. If that reading is right, the service that actually failed is one of the six that alerted and was never dispatched against — the investigation anchored on the named origin and never moved off it.

> Evidence `tr_442706f3c61c`:

```
<tool_result id="tr_442706f3c61c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00" template="error-ratio" baseline="2026-10-13T07:34:09.269054+00:00..2026-10-13T08:06:16.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1c2ff94d632d`:

```
<tool_result id="tr_1c2ff94d632d" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_1c2ff94d632d>
```

> Evidence `tr_37561b9fb5d8`:

```
<tool_result id="tr_37561b9fb5d8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T07:36:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
service: currency
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 205fb90d189cf364  root load-generator/user_checkout_multi  71.2ms  started 2026-10-13T07:57:57.156410+00:00  65 spans
  +0.0ms load-generator/user_checkout_multi 71.2ms [self 27.8ms]
```

## What to do first if this recurs

In rough priority order:

Query the other six alerting services — accounting, payment, quote, shipping, email, fraud-detection. All six alerted, none were touched. This is the largest unexamined surface and it is where the answer most likely sits.

Settle the telemetry question before trusting any other emptiness. Ask whether *any* service produced logs in that window. If the answer is yes, then currency's and frontend's silence is a genuine condition and becomes a strong signal. If the answer is no, every empty result in this record is uninformative and the investigation restarts from different sources.

Map the seven unmeasured edges. Seven services alerting in the same second usually share something — a cache, a datastore, a broker. Those edges were crossed during triage without measurement, so a shared dependency could be sitting behind them unexamined.

Re-run the trace query bounded tightly to after the alert moment, and page past the truncation. Four healthy traces out of ten, drawn from a window that starts an hour early, does not establish that currency was healthy *during* the incident.

> Evidence `tr_37561b9fb5d8`:

```
<tool_result id="tr_37561b9fb5d8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T07:36:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
service: currency
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 205fb90d189cf364  root load-generator/user_checkout_multi  71.2ms  started 2026-10-13T07:57:57.156410+00:00  65 spans
  +0.0ms load-generator/user_checkout_multi 71.2ms [self 27.8ms]
```

> Evidence `tr_b302ee9e949f`:

```
<tool_result id="tr_b302ee9e949f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T08:06:16.664000+00:00..2026-10-13T08:38:24.058946+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_b302ee9e949f>
```

