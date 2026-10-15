# Cart storage returning unparseable payloads, surfacing as edge errors

## What was visible, in order

The page came from the edge: frontend-proxy and load-generator both alerted, severity critical, three services in the blast radius. The first hard number was the proxy's span error ratio, which sits at or near zero for most of the preceding half hour and then crosses the detection threshold about a minute before the reference point, reaching roughly 14% at the crossing and about 27% at its worst. The window mean is only ~1.2x baseline because the shape is a late sharp step, not a climb. That ruled out a slow build, ruled out an onset predating the window, and ruled out the proxy being symptom-free — but also ruled out a total outage, since most spans still completed. Only the error-ratio series came back; request rate and latency percentiles were never returned, so throughput and latency stayed unmeasured rather than cleared.

Frontend logs were the one place with substance. Everything frontend emits is a relayed gRPC status from cart: FAILED_PRECONDITION (code 9, cart storage inaccessible) and INTERNAL (code 13) during checkout. Every stack trace terminates in cart-service Valkey cart-store code at a protobuf deserialization failure, on both the add-item and get-cart paths. A parse failure happens on bytes that came back, so the store was reachable and answering — the content was malformed or truncated. That is why timeouts, deadline-exceeded, connection resets and a store outage were all set aside; none produce that error shape and none appear in the logs. Awkwardly, these same errors run from roughly T-60m, nearly an hour before the edge excursion.

> Evidence `tr_3cc984ae143c`:

```
<tool_result id="tr_3cc984ae143c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T18:05:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" template="error-ratio" baseline="2026-10-14T17:33:33.589964+00:00..2026-10-14T18:05:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.02416 min=0 max=0.2731 sd=0.06916
  baseline window: n=128 mean=0.0202 min=0 max=0.08936 sd=0.03139
```

> Evidence `tr_fb32cfc2242a`:

```
<tool_result id="tr_fb32cfc2242a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:35:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T17:35:36.707029+00:00  Error: 9 FAILED_PRECONDITION: Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:36.707371+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T17:35:36.707378+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T17:35:36.707381+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## Dead ends worth keeping

Proxy logs returned zero lines of any kind for the entire window — not zero errors, zero output under that label. That killed two plans: the proxy could not anchor the onset second, and narrowing the query with level or message filters was pointless, since an empty unfiltered selector guarantees every narrower one is empty too. Still unexplained: collection gap, label mismatch, or the proxy not emitting.

Traces were the fallback. Ten traces, 188 spans, no error status anywhere; proxy ingress and egress spans contributed sub-millisecond self time in every one, which is what retired the proxy as a candidate. Root durations ran 5-97 ms through product-catalog, cart, ad, recommendation and the full checkout chain, all completing normally. The sample ends about 3.5 minutes before the crossing, so clean traces mean errors were narrow in time, not absent.

The change hypothesis failed twice. Proxy change history is completely empty — no rollouts, routing pushes, rate-limit edits, or post-onset remediation — though note the window queried ran forward from the reference time, so the lead-up was never directly examined. Frontend's log holds six entries, all automation-authored, all one variable (CART_ADDR), as three apply-then-revert pairs ending about 2.7 hours before onset with a revert. No deploy, no flag flip, no human edit, no lingering drift.

Finally, frontend itself: two independent passes put its error ratio at identically zero across 128 samples, against a ~1.9% baseline. The metric improved. Frontend is a relay, not the surface.

> Evidence `tr_c246a55b30e6`:

```
<tool_result id="tr_c246a55b30e6" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T18:05:31.664000+00:00..2026-10-14T18:37:29.738036+00:00">
no log lines matched {service="frontend-proxy"} over this window
</tool_result:tr_c246a55b30e6>
```

> Evidence `tr_3584deb08b7a`:

```
<tool_result id="tr_3584deb08b7a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T17:35:31.664000+00:00..2026-10-14T18:37:29.738036+00:00">
service: frontend-proxy
10 trace(s) shown of 10 found, 188 spans; offsets are from each trace's root

trace 1addabbcc131f566  root load-generator/user_browse_product  7.7ms  started 2026-10-14T18:25:07.820425+00:00  10 spans
  +0.0ms load-generator/user_browse_product 7.7ms [self 0.4ms]
```

> Evidence `tr_0c5702aba5e7`:

```
<tool_result id="tr_0c5702aba5e7" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T18:35:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" radius="candidate_cause" hops="1">
service: frontend
6 changes, ranked by suspicion
  #1  2.7h before onset  2026-10-14T15:54:48.298326+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  2.8h before onset  2026-10-14T15:45:50.202497+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_1b45dab3107b`:

```
<tool_result id="tr_1b45dab3107b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T18:05:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" template="error-ratio" baseline="2026-10-14T17:33:33.589964+00:00..2026-10-14T18:05:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.01905 min=0 max=0.08558 sd=0.02997
```

## Conclusion and what is still open

The failing mechanism is in the cart service's Valkey-backed cart store: stored cart payloads cannot be deserialized. The edge excursion is the user-visible surfacing of cart-path failures. Fix class is data restoration. Confidence is medium, for a blunt reason: no query was ever dispatched against cart itself — no cart logs, metrics, traces or change history exist in this record. The whole conclusion rests on stack traces frontend happened to relay.

Open items for the next responder. First, get cart-side confirmation: parse-failure rate, direct key inspection, recent cart rollout or serialization-format change. Second, resolve the hour-long gap — cart errors from T-60m versus an edge crossing at T-1m. The frontend log result was truncated with its newest retained line near T-53m and the trace sample ends 3.5 minutes early, so the onset minutes were never directly observed by anything but the proxy's counter; whether the corruption worsened or something separate drove the spike is unsettled. Third, explain the proxy's total log silence, since until then a proxy-local problem is excluded only by trace evidence. Fourth, no latency, request-rate or saturation series were returned for either service, so a concurrent slowdown is unmeasured. Fifth, the origin of the corruption — format change, partial write, eviction or truncation, or a store-side failure — is unestablished, and that determines whether clearing the store is sufficient or the problem recurs.

> Evidence `tr_fb32cfc2242a`:

```
<tool_result id="tr_fb32cfc2242a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T17:35:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T17:35:36.707029+00:00  Error: 9 FAILED_PRECONDITION: Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T17:35:36.707371+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T17:35:36.707378+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T17:35:36.707381+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

> Evidence `tr_3cc984ae143c`:

```
<tool_result id="tr_3cc984ae143c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T18:05:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" template="error-ratio" baseline="2026-10-14T17:33:33.589964+00:00..2026-10-14T18:05:31.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=128 mean=0.02416 min=0 max=0.2731 sd=0.06916
  baseline window: n=128 mean=0.0202 min=0 max=0.08936 sd=0.03139
```

> Evidence `tr_474fb03453e0`:

```
<tool_result id="tr_474fb03453e0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T18:05:31.664000+00:00..2026-10-14T18:37:29.738036+00:00" template="error-ratio" baseline="2026-10-14T17:33:33.589964+00:00..2026-10-14T18:05:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0.01905 min=0 max=0.08558 sd=0.02997
```

