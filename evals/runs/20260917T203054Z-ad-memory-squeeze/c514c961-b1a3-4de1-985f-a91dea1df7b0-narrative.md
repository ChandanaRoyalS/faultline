# Shipping-quote path pointed at a non-existent quote endpoint

## What we saw first

The page arrived from frontend and loadgenerator, with a blast radius nominally spanning seven services and a critical severity. The obvious first move was to treat this as a frontend error surge and work backwards. That framing was wrong, and it cost the first stretch of the investigation.

The only signal that actually described a failure mode came from frontend's own log stream. The oldest retained lines, roughly an hour before the end of the window, show frontend failing a shipping-quote call with gRPC status 13 INTERNAL. Nested inside that status is an outbound HTTP request to a quote-service host on port 8090 that never got past name resolution. That hostname is the single explicitly named upstream target anywhere in the evidence we gathered.

> Evidence `tr_fd8f527583db`:

```
<tool_result id="tr_fd8f527583db" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T19:35:36.956476+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-17T19:35:36.956496+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T19:35:36.956497+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T19:35:36.956498+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## How the signature evolved

The failure shape is not constant across the window. Early on it is a name-resolution failure wrapped in an INTERNAL status. By the end of the window — the last lines are at T+0 relative to query close, roughly 20:36 — the errors have flattened into bare gRPC 14 UNAVAILABLE with the detail that no connection was established. Those late stack traces are grpc-js client-side and name no host or URL at all, which is why reading only the tail of the log would have told you nothing useful.

Both signatures share a property worth noting: they occur before any connection or response exists. There is no deadline expiry, no context cancellation, no resource-exhausted status anywhere in the retained lines. That rules out the two most reflexive hypotheses — that an upstream was slow and blowing deadlines, or that an upstream was up but saturated and shedding load. Neither is compatible with failing at name lookup.

Errors were still being emitted in the final seconds of the query window, so the condition was live and unresolved when we stopped looking.

> Evidence `tr_fd8f527583db`:

```
<tool_result id="tr_fd8f527583db" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T19:35:36.956476+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-17T19:35:36.956496+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T19:35:36.956497+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T19:35:36.956498+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Why this is not frontend's own bug

Every retained error is a client-side outbound-call error from frontend's gRPC stack, not an internal handler failure. Frontend kept running and kept logging through the end of the window. The remote error arrives wrapped in a code = Unknown envelope carrying an HTTP client failure for the quote URL, which places the bad address on the far side of the hop — in the shipping-quote service — rather than in frontend's request handling. That nesting is the whole basis of the conclusion.

> Evidence `tr_fd8f527583db`:

```
<tool_result id="tr_fd8f527583db" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T19:35:36.956476+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-17T19:35:36.956496+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T19:35:36.956497+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T19:35:36.956498+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Dead end: the error-rate metrics

Two separate baseline comparisons on frontend error ratio were run, one over a two-hour span and one over three. Both said the same uncomfortable thing: error ratio during the incident window was *lower* than the preceding baseline — about a third in the shorter comparison, about 62% of baseline mean in the longer. No sustained departure was flagged. The only two detected change points sit roughly two and a half hours before the moment of interest and look like isolated excursions, not a level shift.

We spent real time trying to reconcile this with a critical-severity page. The reconciliation is that the alert is probably not error-shaped at all. By elimination, if a breach is real it must be carried by latency or throughput — and neither of those was ever measured. That gap is still open.

The same exercise on checkoutservice returned the same shape: a populated, continuous ratio series (so the service was definitely serving traffic), with error ratio roughly sixfold *below* its own preceding baseline and peaks within historically normal range. checkoutservice was not down, and was not surging. Absolute request rate and replica availability were never measured there either.

> Evidence `tr_591a8b1d1900`:

```
<tool_result id="tr_591a8b1d1900" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T18:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" template="error-ratio" baseline="2026-09-17T16:32:18.143323+00:00..2026-09-17T18:34:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=488 mean=0.01634 min=0 max=0.1019 sd=0.02643
  baseline window: n=439 mean=0.05779 min=0 max=0.4775 sd=0.1052
```

> Evidence `tr_b3279f394d77`:

```
<tool_result id="tr_b3279f394d77" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T17:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" template="error-ratio" baseline="2026-09-17T14:32:18.143323+00:00..2026-09-17T17:34:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=728 mean=0.02491 min=0 max=0.3223 sd=0.06042
  baseline window: n=551 mean=0.04042 min=0 max=0.4775 sd=0.07572
```

> Evidence `tr_c6684efc0244`:

```
<tool_result id="tr_c6684efc0244" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T20:04:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" template="error-ratio" baseline="2026-09-17T19:32:18.143323+00:00..2026-09-17T20:04:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.02354 min=0 max=0.2909 sd=0.06748
  baseline window: n=128 mean=0.1357 min=0 max=0.2963 sd=0.124
```

## Dead end: the traces

Ten frontend traces were pulled, 42 spans total. Every one is fast — 0.8ms to 29.9ms end to end. No slow population at all.

The trap here is that this looks like exculpatory evidence and is not. All ten traces start in the final six seconds of a sixty-two-minute window. The onset period is entirely unrepresented. Absence of slow traces in that sliver says nothing about conditions at onset.

What the sample does say, for what it is worth: checkoutservice appears in zero spans. The services present are loadgenerator, frontend, productcatalogservice and cartservice, plus cartservice's Redis operations. The sampled request mix is product-page GETs and cart AddItem/GetCart POSTs — none of it reaches checkout. Dominant self-time sits consistently in frontend's own client spans (70–87% for GetProduct, 55–60% for AddItem), while downstream server spans are sub-millisecond to about 2ms. So no downstream backend was holding requests open, and there is no deep or wide fan-out to blame.

One minor artefact: two traces show a child span apparently starting after its parent's client span, which reads as clock skew between frontend and productcatalogservice rather than real queueing. Not load-bearing.

> Evidence `tr_7383c104a38e`:

```
<tool_result id="tr_7383c104a38e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T19:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00">
service: frontend
10 trace(s) shown of 10 found, 42 spans; offsets are from each trace's root

trace 39504ca1becd1669  root loadgenerator/HTTP GET  10.2ms  started 2026-09-17T20:36:06.836631+00:00  3 spans
  +0.0ms loadgenerator/HTTP GET 10.2ms [self 0.9ms]
```

## Dead end: the change log

Two change-history queries were run, one against frontend and one against checkoutservice. Both came back empty — no deploys, no config edits, no flag flips.

Both queries are also useless for the question we actually had. Each window begins at the onset timestamp and extends roughly twenty-four hours *forward*. The period we needed to inspect was the hours *before* onset, and neither query touched it. What the empty results legitimately rule out is narrow: nothing landed on frontend or checkoutservice during or after the incident, so no in-flight rollout was compounding the failure and no logged change drove any recovery. The frontend query was also scoped to the seed service only, with zero dependency hops, so adservice, cartservice, checkoutservice, productcatalogservice and recommendationservice were never covered.

If you are re-running this, re-run the change queries with a pre-onset window first. That is the single highest-value repeat.

> Evidence `tr_a65fc36b77d2`:

```
<tool_result id="tr_a65fc36b77d2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_a65fc36b77d2>
```

> Evidence `tr_6e15fe00e6d4`:

```
<tool_result id="tr_6e15fe00e6d4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_6e15fe00e6d4>
```

## Conclusion and confidence

The shipping-quote path is pointed at a quote-service endpoint that does not exist. The mechanism is the configured address itself: an unresolvable hostname on port 8090, which means every shipping-quote request dies at name lookup and never reaches a server. Fix class is a configuration revert of that endpoint value.

Confidence is medium, and the reason is worth stating plainly. No dispatch ever touched shippingservice or the quote service directly. Their logs, metrics and change history are entirely unmeasured. The attribution of the bad value to shippingservice rests solely on the nesting of the remote error inside frontend's log lines — a single thread of evidence, from one source, over one window.

> Evidence `tr_fd8f527583db`:

```
<tool_result id="tr_fd8f527583db" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T19:35:36.956476+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-17T19:35:36.956496+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T19:35:36.956497+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T19:35:36.956498+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Open questions for the next responder

Three gaps remain, in rough order of how much they would change the picture.

First, shippingservice and the quote service were never queried. Go there directly: pull their logs, their configured endpoint value, and their change history. That converts the central claim from inference to observation.

Second, no change record for the endpoint edit exists, because both change queries ran forward from onset and missed the period in which the edit must have happened. Re-query with a window that precedes onset.

Third, whether the alert was error-shaped at all is unresolved. Error ratios fell on both frontend and checkoutservice. Frontend latency and throughput were never measured, and the frontend log stream has an hour-long retention hole spanning the onset timestamp — the result was truncated to the oldest eight and newest thirty-two lines, dropping everything in between. Narrow the log query to a tight window around onset and it will return the lines that were dropped here.

> Evidence `tr_fd8f527583db`:

```
<tool_result id="tr_fd8f527583db" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T19:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T19:35:36.956476+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unknown desc = Request error: error sending request for url (http://quoteservice-gone:8090/getquote): error trying to connect: dns error: failed to lookup address information: Name does not resolve
2026-09-17T19:35:36.956496+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T19:35:36.956497+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T19:35:36.956498+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_a65fc36b77d2`:

```
<tool_result id="tr_a65fc36b77d2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_a65fc36b77d2>
```

> Evidence `tr_6e15fe00e6d4`:

```
<tool_result id="tr_6e15fe00e6d4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T20:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_6e15fe00e6d4>
```

> Evidence `tr_591a8b1d1900`:

```
<tool_result id="tr_591a8b1d1900" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T18:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" template="error-ratio" baseline="2026-09-17T16:32:18.143323+00:00..2026-09-17T18:34:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=488 mean=0.01634 min=0 max=0.1019 sd=0.02643
  baseline window: n=439 mean=0.05779 min=0 max=0.4775 sd=0.1052
```

> Evidence `tr_b3279f394d77`:

```
<tool_result id="tr_b3279f394d77" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T17:34:15.583000+00:00..2026-09-17T20:36:13.022677+00:00" template="error-ratio" baseline="2026-09-17T14:32:18.143323+00:00..2026-09-17T17:34:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=728 mean=0.02491 min=0 max=0.3223 sd=0.06042
  baseline window: n=551 mean=0.04042 min=0 max=0.4775 sd=0.07572
```

