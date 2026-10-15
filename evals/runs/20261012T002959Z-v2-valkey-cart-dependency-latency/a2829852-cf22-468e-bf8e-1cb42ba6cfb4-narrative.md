# Cart request latency traced to a fixed per-command delay on its Valkey store path

## What the page looked like

The first thing visible from the responder's chair was a cluster of latency warnings arriving together across five services — cart, checkout, frontend, frontend-proxy and load-generator — with cart named as the seed and a blast radius of fourteen services behind it. Nothing in the page said what had broken. Severity was warning, not critical, and crucially no error-rate rule fired anywhere. That shape matters: four of the five alerted services are callers of cart, and the one that is not (load-generator) is the thing driving traffic through them. Before any evidence was pulled, the working assumption was simply that something in or under cart had become slow while continuing to succeed.

## First pass: is anything actually failing?

The opening question was whether this was a latency problem or an error problem wearing latency's clothes. It was not. Cart's error ratio was flat at exactly zero across 128 samples in the alert window, with zero variance, and identically zero over the equal-length baseline immediately before it. Checkout read the same — zero throughout both windows, no spike, no residue of an earlier spike that had already recovered. Because an error ratio is a quotient, a defined sample requires a non-zero denominator, so the fact that both series returned full sample counts rather than gaps was weak but real evidence that traffic was still flowing and the telemetry pipeline was still reporting. Three hypotheses died here: cart failing fast, checkout failing fast, and a hard dependency failure propagating up as errored spans. Whatever was wrong, requests were completing successfully and slowly.

> Evidence `tr_6bcdc2aaf99e`:

```
<tool_result id="tr_6bcdc2aaf99e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_e358164dfd34`:

```
<tool_result id="tr_e358164dfd34" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_da71743adda0`:

```
<tool_result id="tr_da71743adda0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Dead end: looking for a change to blame

The reflex move was to find a recent change and roll it back. The change log for cart over a twenty-four hour window — extending roughly a full day past the alert, so even post-incident remediation would have shown — returned nothing at all. No image rollouts, no environment edits, no configuration writes. The same query against product-catalog, scoped one hop out from the candidate cause, was likewise empty. That closed off rollback and configuration-revert as remediation paths entirely, since there is no prior value recorded to return to. It also redirected the investigation: with no change-side anchor, causation had to be sought in dependency or infrastructure state rather than in something a human had recently done. Worth noting for next time — an empty change log is not by itself exculpatory in this world, since some classes of failure leave no record anywhere. It only means rollback is not the lever.

> Evidence `tr_0e9c09a06405`:

```
<tool_result id="tr_0e9c09a06405" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T00:34:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" radius="seed" hops="0">
no changes recorded for cart over this window
</tool_result:tr_0e9c09a06405>
```

> Evidence `tr_4a70727fa40b`:

```
<tool_result id="tr_4a70727fa40b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T00:34:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_4a70727fa40b>
```

## Dead end: cart's own logs

Cart's logs were read next and turned out to be almost entirely uninformative, which is itself a finding. Every retained line was info-level output from the Valkey cart-store component recording ordinary operations — add item, get cart, empty cart — against a rolling set of distinct user ids, at sub-second spacing, right up to the close of the window. No startup banner anywhere, which rules out a crash or restart loop. No connection or timeout diagnostics, which rules out the store having gone unreachable. No allocation or out-of-memory output. No parse, decode or serialization errors; even one get-cart call carrying an empty user identifier was logged as a routine operation rather than a validation failure. The service was plainly up and serving throughout.

The caveat a future responder should carry: the result was truncated to the oldest eight and newest thirty-two lines, leaving roughly a thirty-minute interior of the window unobserved. Nothing in the record speaks to what happened in that gap. The clean log was read at the time as evidence that cart was not the originator, which pushed the search toward callers — a reading that later proved to be looking in the wrong direction.

> Evidence `tr_0fa62ef7350b`:

```
<tool_result id="tr_0fa62ef7350b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-12T00:04:33.517766+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T00:04:33.517906+00:00        AddItemAsync called with userId=8113b266-c5d0-11f1-9e56-ba3679c5fcbe, productId=9SIQT8TOJO, quantity=2
2026-10-12T00:04:33.526463+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T00:04:33.526489+00:00        GetCartAsync called with userId=8113b266-c5d0-11f1-9e56-ba3679c5fcbe
```

## The trace read that resolved it

Traces were where the shape finally appeared. Cart's server spans fell into exactly two clusters with almost no spread: AddItem handler spans at roughly 901 to 906 ms, and GetCart handler spans at roughly 300 to 303 ms. The ratio is the clue — AddItem issues three sequential commands to its Valkey cart store (HGET, HMSET, EXPIRE) where GetCart issues one, and each command span carried a near-constant 300 to 303 ms of self-time. Three times the cost, three times the commands. Cart's own handler self-time was a fraction of a millisecond in every sampled trace, so the service was not doing in-process work, garbage collecting, or contending on locks; it was waiting.

The uniformity is the signature. A real queue or an expensive key would produce a wide spread and would differ by command semantics — a write costing more than a read, a scan costing more than either. Here HGET, HMSET and EXPIRE all cost the same, in every sampled trace, which reads as a fixed delay applied to the network path between cart and its store rather than organic contention. The degrading-hop attribution agreed, pointing from the cart server span to a store command span in nearly every trace: about 25% of end-to-end for each of the three AddItem commands, and about 97% for the view-cart trace.

> Evidence `tr_3802202f2784`:

```
<tool_result id="tr_3802202f2784" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00">
service: cart
10 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 170ada5a2258cea3  root load-generator/user_add_to_cart  1216.8ms  started 2026-10-12T00:33:58.358207+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 1216.8ms [self 1.0ms]
```

## What the traces also ruled out

The same trace read closed several plausible alternatives in one pass. Flag evaluation was not the slow dependency: a cart-to-flagd ResolveBoolean call completed in about 1.6 ms end-to-end with sub-millisecond work on the flagd side, three orders of magnitude below the per-command cost dominating everything else. The upstream services were not the origin either — frontend, frontend-proxy and load-generator spans carried negligible self-time and were simply blocked waiting on cart. Product-catalog and its database calls completed in under 2 ms. No sampled span carried an error status, confirming from a second angle what the metrics had already said.

The flagd result did double duty. Because cart's own egress to flagd was fast in the same window, a delay sitting on cart's own network namespace would be expected to tax that call too and did not. That argues the delay sits on the store container's interface rather than cart's. This inference rests on a single fast trace and is the weakest load-bearing step in the chain.

> Evidence `tr_3802202f2784`:

```
<tool_result id="tr_3802202f2784" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00">
service: cart
10 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 170ada5a2258cea3  root load-generator/user_add_to_cart  1216.8ms  started 2026-10-12T00:33:58.358207+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 1216.8ms [self 1.0ms]
```

## Conclusion and remediation

Every cart request pays a fixed cost of roughly 300 ms per command issued to its Valkey cart store. AddItem pays it three times and lands near 900 ms; GetCart pays it once and lands near 300 ms. Nothing fails, which is why the error rules stayed silent and only the latency rules fired, and why the four non-cart alerts are callers queueing behind cart rather than independent problems. The remediation class is a restart: recreate the container whose network namespace holds the delay, which removes it. Confidence is medium — the chain from symptom to per-command cost is solid, the attribution of the delay to the store's interface rather than cart's is not.

> Evidence `tr_3802202f2784`:

```
<tool_result id="tr_3802202f2784" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00">
service: cart
10 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 170ada5a2258cea3  root load-generator/user_add_to_cart  1216.8ms  started 2026-10-12T00:33:58.358207+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 1216.8ms [self 1.0ms]
```

> Evidence `tr_6bcdc2aaf99e`:

```
<tool_result id="tr_6bcdc2aaf99e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_e358164dfd34`:

```
<tool_result id="tr_e358164dfd34" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_0fa62ef7350b`:

```
<tool_result id="tr_0fa62ef7350b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-12T00:04:33.517766+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T00:04:33.517906+00:00        AddItemAsync called with userId=8113b266-c5d0-11f1-9e56-ba3679c5fcbe, productId=9SIQT8TOJO, quantity=2
2026-10-12T00:04:33.526463+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T00:04:33.526489+00:00        GetCartAsync called with userId=8113b266-c5d0-11f1-9e56-ba3679c5fcbe
```

> Evidence `tr_0e9c09a06405`:

```
<tool_result id="tr_0e9c09a06405" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-11T00:34:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" radius="seed" hops="0">
no changes recorded for cart over this window
</tool_result:tr_0e9c09a06405>
```

## Open questions for whoever reads this next

Four things were never settled and should be checked first if this recurs.

No evidence at all was gathered from the Valkey cart-store container itself — no logs, no metrics, no change history. The entire argument that the delay sits on the store side rather than cart's rests on the one fast flagd trace. Pull the store's own telemetry before accepting that placement.

No p95 latency series and no request-rate series was retrieved for cart or for checkout. The metric queries that were run returned the error-ratio template instead. That means onset time and magnitude over the window are completely unmeasured; the latency figures in this record come from sampled traces, not from a series. Whether the delay ramped, stepped, or was present from the window's start is unknown.

Cart's logs are truncated across roughly thirty minutes of the window's interior. Nothing is known about that stretch.

And two traces show about 300 ms of self-time sitting outside the store command spans — once on the cart AddItem handler, twice on the frontend api-route span — which the store hypothesis does not account for. It may be an unsampled child operation or an occasional additional stall. It was not chased.

> Evidence `tr_6bcdc2aaf99e`:

```
<tool_result id="tr_6bcdc2aaf99e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_da71743adda0`:

```
<tool_result id="tr_da71743adda0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" template="error-ratio" baseline="2026-10-11T23:32:41.012028+00:00..2026-10-12T00:04:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_0fa62ef7350b`:

```
<tool_result id="tr_0fa62ef7350b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-12T00:04:33.517766+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T00:04:33.517906+00:00        AddItemAsync called with userId=8113b266-c5d0-11f1-9e56-ba3679c5fcbe, productId=9SIQT8TOJO, quantity=2
2026-10-12T00:04:33.526463+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-12T00:04:33.526489+00:00        GetCartAsync called with userId=8113b266-c5d0-11f1-9e56-ba3679c5fcbe
```

> Evidence `tr_3802202f2784`:

```
<tool_result id="tr_3802202f2784" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-12T00:04:31.664000+00:00..2026-10-12T00:36:22.315972+00:00">
service: cart
10 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 170ada5a2258cea3  root load-generator/user_add_to_cart  1216.8ms  started 2026-10-12T00:33:58.358207+00:00  24 spans
  +0.0ms load-generator/user_add_to_cart 1216.8ms [self 1.0ms]
```

