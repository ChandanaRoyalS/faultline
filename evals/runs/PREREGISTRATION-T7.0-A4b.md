# Pre-registration — A4b, datastore corruption at a cadence that lands inside live carts

**Written before the attempt is run. Nothing here is a result.** This is a new attempt, not an edit
to `PREREGISTRATION-T7.0.md`, which is frozen. It exists because A4 (see
`evals/attempts/A4-datastore-corruption/RESULT.md`) established that its mechanism is real and its
errors would be counted, but its **cadence** — one sweep every five seconds — almost never touched a
cart that would be read, so it did not page. A4's verdict stands: inadmissible as registered. A4b
asks the one question A4 left open and could not answer without a second run under rule 7.

**The question.** A cart in this world is written and read within milliseconds and then abandoned
(A4's "Why a verified injection produced zero errors"). Does corrupting every key ~20 times a
second — faster than any load-generator task completes — land inside enough live read windows to
push `cart`'s error ratio over 5 %?

## Protocol — identical to the eight, with one change

Steps 1–6 of `PREREGISTRATION-T7.0.md` apply unchanged (pre-state quiet, inject, `watch.py 12`,
`shape.py cart`, revert, `watch.py 10`, transcript + RESULT.md). The only change is the injection
command's cadence and its delivery.

- **Mechanism**: overwrite the `cart` hash field of every key with four `0xFF` bytes (an
  unparseable varint), swept continuously rather than every five seconds.
- **Target**: `valkey-cart`; the paging service is `cart`. Callers: `frontend`, `checkout`.
- **Inject** (run it, leave it running; it ends on its own after ~12 min):
  `docker exec -i valkey-cart sh < evals/attempts/a4b-corrupt-loop.sh`
  The script (verified against a local redis before registration) SCANs every key, `HSET`s the
  `cart` field of each hash to the four bytes, sleeps 50 ms, and prints the clock and the number of
  keys corrupted every ~10 s. Fed on stdin so no quoting crosses a shell boundary — the failure
  mode of the A4 void run.
- **Revert**: let the loop end (or `Ctrl-C`), then `docker exec valkey-cart valkey-cli FLUSHALL`.
- **Comparator**: `bad_config` on `cart` (`cart-redis-misconfig`), exactly as A4.
- **What would distinguish (unchanged from A4)**: (c) — a misconfigured cart logs *connection*
  failures; a corrupted store produces *parse* failures with the store reachable. (b) — no change
  recorded.

## The arithmetic, fixed now

A4 measured ~11 s of live-cart time per 300 s of wall clock (0.14 single + 0.14 multi checkouts/s,
live windows summed). A 50 ms sweep is 6,000 sweeps per 300 s. The chance a given live window is
missed entirely by every sweep is negligible (a window ≥ 50 ms is hit at least once by
construction; the shortest, ~5 ms `POST /api/cart` read-back, is caught by whichever sweep overlaps
its ~5 ms). Expected caught reads per 300 s: essentially all of the ~0.28 checkout-path reads/s
that read a previously-written cart, i.e. the multi-item `AddItem` reads and the `PlaceOrder`
`GetCart`. Against ~1,040 cart calls per five minutes that is well above 5 % **if** the abandoned
carts the sweep also corrupts are never read (they are not) and the live ones are (they are).

## Prediction

**PAGES**, `ServiceHighErrorRate/cart`, within ~8 min (the `[5m]` window has to fill past 5 % and
`for: 3m` applies). Confidence moderate-high — higher than A4's, because the one thing A4 proved is
that the errors are real and counted; the only uncertainty left is timing, and 50 ms removes it. If
it still does not page, the finding is that corruption of *abandoned* state is invisible to
error-rate rules on this world at any cadence, and the mechanism is inadmissible for a reason
stronger than A4's — recorded, not tuned away. DISTINCT on (c) if it pages. REVERTS.

## What A4b decides, and what it does not

If A4b pages, distinct, reverts, then `datastore_corruption` is admissible and the class count in
`PREREGISTRATION-T7.0.md`'s outcome table rises by one (A1 + the admissible subset of
A2/A3/A8 + this). If it does not, the mechanism is inadmissible and the class count is unchanged.
A4b changes no threshold, rule, or stamp; the class list is still changed once, after all attempts
settle.
