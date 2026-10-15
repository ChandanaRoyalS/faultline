# Checkout crash loop surfacing as 15-second cut-offs at the edge

## What the responder saw first

Paging came from the edge, not from the thing that broke. frontend-proxy and load-generator alerted; the declared origin was frontend-proxy and the blast radius was three services, severity warning. The first instinct — read frontend's own error ratio and confirm the edge is burning — produced the opposite of the expected picture. Frontend's span-derived error ratio over the window averaged roughly 2.5% against a baseline of about 5.7%, i.e. slightly better than normal, with no sustained departure flagged. frontend-proxy told a similar story: about 3.2% in-window against about 5.4% baseline, with one isolated spike to roughly 14.4% about a minute after onset and nothing elevated before it. Both series were much more dispersed than baseline and both touched zero at points, which reads as thinned or intermittent traffic making a ratio noisy rather than as rising failures. If you arrive at this record expecting an error-rate story at the edge, stop: the user-visible harm here does not show up as errors in the aggregate ratios.

> Evidence `tr_4b7fb366dc99`:

```
<tool_result id="tr_4b7fb366dc99" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" template="error-ratio" baseline="2026-10-13T04:05:18.560474+00:00..2026-10-13T04:37:16.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.02501 min=0 max=0.05693 sd=0.02244
  baseline window: n=128 mean=0.05694 min=0.04381 max=0.07315 sd=0.00705
```

> Evidence `tr_03e3dd383648`:

```
<tool_result id="tr_03e3dd383648" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" template="error-ratio" baseline="2026-10-13T04:05:18.560474+00:00..2026-10-13T04:37:16.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.03188 min=0 max=0.1438 sd=0.02959
  baseline window: n=128 mean=0.05417 min=0.0412 max=0.06914 sd=0.007035
```

## The shape that actually mattered: 15-second cut-offs

Traces were where the harm became legible. Five errored traces in the window — a recommendations GET, a checkout POST, three product-browse GETs and an add-to-cart GET — all had the same shape: a frontend handler span running about 15000ms with essentially all of it as self-time and no child spans at all. The durations clustered within three milliseconds of each other across independent traces, which is the fingerprint of a fixed client-side cut-off, not variable backend latency. Error status propagated upward only: the proxy ingress span and the load-generator span were marked ERROR while the frontend span and the proxy egress span were not, consistent with callers abandoning requests at their deadline rather than frontend returning a code. In the same window other frontend requests completed normally — product-reviews calls in the 38-81ms range, cart AddItem at 10.6ms and GetCart at 6.6ms and 1.2ms, a frontend-rooted page render at 61.6ms — so this was partial, not a total outage. Durations were bimodal: tens of milliseconds, or pinned at 15.00s, nothing between.

> Evidence `tr_90a6a61fbe13`:

```
<tool_result id="tr_90a6a61fbe13" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T04:07:16.664000+00:00..2026-10-13T05:09:14.767526+00:00">
service: frontend
10 trace(s) shown of 10 found, 86 spans; offsets are from each trace's root

trace 1c4937625ddc431b  root load-generator/user_get_recommendations  15005.9ms  started 2026-10-13T05:07:28.433614+00:00  5 spans
  +0.0ms load-generator/user_get_recommendations 15005.9ms [self 1.3ms]
```

## Following the transport errors to a port

Frontend's logs were homogeneous: every retained error line was gRPC status 14 UNAVAILABLE, in two interleaved variants — an established upstream connection dropped mid-call, and an outright refusal to connect. The refusals named a single fixed container-network IP on port 5050, and they were immediate, not deadline-driven. That combination is informative: the name resolved fine, the address was routable, and nothing was accepting on that port. The stack frames were from a bundled Node server chunk, so these were server-side render-path gRPC calls, not browser code. The errors clustered at roughly T-30m, T-16m and T-15m with multi-minute gaps, which fits an upstream flapping between dropping live connections and refusing new ones.

> Evidence `tr_3382f79d68aa`:

```
<tool_result id="tr_3382f79d68aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T04:37:26.448223+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-13T04:37:26.448327+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-13T04:37:26.448333+00:00      at new Promise (<anonymous>) {
2026-10-13T04:37:26.448334+00:00    code: 14,
```

## Checkout: the repeating crash

Checkout's logs carried at least three unrecovered runtime panics in the window — nil pointer dereference on SIGSEGV — at roughly T-30m, T-16m and T-15m, with an identical signature each time: same signal, same fault address, same program counter. The path is checkout's own code: a gRPC PlaceOrder request dispatched to the service handler, which calls an internal send-to-post-processor routine around main.go:630, where the dereference happens. The panic re-raises through the OpenTelemetry deferred span-End wrapper, which puts the trace SDK on the unwind path but not necessarily at the origin — do not chase the SDK. Each panic occurs on a goroutine serving a live gRPC stream, so the process was up, bound and taking traffic between crashes. Each crash takes the listener down, and that is what frontend's refusals on 5050 are seeing. The timing correspondence between the panic timestamps and the frontend connection errors is the strongest link in this record.

> Evidence `tr_e2eb7807b28d`:

```
<tool_result id="tr_e2eb7807b28d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-13T04:37:26.439239+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-13T04:37:26.439348+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-13T04:37:26.439355+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-13T04:37:26.439356+00:00  
```

> Evidence `tr_3382f79d68aa`:

```
<tool_result id="tr_3382f79d68aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T04:37:26.448223+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-13T04:37:26.448327+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-13T04:37:26.448333+00:00      at new Promise (<anonymous>) {
2026-10-13T04:37:26.448334+00:00    code: 14,
```

## Dead ends worth keeping

Frontend's change history looked promising and was not. Six records exist across a 24-hour window, all environment-variable edits to a single key (CART_ADDR), all by the automated actor platform-automation, forming three set-then-revert pairs roughly eight to nine minutes apart at about T-23h, T-3.5h and T-2.7h. No code deploy, no image rollout, no flag edit appears at all. Critically, the last event is a revert back to unset completing about 2.6 hours before onset, so at onset frontend was running the default value. The repeating pattern is interesting as a background config-reconciliation oddity but it is not this story.

The dependency hunt through traces also came up empty in the useful direction: cart and its Redis operations all completed in under a few milliseconds and never appeared beneath an errored span; product-reviews succeeded end to end in 50-95ms with its SELECT under 10ms. The proxy itself was exonerated — ingress and egress spans had near-zero self-time and merely wrapped the long frontend span. And the checkout trace is instructive as a trap: the frontend POST stalled 15000ms while a sibling checkout-to-cart GetCart returned in 1.2ms, so a reader tempted to blame the cart chain should not.

Finally, the aggregate error ratios on frontend and frontend-proxy ruled themselves out as the alert trigger and as evidence of origin. A rising-ratio threshold on those service-level series cannot have fired; whatever paged came from somewhere else.

> Evidence `tr_daf4e6c3ed89`:

```
<tool_result id="tr_daf4e6c3ed89" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-12T05:07:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" radius="candidate_cause" hops="1">
service: frontend
6 changes, ranked by suspicion
  #1  2.6h before onset  2026-10-13T02:29:23.019832+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  2.8h before onset  2026-10-13T02:20:44.353757+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_90a6a61fbe13`:

```
<tool_result id="tr_90a6a61fbe13" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T04:07:16.664000+00:00..2026-10-13T05:09:14.767526+00:00">
service: frontend
10 trace(s) shown of 10 found, 86 spans; offsets are from each trace's root

trace 1c4937625ddc431b  root load-generator/user_get_recommendations  15005.9ms  started 2026-10-13T05:07:28.433614+00:00  5 spans
  +0.0ms load-generator/user_get_recommendations 15005.9ms [self 1.3ms]
```

> Evidence `tr_4b7fb366dc99`:

```
<tool_result id="tr_4b7fb366dc99" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" template="error-ratio" baseline="2026-10-13T04:05:18.560474+00:00..2026-10-13T04:37:16.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.02501 min=0 max=0.05693 sd=0.02244
  baseline window: n=128 mean=0.05694 min=0.04381 max=0.07315 sd=0.00705
```

> Evidence `tr_03e3dd383648`:

```
<tool_result id="tr_03e3dd383648" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" template="error-ratio" baseline="2026-10-13T04:05:18.560474+00:00..2026-10-13T04:37:16.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.03188 min=0 max=0.1438 sd=0.02959
  baseline window: n=128 mean=0.05417 min=0.0412 max=0.06914 sd=0.007035
```

## Where the record is thin

Confidence in the conclusion is low, and the gaps are specific. Both log queries truncate at about T-15m, keeping only the oldest few and newest few lines; nothing observed speaks to checkout's or frontend's state at onset itself. No evidence places a checkout restart or crash against the onset moment. The upstream IP on 5050 was never resolved to a named service — identifying it as checkout is inference from the port and the timing, not measurement. The 15-second traces remain partly unexplained: if an upstream were refusing connections you would normally expect a failed child span under the frontend handler, and there is none; the stall lives inside frontend with no downstream attribution. And the checkout change query was issued over a window that begins at the onset timestamp rather than before it, so it is silent on whether anything landed in the hours preceding — it does establish that nothing was recorded in the 24 hours after, which rules out a post-onset remediation deploy, a restart loop driven by a scaling controller, or any logged responder action.

> Evidence `tr_e2eb7807b28d`:

```
<tool_result id="tr_e2eb7807b28d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-13T04:37:26.439239+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-13T04:37:26.439348+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-13T04:37:26.439355+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-13T04:37:26.439356+00:00  
```

> Evidence `tr_3382f79d68aa`:

```
<tool_result id="tr_3382f79d68aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T04:37:26.448223+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-13T04:37:26.448327+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-13T04:37:26.448333+00:00      at new Promise (<anonymous>) {
2026-10-13T04:37:26.448334+00:00    code: 14,
```

> Evidence `tr_90a6a61fbe13`:

```
<tool_result id="tr_90a6a61fbe13" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T04:07:16.664000+00:00..2026-10-13T05:09:14.767526+00:00">
service: frontend
10 trace(s) shown of 10 found, 86 spans; offsets are from each trace's root

trace 1c4937625ddc431b  root load-generator/user_get_recommendations  15005.9ms  started 2026-10-13T05:07:28.433614+00:00  5 spans
  +0.0ms load-generator/user_get_recommendations 15005.9ms [self 1.3ms]
```

> Evidence `tr_f419323593fd`:

```
<tool_result id="tr_f419323593fd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T05:07:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" radius="outside_radius">
no changes recorded for checkout over this window
</tool_result:tr_f419323593fd>
```

## Where this landed and what to do next time

Best reading: checkout is running a build whose PlaceOrder path dereferences nil on live traffic at the send-to-post-processor step, killing the process repeatedly; each death drops the listener, frontend's server-side calls get refused on 5050, and the resulting partial degradation reaches users as fixed-length client cut-offs at the proxy and load-generator rather than as error-ratio movement. Remedy class is rollback of the checkout artifact — but note that the rollback target is unidentified, because no change record covering the period before onset was ever retrieved. The first action for a future responder is to re-run the checkout change query with a window that starts well before onset, and the second is to resolve the 5050 peer address to a service name so the link stops being inference.

> Evidence `tr_e2eb7807b28d`:

```
<tool_result id="tr_e2eb7807b28d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-13T04:37:26.439239+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-13T04:37:26.439348+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-13T04:37:26.439355+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-13T04:37:26.439356+00:00  
```

> Evidence `tr_f419323593fd`:

```
<tool_result id="tr_f419323593fd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T05:07:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" radius="outside_radius">
no changes recorded for checkout over this window
</tool_result:tr_f419323593fd>
```

> Evidence `tr_3382f79d68aa`:

```
<tool_result id="tr_3382f79d68aa" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T04:37:16.664000+00:00..2026-10-13T05:09:14.767526+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-13T04:37:26.448223+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-13T04:37:26.448327+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-13T04:37:26.448333+00:00      at new Promise (<anonymous>) {
2026-10-13T04:37:26.448334+00:00    code: 14,
```

