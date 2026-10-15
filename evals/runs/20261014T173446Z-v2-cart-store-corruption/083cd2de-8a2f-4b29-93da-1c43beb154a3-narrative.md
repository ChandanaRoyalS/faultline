# Cart storage payloads failing protobuf decode; errors relayed through frontend and proxy

## What was on the screen first

The page came from the load generator and from frontend-proxy, severity warning, with the blast radius drawn around three services and the entry point at frontend-proxy. Taking T+0 as the start of the investigation window, nothing of interest existed for the first twenty-seven minutes: the frontend log stream returns nothing matching the selector until T+27m, and cart's error ratio is an exact flat zero across the whole preceding baseline — 124 samples, zero variance, zero floor. That flat baseline is worth remembering, because it means any nonzero reading later is a genuine regime change and not noise against normal spread.

The first instinct, given the alert source, was to treat frontend-proxy as the origin. That was wrong, and the proxy metrics said so quickly: across the window the proxy's upstream error ratio averaged about 0.65%, which is *lower* than its own preceding baseline of about 1.13%. The proxy was not the sick component. It did register a burst — a non-zero peak near 8.7% and a single threshold crossing at the final minute, T+31m — but for the bulk of the window it looked better than usual. The entry point of the blast radius was simply the first place a human-visible symptom surfaced.

> Evidence `tr_dd1afe8b86de`:

```
<tool_result id="tr_dd1afe8b86de" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=109 mean=0.006524 min=0 max=0.08676 sd=0.01742
  baseline window: n=124 mean=0.01133 min=0 max=0.03544 sd=0.01382
```

> Evidence `tr_ef0fc0ae8f42`:

```
<tool_result id="tr_ef0fc0ae8f42" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=109 mean=0.005152 min=0 max=0.0737 sd=0.01427
  baseline window: n=124 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_4475d4ef6c87`:

```
<tool_result id="tr_4475d4ef6c87" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T17:35:05.423067+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:05.427168+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T17:35:05.427194+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T17:35:05.427217+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## Following the errors down

Frontend's own error ratio told a similar shape: roughly 0.59% mean against a 0.26% baseline, a 2.3x move, but with a single change point detected at T+31m rather than any sustained elevation. The mean being near baseline for most of the window, with a late crossing, is the signature of something that began recently and was still ramping when the window closed.

The frontend logs are what broke the case open. Every error frontend emitted was a gRPC code 13 INTERNAL wrapper whose details carried a cart-service FailedPrecondition, and inside that, a .NET protobuf deserialization exception complaining that the message input ended mid-field — a truncated payload, or an embedded message misreporting its own length. The frontend frames in those traces are only the promise-rejection wrapper around a remote call. Frontend was a relay, not a source. The same signature was present on the oldest line (T+27m) and the newest (T+32m), so this was ongoing, not a blip, and it appeared on more than one cart operation: item addition and cart retrieval during checkout.

> Evidence `tr_2df8c615d997`:

```
<tool_result id="tr_2df8c615d997" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=109 mean=0.005935 min=0 max=0.08301 sd=0.01621
  baseline window: n=124 mean=0.002608 min=0 max=0.021 sd=0.006806
```

> Evidence `tr_4475d4ef6c87`:

```
<tool_result id="tr_4475d4ef6c87" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T17:35:05.423067+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:05.427168+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T17:35:05.427194+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T17:35:05.427217+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## Confirming at the source

Querying cart's own log stream directly confirmed the errors originate there rather than being an artifact of how frontend reports them. Cart emits one uniform signature: FailedPrecondition, detail reporting inability to access cart storage, caused by the protobuf parse failing on data it had already received. Earliest occurrence T+27m, continuing densely to the end of the window, frequently in bursts of two to four inside the same second.

The critical distinction here is between reachability and content. Cart connected to its Valkey-backed store, received bytes, and got a response body — all of which a parse exception presupposes. No connection-refused, DNS, timeout, or credential text appears anywhere in the matched lines. The failure sits at the stored-content and decode layer. Cart is also the originator of the status, not a pass-through: the exception comes from cart's own protobuf runtime.

Cart's metrics agree on severity: nonzero mean around 0.5% with a peak near 7.4%, so under 8% of calls affected at worst. Degraded, not down.

> Evidence `tr_7f7b1cd0a147`:

```
<tool_result id="tr_7f7b1cd0a147" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" oldest_kept="8" newest_kept="32" contains="FailedPrecondition">
selector: {service="cart"} |= "FailedPrecondition"
2026-10-14T17:35:05.368238+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:06.942076+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:06.971421+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:10.536205+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

> Evidence `tr_ef0fc0ae8f42`:

```
<tool_result id="tr_ef0fc0ae8f42" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=109 mean=0.005152 min=0 max=0.0737 sd=0.01427
  baseline window: n=124 mean=0 min=0 max=0 sd=0
```

## Dead ends worth keeping

Three lines of enquiry consumed time and produced nothing causal. Keep them so the next responder doesn't re-run them.

First, the change history on cart. Sixteen entries in a twenty-four-hour lookback, all from a platform-automation actor, all image-reference updates or reverts — eight on/off cycles of the same hotfix tag. It looks exactly like a smoking gun until you line up the clocks: the nearest entry is about 8.1 hours before onset, and it is a revert. Every update is paired with a revert, so the artifact actually running at onset is the same baseline image that was running before the first cycle. There is nothing newer to roll back from. No code change, no config change, no flag toggle, no human actor appears anywhere in the window.

Second, the change history on frontend. Six entries, same automation actor, all edits to one environment key, CART_ADDR — three matched set/revert pairs about eight to ten minutes apart, recurring three times over the day. The nearest one cleared the key roughly 1.7 hours before onset. Tempting, but again decoupled in time, and the surface is a single key rather than a broad config drift.

Third, the proxy-as-origin theory described above. It cost a round trip to disprove and the metric answer was unambiguous.

What these two change logs *do* leave behind is a genuine oddity: automation flapping repeatedly on both cart's image reference and frontend's CART_ADDR, with no human in the loop. Neither coincides with onset so neither explains this incident, but the loop itself deserves its own look.

> Evidence `tr_f6354810309e`:

```
<tool_result id="tr_f6354810309e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T17:37:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" radius="outside_radius">
service: cart
16 changes, ranked by suspicion
  #1  8.1h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  8.2h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_3c9db5402b70`:

```
<tool_result id="tr_3c9db5402b70" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T17:37:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" radius="candidate_cause" hops="1">
service: frontend
6 changes, ranked by suspicion
  #1  1.7h before onset  2026-10-14T15:54:48.298326+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  1.9h before onset  2026-10-14T15:45:50.202497+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

## Where this lands

The mechanism is corrupted or unparseable content in cart's Valkey-backed store, not an act of deployment and not a reachability problem. The fix class is restoring the stored data. Confidence is high on that reading: the error signature is byte-identical across every retained line, it appears on two independent cart code paths, cart's baseline error floor was exactly zero, and no change of any kind lands within hours of onset on either service.

> Evidence `tr_7f7b1cd0a147`:

```
<tool_result id="tr_7f7b1cd0a147" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" oldest_kept="8" newest_kept="32" contains="FailedPrecondition">
selector: {service="cart"} |= "FailedPrecondition"
2026-10-14T17:35:05.368238+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:06.942076+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:06.971421+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:10.536205+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

> Evidence `tr_4475d4ef6c87`:

```
<tool_result id="tr_4475d4ef6c87" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T17:35:05.423067+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = FailedPrecondition desc = Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:05.427168+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T17:35:05.427194+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T17:35:05.427217+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

> Evidence `tr_ef0fc0ae8f42`:

```
<tool_result id="tr_ef0fc0ae8f42" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=109 mean=0.005152 min=0 max=0.0737 sd=0.01427
  baseline window: n=124 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_f6354810309e`:

```
<tool_result id="tr_f6354810309e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T17:37:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" radius="outside_radius">
service: cart
16 changes, ranked by suspicion
  #1  8.1h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  8.2h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

## Open questions for whoever picks this up

The cart-to-store edge was never dispatched. That is the unmeasured edge triage flagged, and it is the single biggest gap: nobody queried the store itself. Whether the corruption lives in the stored values, in a writer that serialized them badly, or in some truncation or eviction behaviour of the store is unestablished.

The triggering event at T+27m is unidentified. Nothing is recorded near onset on cart or frontend, so a store restart, a memory-policy change, an eviction, or a partial write are all still live candidates and all unexamined.

Scope is unknown. A roughly 7% ceiling is consistent with a bounded set of affected keys, but no per-key or per-operation breakdown was obtained, so it is equally consistent with a rate still climbing when the window closed.

Request rate and latency were never queried for cart or frontend. Only the error-ratio template was run against each. A traffic or latency contribution is untouched rather than excluded — do not read it as ruled out.

The cart log query was filtered on the FailedPrecondition string. Other failure modes on cart would not have appeared under that filter, so the claim that cart has exactly one failure signature is scoped to that selector.

Finally, the metric change point at T+31m sits three and a half minutes after the first log line at T+27m. That is a detector threshold artifact, not a second event — low-level errors were present earlier but below the crossing level. Do not anchor a timeline on the change point.

> Evidence `tr_ef0fc0ae8f42`:

```
<tool_result id="tr_ef0fc0ae8f42" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=109 mean=0.005152 min=0 max=0.0737 sd=0.01427
  baseline window: n=124 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_2df8c615d997`:

```
<tool_result id="tr_2df8c615d997" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" template="error-ratio" baseline="2026-10-14T16:35:25.929973+00:00..2026-10-14T17:07:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=109 mean=0.005935 min=0 max=0.08301 sd=0.01621
  baseline window: n=124 mean=0.002608 min=0 max=0.021 sd=0.006806
```

> Evidence `tr_7f7b1cd0a147`:

```
<tool_result id="tr_7f7b1cd0a147" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:07:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" oldest_kept="8" newest_kept="32" contains="FailedPrecondition">
selector: {service="cart"} |= "FailedPrecondition"
2026-10-14T17:35:05.368238+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:06.942076+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:06.971421+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:10.536205+00:00        Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
```

> Evidence `tr_f6354810309e`:

```
<tool_result id="tr_f6354810309e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T17:37:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" radius="outside_radius">
service: cart
16 changes, ranked by suspicion
  #1  8.1h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  8.2h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_3c9db5402b70`:

```
<tool_result id="tr_3c9db5402b70" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T17:37:31.664000+00:00..2026-10-14T17:39:37.398027+00:00" radius="candidate_cause" hops="1">
service: frontend
6 changes, ranked by suspicion
  #1  1.7h before onset  2026-10-14T15:54:48.298326+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  1.9h before onset  2026-10-14T15:45:50.202497+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

