# Browse-product path hangs to a 15s deadline behind frontend

## What paged, and the dead ends that followed

Error-rate alerts arrived at frontend-proxy and the load-generator — both callers, several hops above whatever stopped answering. Nothing paged on frontend, and nothing paged on the service eventually implicated.

The first hours went into things that did not matter. The proxy tier was cleared: its span error ratio averaged about 2.2% in the window against a baseline averaging ~7.6% with peaks near 28.5%, so error behaviour improved going in, and the query aggregated by service name only, with no route or upstream dimension to localise anything with. Frontend's own ratio was flat zero across 128 samples with zero variance, down from a volatile ~7.6% baseline — errors went away at frontend rather than appearing, and the defined-zero samples confirm it kept emitting spans throughout. That eliminates frontend as the error origin and rules out any downstream error propagating through it as error-status spans. A separate request for frontend request rate and p95 came back with the error-ratio template again, so the throughput collapse that should accompany a hang was never confirmed. That hole is still open.

> Evidence `tr_e04d6d85203c`:

```
<tool_result id="tr_e04d6d85203c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:22:31.664000+00:00..2026-10-14T00:54:26.856026+00:00" template="error-ratio" baseline="2026-10-13T23:50:36.471974+00:00..2026-10-14T00:22:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.02241 min=0 max=0.2455 sd=0.06325
  baseline window: n=128 mean=0.07594 min=0 max=0.2851 sd=0.1112
```

> Evidence `tr_3b2cfa752b21`:

```
<tool_result id="tr_3b2cfa752b21" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:22:31.664000+00:00..2026-10-14T00:54:26.856026+00:00" template="error-ratio" baseline="2026-10-13T23:50:36.471974+00:00..2026-10-14T00:22:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.07624 min=0 max=0.294 sd=0.1114
```

> Evidence `tr_80d5938f2d29`:

```
<tool_result id="tr_80d5938f2d29" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T00:22:31.664000+00:00..2026-10-14T00:54:26.856026+00:00" template="error-ratio" baseline="2026-10-13T23:50:36.471974+00:00..2026-10-14T00:22:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.07624 min=0 max=0.294 sd=0.1114
```

## Empty logs are not evidence; the traces are

Queries for all lines labelled frontend and frontend-proxy each returned nothing across the full window — not thinned volume, zero lines of any level. Do not read that as a quiet healthy service: a serving frontend emits baseline lines, so total silence across 32 minutes looks like a collection-side gap. Narrowing would not help. Whether logging was broken world-wide was never resolved, and it is the weakest joint here.

The traces carried the shape. Four browse-product traces all terminated at ~15.00s with the frontend root span holding essentially the whole duration as self-time and **zero child spans**; the proxy and generator parents were marked error. In the same window through the same instance, product-reviews finished in ~12–26ms, cart in ~6–12ms, index in ~21ms, each with a full child chain and backends answering under ~1.5ms. So: frontend was not broadly degraded, no slow store was dragging latency, the proxy carried near-zero self-time in both healthy and failing traces, rendering work was not the cost, and the requests did not fail fast with an application error — they ran the full 15s first. A call that errors still writes a span; a call opened and never completed writes none.

> Evidence `tr_80babfbaf32c`:

```
<tool_result id="tr_80babfbaf32c" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T00:22:31.664000+00:00..2026-10-14T00:54:26.856026+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_80babfbaf32c>
```

> Evidence `tr_151abc31d0c5`:

```
<tool_result id="tr_151abc31d0c5" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T00:22:31.664000+00:00..2026-10-14T00:54:26.856026+00:00">
no log lines matched {service="frontend-proxy"} over this window
</tool_result:tr_151abc31d0c5>
```

> Evidence `tr_6344d08e88d5`:

```
<tool_result id="tr_6344d08e88d5" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T00:22:31.664000+00:00..2026-10-14T00:54:26.856026+00:00">
service: frontend
10 trace(s) shown of 10 found, 81 spans; offsets are from each trace's root

trace 68e38f68b26a2a21  root load-generator/user_browse_product  15004.1ms  started 2026-10-14T00:52:07.802398+00:00  5 spans
  +0.0ms load-generator/user_browse_product 15004.1ms [self 0.9ms]
```

## Change history was a clean miss, and what is still open

The change log for frontend and its one-hop dependencies held exactly four records, all environment edits to CART_ADDR by platform automation, forming two complete set-then-revert pairs ~23h and ~22.5h before onset. Net zero drift; nearest record ~22.4h prior. No deploys, image bumps, flag edits, or neighbour changes. Read the emptiness carefully: it eliminates change-shaped causes, and it is also what the causes that leave no record look like.

Conclusion, held at low confidence: the browse-product handler calls a backend that accepts and never answers, everything above waits out a ~15s deadline, and errors surface one hop up rather than propagating from below. By route topology that callee is the product catalog service. Fix class is restart.

Still open, and all of it matters. The callee was inferred, never confirmed by a dispatch — one unmeasured edge. Its own log was never read, which is the only test separating a stopped process from a severed network path. Whether its span metrics went absent and whether a no-traffic alert fired on it were never checked. Frontend throughput was never returned. Start there.

> Evidence `tr_b6fa89c7b1fb`:

```
<tool_result id="tr_b6fa89c7b1fb" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T00:52:31.664000+00:00..2026-10-14T00:54:26.856026+00:00" radius="candidate_cause" hops="1">
service: frontend
4 changes, ranked by suspicion
  #1  22.4h before onset  2026-10-13T02:29:23.019832+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  22.5h before onset  2026-10-13T02:20:44.353757+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

