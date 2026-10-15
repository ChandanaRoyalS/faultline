# Seven services alert at once while currency says nothing

## What the responder saw first

The page arrived as a wide one: seven services alerting at effectively the same instant — accounting, currency, email, fraud-detection, payment, quote and shipping — with a stated blast radius of ten services and critical severity. Triage pointed at currency as the origin, mostly on topology grounds: it sits downstream of most of the alerting callers, and a single shared dependency is the cheapest explanation for six callers lighting up together.

The first thing worth recording is the shape of the signal, not its content. Nothing in the initial page described a failure mode. There were no error messages attached, no obvious latency graph, no crash notice. The simultaneity was the only real evidence, and simultaneity across callers of a common dependency is what the rest of the investigation tried to explain.

## Going to currency's own logs (T+3m)

The obvious first move was to read currency's log narrative over the onset window. The query was deliberately unfiltered — no level filter, no substring — covering roughly half an hour that straddled onset. It returned nothing. Not a single line, of any level, from that service name over the whole window.

That is a strong but ambiguous result. It rules out the comfortable outcomes: there is no exception, no panic, no stack trace, no "cannot reach X" complaint sitting in the store waiting to name the cause. It also rules out the benign reading that currency was fine and simply quiet — a serving process normally emits request or lifecycle lines, and total silence is not what healthy looks like.

What it does not do is distinguish a wedged process from a log pipeline that never carried this service's lines in the first place. That ambiguity was never closed and is the central weakness of this record.

> Evidence `tr_300a9266f8bb`:

```
<tool_result id="tr_300a9266f8bb" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T04:55:46.664000+00:00..2026-10-14T05:27:50.373824+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_300a9266f8bb>
```

## Metrics on currency: the second empty hand (T+9m)

With no logs, the next stop was span metrics — an error-ratio query against currency. This too came back empty, and in a way that actively damaged the earlier inference: the baseline window preceding onset was equally empty. The series is absent on both sides of the incident boundary.

Symmetric absence means the gap predates the incident. Whatever is wrong with currency's visibility in span metrics, it did not start when the pages fired. The most likely readings are missing instrumentation or a service-name label that does not match what was queried. Either way, this metric is not a usable diagnostic surface for currency in this incident, and no further queries against it are worth a responder's time.

This also means the "step vs ramp" question — did currency degrade suddenly or gradually — was never answered. Only the error-ratio template was run; no request-rate or latency-percentile data was collected.

> Evidence `tr_7928919563fa`:

```
<tool_result id="tr_7928919563fa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-14T04:55:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" template="error-ratio" baseline="2026-10-14T04:23:42.954176+00:00..2026-10-14T04:55:46.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

## Dead end: the change surface on currency

A natural hypothesis for a service disappearing from two independent backends at once is that something was changed about it: a rename, an SDK or exporter swap, a sampling or log-level adjustment, a collector endpoint push. All of these fall inside the change log's scope.

The change history for currency over the preceding day was empty. No deployments, no renames, no instrumentation edits, no scoped config pushes. Note the distinction that matters here: the record is empty, not missing. The backend answered and had nothing to report.

So the most common benign explanation — telemetry still flowing under a different name — is off the table, and so is the release-boundary correlation a responder normally reaches for. Whatever caused this sits outside the tracked change surface, or came through a path the change log does not capture.

> Evidence `tr_1837bdd6f4d8`:

```
<tool_result id="tr_1837bdd6f4d8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T05:25:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_1837bdd6f4d8>
```

## Dead end: chasing flagd

A meaningful fraction of the investigation went into flagd, on the theory that a shared flag-evaluation service failing or receiving an edit could fan out to many callers at once. This produced nothing, and the reader should know it was checked so they do not repeat it.

flagd's error ratio over the incident window averaged roughly a third of a percent against a baseline of roughly two-tenths of a percent. That is a 1.5x shift in the mean, but the ranges overlap, the variance is comparable, and the peak in the incident window stays under one percent. Sample coverage was identical on both sides (129 points each), so the comparison is not distorted by thinned data around onset. No sustained departure. An outage or crash-loop would have pushed the maximum far above baseline; it did not. And since flagd's own span error ratio stayed near zero, errors seen elsewhere were not sourced from flagd span failures.

A substring search for "error" in flagd logs across the same window returned zero lines. Evaluation errors and provider/sync connection failures are conventionally logged at error level, so both of those are ruled out — though with a caveat worth preserving: no unfiltered baseline query was run against flagd, so this result cannot distinguish a quiet service from one whose logs are not reaching the store at all.

The change history for flagd was likewise empty — two separate queries, same answer. No deploy, no flag-definition edit, no config push, and no quiet remediation that would make any later recovery a change artifact rather than natural resolution.

One honest defect in both flagd change queries: the window as actually executed begins at the incident timestamp and runs forward about a day. It does not cover the hours immediately preceding onset. A flagd change made shortly before the page would not appear in this evidence. The question as asked is only partly answered.

> Evidence `tr_9bc4026a5a66`:

```
<tool_result id="tr_9bc4026a5a66" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T04:55:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" template="error-ratio" baseline="2026-10-14T04:23:42.954176+00:00..2026-10-14T04:55:46.664000+00:00">
service: flagd
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="flagd"}[5m]))
  incident window: n=129 mean=0.003272 min=0 max=0.00823 sd=0.001662
  baseline window: n=129 mean=0.002163 min=0 max=0.005556 sd=0.001092
```

> Evidence `tr_b5227c17ac05`:

```
<tool_result id="tr_b5227c17ac05" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T04:55:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" contains="error">
no log lines matched {service="flagd"} |= "error" over this window
</tool_result:tr_b5227c17ac05>
```

> Evidence `tr_f6931df3ac13`:

```
<tool_result id="tr_f6931df3ac13" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T05:25:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_f6931df3ac13>
```

> Evidence `tr_8519d63075e0`:

```
<tool_result id="tr_8519d63075e0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T05:25:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_8519d63075e0>
```

## Where the reasoning landed

The working conclusion is a wedged currency process: one whose listening socket still accepts connections but which never completes work, leaving callers to hang until their own deadlines expire and alert. This fits the two facts that were established — six callers alerting at the same instant, and the suspected culprit producing no failure narrative at all, not even a complaint about being unable to reach something downstream.

But this is inference from silence, and the record should be blunt about that. Silence is consistent with a wedged process; it is also consistent with currency's logs never having been collected under that service name. The span-metric evidence actively supports the second reading, since the series was absent before the incident as well. The stated fix class is a restart, which is a reasonable first action precisely because it is cheap and discriminating: if a restart clears the callers' symptoms, the wedged-process reading is confirmed retroactively. Confidence in the conclusion as written is low.

> Evidence `tr_300a9266f8bb`:

```
<tool_result id="tr_300a9266f8bb" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T04:55:46.664000+00:00..2026-10-14T05:27:50.373824+00:00">
no log lines matched {service="currency"} over this window
</tool_result:tr_300a9266f8bb>
```

> Evidence `tr_7928919563fa`:

```
<tool_result id="tr_7928919563fa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-14T04:55:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" template="error-ratio" baseline="2026-10-14T04:23:42.954176+00:00..2026-10-14T04:55:46.664000+00:00">
service: currency
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="currency"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_1837bdd6f4d8`:

```
<tool_result id="tr_1837bdd6f4d8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T05:25:46.664000+00:00..2026-10-14T05:27:50.373824+00:00" radius="seed" hops="0">
no changes recorded for currency over this window
</tool_result:tr_1837bdd6f4d8>
```

## What a future responder should do differently

Three gaps dominate.

First, no pre-incident baseline log query was ever run for currency. The entire "went silent" inference rests on an absence that was only measured inside the incident window plus thirty minutes before it. Run an unfiltered currency log query over a clearly normal period — hours or days earlier. If it is also empty, the central inference of this record collapses and the real story is an observability gap, not a wedged service.

Second, no caller-side data was collected at all. Whether the six alerting callers were hanging to their deadlines or failing fast is unverified, and it is the single cheapest discriminator available. Latency percentiles or traces from accounting, payment, quote or shipping would settle it in minutes and would also reveal whether currency spans appear at all from the caller's side — which would answer the label-mismatch question for free.

Third, nothing was gathered about currency's process lifecycle: no restart counts, no memory-kill records, no container events. For a wedged-process hypothesis this is the most direct evidence there is, and it was never consulted.

Finally, scope. Ten services were affected; two were examined. Seven unmeasured edges were crossed in reaching currency from the alerting set. The path to the conclusion is therefore mostly assumed rather than traced.

