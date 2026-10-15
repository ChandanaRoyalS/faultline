# Checkout order failures traced to unreadable cart store contents

## What the alert said and what we saw first

The page came from checkout, presenting as a latency step at the edge. The first instinct was that checkout itself had gone bad.

Checkout's own error behaviour did not support that. The ratio of error-status spans to total spans showed no sustained departure from baseline; the window mean sat around a thirteenth of the baseline mean, with the window maximum below the baseline maximum. Not an outage, not a 5xx spike. One caveat for the next reader: the baseline series was very dispersed (standard deviation roughly twice the mean), which is what sparse errors at low call volume look like. Do not read the drop as checkout getting healthier — read it as no error step here. The same query returned nothing for checkout p95/p99 or request rate, so the latency half of the alert stayed unquantified for the whole investigation.

Frontend told the same story: its error ratio showed no departure from baseline either, running about half the baseline mean. That also kills the tidy theory that checkout slowness was tipping frontend calls into timeouts and surfacing as edge 5xx — a timeout conversion would have stepped the frontend error ratio at the alert boundary, and it did not.

> Evidence `tr_366bb131b4b8`:

```
<tool_result id="tr_366bb131b4b8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T06:20:46.664000+00:00..2026-10-14T06:52:47.872732+00:00" template="error-ratio" baseline="2026-10-14T05:48:45.455268+00:00..2026-10-14T06:20:46.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=129 mean=0.01079 min=0 max=0.08511 sd=0.02373
  baseline window: n=129 mean=0.1375 min=0 max=0.6667 sd=0.2561
```

> Evidence `tr_b556406d8424`:

```
<tool_result id="tr_b556406d8424" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T04:50:46.664000+00:00..2026-10-14T06:52:47.872732+00:00" template="error-ratio" baseline="2026-10-14T02:48:45.455268+00:00..2026-10-14T04:50:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=489 mean=0.02932 min=0 max=0.3 sd=0.06929
  baseline window: n=348 mean=0.05856 min=0 max=0.2904 sd=0.09897
```

## The dead ends, in the order we walked into them

Checkout's logs. The obvious next move returned zero lines across the full thirty-two minute window — not reduced volume, nothing, including the thirty minutes of healthy pre-alert operation that should have been chatty. Most plausible readings are a label or stream mismatch, a shipping outage for that one service, or retention not covering the window. This closed the most direct route to attribution: no timeout messages naming a downstream, no exception text, no error-rate inflection to use as a timing signal. Still unexplained, and the most actionable follow-up here.

Change history. Empty for checkout over twenty-four hours — no releases, config pushes, flag flips or manifest bumps. Two caveats: the query was scoped to the seed service only, zero hops, so cart and the other five direct dependencies were never covered; and the window's lower bound sat at the alert instant, so earlier changes fell outside what was searched. Change history for email was likewise empty at one hop; email had drawn suspicion only because its hop was the largest downstream call in one trace.

Traces, hunting a slow hop. Four checkout traces ran 43-78ms end to end, yet every client span to cart, payment, currency, product-catalog and shipping landed between sub-millisecond and about 5ms. Catalog SQL spans and cart hash-read spans were under a millisecond; flag-evaluation spans under the cart-empty path were 0.0-0.2ms; the shipping quote subtree totalled 2-5ms. Email looked interesting at ~16ms once but came in at ~8ms and ~3ms elsewhere. The time was instead unattributed self time: 17-35ms at the root span in every trace, and ~15ms inside the checkout PlaceOrder span in one trace with all its children under 2ms. One trace was structurally incomplete, stopping after order preparation with an unattached subtree at a negative offset — dropped or skewed spans, and how much that degrades these rule-outs is unquantified.

> Evidence `tr_fb725a1a554e`:

```
<tool_result id="tr_fb725a1a554e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T06:20:46.664000+00:00..2026-10-14T06:52:47.872732+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_fb725a1a554e>
```

> Evidence `tr_8c5a6ecb43bc`:

```
<tool_result id="tr_8c5a6ecb43bc" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T06:50:46.664000+00:00..2026-10-14T06:52:47.872732+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_8c5a6ecb43bc>
```

> Evidence `tr_941b36069ef9`:

```
<tool_result id="tr_941b36069ef9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T06:50:46.664000+00:00..2026-10-14T06:52:47.872732+00:00" radius="candidate_cause" hops="1">
no changes recorded for email over this window
</tool_result:tr_941b36069ef9>
```

> Evidence `tr_268f87638e09`:

```
<tool_result id="tr_268f87638e09" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T06:20:46.664000+00:00..2026-10-14T06:52:47.872732+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 4fa0ba4ba59e4bc1  root load-generator/user_checkout_multi  78.2ms  started 2026-10-14T06:31:50.736347+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 78.2ms [self 35.2ms]
```

## What actually broke, and what is still open

The answer came from frontend's log stream, which unlike checkout's was readable. Frontend's errors are gRPC application failures, not transport or timing failures: checkout returns status 13 INTERNAL saying it failed to get the user cart, wrapping an upstream status 9 FAILED_PRECONDITION from cart saying its cart storage could not be read, wrapping the actual cause — a protobuf deserialization failure in cart's Valkey-backed store, message truncated mid-field, on both the add-item and get-cart paths. The edge-visible failure originates two hops down, in the contents of cart's store. Frontend contributes only client stack frames; checkout is a relay.

This also settles three things. The store connection is fine: cart is reached, runs the read, and raises a decode exception rather than a connection error, which with the single-digit-millisecond dependency spans rules out a slow or unreachable datastore. Checkout is not crash-looping. And there is no retry storm — no retry or backoff lines, failures are terminal. The signature is present at the earliest retained line (about T-5m) and the last (about T+2m), so the condition spans the alert boundary rather than starting at it.

The latency signal is a separate thread and should not be re-merged: it sits in unattributed self time at the root and in PlaceOrder, in no dependency hop, with no accompanying error-ratio step anywhere. It may be independent or a telemetry artifact, and no checkout latency series was ever returned to test it.

Confidence is medium because cart itself was never dispatched — no cart logs, metrics, traces or change history. The whole verdict rests on cart's exception relayed through frontend. Still open: the scope of the bad data (all keys, a subset, spreading or static) is unmeasured; the store's persistence state, eviction policy and restart history were never checked and the writer of the truncated bytes is unidentified; change history for cart and the store was never queried, leaving a cart-side serialization change — writer and reader disagreeing on format — fully unexcluded; onset is unpinned, since the signature predates the alert; and checkout's telemetry gap deserves its own ticket. Fix class as reached is restore the store contents, but treat that as a hypothesis needing cart-side confirmation, not a dispatch order.

> Evidence `tr_ae3a9b7f0a85`:

```
<tool_result id="tr_ae3a9b7f0a85" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T06:20:46.664000+00:00..2026-10-14T06:52:47.872732+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T06:45:20.451154+00:00  Error: 9 FAILED_PRECONDITION: Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T06:45:20.451238+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillFromCodedInputStream(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T06:45:20.451252+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T06:45:20.451253+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

> Evidence `tr_268f87638e09`:

```
<tool_result id="tr_268f87638e09" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T06:20:46.664000+00:00..2026-10-14T06:52:47.872732+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 4fa0ba4ba59e4bc1  root load-generator/user_checkout_multi  78.2ms  started 2026-10-14T06:31:50.736347+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 78.2ms [self 35.2ms]
```

> Evidence `tr_fb725a1a554e`:

```
<tool_result id="tr_fb725a1a554e" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T06:20:46.664000+00:00..2026-10-14T06:52:47.872732+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_fb725a1a554e>
```

