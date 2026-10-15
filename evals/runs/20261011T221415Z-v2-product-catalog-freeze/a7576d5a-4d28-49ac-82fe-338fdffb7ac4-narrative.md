# Cart store returns unparseable values; user-visible 500s at the edge

## Summary

Take T0 as the moment frontend-proxy and the load-generator paged. The user-visible symptom was a modest but persistent stream of errors at the edge; the actual trouble sat two hops in, at the cart service's Valkey-backed store, which was handing back values that could not be deserialized. Cart raised a protobuf parse error (input ending unexpectedly mid-field), returned gRPC FailedPrecondition with 'Can't access cart storage', and frontend re-wrapped that as INTERNAL (13). The proxy and the load-generator only ever saw the last link in that chain. Nothing was deployed, pushed, flipped, or re-configured anywhere along the path. The fix class is data restoration, not a code or config rollback.

> Evidence `tr_b739b6f3ae1b`:

```
<tool_result id="tr_b739b6f3ae1b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32" contains="InvalidProtocolBufferException">
selector: {service="cart"} |= "InvalidProtocolBufferException"
2026-10-11T21:56:30.169443+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:34.793718+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:51.495733+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:57:37.882358+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

> Evidence `tr_ccb0e7094d7d`:

```
<tool_result id="tr_ccb0e7094d7d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-11T21:56:30.180951+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:30.181453+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-11T21:56:30.181459+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-11T21:56:30.181461+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## What was visible first

Two alarms, both at the edge: frontend-proxy and the load-generator. Checking frontend-proxy's error ratio against its own recent history, the baseline was clean — flat zero, no variance at all — and then errors appeared and stayed. Across the incident window the ratio averaged around 3% with bursts up to roughly 23%, and the sharpest escalation crossed 5% about two minutes before T0. Worth noting for anyone reading the graph later: errors were already non-zero well before that crossing. The change point is where it got loud, not where it started. The shape (high standard deviation around a low mean, over a hundred samples) said intermittent-but-sustained, not a single transient.

> Evidence `tr_5e9dce310bd5`:

```
<tool_result id="tr_5e9dce310bd5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" template="error-ratio" baseline="2026-10-11T21:16:29.247966+00:00..2026-10-11T21:48:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=129 mean=0.03206 min=0 max=0.2283 sd=0.0567
  baseline window: n=57 mean=0 min=0 max=0 sd=0
```

## One hop in: frontend

Frontend showed the same story in miniature — zero baseline, then a mean around 1% with a peak near 4%. That ratio is small enough to be misleading if you stop there; it ruled out any notion of a frontend-wide outage, but it also meant the failing path was a minority of frontend's traffic. Only requests that touched a cart were affected, which is exactly what a ~1% service-level ratio looks like when the edge sees 3%.

> Evidence `tr_2065b6b7a9b0`:

```
<tool_result id="tr_2065b6b7a9b0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" template="error-ratio" baseline="2026-10-11T21:16:29.247966+00:00..2026-10-11T21:48:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=129 mean=0.01014 min=0 max=0.04033 sd=0.01503
  baseline window: n=57 mean=0 min=0 max=0 sd=0
```

## The log line that decided it

Frontend's logs carried the upstream error verbatim: 'cart failure: failed to get user cart during checkout' and 'Can't access cart storage', with a Google.Protobuf.InvalidProtocolBufferException underneath — input ended unexpectedly mid-field. The stack placed the throw inside ValkeyCartStore within cartservice, not in frontend code. Critically, both GetCartAsync and AddItemAsync were failing with the identical exception, so this was not a read-only condition from the caller's point of view. Cart's own logs confirmed it independently: the same exception text on every one of forty-plus sampled lines, no variation, first seen about 22 minutes before T0, continuous through at least nine minutes later with no recovery gap. Failures arrived in tight bursts, several within milliseconds, which reads as concurrent requests landing on the same bad value.

> Evidence `tr_ccb0e7094d7d`:

```
<tool_result id="tr_ccb0e7094d7d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-11T21:56:30.180951+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:30.181453+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-11T21:56:30.181459+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-11T21:56:30.181461+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

> Evidence `tr_b739b6f3ae1b`:

```
<tool_result id="tr_b739b6f3ae1b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32" contains="InvalidProtocolBufferException">
selector: {service="cart"} |= "InvalidProtocolBufferException"
2026-10-11T21:56:30.169443+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:34.793718+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:51.495733+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:57:37.882358+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

## Dead ends worth keeping

Cart's error-ratio metric came back a flat, varianceless zero and would have talked you out of the correct answer entirely. The reason is boring and important: that query ran over a window beginning roughly eighteen hours before the event and almost certainly never covered it. If you are retracing this, re-run the cart error ratio over the actual half-hour around the alert before believing it.

Traces were a second dead end. Ten traces came back for frontend across the window, two hundred spans, and not one carried an error status — latency was the only signal. The explanation is coverage, not health: the newest returned trace started about seven minutes before T0, so the interesting minutes simply were not in the result set. Do not conclude from this that frontend spans were healthy at the time of the page.

The frontend logs were also truncated in the middle (oldest few and newest few lines retained), so the lines sitting exactly at T0 were dropped. The state at the alert is inferred from continuity on either side rather than directly observed.

> Evidence `tr_6ab71b11b784`:

```
<tool_result id="tr_6ab71b11b784" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T22:18:31.664000+00:00..2026-10-11T04:18:31.664000+00:00" template="error-ratio" baseline="2026-10-10T16:18:31.664000+00:00..2026-10-10T22:18:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=1441 mean=0 min=0 max=0 sd=0
  baseline window: n=720 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_efaacc5cefb2`:

```
<tool_result id="tr_efaacc5cefb2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00">
service: frontend
10 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace f5369e274047bc65  root load-generator/user_browse_product  4.9ms  started 2026-10-11T22:01:56.690678+00:00  10 spans
  +0.0ms load-generator/user_browse_product 4.9ms [self 0.6ms]
```

> Evidence `tr_ccb0e7094d7d`:

```
<tool_result id="tr_ccb0e7094d7d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-11T21:56:30.180951+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:30.181453+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-11T21:56:30.181459+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-11T21:56:30.181461+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## What turned out not to matter

Every change-related hypothesis came back empty over a 24-hour lookback. No deploys, config pushes, flag changes, or environment-variable changes for frontend; none for frontend-proxy, including routes, timeouts, and upstream pool settings; none for cart or its valkey-cart store, including eviction policy, memory limits, and connection settings. The empty answers were real observations of the window, not missing queries, and together they remove 'something shipped' from the table.

Also ruled out along the way: a frontend code bug (the exception originates downstream, frontend is a pass-through reporter); a network-level break between frontend and cart (the call reaches cart and returns a structured, detailed error — you would see connection refused or deadline exceeded otherwise); a write-side serialization bug (the exception fires while parsing a stored value, not while building one); mixed failure modes (one exception text, everywhere); and a pre-existing background error rate at either edge service (both baselines were exactly zero).

> Evidence `tr_aa075d94191b`:

```
<tool_result id="tr_aa075d94191b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T22:18:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" radius="candidate_cause" hops="1">
no changes recorded for frontend over this window
</tool_result:tr_aa075d94191b>
```

> Evidence `tr_9d3143f3ea59`:

```
<tool_result id="tr_9d3143f3ea59" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T22:18:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" radius="seed" hops="0">
no changes recorded for frontend-proxy over this window
</tool_result:tr_9d3143f3ea59>
```

> Evidence `tr_7a611a36b0ee`:

```
<tool_result id="tr_7a611a36b0ee" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-10T22:18:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" radius="outside_radius">
no changes recorded for cart over this window
</tool_result:tr_7a611a36b0ee>
```

> Evidence `tr_ccb0e7094d7d`:

```
<tool_result id="tr_ccb0e7094d7d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-11T21:56:30.180951+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:30.181453+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-11T21:56:30.181459+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-11T21:56:30.181461+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

> Evidence `tr_b739b6f3ae1b`:

```
<tool_result id="tr_b739b6f3ae1b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32" contains="InvalidProtocolBufferException">
selector: {service="cart"} |= "InvalidProtocolBufferException"
2026-10-11T21:56:30.169443+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:34.793718+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:51.495733+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:57:37.882358+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

## Conclusion

The stored cart values were corrupt or truncated. The store was reachable and the connection healthy; the breakage is on read-back and parse. Because both read and write request paths route through the same deserialization step, both surfaced the same error to callers. Confidence is high on the mechanism. Remediation belongs in the data layer — restore or clear the affected cart contents — not in a rollback of any service.

> Evidence `tr_b739b6f3ae1b`:

```
<tool_result id="tr_b739b6f3ae1b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32" contains="InvalidProtocolBufferException">
selector: {service="cart"} |= "InvalidProtocolBufferException"
2026-10-11T21:56:30.169443+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:34.793718+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:51.495733+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:57:37.882358+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

> Evidence `tr_ccb0e7094d7d`:

```
<tool_result id="tr_ccb0e7094d7d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-11T21:56:30.180951+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:30.181453+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-11T21:56:30.181459+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-11T21:56:30.181461+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## Still open

Nobody looked at valkey-cart itself. Memory pressure, eviction behaviour, persistence/AOF state, and restart history are all unexamined, so the origin of the truncation — an eviction, a partial save, a short write — is unsettled, and so is whether it can recur.

Scope and timing remain unpinned. Cart logs record no keys, cart IDs, or byte sizes, so we cannot say whether one value or many were affected; the burst pattern hints broad but cannot prove it. Combined with the truncated log result and the trace coverage gap, the precise start and the state at T0 are inferred rather than measured.

Finally, re-run cart's error ratio over the correct window. One unmeasured edge was crossed in this investigation, and that metric is the cheapest way to close it.

> Evidence `tr_b739b6f3ae1b`:

```
<tool_result id="tr_b739b6f3ae1b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00" oldest_kept="8" newest_kept="32" contains="InvalidProtocolBufferException">
selector: {service="cart"} |= "InvalidProtocolBufferException"
2026-10-11T21:56:30.169443+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:34.793718+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:56:51.495733+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-11T21:57:37.882358+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

> Evidence `tr_6ab71b11b784`:

```
<tool_result id="tr_6ab71b11b784" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T22:18:31.664000+00:00..2026-10-11T04:18:31.664000+00:00" template="error-ratio" baseline="2026-10-10T16:18:31.664000+00:00..2026-10-10T22:18:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=1441 mean=0 min=0 max=0 sd=0
  baseline window: n=720 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_efaacc5cefb2`:

```
<tool_result id="tr_efaacc5cefb2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-11T21:48:31.664000+00:00..2026-10-11T22:20:34.080034+00:00">
service: frontend
10 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace f5369e274047bc65  root load-generator/user_browse_product  4.9ms  started 2026-10-11T22:01:56.690678+00:00  10 spans
  +0.0ms load-generator/user_browse_product 4.9ms [self 0.6ms]
```

