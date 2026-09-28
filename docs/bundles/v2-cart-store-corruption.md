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
| capture window | 2026-09-28T12:36:00+00:00 → 2026-09-28T12:54:17+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+6m16s |
| `t_revert` | T+11m16s |
| all clear | T+11m17s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+6m15s | `cart` | ServiceHighErrorRate | 3.0 min | **paged** |
| T+6m15s | `checkout` | ServiceHighErrorRate | 3.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="valkey-cart"}` |

`logs/valkey-cart.txt` — 74 lines.

## A look at the logs

From `logs/valkey-cart.txt` (---- onset 2026-09-28T12:41:00+00:00 ----):

```
2026-09-28T12:37:17+00:00  1:M 28 Sep 2026 12:37:17.030 * 100 changes in 300 seconds. Saving...
2026-09-28T12:37:17+00:00  1:M 28 Sep 2026 12:37:17.031 * Background saving started by pid 110800
2026-09-28T12:37:17+00:00  110800:C 28 Sep 2026 12:37:17.042 * DB saved on disk
2026-09-28T12:37:17+00:00  110800:C 28 Sep 2026 12:37:17.043 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-09-28T12:37:17+00:00  1:M 28 Sep 2026 12:37:17.131 * Background saving terminated with success
2026-09-28T12:41:01+00:00  1:M 28 Sep 2026 12:41:01.711 * 10000 changes in 60 seconds. Saving...
2026-09-28T12:41:01+00:00  1:M 28 Sep 2026 12:41:01.711 * Background saving started by pid 110884
2026-09-28T12:41:01+00:00  110884:C 28 Sep 2026 12:41:01.718 * DB saved on disk
2026-09-28T12:41:01+00:00  110884:C 28 Sep 2026 12:41:01.718 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-09-28T12:41:01+00:00  1:M 28 Sep 2026 12:41:01.812 * Background saving terminated with success
2026-09-28T12:42:02+00:00  1:M 28 Sep 2026 12:42:02.029 * 10000 changes in 60 seconds. Saving...
2026-09-28T12:42:02+00:00  1:M 28 Sep 2026 12:42:02.030 * Background saving started by pid 113467
```

_53 further lines are in the bundle._

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

The page came 6m16s after the first failed request, and it was two lines that fired in the same
evaluation: `ServiceHighErrorRate` on **checkout** and `ServiceHighErrorRate` on **cart**. Nothing
before them, nothing beside them - no latency alert anywhere, no service gone quiet - and nothing
after them. Two alerts on two services by the fix.

Then, 2m45s after they fired and 2m16s before anything was done, both alerts cleared on their own.
Cart's error ratio had come down from 7.1% to 4.0% and checkout's from 6.9% to 4.3%, under the
line and back over nothing, while every failure they were counting went on exactly as before. The
world read all clear for the last two minutes of the fault; the record's all-clear is stamped one
second after the fix because there was nothing left firing for the fix to clear.

The storefront was mostly working. Product pages, recommendations and ads served at their usual
speed; the frontend's p95 sat at 32 to 38ms for the whole window and its request rate did not
move from 11.6 to 12 a second. 68 orders completed while the fault held and 24 failed - about one
checkout in four - and every failed one was fast. The frontend's error ratio climbed to 3.5% and
the proxy's to 3.6%, both under their 5% line, the load generator's to 2.0%. Checkout's ratio rose
from the first minute - 0.6, 1.9, 3.8, 5.6% - to a peak of 6.9% at T+6, and its 95th percentile
went *down* while it did, from 30ms to 24ms: the orders that failed were shorter than the ones
that completed. Cart's ratio ran a minute ahead of checkout's and a point above it, 3.8% at T+2,
7.1% at T+5, with its p95 at 2ms throughout, the same 2 to 3ms it shows at rest. Nothing anywhere
hung, slowed, restarted or went silent; something was failing at once, a few times a minute, on a
service whose store is the fastest thing in the system.

### What was checked

**The page, and what its two names have in common.** Checkout reads the cart once per order and
fails the order if that read fails; cart serves the cart. The two alerts naming them together, at
the same ratio, with no latency and no silence anywhere, said the failures were fast and were
being counted twice: once where they happened and once where they were felt.

**Checkout's error traces.** 24 in the eleven minutes, every one an order - `user_checkout_multi`
and `user_checkout_single` from the load generator - and every one 14 to 164 milliseconds long
from edge to end. Under each, checkout's `PlaceOrder` in error at 1.4 to 2.9ms with one message:
`cart failure: failed to get user cart during checkout`, wrapping a `FailedPrecondition` from the
cart service; beneath that, `CartService/GetCart` in error, and beneath that cart's own server
span, **in error at 0.5 to 1.0 milliseconds**, carrying the detail: `Can't access cart storage.
Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended
unexpectedly in the middle of a field`. Not a timeout, not a refused connection, not a missing
key: a read that returned, at once, with bytes that were not a cart. Nothing hung under any of
them; the proxy cut nothing at its fifteen-second timeout in the whole window.

**The frontend's error traces, because the page did not name it.** 53, of which the 24 orders
above and 29 `user_add_to_cart` - the same span, the same message, on `AddItem`, which reads the
cart before it adds to it. The frontend recorded them as errors it passed on; its own log carried
77 lines of the cart service's message and nothing of its own.

**Cart's log.** At rest it writes a `GetCartAsync called` line per read, 27 to 56 a minute, and
those went on unchanged. From 20 seconds after the onset it added a new one: `Error status code
'FailedPrecondition' with detail 'Can't access cart storage.
Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended
unexpectedly in the middle of a field'`. 53 of them in the fault's eleven minutes, three to ten a
minute and none at all in the ninth - the minute the alerts cleared in - none in the hour before
the fault and none after the fix. **Cart was not failing to reach its store; it was reaching it
and failing to read what it got back.** A wrong address logs a connection failure; a store that is
down logs a refused or timed-out connection; a store that is slow does not log at all and shows
in the p95. This was a decode failure on a connection that was fine.

**Cart's own view of itself.** Its 44 runtime series - .NET memory, garbage collection, threads -
reported without a gap for the whole window; it did not restart, and its p95 did not move. The
process was healthy. Whatever was wrong was in what it read.

**The store.** valkey-cart had not restarted in six days, held about a thousand keys at 1.6 MiB
with no memory limit, and answered every request in the traces in under a millisecond. Its own
log said one thing had changed: at rest it saves to disk when a hundred changes have accumulated
over five minutes - one save, five lines, every five minutes - and from the second second of the
fault it saved **every minute, because ten thousand changes had accumulated in sixty seconds**.
Twelve saves in twelve minutes, each one successful, each one reporting a write volume the store's
clients do not produce: the whole storefront writes to it about forty times a minute. Something
was rewriting the store's contents at ten thousand changes a minute at the least, and the store,
being a healthy store, was faithfully saving the result.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on cart, on
checkout, on the store or on anything else. The change history for the window is empty.

### Root cause

The contents of the cart store were being overwritten. A loop running inside the valkey-cart
container rewrote the `cart` field of every hash in the store about eighteen times a second, on a
fifty-millisecond interval, with four bytes that are not a serialised cart. The store itself was
never wrong: it was up, reachable, fast, and answered every read with exactly what it held. The
cart service connected, read, and could not decode what it read, so every read that landed on a
cart the loop had reached failed as a parse error with a failed-precondition status - `GetCart`
and `AddItem` alike, since both read the cart first - and checkout, which reads the cart as the
first step of every order, failed the order on it. The storefront writes a cart and reads it back
within milliseconds, and the loop passed every fifty-odd, so which reads fell on the far side of
a pass was chance: about one checkout in four, about one cart operation in ten, three to ten
failures a minute, enough to hold cart's and checkout's ratios near their 5% line and not enough
to keep them over it. Nothing was deployed, configured or flagged; the address, the connection and
the process were right all along.

### Resolution

The loop was stopped and the store flushed: every cart discarded, so that each user's next
request created a fresh one the loop was no longer touching. Class of fix: **restore_data**. There
was nothing to roll back or revert, and restarting cart would have changed nothing - it would have
reconnected to the same store and read the same bytes on its next request.

The recovery was clean. No parse-failure line, no error trace on checkout, the frontend or cart,
and no alert followed the fix; cart's error ratio read 3.1% in the minute after it and zero by the
fourth minute, checkout's 3.4% and zero by the fifth, as their five-minute windows drained of the
last failures; no p95 moved. The store came out of the flush with seven keys and held 89 five
minutes later, refilling from its clients. The carts users had at the moment of the fix were gone
with it, and no second wave followed from that: an empty cart is a state the storefront handles
every day. Neither cart nor the store restarted. The alerts themselves had cleared 2m16s before
the fix, while the fault held, which is why the record's fix-to-all-clear reads one second.

### Detection notes

- Onset to first page: **6m16s** - the ratios crossed at T+4 and the rule's two-minute hold ran
  from there. First failure at T+20s.
- Services on the page: **two**, the culprit's service and its caller, together. By the fix: two
  alerts on two services. The store, which held the fault, has no spans, no metrics and no rule,
  and was on no page.
- Alerts that fired only during recovery: **none.**
- Did the loudest service turn out to be the culprit? **Half.** Cart paged, and cart was the
  service that failed; but nothing about cart was wrong - its process, its connection and its
  configuration were all as they should be. The fault was in the bytes its store handed it.
- Would the page alone have led you to the right service? **To cart, yes; to the fault, no.** The
  page said cart was failing. The traces said it was failing fast, with a parse error, on a read
  that returned. The log said the same in words. The store's own log said its contents were
  changing ten thousand times a minute in a world that writes forty. Together they said the store
  was healthy and its contents were not.
- **A failure that is fast and named is a datastore fault, not a service fault.** A slow store
  shows in the p95 with zero errors; a dead or misaddressed store logs a connection failure; a
  store whose contents are wrong answers at once with something the client cannot parse, and
  the client's log names the decoder. Read the error's text, not just its count.
- **An error ratio near its line can clear on its own and the fault has not gone.** These
  alerts resolved with the fault still running because one minute happened to hold no failure
  and the five-minute window fell under 5%. A resolved alert is a ratio, not a repair; check the
  log's last failure, not the alert's state.
- **The p95 falling during an error-rate incident is a clue, not a comfort.** Checkout's 95th
  percentile went down because the orders that failed were the short ones, cut off at their
  first step. A service that is getting faster while it fails is failing early.
- **The fix for a corrupted store is neither a restart nor a revert.** Nothing was deployed and
  nothing was misconfigured; the wrong thing was the data. Discarding or restoring the store's
  contents was the fix, and restarting the service that read them would have read them again.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-cart-store-corruption/`](../../evals/scenarios/artifacts/dev/v2-cart-store-corruption/) by `faultline-render`. [All bundles](README.md).
