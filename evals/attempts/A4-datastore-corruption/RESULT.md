# A4 — datastore corruption via `docker exec` into `valkey-cart` — RESULT

**Run 2026-09-23 02:10:12 → 02:35:38 UTC, \$0.** The first run at 01:42 was void (`VOID.md`,
`transcript-void-0142.txt`). This is the second run, `transcript.txt`, and the only one scored.
This time the injection was verified before it was observed: `DBSIZE` 222; a sampled key of type
`hash`; one `EVAL` whose return value, `225`, was the number of keys it rewrote; `HGET` on the
sampled key showing the four unparseable bytes; then the loop, printing `231 … 433` keys rewritten
every five seconds from 02:10:12 to 02:22:33. **The injection happened, 144 times.**

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **no** | Nothing reached `pending`, let alone `firing`, on `cart`, `frontend` or `checkout` — or anywhere. `watch.py 12` polled 02:14:00–02:25:30: `quiet` on every poll. At minute twelve `cart` showed **0.00 % errors, p95 6 ms, 3.48 req/s**, and its log was ordinary `GetCartAsync` / `AddItemAsync` / `EmptyCartAsync` lines. The helper was started four minutes after the loop; an alert needs three minutes of `for:` to fire and could not have fired and cleared inside that gap, so the gap does not hide a page. |
| **DISTINCT from `bad_config`** | not assessed | The definition applies *after it pages* |
| **REVERTS** | **yes** | `FLUSHALL` at 02:25:57; nothing to clear; `watch.py 10` quiet to 02:35:38 |
| **ADMISSIBLE** | **no** | Under the registration's own words: *"If it does not page, the mechanism is recorded as not observable through the rules and is inadmissible."* |

**Prediction scorecard.** PAGES: **wrong**, and wrong for a reason the registration did not name.
The registered uncertainty was whether the cart *"surfaces a parse failure as an error status
rather than treating garbage as an empty cart"*. That question has an answer, and it is not the
explanation.

## Why a verified injection produced zero errors

**The cart does surface parse failures as errors.** `ValkeyCartStore.GetCartAsync` (lines
207–236) does `HashGetAsync(userId, "cart")` and, if the field is present, `Cart.Parser.ParseFrom`;
any exception is rethrown as `RpcException(FailedPrecondition, "Can't access cart storage. …")`
(233–235). `AddItemAsync` (132–178) has the same shape. `CartService.GetCart` (49–71) and
`AddItem` (41–45) catch that, set the span status to `Error`, and rethrow. Four bytes of `0xFF` are a
varint whose continuation bit never clears — a truncated tag — and every protobuf implementation
rejects it (`InvalidProtocolBufferException` in C#; checked with Python's implementation, which
raises `DecodeError` on the same bytes). **Any read of a rewritten cart is an error span.** So the
question is not whether errors would be counted; it is whether a rewritten cart is ever read.

**It is not, because of how the load generator uses carts.** `locustfile.py` (lines 177–216):
`add_to_cart` makes a fresh `uuid1()` per call; `checkout` and `checkout_multi` make one fresh id
and run their adds and the checkout POST back to back with no `wait_time` between them; and
`view_cart` (171–175) calls `/api/cart` with no session id, which reads a key that never exists. So
**a cart is written and read within the same locust task, and never touched again.** The reads of
an existing cart are: the `getCart` the frontend issues right after `addItem` in `POST /api/cart`
(`pages/api/cart.ts`, lines 34–38 — one gRPC round trip, ~5 ms after the write); each further
`AddItem` in a multi-item checkout (~50–100 ms apart); and `checkout`'s `GetCart` at `PlaceOrder`
(tens of ms after the last write). A cart is **live for between 5 and ~300 ms** and then dead.
Every key the loop rewrote — 231 rising to 433 as new carts were written and abandoned — was a
dead key. `EmptyCart` writes an empty cart rather than deleting (line 198), which is why the count
only rises.

**The arithmetic.** With 25 users at 1–10 s between tasks and the task weights in the file, the
world runs ~0.14 single and ~0.14 multi-item checkouts a second. Summing every live window gives
~11 s of live-cart time per 300 s. A sweep every 5 s is 60 sweeps per 300 s; each lands in a live
window with probability ~11/300, so ~2 hits per five minutes, of ~1,040 cart calls: **~0.2–0.5 %,
an order of magnitude under the 5 % rule even if every sweep had been perfectly timed.** The
`shape.py` window (02:20:30–02:25:30) overlapped the loop for two minutes; one expected hit;
`0.00 %` is what that looks like. Nothing about the result is surprising once the access pattern
is known. The registration's *"repeated every five seconds because the load generator writes new
carts continuously"* was written without checking how long a cart lives, and that is the miss.

**This also corrects `VOID.md`.** The void verdict stands — an unverified injection is void — but
its reasoning that zero errors *"is only consistent with the `EVAL` doing nothing"* was wrong: the
access pattern makes zero errors the expected result whether or not the first loop ran. Recorded as
an addendum there.

## What this means for the class

The mechanism is not shown to be unobservable; **the registered cadence is what failed**. A
rewrite that lands inside a live cart's read window is an error the rules count, and the store's
own reachability is untouched — which is exactly the (c) distinction from `bad_config` the
registration named. So there is a real, unanswered question: does the same mechanism at a cadence
that actually lands inside live windows page?

Under rule 7 that question is a **new** registered attempt, not a re-run of this one — and whether
to run it is Chandana's call, because the registration fixed A4's own outcome as inadmissible and
that verdict stands regardless. A candidate registration (A4b) and a verified tool for it
(`evals/attempts/a4b-corrupt-loop.sh`, a 50 ms SCAN-and-`HSET` loop fed to `docker exec -i` on
stdin so no quoting crosses a shell boundary) are prepared and waiting; the arithmetic says 50 ms
is shorter than every checkout task and would land in ~9 of every 10 live windows. **A4 as
registered is inadmissible; A4b is a recommendation, not a decision I have taken.**

## Timeline

| clock (UTC) | event |
|---|---|
| ~02:09 | `DBSIZE`, key type, single `EVAL` → `225`, `HGET` read-back — injection verified |
| 02:10:12 | loop starts; `231` keys rewritten |
| 02:14:00 | `watch.py 12` first poll — quiet |
| 02:22:33 | loop ends after 144 iterations; `433` keys rewritten |
| 02:25:30 | `watch.py 12` last poll — quiet; `shape.py cart`: 0.00 % / 6 ms / 3.48 req/s, nothing firing |
| 02:25:57 | `FLUSHALL` |
| 02:35:38 | `watch.py 10` ends — quiet throughout |
