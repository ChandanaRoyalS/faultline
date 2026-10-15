# Frontend gRPC calls refused by a backend on port 7070

## How it looked from the chair

Alerts arrived from frontend-proxy, load-generator and frontend at roughly the same moment, with a blast radius spanning nine services and a severity of critical. The seed was frontend-proxy, so that is where the first dispatches went. Time offsets in this record are measured from the start of the investigation window; the relevant anchors are a first connection-level error at T+4m, a statistical change point at T+5m on two services, the last frontend log line at T+14m, and a second threshold crossing at T+28m.

The shape of the failure mattered more than its size. Error ratios on frontend-proxy went from a baseline mean near 1.8% to about 11.2% during the window — roughly six baseline standard deviations out, peaking near 30% and dipping back to zero between bursts. Frontend showed the same pattern more sharply: a jump of about 12.5x over a very quiet preceding half hour, with a dispersion larger than the mean. Both crossed at T+5m. That told us two things early: this was real and not monitoring noise, and it was not a total outage. Most requests kept succeeding the whole time, which is consistent with only certain request paths being affected.

> Evidence `tr_39825163a4f0`:

```
<tool_result id="tr_39825163a4f0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" template="error-ratio" baseline="2026-10-14T05:07:48.433427+00:00..2026-10-14T05:39:46.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.1117 min=0 max=0.2989 sd=0.1177
  baseline window: n=128 mean=0.0177 min=0 max=0.05431 sd=0.01571
```

> Evidence `tr_c9826424f3bd`:

```
<tool_result id="tr_c9826424f3bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" template="error-ratio" baseline="2026-10-14T05:07:48.433427+00:00..2026-10-14T05:39:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.08516 min=0 max=0.3 sd=0.1152
  baseline window: n=128 mean=0.006787 min=0 max=0.0492 sd=0.01455
```

## The line that actually named the problem

Frontend's own logs carried the finding. From T+4m — about a minute before the metric change point on either service — frontend repeatedly failed gRPC calls to a single backend endpoint, IP 172.18.0.24 on port 7070, with status 14 UNAVAILABLE and a connection-refused cause. The errors run through at least T+14m.

Three details narrowed this a long way. The failure is an immediate TCP-level rejection, not a deadline or a timeout, so slowness, pool saturation and load-shedding are all off the table — nothing was listening on that port and no request ever waited on a slow peer. The error names a concrete resolved IPv4 address, so name resolution worked; the break is at connection establishment, not discovery. And the embedded 'last error' timestamp lags the emission time — lines emitted around T+14m all reference a connect attempt from roughly T+12m — which says the client was replaying a stuck connection failure rather than re-attempting the connect per request. That stickiness is why a restart is the indicated fix class rather than a config edit.

Port 7070 matches the normal cart address. That identification is inference from the port number, not observation of the service itself. Treat it as a lead, not a fact.

> Evidence `tr_83aa4bdc809b`:

```
<tool_result id="tr_83aa4bdc809b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T05:43:36.308379+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.24:7070 (2026-10-14T05:43:36.301Z)
2026-10-14T05:43:36.308552+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1971)
2026-10-14T05:43:36.308561+00:00      at new Promise (<anonymous>) {
2026-10-14T05:43:36.308580+00:00    code: 14,
```

## Dead ends, in the order we walked them

Frontend-proxy change history: empty across a full day. No deploy, no config edit, nothing. Useful as an exoneration of the proxy, but the query was scoped to the seed service with zero hops, so it says nothing about frontend or any downstream. Worth noting the window queried ran forward from the incident hour rather than backward, so the hours immediately before onset were not actually covered by that lookup.

Frontend-proxy logs: zero lines for the entire window, including the quiet period before onset. This is almost certainly a shipping or labelling gap rather than the proxy going silent at onset — if it had been healthy and then broken, there would be pre-onset lines. The operational consequence is that no 'the proxy saw no errors' conclusion from this source is safe. Someone should fix the label or the pipeline before the next incident.

Sampled traces through frontend-proxy: ten traces, 164 spans, and not one error span among them. Every chain completed to a terminal leaf, root durations between about 3ms and 27ms, nothing near a timeout boundary. This looked like contradictory evidence at first and cost time; it is better read as sampling that never caught the failing path. It did usefully clear several suspects — proxy routing and self-time were negligible, product-catalog SQL leaves stayed in the 0.2–2.0ms range, cart's Redis operations completed in 0.1–2.6ms with no errors. The one 'degrading hop' the tooling flagged resolved to the load-generator's own client span holding 88–98% self-time, which is client-side or sampling-side accounting, not backend latency. Product-reviews' AI-assistant call was the heaviest genuine server-side work at about 20ms, and it was fine.

Frontend change history: two entries, both by platform-automation, both touching the cart address variable — a set at roughly T-65m and a revert at roughly T-57m. The pair is self-cancelling, so frontend's configuration at onset matched its earlier baseline, and the transient override (a different port, 7071) was not in effect when the failures began. No frontend deploy, release or flag change appears anywhere in the day. This was the most tempting false lead in the record: it is the only recorded activity anywhere near the incident and it names the right subsystem, but it is over an hour away from onset and reverted. Its real value was supplying the port mapping that let us guess what sits at 7070.

Both error-ratio metrics were aggregated by service name only, with no route, upstream, or peer dimension. Neither can implicate or clear any individual dependency. Do not re-run them expecting a breakdown.

> Evidence `tr_5be4a3a171b2`:

```
<tool_result id="tr_5be4a3a171b2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T06:09:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" radius="seed" hops="0">
no changes recorded for frontend-proxy over this window
</tool_result:tr_5be4a3a171b2>
```

> Evidence `tr_34f5c2d8163e`:

```
<tool_result id="tr_34f5c2d8163e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00">
no log lines matched {service="frontend-proxy"} over this window
</tool_result:tr_34f5c2d8163e>
```

> Evidence `tr_a469193f329f`:

```
<tool_result id="tr_a469193f329f" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00">
service: frontend-proxy
10 trace(s) shown of 10 found, 164 spans; offsets are from each trace's root

trace 250f9f1b3e8c6555  root load-generator/user_browse_product  8.0ms  started 2026-10-14T05:55:24.604135+00:00  10 spans
  +0.0ms load-generator/user_browse_product 8.0ms [self 0.8ms]
```

> Evidence `tr_1faaffc58867`:

```
<tool_result id="tr_1faaffc58867" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T06:09:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" radius="seed" hops="0">
service: frontend
2 changes, ranked by suspicion
  #1  1.4h before onset  2026-10-14T04:43:01.757364+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  1.6h before onset  2026-10-14T04:34:34.057124+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_39825163a4f0`:

```
<tool_result id="tr_39825163a4f0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" template="error-ratio" baseline="2026-10-14T05:07:48.433427+00:00..2026-10-14T05:39:46.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.1117 min=0 max=0.2989 sd=0.1177
  baseline window: n=128 mean=0.0177 min=0 max=0.05431 sd=0.01571
```

> Evidence `tr_c9826424f3bd`:

```
<tool_result id="tr_c9826424f3bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" template="error-ratio" baseline="2026-10-14T05:07:48.433427+00:00..2026-10-14T05:39:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.08516 min=0 max=0.3 sd=0.1152
  baseline window: n=128 mean=0.006787 min=0 max=0.0492 sd=0.01455
```

## Where it landed, and what is still open

Working conclusion, held at low confidence: the process behind 172.18.0.24:7070 stopped accepting connections shortly before T+4m, frontend held a stuck failed connection to it, and the bursty partial error elevation on frontend and frontend-proxy is that failure relayed outward. Neither alerting service is the origin. Indicated remediation is a restart of the backend, with frontend restarted or forced to re-resolve if the stuck connection persists.

Open items for whoever picks this up:

First, no dispatch ever looked at the service behind that address. Its identity is inferred from a port number. Confirm what it is, then pull its logs, metrics, change record and restart history. Without that the mechanism is unnamed.

Second, there is a second error family in the same window that nobody explained: gRPC 13 INTERNAL on the shipping-quote path, caused by an HTTP 400 from the email service. That path was reachable and responding, so it is a different failure mode entirely and may be an unrelated concurrent problem. It was set aside, not resolved.

Third, frontend log lines stop at T+14m with nothing for the remaining eighteen minutes of the window. That is consistent with errors ceasing, but given the proxy's log pipeline was demonstrably broken, do not assume recovery from an absence of lines. The second metric threshold crossing at T+28m argues against a clean stop.

> Evidence `tr_83aa4bdc809b`:

```
<tool_result id="tr_83aa4bdc809b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T05:43:36.308379+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.24:7070 (2026-10-14T05:43:36.301Z)
2026-10-14T05:43:36.308552+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1971)
2026-10-14T05:43:36.308561+00:00      at new Promise (<anonymous>) {
2026-10-14T05:43:36.308580+00:00    code: 14,
```

> Evidence `tr_39825163a4f0`:

```
<tool_result id="tr_39825163a4f0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" template="error-ratio" baseline="2026-10-14T05:07:48.433427+00:00..2026-10-14T05:39:46.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.1117 min=0 max=0.2989 sd=0.1177
  baseline window: n=128 mean=0.0177 min=0 max=0.05431 sd=0.01571
```

> Evidence `tr_a469193f329f`:

```
<tool_result id="tr_a469193f329f" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00">
service: frontend-proxy
10 trace(s) shown of 10 found, 164 spans; offsets are from each trace's root

trace 250f9f1b3e8c6555  root load-generator/user_browse_product  8.0ms  started 2026-10-14T05:55:24.604135+00:00  10 spans
  +0.0ms load-generator/user_browse_product 8.0ms [self 0.8ms]
```

> Evidence `tr_5be4a3a171b2`:

```
<tool_result id="tr_5be4a3a171b2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T06:09:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" radius="seed" hops="0">
no changes recorded for frontend-proxy over this window
</tool_result:tr_5be4a3a171b2>
```

> Evidence `tr_1faaffc58867`:

```
<tool_result id="tr_1faaffc58867" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T06:09:46.664000+00:00..2026-10-14T06:11:44.894573+00:00" radius="seed" hops="0">
service: frontend
2 changes, ranked by suspicion
  #1  1.4h before onset  2026-10-14T04:43:01.757364+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  1.6h before onset  2026-10-14T04:34:34.057124+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_34f5c2d8163e`:

```
<tool_result id="tr_34f5c2d8163e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T05:39:46.664000+00:00..2026-10-14T06:11:44.894573+00:00">
no log lines matched {service="frontend-proxy"} over this window
</tool_result:tr_34f5c2d8163e>
```

