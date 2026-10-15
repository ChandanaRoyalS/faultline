# Cart store reads stalling at ~300 ms, five services alerting

## What the responder saw first

The page opened on cart at T+0, severity warning. Within about a minute four more services joined: checkout, frontend, frontend-proxy and load-generator. That shape — one backend service first, then everything sitting in front of it — is what set the initial reading direction: treat cart as the origin and the rest as waiters until proven otherwise. The declared blast radius was fourteen services, but fourteen of the edges crossed were never measured, so that number describes reachability, not confirmed damage.

Nothing in the alert text said what was wrong with cart. No error storm, no crash loop, no obvious bad actor. The first half hour was spent establishing what cart was *not* doing.

## Clearing the easy explanations

The first instinct was the usual one: something shipped. The change log was queried across a wide window around the incident start and came back empty for cart — no deployments, no config pushes, no flag changes. An empty result is weak evidence on its own, but it was enough to stop chasing a release and it held up for the rest of the investigation.

Logs were the second stop, and they were quietly unhelpful in a useful way. Every retained line for cart across the hour before and through the incident was info level. Continuous AddItemAsync and GetCartAsync chatter, no gaps, no startup or shutdown markers, no exceptions. Cart was alive and serving the whole time. One oddity surfaced in the tail — a run of GetCartAsync calls with an empty userId near the end of the window — which looked suspicious for about ten minutes and then went nowhere. It was logged at info, it did not correlate with the slow requests, and it never became part of the explanation. Note it, don't chase it.

Error-rate metrics were the third stop and nearly sent the investigation sideways. Cart's error ratio over the incident window averaged 0.0014 with a single spike to roughly 4%, against a baseline of exactly zero errors across more than a hundred samples in the preceding three hours. That is a real change — cart was clean before and was not clean during — but 4% peak, intermittent rather than sustained, is not a service falling over. The temptation was to treat the error elevation as the incident. It was a symptom at the edges, not the mechanism.

> Evidence `tr_189486765dc3`:

```
<tool_result id="tr_189486765dc3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T21:07:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" radius="seed" hops="0">
no changes recorded for cart over this window
</tool_result:tr_189486765dc3>
```

> Evidence `tr_3e503166b3a3`:

```
<tool_result id="tr_3e503166b3a3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T20:07:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-13T20:07:40.951760+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-13T20:07:40.951825+00:00        AddItemAsync called with userId=b5a19efe-c741-11f1-acc9-ba1d51da3ea9, productId=2ZYFJ3GM2N, quantity=4
2026-10-13T20:07:40.957979+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-13T20:07:40.958032+00:00        GetCartAsync called with userId=b5a19efe-c741-11f1-acc9-ba1d51da3ea9
```

> Evidence `tr_f5d1b25eb7ad`:

```
<tool_result id="tr_f5d1b25eb7ad" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T18:07:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" template="error-ratio" baseline="2026-10-13T15:04:28.976898+00:00..2026-10-13T18:07:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=702 mean=0.0014 min=0 max=0.04018 sd=0.005922
  baseline window: n=106 mean=0 min=0 max=0 sd=0
```

## The dead end at the proxy

Because frontend-proxy alerted, it was checked as a candidate failure point — the theory being requests piling up against a route timeout at the edge. The metrics said the opposite, and emphatically. The proxy's error ratio during the incident averaged around 1% with a 5.4% peak, which is *lower* than its own pre-incident baseline of roughly 6%. A timeout boundary doing systematic damage would have pushed that number up, not down. The proxy was passing traffic fine; it was alerting because it was waiting, not because it was breaking. That closed the edge-layer theory and pushed the search back down the stack.

> Evidence `tr_fc40edd3ed73`:

```
<tool_result id="tr_fc40edd3ed73" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T20:37:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" template="error-ratio" baseline="2026-10-13T20:04:28.976898+00:00..2026-10-13T20:37:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=133 mean=0.009996 min=0 max=0.05445 sd=0.01642
  baseline window: n=133 mean=0.06139 min=0 max=0.2707 sd=0.1
```

## Where the time actually went

Traces were what broke the case open. Eight traces were pulled from the back half of the window. Three of them showed the same signature: a single cart span talking to the Valkey/Redis cart store — the HGET — consuming roughly 300 ms entirely on its own. The figures were ~300.7 ms, ~300.6 ms and ~301.2 ms. In each case the cart handler's own self-time was small; the latency was sitting inside the store call, not in cart's logic.

The five healthy traces from the same window made the contrast unambiguous: HGET, HMSET and EXPIRE all completing in 0.1 to 0.6 ms. So this is not a slow baseline, it is an intermittent stall two to three orders of magnitude outside normal.

One trace was worse than the rest. An AddItem request ran 904.5 ms total with 603.3 ms of handler self-time unaccounted for by any child span — and the HMSET and EXPIRE spans that appear in healthy traces were simply missing. Either those writes also stalled badly, or their spans were never emitted. Either way it suggests the problem is not confined to reads.

Notably, none of the cart spans in any of the eight traces carried an error status. The failure presents purely as latency. That is why the error-rate metrics only showed a 4% blip — the small error elevation is almost certainly timeouts firing somewhere downstream of the stall, not cart rejecting work.

> Evidence `tr_f8e53e09966c`:

```
<tool_result id="tr_f8e53e09966c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T20:37:31.664000+00:00..2026-10-13T21:10:34.351102+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 509453f073b1a7bf  root load-generator/user_add_to_cart  18.4ms  started 2026-10-13T21:00:13.914323+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 18.4ms [self 1.7ms]
```

## Neighbours checked and cleared

Three plausible neighbours were examined in the trace data and each was eliminated. Flag evaluation appeared in exactly one trace, during EmptyCart, completing in under a millisecond with no errors — and it was absent entirely from all three slow traces. Product-catalog never appears as a direct callee of cart at all; its calls originate from frontend and checkout and complete in under 3 ms throughout. Network transport between the callers and cart was ruled out because the cart handler span itself accounts for the full 301–304 ms in two of the slow traces, with essentially all of it inside the store call — the time is spent after the request arrives at cart, not getting there.

> Evidence `tr_f8e53e09966c`:

```
<tool_result id="tr_f8e53e09966c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T20:37:31.664000+00:00..2026-10-13T21:10:34.351102+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 509453f073b1a7bf  root load-generator/user_add_to_cart  18.4ms  started 2026-10-13T21:00:13.914323+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 18.4ms [self 1.7ms]
```

## Conclusion and confidence

Cart's calls into its Valkey/Redis cart store are intermittently taking around 300 ms where they normally take well under a millisecond. Everything else about cart is normal: no change shipped, logs clean and continuous, errors only mildly and intermittently elevated. The downstream alerts arriving about a minute later are consistent with four services queued behind a slow cart, and the proxy's suppressed error ratio supports that reading. The fix class is a restart of the store path.

Confidence is medium, not high, and the reason is in the next section.

> Evidence `tr_f8e53e09966c`:

```
<tool_result id="tr_f8e53e09966c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T20:37:31.664000+00:00..2026-10-13T21:10:34.351102+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 509453f073b1a7bf  root load-generator/user_add_to_cart  18.4ms  started 2026-10-13T21:00:13.914323+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 18.4ms [self 1.7ms]
```

> Evidence `tr_189486765dc3`:

```
<tool_result id="tr_189486765dc3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T21:07:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" radius="seed" hops="0">
no changes recorded for cart over this window
</tool_result:tr_189486765dc3>
```

> Evidence `tr_3e503166b3a3`:

```
<tool_result id="tr_3e503166b3a3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T20:07:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-13T20:07:40.951760+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-13T20:07:40.951825+00:00        AddItemAsync called with userId=b5a19efe-c741-11f1-acc9-ba1d51da3ea9, productId=2ZYFJ3GM2N, quantity=4
2026-10-13T20:07:40.957979+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-13T20:07:40.958032+00:00        GetCartAsync called with userId=b5a19efe-c741-11f1-acc9-ba1d51da3ea9
```

> Evidence `tr_f5d1b25eb7ad`:

```
<tool_result id="tr_f5d1b25eb7ad" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T18:07:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" template="error-ratio" baseline="2026-10-13T15:04:28.976898+00:00..2026-10-13T18:07:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=702 mean=0.0014 min=0 max=0.04018 sd=0.005922
  baseline window: n=106 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_fc40edd3ed73`:

```
<tool_result id="tr_fc40edd3ed73" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T20:37:31.664000+00:00..2026-10-13T21:10:34.351102+00:00" template="error-ratio" baseline="2026-10-13T20:04:28.976898+00:00..2026-10-13T20:37:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=133 mean=0.009996 min=0 max=0.05445 sd=0.01642
  baseline window: n=133 mean=0.06139 min=0 max=0.2707 sd=0.1
```

## What was never settled

The store itself was never investigated. No specialist was dispatched to it — no store-side metrics, no store logs, no eviction counters, no connection-pool telemetry. That leaves three distinct mechanisms live and indistinguishable from the client side: the store genuinely stalling, cart's client-side connection pool queuing requests behind a saturated connection, or a deliberate fixed delay sitting in the path. A responder picking this up should start there.

The uniformity of the number is the loudest unresolved detail. 300.7, 300.6, 301.2 — three independent traces landing within 600 microseconds of each other. Organic store contention does not usually produce a figure that tight. That pattern argues for something configured or imposed rather than emergent, and it is the single strongest reason not to close this as a store health problem without looking.

Finally, no latency was ever measured on checkout, frontend or load-generator. Their inclusion in the propagation story rests on topology and the one-minute alert offset, not on any measurement. If a future recurrence has budget for one more query, measure one of them and turn that inference into evidence.

> Evidence `tr_f8e53e09966c`:

```
<tool_result id="tr_f8e53e09966c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T20:37:31.664000+00:00..2026-10-13T21:10:34.351102+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 509453f073b1a7bf  root load-generator/user_add_to_cart  18.4ms  started 2026-10-13T21:00:13.914323+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 18.4ms [self 1.7ms]
```

