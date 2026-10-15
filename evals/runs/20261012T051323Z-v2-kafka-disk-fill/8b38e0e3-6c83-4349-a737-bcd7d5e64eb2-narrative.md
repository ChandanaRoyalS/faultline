# Checkout PlaceOrder crashing in its own post-processor path

## What the responder saw first

The page came from checkout, at T+0 (05:18:31 in wall-clock terms, used here only as the onset marker). frontend-proxy followed roughly two minutes later. Severity was called critical and the blast radius was recorded as nine services, with eight edges crossed that nobody had measurement on. From the chair, that shape reads as a single broken RPC with a caller noticing: checkout fails, the proxy in front of it reports the broken call, and the rest of the count is reachability rather than independent damage. Nothing in the later evidence changed that first reading.

## The change log, and why it went nowhere

The obvious first move was to ask what had changed on checkout in the preceding week. The change log returned eight entries, every one of them an edit to a single environment variable (CURRENCY_ADDR), all attributed to the same automated actor. They form a flapping pattern: four set/revert pairs over about ninety minutes, each cycle lasting eight to seventeen minutes. That looks damning until you line it up against the clock. The whole sequence sits roughly 46.5 to 48 hours before onset, and the last entry in the sequence is a revert — the variable was left unset. So checkout was not running with the applied value when it started failing, and there is a two-day quiet period immediately before the page. No deploy or release entries appear for checkout at all in the window, and no flag flips. Every entry is automation, not a human mid-response edit. This was the most seductive dead end in the investigation and it should be remembered as one.

> Evidence `tr_4107f89ed02e`:

```
<tool_result id="tr_4107f89ed02e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:21:22.530566+00:00" radius="seed" hops="0">
service: checkout
8 changes, ranked by suspicion
  #1  46.5h before onset  2026-10-10T06:47:58.823426+00:00  platform-automation  environment reverted: CURRENCY_ADDR reverted on checkout
      CURRENCY_ADDR=currencyservice:7001  ->  None
  #2  46.6h before onset  2026-10-10T06:39:40.851789+00:00  platform-automation  environment updated: CURRENCY_ADDR updated on checkout
```

## Currency ruled out as a change source

Because the flapping key named the checkout-to-currency edge, the next step was to ask the same question of currency-service. The log came back completely empty — no deploys, no port or listen-address edits, no scaling events. Note the window actually executed started at the onset timestamp and ran forward seven days rather than backward, so this evidence is strong on 'nothing changed during or after' and weaker on 'nothing changed before'. Within what it covers, no deploy, config edit, or scaling event on currency coincides with or sustains the incident.

> Evidence `tr_2754c2f01980`:

```
<tool_result id="tr_2754c2f01980" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:21:22.530566+00:00" radius="candidate_cause" hops="1">
no changes recorded for currency over this window
</tool_result:tr_2754c2f01980>
```

## Metrics: two attempts, nothing retrieved

Both attempts to baseline checkout's error ratio and request rate were rejected outright by Prometheus with HTTP 400. This is worth stating plainly because an empty metrics panel is easy to misread as a quiet service. It is not. The query never evaluated, so the empty payload carries no information about traffic or errors either way. The 400 also tells us the backend was alive and validating requests — a dead endpoint would have produced a timeout or connection error — so the metrics stack being down is not an explanation for anything here. The failure is in the query expression or its template parameters, probably the label or method selector. Checkout's error ratio and request rate at onset remain unmeasured.

> Evidence `tr_e1b6682a980d`:

```
<tool_result id="tr_e1b6682a980d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-28T05:18:31.664000+00:00..2026-10-05T05:18:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_e1b6682a980d>
```

> Evidence `tr_4d375df5a94e`:

```
<tool_result id="tr_4d375df5a94e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-28T05:18:31.664000+00:00..2026-10-05T05:18:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_4d375df5a94e>
```

## The logs, which carried the answer

Retained checkout logs are not warnings or degraded-mode chatter. They are Go runtime panics — nil pointer dereference, SIGSEGV — and the stack names a specific operation: the send-to-post-processor path, reached from the PlaceOrder handler, invoked through the generated CheckoutService gRPC unary handler. The same signature, with identical faulting address and program counter, appears at both the earliest and latest retained points of the week. That repetition across days is what rules out a one-off bad request or a single sick pod; this is a reproducible defect in the artifact checkout is running. Two near-misses to record: the panic surfaces through the OpenTelemetry SDK's span-End deferred recovery path, which makes tracing look implicated, but those frames are only the wrapper around the crash, not its origin. And no downstream RPC error status appears anywhere in the stack — the dereference happens in checkout's own frame before any downstream response handling, so the propagated-failure theory does not hold.

> Evidence `tr_6943c47a6092`:

```
<tool_result id="tr_6943c47a6092" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-07T23:48:58.039586+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-07T23:48:58.040239+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-07T23:48:58.040253+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-07T23:48:58.040258+00:00  
```

## Traces: clean, and from the wrong time

Five sampled PlaceOrder traces all show complete, normally-terminating span trees — cart GetCart, product-catalog GetProduct, two currency Convert calls, shipping get-quote, payment Charge, shipping ship-order, the email confirmation leg with its nested template renders, cart EmptyCart, and a terminal checkout 'orders publish'. Every downstream leg completes in single- or low-double-digit milliseconds, and the tool's own self-time attribution puts all of it in the load-generator root. On this evidence, currency Convert is not where PlaceOrder hangs, the email leg is not dangling, and the post-processor publish span is present and closed in four of five traces. Two caveats that matter more than the findings. First, every returned trace is timestamped roughly a day after onset, in a twenty-minute band; none fall at or before the onset moment, so the cohort we actually wanted was never inspected. Second, the result was truncated — five of ten matching traces — so nearer-boundary traces may exist and simply weren't returned. Also noted in passing and not pursued: quote-service spans carry large negative child offsets, tens of minutes to about an hour, which reads as clock skew or timestamp misattribution on that service rather than real ordering, and one trace is missing its entire frontend/checkout branch, an export gap rather than an abnormal termination.

> Evidence `tr_220bfd64ac6d`:

```
<tool_result id="tr_220bfd64ac6d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00">
service: checkout
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 6bf8a0c61ae3a138  root load-generator/user_checkout_single  288.0ms  started 2026-10-11T06:19:23.008374+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 288.0ms [self 176.5ms]
```

## Where it landed

Checkout crashes inside its own code. The panic signature is stable across the week and localised to one code path reached from PlaceOrder. That explains checkout alerting first and frontend-proxy following as the caller observing a broken RPC, and it explains why the eight crossed edges carry no sign of trouble. Fix class is rollback. Confidence is low, and deliberately so — see the gaps below.

> Evidence `tr_6943c47a6092`:

```
<tool_result id="tr_6943c47a6092" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-07T23:48:58.039586+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-07T23:48:58.040239+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-07T23:48:58.040253+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-07T23:48:58.040258+00:00  
```

> Evidence `tr_220bfd64ac6d`:

```
<tool_result id="tr_220bfd64ac6d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00">
service: checkout
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 6bf8a0c61ae3a138  root load-generator/user_checkout_single  288.0ms  started 2026-10-11T06:19:23.008374+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 288.0ms [self 176.5ms]
```

## Open questions for whoever picks this up

The artifact-version claim is inferred, not observed: there is no deploy record for checkout in the change log, so we cannot say when the faulting build started running. Checkout's error ratio and request rate at onset are still unmeasured and need the metric query corrected and re-run. The onset trace cohort was never inspected; re-query with a tighter window and a higher result limit. And the one thread genuinely worth pulling: whether an unset CURRENCY_ADDR is what leaves the nil pointer in the post-processor path. The config flap was dismissed on timing grounds, but the reverted-to-unset end state and the nil dereference may be the same story told from two directions.

> Evidence `tr_4107f89ed02e`:

```
<tool_result id="tr_4107f89ed02e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:21:22.530566+00:00" radius="seed" hops="0">
service: checkout
8 changes, ranked by suspicion
  #1  46.5h before onset  2026-10-10T06:47:58.823426+00:00  platform-automation  environment reverted: CURRENCY_ADDR reverted on checkout
      CURRENCY_ADDR=currencyservice:7001  ->  None
  #2  46.6h before onset  2026-10-10T06:39:40.851789+00:00  platform-automation  environment updated: CURRENCY_ADDR updated on checkout
```

> Evidence `tr_e1b6682a980d`:

```
<tool_result id="tr_e1b6682a980d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-28T05:18:31.664000+00:00..2026-10-05T05:18:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_e1b6682a980d>
```

> Evidence `tr_4d375df5a94e`:

```
<tool_result id="tr_4d375df5a94e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-28T05:18:31.664000+00:00..2026-10-05T05:18:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_4d375df5a94e>
```

> Evidence `tr_220bfd64ac6d`:

```
<tool_result id="tr_220bfd64ac6d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-05T05:18:31.664000+00:00..2026-10-12T05:18:31.664000+00:00">
service: checkout
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 6bf8a0c61ae3a138  root load-generator/user_checkout_single  288.0ms  started 2026-10-11T06:19:23.008374+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 288.0ms [self 176.5ms]
```

