# Checkout order placement failing on unreadable cart records

## What we saw first

The page came from checkout, and nothing else. The visible symptom was order placement failing; everything downstream of that was inference until late in the investigation. The first instinct, which I'll flag now so you don't repeat it, was to treat checkout as the broken service. It was not. It was the service that noticed.

The blast radius counter showed nine services and eight edges we had no measurement across, which set the tone: almost every hop we cared about was unobserved, and most of the first hour was spent discovering that rather than learning anything.

## T+3m — the change log, and why it went nowhere

The obvious first move was to ask what had recently altered on checkout. The change history returned exactly eight entries for the whole seven-day window, every one of them an edit to a single environment variable holding the currency service address, and every one attributed to a platform automation actor rather than a person. They form four identical set-then-revert pairs, each cycle ten to twenty minutes long — a reconciliation loop or two controllers arguing over checkout's config, not a rollout.

All of that activity is packed into a roughly two-hour burst about three and a half days before onset. The log is completely empty for the days immediately preceding the incident. There were no code deploys, no image rollouts, no flag toggles anywhere in the history. So: no recent change to blame, no human to ask, no build to roll back.

One loose thread survives. The last entry in the sequence is a revert, meaning the currency address variable ends up absent rather than set. That is not obviously harmless — it is only obviously not proximate. Nobody has since demonstrated that checkout runs correctly without it.

> Evidence `tr_608b42db3d5b`:

```
<tool_result id="tr_608b42db3d5b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:53:31.370575+00:00" radius="seed" hops="0">
service: checkout
8 changes, ranked by suspicion
  #1  86.1h before onset  2026-10-10T06:47:58.823426+00:00  platform-automation  environment reverted: CURRENCY_ADDR reverted on checkout
      CURRENCY_ADDR=currencyservice:7001  ->  None
  #2  86.2h before onset  2026-10-10T06:39:40.851789+00:00  platform-automation  environment updated: CURRENCY_ADDR updated on checkout
```

## T+11m — two metric pulls that returned nothing

Both attempts to get checkout's error ratio and request rate over the window were rejected by the metrics backend with HTTP 400. Not a timeout, not a truncation, not an empty-but-valid answer — a parsed, server-generated rejection at query construction time. The backend was plainly alive to produce it.

This matters mainly as a warning about how to read the gap. An empty metrics panel here tells you nothing about whether checkout was serving traffic or emitting errors. It is a tooling problem wearing the costume of a signal, and more than one person in the room briefly read it as "checkout went silent." It did not; we simply never asked the question successfully. As a consequence, the size of the blast and the exact shape of onset remain unquantified to this day.

> Evidence `tr_1103cb2a4cb6`:

```
<tool_result id="tr_1103cb2a4cb6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-29T20:51:31.664000+00:00..2026-10-06T20:51:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_1103cb2a4cb6>
```

> Evidence `tr_8db102268896`:

```
<tool_result id="tr_8db102268896" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-29T20:51:31.664000+00:00..2026-10-06T20:51:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_8db102268896>
```

## T+24m — traces, sampled from the wrong minutes

The trace query matched ten checkout traces and returned four. All four show complete, clean PlaceOrder flows: cart, currency, email, payment, product-catalog, shipping and quote all present, none error-marked, all downstream latencies sub-millisecond to low single-digit milliseconds including the backing cache and SQL spans. The dominant time in every trace is self-time at the load-generator root, not any service-to-service hop.

Two things tempted us here and both are dead ends. First, the quote service child spans carry wildly negative start offsets against their parents in three of four traces — this is clock skew on that host, confirmed by the fourth trace showing a normal offset and by the sub-millisecond durations; it is not reordering and it is not a stall. Second, the clean traces nearly got written up as "downstream is healthy, so the problem is inside checkout." That conclusion was wrong, because every sampled trace is dated roughly an hour to ninety minutes before the point of interest. We never sampled the failing request path at all. The traces describe a healthy system shortly before the window we cared about.

> Evidence `tr_76bcce1c73ab`:

```
<tool_result id="tr_76bcce1c73ab" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 583467b0a10e3dbc  root load-generator/user_checkout_single  43.8ms  started 2026-10-13T19:24:03.074058+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 43.8ms [self 14.7ms]
```

## T+38m — the panics, which are real and not the answer

Searching checkout's logs surfaced a recurring Go nil-pointer dereference, and for a while this looked like the whole story. The stack names a specific application path — the PlaceOrder gRPC handler calling into its post-processor, surfacing through the tracing SDK's deferred span-end wrapper — which is satisfyingly specific.

The narrowed search settled it as a distraction. The identical signature, with the same panic argument values and the same runtime frame, appears at both the oldest and newest ends of the seven-day window, so it predates anything recent. The occurrences are annotated as recovered, so checkout is not crash-looping on it. And crucially, the most recent panic line is about thirteen hours before onset; the query retained the newest lines in the window, so a panic adjacent to the incident minute would have been kept, and none is.

This is a genuine latent defect in checkout's order path, including a dense burst of six events inside about two minutes earlier that day. It should be filed and fixed. It is not what paged us.

> Evidence `tr_3eadc1304f16`:

```
<tool_result id="tr_3eadc1304f16" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" oldest_kept="8" newest_kept="32" contains="panic">
selector: {service="checkout"} |= "panic"
2026-10-07T23:48:58.039586+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-07T23:48:58.040239+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-07T23:48:58.040274+00:00  panic({0x97b300?, 0x134c840?})
2026-10-07T23:48:58.040277+00:00  	/usr/local/go/src/runtime/panic.go:792 +0x124
```

> Evidence `tr_f363288ec2f7`:

```
<tool_result id="tr_f363288ec2f7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout"}
2026-10-07T23:48:58.039586+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-07T23:48:58.040239+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-07T23:48:58.040253+00:00  [signal SIGSEGV: segmentation violation code=0x1 addr=0x58 pc=0x82298c]
2026-10-07T23:48:58.040258+00:00  
```

## T+52m — the line that named the origin

The break came from looking one hop upstream instead of downstream. Frontend's logs, seconds before the reference timestamp, carry gRPC status 13 INTERNAL returned from the checkout call, describing a cart failure while fetching the user cart during checkout. The error detail checkout forwarded is the useful part: a FailedPrecondition raised by the cart service, originating in a protobuf deserialization failure in its Valkey-backed store, with both the add-item and get-cart paths appearing.

Three readings die on this evidence. It is not a transport problem — the RPC completed and the server produced a structured application-level error, so there was no reset or teardown. It is not checkout being unreachable; the only connection-refused line in the whole result is from frontend's own startup a week earlier and has nothing to do with this. And it is not transient: a deterministic decode failure against the same stored bytes fails identically on retry, which is consistent with the absence of any retry or backoff logging around that minute.

So the store was reachable and answering. What it handed back could not be read.

> Evidence `tr_aa1309b0cabe`:

```
<tool_result id="tr_aa1309b0cabe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T22:23:41.162149+00:00  ▲ Next.js 16.1.1
2026-10-06T22:23:41.162269+00:00  - Local:         http://e5aaed1047be:8080
2026-10-06T22:23:41.162271+00:00  - Network:       http://e5aaed1047be:8080
2026-10-06T22:23:41.162272+00:00  
```

## Where this landed

Checkout's PlaceOrder calls were failing with INTERNAL because cart could not deserialize the records it read back from its own store, on both the write and read paths. The problem is in the content of the stored bytes, not in connectivity, capacity, or latency. Checkout propagated the failure; it did not create it. Remediation class is data restoration.

Confidence here is medium, and the reason is worth stating plainly: the entire chain rests on one secondhand observation. We read cart's error through checkout's forwarding into frontend's logs.

> Evidence `tr_aa1309b0cabe`:

```
<tool_result id="tr_aa1309b0cabe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T22:23:41.162149+00:00  ▲ Next.js 16.1.1
2026-10-06T22:23:41.162269+00:00  - Local:         http://e5aaed1047be:8080
2026-10-06T22:23:41.162271+00:00  - Network:       http://e5aaed1047be:8080
2026-10-06T22:23:41.162272+00:00  
```

## Still open — read this before you repeat our path

No investigation was ever run against cart itself. Its own logs, the health of its Valkey instance, and the exact decode error are unknown except through the forwarded detail. That is the first thing to do next time, and it should have been the second thing we did this time.

The scope of the bad data is unsettled: all cart keys, a subset written by one path, or a version mismatch between the writing and reading encodings — we do not know. Relatedly, what wrote the unreadable bytes is entirely unestablished. Until that is answered, restoring data may fix the symptom and not prevent recurrence.

Checkout's error and request rates across onset are still unmeasured because both metric pulls were rejected; fix the query before you need it. The failing request was never captured in a trace. Whether the recurring nil-pointer panic is causally linked to malformed cart responses reaching a path that dereferences an unset field, or is wholly independent, is unresolved. And the absent currency address left behind by the last automated revert has not been shown to be harmless.

> Evidence `tr_aa1309b0cabe`:

```
<tool_result id="tr_aa1309b0cabe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T22:23:41.162149+00:00  ▲ Next.js 16.1.1
2026-10-06T22:23:41.162269+00:00  - Local:         http://e5aaed1047be:8080
2026-10-06T22:23:41.162271+00:00  - Network:       http://e5aaed1047be:8080
2026-10-06T22:23:41.162272+00:00  
```

> Evidence `tr_1103cb2a4cb6`:

```
<tool_result id="tr_1103cb2a4cb6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-29T20:51:31.664000+00:00..2026-10-06T20:51:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_1103cb2a4cb6>
```

> Evidence `tr_8db102268896`:

```
<tool_result id="tr_8db102268896" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-29T20:51:31.664000+00:00..2026-10-06T20:51:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_8db102268896>
```

> Evidence `tr_76bcce1c73ab`:

```
<tool_result id="tr_76bcce1c73ab" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 583467b0a10e3dbc  root load-generator/user_checkout_single  43.8ms  started 2026-10-13T19:24:03.074058+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 43.8ms [self 14.7ms]
```

> Evidence `tr_3eadc1304f16`:

```
<tool_result id="tr_3eadc1304f16" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:51:31.664000+00:00" oldest_kept="8" newest_kept="32" contains="panic">
selector: {service="checkout"} |= "panic"
2026-10-07T23:48:58.039586+00:00  panic: runtime error: invalid memory address or nil pointer dereference [recovered]
2026-10-07T23:48:58.040239+00:00  	panic: runtime error: invalid memory address or nil pointer dereference
2026-10-07T23:48:58.040274+00:00  panic({0x97b300?, 0x134c840?})
2026-10-07T23:48:58.040277+00:00  	/usr/local/go/src/runtime/panic.go:792 +0x124
```

> Evidence `tr_608b42db3d5b`:

```
<tool_result id="tr_608b42db3d5b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-06T20:51:31.664000+00:00..2026-10-13T20:53:31.370575+00:00" radius="seed" hops="0">
service: checkout
8 changes, ranked by suspicion
  #1  86.1h before onset  2026-10-10T06:47:58.823426+00:00  platform-automation  environment reverted: CURRENCY_ADDR reverted on checkout
      CURRENCY_ADDR=currencyservice:7001  ->  None
  #2  86.2h before onset  2026-10-10T06:39:40.851789+00:00  platform-automation  environment updated: CURRENCY_ADDR updated on checkout
```

