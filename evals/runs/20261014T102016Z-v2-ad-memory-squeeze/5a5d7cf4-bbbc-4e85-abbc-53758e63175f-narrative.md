# Edge errors on the ad-serving path traced to a tightened memory cap on the ad service

## What we saw first, and why it misled

The page opened on two alerts: frontend and frontend-proxy. That framing cost us the first stretch of the investigation, because neither service was the source.

The opening check was whether frontend was actually erroring more than usual. It was not. Aggregate error ratio over the incident window came in at roughly a third of the preceding baseline average, with a lower peak too, and no sustained departure was flagged. Odder still, the baseline window was higher and more variable than the incident window — error-producing activity predates the declared onset. So "frontend is broken" and "frontend is failing all traffic" were both gone within minutes. Two limits of that look, recorded so nobody re-runs it hoping for more: it aggregated by service name only, with no route or dependency labels, and it returned no latency metric at all.

Traces then narrowed things sharply. Across ten frontend traces (152 spans) exactly one carried an error, innermost at frontend's outbound gRPC call to ad's GetAds, propagating up through the /api/data handler, the frontend GET span, both proxy spans, and the load generator — which is precisely why the two edge services alerted. They were reporting someone else's failure. The failing call is a leaf with no ad-side server span beneath it, and it is sub-millisecond: a fast-fail, not a timeout. Every other downstream (cart, product-catalog, checkout, currency, payment, shipping, email, quote, flagd) completed clean with child server spans, including the full checkout fan-out; nine of ten traces succeeded end to end. The trace data carried no span attributes, so it could not confirm a status code or a peer address.

> Evidence `tr_8385af5d0deb`:

```
<tool_result id="tr_8385af5d0deb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" template="error-ratio" baseline="2026-10-14T09:23:57.386417+00:00..2026-10-14T09:55:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.02211 min=0 max=0.07208 sd=0.02275
  baseline window: n=128 mean=0.0733 min=0 max=0.2447 sd=0.07896
```

> Evidence `tr_0d539ca75829`:

```
<tool_result id="tr_0d539ca75829" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00">
service: frontend
10 trace(s) shown of 10 found, 152 spans; offsets are from each trace's root

trace d53fe0bb6a313adb  root load-generator/user_checkout_single  74.7ms  started 2026-10-14T10:25:04.833997+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 74.7ms [self 11.6ms]
```

## Logs, and the detour worth keeping

The frontend log query was aimed at onset and missed it: the result truncated to the oldest eight lines (around T-22m) and the newest thirty-two (T+1m15s onward), discarding the middle. Narrow the range if you re-run this.

The tail was still decisive. From about T+1m15s to T+1m45s frontend repeated a gRPC status 14 UNAVAILABLE with a connect-time EHOSTUNREACH to 172.18.0.19:9555, carrying an embedded last-error stamp around T+20s and replayed identically on every attempt — one sticky connect failure surfaced per request. That killed several live hypotheses: not a deadline problem (the transport never established; no timeout value appears anywhere), not an application error from a reachable peer, not frontend crashing (it logs continuously to the end of the window), not DNS (the address resolved; the failure is at connect).

The dead end: at T-22m frontend logged a gRPC FAILED_PRECONDITION about cart storage with a .NET protobuf parse stack. Different signature, predates onset, consumed real attention, and still unexplained. No cart-scoped dispatch was ever run.

> Evidence `tr_da6b4d527fda`:

```
<tool_result id="tr_da6b4d527fda" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T10:03:49.437529+00:00  Error: 9 FAILED_PRECONDITION: Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T10:03:49.437591+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T10:03:49.437593+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T10:03:49.437594+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

## Change history and the ad-side signal

Frontend's change log looked promising and was noise: four platform-automation edits to a single environment variable (CART_ADDR), forming two matched set-then-revert pairs around 5.9h/5.7h and 2.0h/1.9h before onset. Net state at onset is the original value; closest action is ~1.9h out; no deploys, images, flags, or human actors. Product-catalog returned nothing at all for the window — no change to blame, and no release to roll back.

Ad is where it landed. At T-5m automation lowered ad's memory limit to a 144m cap, still in effect at onset with no revert recorded. This is the third identical lower-then-revert cycle in the window (earlier pairs ~02:34/02:43 and ~07:31/07:42), which also rules out the cap being a long-standing baseline condition.

Ad's own metrics nearly sent us away: error ratio below one percent, mean about 0.68x baseline, 116 samples showing it up and serving. The signal is in the absences — twelve intervals with no traffic at all, against zero in baseline. That is the fingerprint of a container being killed and restarted under the cap.

> Evidence `tr_7dfcc4517d4c`:

```
<tool_result id="tr_7dfcc4517d4c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T10:25:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" radius="seed" hops="0">
service: frontend
4 changes, ranked by suspicion
  #1  1.9h before onset  2026-10-14T08:32:57.576559+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  2.0h before onset  2026-10-14T08:24:32.568719+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_96b2087cdbd1`:

```
<tool_result id="tr_96b2087cdbd1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T10:25:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_96b2087cdbd1>
```

> Evidence `tr_2df4ae913d06`:

```
<tool_result id="tr_2df4ae913d06" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T10:25:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" radius="candidate_cause" hops="1">
service: ad
5 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T10:20:21.345000+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  2.7h before onset  2026-10-14T07:42:46.377755+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_8034c08b4603`:

```
<tool_result id="tr_8034c08b4603" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" template="error-ratio" baseline="2026-10-14T09:23:57.386417+00:00..2026-10-14T09:55:46.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=116 mean=0.003038 min=0 max=0.009901 sd=0.004238
  baseline window: n=128 mean=0.004462 min=0 max=0.01299 sd=0.005186
```

## Conclusion and open threads

The chain: automation lowered ad's memory limit to 144m at T-5m and never reverted it; under that cap ad is killed and restarted, producing the twelve no-traffic intervals; during those gaps frontend's GetAds call fails at connect time — the only error-bearing path across ten traces — and surfaces as gRPC 14 UNAVAILABLE to 172.18.0.19:9555; the error rides to the edge, which is the only reason frontend and frontend-proxy paged. Confidence medium. Fix is a configuration revert of the memory limit.

Three things stayed open. No ad-side logs, kill/restart events, or memory-usage metrics were gathered, so the memory mechanism is inferred rather than observed. The twelve no-traffic intervals carry no timestamps, so their clustering near the change and onset is unconfirmed, and the frontend log query dropped the lines spanning onset. The cart protobuf parse failure at T-22m is unexplained by this verdict.

> Evidence `tr_2df4ae913d06`:

```
<tool_result id="tr_2df4ae913d06" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T10:25:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" radius="candidate_cause" hops="1">
service: ad
5 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T10:20:21.345000+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  2.7h before onset  2026-10-14T07:42:46.377755+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_8034c08b4603`:

```
<tool_result id="tr_8034c08b4603" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" template="error-ratio" baseline="2026-10-14T09:23:57.386417+00:00..2026-10-14T09:55:46.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=116 mean=0.003038 min=0 max=0.009901 sd=0.004238
  baseline window: n=128 mean=0.004462 min=0 max=0.01299 sd=0.005186
```

> Evidence `tr_0d539ca75829`:

```
<tool_result id="tr_0d539ca75829" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00">
service: frontend
10 trace(s) shown of 10 found, 152 spans; offsets are from each trace's root

trace d53fe0bb6a313adb  root load-generator/user_checkout_single  74.7ms  started 2026-10-14T10:25:04.833997+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 74.7ms [self 11.6ms]
```

> Evidence `tr_da6b4d527fda`:

```
<tool_result id="tr_da6b4d527fda" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T09:55:46.664000+00:00..2026-10-14T10:27:35.941583+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T10:03:49.437529+00:00  Error: 9 FAILED_PRECONDITION: Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field.  This could mean either that the input has been truncated or that an embedded message misreported its own length.
2026-10-14T10:03:49.437591+00:00     at Google.Protobuf.SegmentedBufferHelper.RefillBuffer(ReadOnlySpan`1& buffer, ParserInternalState& state, Boolean mustSucceed)
2026-10-14T10:03:49.437593+00:00     at Google.Protobuf.ParsingPrimitives.ReadRawByte(ReadOnlySpan`1& buffer, ParserInternalState& state)
2026-10-14T10:03:49.437594+00:00     at Google.Protobuf.ParsingPrimitives.ParseRawVarint32SlowPath(ReadOnlySpan`1& buffer, ParserInternalState& state)
```

