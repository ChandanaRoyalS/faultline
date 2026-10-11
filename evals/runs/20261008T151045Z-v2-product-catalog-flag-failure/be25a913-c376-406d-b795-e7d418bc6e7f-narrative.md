# Intermittent catalog errors surfacing as frontend 500s on the recommendations route

## What we saw, in order

Frontend and frontend-proxy paged on error ratio; nothing else did, despite eight services in the blast radius and seven unmeasured edges between them. That framing cost time — both turned out to be reporters, not participants.

Frontend's error ratio averaged ~2.8% with a ~7.9% peak against a flat-zero baseline, so there was a real onset and the service was emphatically not down. Earliest threshold crossing sat around T-21m, a second around T-2m.

Trace sampling settled direction of causality fast. Of ten traces (143 spans), exactly one error path existed, beginning at a product-catalog GetProduct span and walking up through frontend's recommendations route, frontend-proxy, and the load-generator root — marking every ancestor an error. That alone explains why the two services furthest from the problem alerted first. The failing span had essentially zero duration and carried a well-formed gRPC status 13 INTERNAL whose detail text named a catalog failure flag. Frontend's logs showed the same text repeating, with the stack frame in a bundled server chunk — the wrapper rethrowing an upstream reply, not frontend logic producing one.

> Evidence `tr_59d209c02941`:

```
<tool_result id="tr_59d209c02941" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T14:47:16.664000+00:00..2026-10-08T15:19:05.218498+00:00" template="error-ratio" baseline="2026-10-08T14:15:28.109502+00:00..2026-10-08T14:47:16.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.02799 min=0 max=0.07857 sd=0.02926
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_cc8644aeeb1c`:

```
<tool_result id="tr_cc8644aeeb1c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-08T14:47:16.664000+00:00..2026-10-08T15:19:05.218498+00:00">
service: frontend
10 trace(s) shown of 10 found, 143 spans; offsets are from each trace's root

trace 39391a24dfa4ffdb  root load-generator/user_browse_product  4.7ms  started 2026-10-08T15:18:38.849511+00:00  10 spans
  +0.0ms load-generator/user_browse_product 4.7ms [self 0.4ms]
```

> Evidence `tr_f745fc7ccc25`:

```
<tool_result id="tr_f745fc7ccc25" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T14:47:16.664000+00:00..2026-10-08T15:19:05.218498+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-08T14:52:08.119454+00:00  Error: 13 INTERNAL: Error: Product Catalog Fail Feature Flag Enabled
2026-10-08T14:52:08.119766+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-10-08T14:52:08.119778+00:00      at new Promise (<anonymous>) {
2026-10-08T14:52:08.119781+00:00    code: 13,
```

## Dead ends worth keeping

Recommendation service: on the failing route, so a natural suspect, but its span and its own downstream catalog call both succeeded in milliseconds.

Cart and Redis: every AddItem/GetCart span and HGET/HMSET/EXPIRE child under a millisecond, no errors.

The catalog's database: tempting, but sql.conn.query children are sub-2ms and succeed even inside the error trace. The bad status lives in the service span above the query.

Transport problems: no UNAVAILABLE, no DEADLINE_EXCEEDED, no DNS or TLS. A reply was received; the upstream chose to fail the call.

Load-related degradation: the detail text is byte-identical every occurrence, not what variable saturation looks like.

Ad and checkout appear in the blast radius but in no sampled span. product-reviews produced the slowest trace (~36.8ms root, ~14ms self time) and was entirely error-free — a separate latency item.

The empty change log was the biggest misread risk. Both queries came back genuinely empty over a full 24h for frontend and product-catalog, which literally rules out deploy, config edit and recorded toggle. Read correctly it is the tell: the artifact and config files really are unchanged because behaviour was altered at runtime through the flag store, which the change log never sees. There is no rollback target; the fix is a config revert.

Finally, product-catalog returned zero log lines for a full hour spanning healthy and unhealthy periods. Not a crash signature — a crash leaves normal traffic lines beforehand. It is a shipping break or label mismatch, and narrower queries on that label are a strict subset of an already-empty result.

> Evidence `tr_cc8644aeeb1c`:

```
<tool_result id="tr_cc8644aeeb1c" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-08T14:47:16.664000+00:00..2026-10-08T15:19:05.218498+00:00">
service: frontend
10 trace(s) shown of 10 found, 143 spans; offsets are from each trace's root

trace 39391a24dfa4ffdb  root load-generator/user_browse_product  4.7ms  started 2026-10-08T15:18:38.849511+00:00  10 spans
  +0.0ms load-generator/user_browse_product 4.7ms [self 0.4ms]
```

> Evidence `tr_23225d4af2d4`:

```
<tool_result id="tr_23225d4af2d4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-07T15:17:16.664000+00:00..2026-10-08T15:19:05.218498+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_23225d4af2d4>
```

> Evidence `tr_ff97d6346791`:

```
<tool_result id="tr_ff97d6346791" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T14:17:16.664000+00:00..2026-10-08T15:19:05.218498+00:00">
no log lines matched {service="product-catalog"} over this window
</tool_result:tr_ff97d6346791>
```

## Conclusion and what stayed open

product-catalog is deliberately failing a fraction of GetProduct calls because a catalog failure flag is enabled in the flag store. Frontend rethrows; frontend-proxy and the load-generator root inherit the status. Confidence high, fix class config revert.

The source-side numbers look deceptively small: product-catalog's own ratio was ~0.44% mean, ~4.9% peak, from 488 flat-zero baseline samples, with standard deviation above the mean — sparse bursts, exactly what sampled rejection produces. Frontend's higher ratio likely reflects fan-out on the recommendations route or a different span denominator; no per-route or per-dependency breakdown was ever returned.

Open: onset is unbounded on the early side — the identical error is already in the oldest retained log line at T-25m, so the flag may predate every window queried, and nobody read the flag store's audit trail. Who enabled it, and whether intentionally, is unestablished. The product-reviews latency was never investigated. Five of eight services in the radius were never queried directly; their clean bill rests on a ten-trace sample across seven unmeasured edges.

> Evidence `tr_bf2c731f9222`:

```
<tool_result id="tr_bf2c731f9222" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T13:17:16.664000+00:00..2026-10-08T15:19:05.218498+00:00" template="error-ratio" baseline="2026-10-08T11:15:28.109502+00:00..2026-10-08T13:17:16.664000+00:00">
service: product-catalog
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-catalog"}[5m]))
  incident window: n=488 mean=0.004447 min=0 max=0.04915 sd=0.01175
  baseline window: n=488 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_59d209c02941`:

```
<tool_result id="tr_59d209c02941" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T14:47:16.664000+00:00..2026-10-08T15:19:05.218498+00:00" template="error-ratio" baseline="2026-10-08T14:15:28.109502+00:00..2026-10-08T14:47:16.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.02799 min=0 max=0.07857 sd=0.02926
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_f745fc7ccc25`:

```
<tool_result id="tr_f745fc7ccc25" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T14:47:16.664000+00:00..2026-10-08T15:19:05.218498+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-08T14:52:08.119454+00:00  Error: 13 INTERNAL: Error: Product Catalog Fail Feature Flag Enabled
2026-10-08T14:52:08.119766+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-10-08T14:52:08.119778+00:00      at new Promise (<anonymous>) {
2026-10-08T14:52:08.119781+00:00    code: 13,
```

