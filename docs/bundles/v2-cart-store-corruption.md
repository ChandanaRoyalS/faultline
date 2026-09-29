# Every cart in the store is unreadable - the store answers, and what it holds cannot be parsed

## The scenario

| | |
|---|---|
| scenario | `v2-cart-store-corruption` |
| fault class | **`datastore_corruption`** |
| expected remediation | `restore_data` |
| split | `dev` |
| injected at | `valkey-cart` via `v2-cart-store-corruption` |
| time to page | 6m16s |
| steady state captured | 300s |
| capture window | 2026-09-29T00:15:23+00:00 → 2026-09-29T00:33:39+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+6m16s |
| `t_revert` | T+11m16s |
| all clear | T+11m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+6m15s | `checkout` | ServiceHighErrorRate | 2.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="valkey-cart"}` |

`logs/valkey-cart.txt` — 69 lines.

## A look at the logs

From `logs/valkey-cart.txt` (---- onset 2026-09-29T00:20:23+00:00 ----):

```
2026-09-29T00:19:44+00:00  1:M 29 Sep 2026 00:19:44.027 * 100 changes in 300 seconds. Saving...
2026-09-29T00:19:44+00:00  1:M 29 Sep 2026 00:19:44.028 * Background saving started by pid 51944
2026-09-29T00:19:44+00:00  51944:C 29 Sep 2026 00:19:44.030 * DB saved on disk
2026-09-29T00:19:44+00:00  51944:C 29 Sep 2026 00:19:44.030 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-09-29T00:19:44+00:00  1:M 29 Sep 2026 00:19:44.130 * Background saving terminated with success
2026-09-29T00:20:45+00:00  1:M 29 Sep 2026 00:20:45.098 * 10000 changes in 60 seconds. Saving...
2026-09-29T00:20:45+00:00  1:M 29 Sep 2026 00:20:45.098 * Background saving started by pid 52926
2026-09-29T00:20:45+00:00  52926:C 29 Sep 2026 00:20:45.101 * DB saved on disk
2026-09-29T00:20:45+00:00  52926:C 29 Sep 2026 00:20:45.101 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-09-29T00:20:45+00:00  1:M 29 Sep 2026 00:20:45.199 * Background saving terminated with success
2026-09-29T00:21:46+00:00  1:M 29 Sep 2026 00:21:46.052 * 10000 changes in 60 seconds. Saving...
2026-09-29T00:21:46+00:00  1:M 29 Sep 2026 00:21:46.052 * Background saving started by pid 55590
```

_48 further lines are in the bundle._

## The incident record

Written from the responder's chair, by someone who did not know the fault class
or that anything had been injected. This text is also corpus material, which is
why it never names the injector.

**It keeps its own clock.** The table above is measured from the injection, which
is the only origin the manifest records; a narrative's `T+` offsets are the
responder's own and start wherever that responder started counting — usually the
page, sometimes the injection, sometimes an event in the logs. The same moment can
therefore carry two different offsets on this page. The absolute timestamps in the
bundle are the tiebreak.

### What was observed

The page came 6m16s after the first failed request, and it was one line: `ServiceHighErrorRate` on
**checkout**. Nothing before it, nothing beside it - no latency alert anywhere, no service gone
quiet - and nothing after it. One alert on one service by the fix.

Then, under two minutes after it fired and about three minutes before anything was done, it
cleared on its own. Checkout's
error ratio had come down from a peak of 7.2% to 4.5% and kept falling - 3.0, 2.0, 1.3% - while
the failures it was counting went on. The world read all clear for the last three minutes of the
fault, and the record's all-clear is stamped at the fix itself because nothing was left firing
for the fix to clear.

The storefront was mostly working. Product pages, recommendations and ads served as usual; the
frontend's p95 sat at 28 to 35ms for the whole window and its request rate held at 11 to 12 a
second. Its error ratio rose to 3.2% and the proxy's to 3.5%, both under their line, the load
generator's to 1.9%. Checkout's ratio climbed from the first minute - 1.8, 2.2, 3.4, 5.5% - to its
peak at T+6, and its 95th percentile went **down** while it did, from 21ms to 10 to 18ms: the
orders that failed were shorter than the ones that completed. Cart's error ratio moved too, from
zero to 1.2% at T+1 and 2.8% at its highest, never near its line, its p95 at 2ms throughout, the
same 2ms it shows at rest. Nothing anywhere hung, slowed, restarted or went silent; something was
failing at once, a few times a minute, on the way to a store that answers in a fraction of a
millisecond.

### What was checked

**Checkout, because it paged.** Its error traces were all orders - `user_checkout_multi` and
`user_checkout_single` from the load generator - and all short, 16 to 27 milliseconds from edge to
end. Under each, checkout's `PlaceOrder` in error in under a millisecond with one message: `cart
failure: failed to get user cart during checkout`, wrapping a `FailedPrecondition` from the cart
service; beneath that, `CartService/GetCart` in error; beneath that cart's own server span **in
error at 0.4 to 0.6 milliseconds**, carrying the detail `Can't access cart storage.
Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended
unexpectedly in the middle of a field`; and beneath cart's span, the one thing it had done before
failing: **`HGET`, 0.2 milliseconds, not in error**. The store had been asked for the cart and had
answered at once. What it answered with could not be read.

**The frontend's error traces, because they were twice checkout's.** The same orders, and as many
again from `user_add_to_cart`: cart's `AddItem` in error the same way, over the same successful
`HGET`, because adding to a cart reads it first. One trace held both halves of the story - an
`AddItem` that created a new cart, `HGET`, `HMSET`, `EXPIRE`, all fine, and the `GetCart` straight
after it failing on its `HGET`: a cart written a millisecond earlier, read back as something that
was no longer a cart.

**Cart's log.** At rest it writes a `GetCartAsync called` line per read, 30 to 67 a minute, and
those went on. From 10 seconds after the onset it added `Error status code 'FailedPrecondition'
with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While
parsing a protocol message, the input ended unexpectedly in the middle of a field'` - 44 of them in
the fault's eleven minutes, up to ten a minute, none in the five minutes before and none after
the fix. **Cart was reaching its store and failing to read what it got back.** A wrong address logs
a connection failure; a store that is down logs a refused or timed-out connection; a store that is
slow logs nothing and shows in the p95. This was a decode failure on a connection that answered.

**Cart's own view of itself.** Its .NET runtime series reported without a gap for the whole
window; it did not restart; its p95 did not move; its store commands took the same fraction of a
millisecond they take at rest. The process was healthy and so was every call it made. Whatever was
wrong was in the bytes.

**Why cart did not page.** Most of what cart does cannot fail this way: a cart that does not exist
yet reads as empty, a write succeeds, and every store command it sends is a span of its own and
succeeds. Its failures, a few a minute, were a small share of everything it emitted - under 3%.
Checkout's were not: an order reads the cart once and fails whole when that read fails.

**The store.** valkey-cart had not restarted since the evening, held 255 keys at the onset, and
answered every command in the traces in under a millisecond. Its own log said one thing had
changed: at rest it saves to disk when a hundred changes have accumulated over five minutes, and
from 22 seconds into the fault it saved **every minute, because ten thousand changes had
accumulated in sixty seconds** - eleven saves in eleven minutes, each successful, each reporting a
write volume its clients do not produce: the whole storefront writes to it a few dozen times a
minute. Something was rewriting the store's contents at ten thousand changes a minute at the
least, and the store was faithfully saving the result.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on cart, on
checkout, on the store or on anything else. The change history for the window is empty.

### Root cause

The contents of the cart store were being overwritten. A loop running inside the valkey-cart
container rewrote the `cart` field of every hash in the store about nineteen times a second with
four bytes that are not a serialised cart. The store itself was never wrong: it was up, reachable,
fast, and answered every read with exactly what it held. The cart service connected, read, and
could not decode what it read, so every read that landed on a cart the loop had reached failed as
a parse error with a failed-precondition status - `GetCart` and `AddItem` alike - and checkout,
which reads the cart as the first step of every order, failed the order on it. The storefront
writes a cart and reads it back within milliseconds and the loop passed every fifty-odd, so which
reads fell on the far side of a pass was chance: a few failures a minute, enough to carry
checkout's ratio just over its 5% line for two minutes and never cart's near its own. Nothing was
deployed, configured or flagged; the address, the connection and the process were right all
along.

### Resolution

The loop was stopped and the store flushed: every cart discarded, so that each user's next
request created a fresh one the loop was no longer touching. Class of fix: **restore_data**. There
was nothing to roll back or revert, and restarting cart would have changed nothing - it would have
reconnected to the same store and read the same bytes on its next request.

The recovery was clean. No parse-failure line, no error trace on checkout, the frontend or cart,
and no alert followed the fix; checkout's and cart's ratios fell to 1% and under in the minutes
after it as their five-minute windows drained; no p95 moved. The store came out of the flush
empty and refilled from its clients. The carts users had at the moment of the fix went with it,
and no second wave followed: an empty cart is a state the storefront handles every day.
Neither cart nor the store restarted.

### Detection notes

- Onset to first page: **6m16s** - checkout's ratio crossed at T+4 and the rule's two-minute hold
  ran from there. First failure at T+10s.
- Services on the page: **one**, the culprit's caller. By the fix: one alert on one service. The
  store, which held the fault, has no spans of its own, no metrics and no rule, and was on no
  page; cart, which failed every one of those requests, was not on it either.
- Alerts that fired only during recovery: **none.**
- Did the loudest service turn out to be the culprit? **No.** Checkout paged, and checkout was
  failing orders it had no part in breaking.
- Would the page alone have led you to the right service? **No, but one trace would.** The page
  said checkout. Checkout's error message named the cart service and a parse error; cart's span
  named the storage; the successful `HGET` beneath it said the store had answered. The store's
  own log said its contents were changing ten thousand times a minute in a world that writes a
  few dozen.
- **A failure that is fast and named is a datastore fault, not a service fault.** A slow store
  shows in the p95 with zero errors; a dead or misaddressed store logs a connection failure; a
  store whose contents are wrong answers at once with something the client cannot parse, and the
  client's log names the decoder. Read the error's text, not just its count.
- **The span beneath the failure is the witness.** A successful store command under a failed
  request is the store saying it answered. Everything above it failed on what it said.
- **A service can fail every request that touches the fault and still sit far under its line.**
  Cart's ratio never reached 3%, because most of what it emits - empty reads, writes, and a span
  for every store command - cannot fail this way. The caller whose every order depends on one
  read is where the ratio concentrates. Look one hop down from the page, and read the traces.
- **An error ratio near its line can clear on its own and the fault has not gone.** This alert
  resolved about three minutes before the fix. A resolved alert is a ratio, not a repair; check the
  log's last failure, not the alert's state.
- **The p95 falling during an error-rate incident is a clue.** Checkout got faster while it
  failed because the orders that failed were cut off at their first step.
- **The fix for a corrupted store is neither a restart nor a revert.** The wrong thing was the
  data. Discarding or restoring the store's contents was the fix; restarting the service that
  read them would have read them again.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-cart-store-corruption/`](../../evals/scenarios/artifacts/dev/v2-cart-store-corruption/) by `faultline-render`. [All bundles](README.md).
