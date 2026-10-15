# Cart goes silent; four callers alert one deadline later

## What the page looked like

The first signal was cart, with a warning-severity alert. Exactly sixty seconds later, four more alerts landed together: checkout, frontend, frontend-proxy and load-generator. Blast radius ended up at fourteen services, all of them reachable from cart across edges we have no measurements for.

The shape of that sixty-second gap is the single most informative thing on the page. Callers that receive errors from a downstream tend to alert within a few seconds, because the errors propagate as fast as the requests do. Callers that alert in lockstep one deadline after the downstream are not receiving anything at all — they are sitting on open sockets until their own client timeout fires. Treat the 60s offset as a timer, not as propagation delay, and the rest of the investigation follows from it.

## Cart's own account of itself

Pulling cart's log stream for the week was the first move and it was more useful for what it lacked than what it held. In roughly the seven seconds before onset, cart emitted a continuous run of info-level cart-store lines — retrievals, item additions, cart empties — for several distinct user ids, spaced under a second apart. Normal request serving, no gaps.

Then the stream stops. The last line sits about 1.6 seconds before the onset second, and there is nothing at the onset second itself. No exception, no stack trace, no warning, no dependency or connectivity complaint, anywhere in the window — not at the Oct 7 head and not in the final lines. The service did not announce anything. It simply stopped writing.

One cosmetic oddity: several cart-retrieval lines carry an empty user id, including one of the last before onset. The same pattern appears at the very start of the week-long window, so it is routine and was set aside.

> Evidence `tr_8534d32ee05f`:

```
<tool_result id="tr_8534d32ee05f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T18:19:37.367105+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T18:19:37.367443+00:00        GetCartAsync called with userId=
2026-10-07T18:19:37.796894+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T18:19:37.796922+00:00        AddItemAsync called with userId=a7d41b28-c27b-11f1-9fe0-eedf78b04444, productId=0PUK6V6EV0, quantity=5
```

## Traces: healthy, and from the wrong hours

The trace query returned cart server handlers — AddItem, GetCart, EmptyCart — all completing in roughly 0.2 to 4.7ms. Valkey cart-store operations (HGET, HMSET, EXPIRE) were sub-millisecond throughout and made up only a small share of each handler. One flag-evaluation hop from cart measured ~2.6ms, of which the server side was ~0.1ms. No span carried an error status; the full checkout PlaceOrder flow completed, with cart contributing ~2.4ms and ~5.3ms inside a 147.8ms trace. Critical-path attribution never landed on cart — it fell on load-generator self-time, frontend's product-catalog call, or frontend's own client-side self-time on AddItem.

The caveat is large enough to swallow the finding. Only ten traces exist across the whole seven-day window, eight returned, and every one of them started between 06:49 and 06:52 on the final day. The minutes before onset are not represented at all. This evidence says cart was healthy that morning. It says nothing about the onset second.

> Evidence `tr_d49ca741ffa3`:

```
<tool_result id="tr_d49ca741ffa3" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 19ab021edd2aa718  root load-generator/user_checkout_single  147.8ms  started 2026-10-14T06:49:25.158245+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 147.8ms [self 63.8ms]
```

## Nothing landed near onset

The change record for cart is complete and untruncated for the week and holds 26 entries, every one attributed to the same automated actor. No human-authored deploy appears.

The nearest entry to onset is 8.7 hours prior, and it is a revert — cart's image reference moved away from a hotfix tag. The image activity is a repeated paired apply/revert cycle on that same tag: sixteen entries clustered between roughly 12 and 19.5 hours before onset, plus a pair around 64 hours, with each apply undone within 8 to 13 minutes. Because the sequence ends on a revert, cart was not running that build at onset.

A second cluster, eight entries around 136 to 138 hours before onset, records a traffic-shaping container being attached to and removed from cart's network namespace with a fixed 300ms delay and no jitter on eth0. The last entry in that cluster is a removal, with no re-attach afterwards in the window.

Both patterns look like automated reconciliation or test tooling rather than ordinary release work. Neither is active at onset.

> Evidence `tr_cece856a551e`:

```
<tool_result id="tr_cece856a551e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:15:20.088014+00:00" radius="seed" hops="0">
service: cart
26 changes, ranked by suspicion
  #1  8.7h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  8.8h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

## Dead ends, kept deliberately

These cost time and should cost the next reader none.

The hotfix image build. It is the most eye-catching thing in the change record and it is not the answer — every apply is followed by a revert, and the final action is a revert 8.7 hours before onset.

The 300ms shaping sidecar. Equally eye-catching, equally irrelevant: the cluster ends on a removal roughly 136.7 hours before onset.

The cart store. Logs show store calls continuing without interruption to within 1.6s of onset, and traces show store operations sub-millisecond and a minor share of handler time. The store was not stalling cart.

Flag evaluation. Single-digit milliseconds client side, ~0.1ms server side. Too small to matter.

Cart returning errors to its callers. No error status on any sampled span, no error line in any log, and checkout's full flow completes. If cart had been erroring, the callers would not have waited a full minute.

A flag toggle or config edit. The change record contains only image references and namespace container attach/detach events. There are no flag or config entries of any kind in the window.

An unreviewed manual push. All 26 entries carry the same automation actor; no human change exists in the window.

> Evidence `tr_cece856a551e`:

```
<tool_result id="tr_cece856a551e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:15:20.088014+00:00" radius="seed" hops="0">
service: cart
26 changes, ranked by suspicion
  #1  8.7h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  8.8h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_8534d32ee05f`:

```
<tool_result id="tr_8534d32ee05f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T18:19:37.367105+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T18:19:37.367443+00:00        GetCartAsync called with userId=
2026-10-07T18:19:37.796894+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T18:19:37.796922+00:00        AddItemAsync called with userId=a7d41b28-c27b-11f1-9fe0-eedf78b04444, productId=0PUK6V6EV0, quantity=5
```

> Evidence `tr_d49ca741ffa3`:

```
<tool_result id="tr_d49ca741ffa3" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 19ab021edd2aa718  root load-generator/user_checkout_single  147.8ms  started 2026-10-14T06:49:25.158245+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 147.8ms [self 63.8ms]
```

## The instrument that failed

Two metric queries were run against the metrics backend and both were rejected with HTTP 400 Bad Request. No request rate, no latency quantiles, no error counts, and no CPU, memory, thread or connection-pool figures came back.

This matters twice. First, read the empty results correctly: they are empty because the request was refused, not because the series returned zeros. They carry no information about cart's traffic or error rate in either direction. Second, the backend answered with a structured 400, meaning it parsed the request and rejected it — the telemetry store was up; the query was the problem. Inspection of the second attempt shows the call that actually executed carried an error-ratio template and a comparison baseline window of the preceding week, which is not the plain query that was intended. The next responder should re-run with a corrected, non-templated query before concluding anything from metrics.

> Evidence `tr_03ade817f8aa`:

```
<tool_result id="tr_03ade817f8aa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T18:12:31.664000+00:00..2026-10-07T18:12:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_03ade817f8aa>
```

> Evidence `tr_e5ebb21cb828`:

```
<tool_result id="tr_e5ebb21cb828" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T18:12:31.664000+00:00..2026-10-07T18:12:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_e5ebb21cb828>
```

## Where this landed

A service that is unchanged, that logs no errors, whose dependencies are fast, and whose callers all time out exactly one deadline after it goes quiet, is a service whose process has stopped doing work while its listening socket still accepts connections. Callers connect, send, and wait; nothing comes back; they give up on their own timer sixty seconds later. That is the reading that fits every piece of evidence here, including the absence of evidence.

Fix class: restart the cart process.

Confidence is low, and the reason is structural rather than interpretive. Every query window terminates at onset. There is no observation of cart after it went quiet — the stall is inferred from silence at a boundary, not seen.

> Evidence `tr_8534d32ee05f`:

```
<tool_result id="tr_8534d32ee05f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T18:19:37.367105+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T18:19:37.367443+00:00        GetCartAsync called with userId=
2026-10-07T18:19:37.796894+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T18:19:37.796922+00:00        AddItemAsync called with userId=a7d41b28-c27b-11f1-9fe0-eedf78b04444, productId=0PUK6V6EV0, quantity=5
```

> Evidence `tr_d49ca741ffa3`:

```
<tool_result id="tr_d49ca741ffa3" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00">
service: cart
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 19ab021edd2aa718  root load-generator/user_checkout_single  147.8ms  started 2026-10-14T06:49:25.158245+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 147.8ms [self 63.8ms]
```

> Evidence `tr_cece856a551e`:

```
<tool_result id="tr_cece856a551e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:15:20.088014+00:00" radius="seed" hops="0">
service: cart
26 changes, ranked by suspicion
  #1  8.7h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  8.8h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

## Still open

Three gaps, in the order I would close them.

One: caller-side evidence was never gathered. Whether checkout and frontend recorded timeouts versus non-OK statuses from cart would separate a stalled process from a connectivity break decisively, and it is a single query away.

Two: saturation is entirely unmeasured because both metric calls were refused. A garbage-collection pause or a lock deadlock driven by resource pressure is not excluded and cannot be until a working query runs.

Three: nothing covers cart after onset. Extend the window past the onset second — logs, traces and process state — before accepting the account above.

> Evidence `tr_03ade817f8aa`:

```
<tool_result id="tr_03ade817f8aa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T18:12:31.664000+00:00..2026-10-07T18:12:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_03ade817f8aa>
```

> Evidence `tr_e5ebb21cb828`:

```
<tool_result id="tr_e5ebb21cb828" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T18:12:31.664000+00:00..2026-10-14T18:12:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T18:12:31.664000+00:00..2026-10-07T18:12:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_e5ebb21cb828>
```

