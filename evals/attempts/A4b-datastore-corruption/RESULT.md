# A4b — datastore corruption at a cadence that lands inside live carts — RESULT

**Run 2026-09-23 ≈02:56 → 03:17:35 UTC, \$0.** One run, `transcript.txt`, registered in
`evals/runs/PREREGISTRATION-T7.0-A4b.md` before it was run. The verdicts are the pre-registered
definitions applied to the transcript and nothing else. Terminal 2's output (the loop's own lines
and the two clock stamps) was not pasted; the injection and revert instants are bracketed from
terminal 1 and marked *inferred* wherever used. Nothing below turns on them to better than a
minute.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes** | `ServiceHighErrorRate/checkout` firing at 03:00:55 — **≈4 min 45 s** after injection (inferred ≤02:56:25, the first quiet poll, since the `HGET` read-back before it already showed the corrupted bytes). `checkout` calls `cart` directly (`PlaceOrder` → `GetCart`), which the definition covers. `ServiceHighErrorRate/frontend`, the other direct caller, at 03:02:25 (≈+6:15). `frontend-proxy` at 03:01:55, recorded as a finding as in A1. **`cart` itself** reached 6.96 % at minute twelve and fired at 03:08:35 — after the window, so it does not carry the verdict; its callers do |
| **DISTINCT from `bad_config`** | **yes, on (c) and (b)** | **(c)** 154 lines in Loki under `service="cart"`: `Error status code 'FailedPrecondition' with detail 'Can't access cart storage. Google.Protobuf.InvalidProtocolBufferException: While parsing a protocol message, the input ended unexpectedly in the middle of a field'` — a *parse* failure with the store reachable, read back through the label the agent's `logql_query` selects on. `cart-redis-misconfig` logs *connection* failures (`Wasn't able to connect to redis`, `ValkeyCartStore.cs:101`). **(b)** no change recorded; a `bad_config` injection leaves a compose override in `change_history`. (d) supports it — the span status message is the same text (`CartService.cs:70`) — stated from source, not read back, same standing as A1's (d) |
| **REVERTS** | **yes** | `FLUSHALL` between 03:08:05 and 03:10:35 (inferred: four alerts at the former, one at the latter). All clear by 03:11:35 — **≤3 min 30 s** from the latest the revert could have been — and quiet for the remaining **6 min** to 03:17:35. The cleanest recovery of the series: no second wave, because nothing was hanging |
| **ADMISSIBLE** | **yes** | pages, distinct on two dimensions, reverts, and is a tool and surface (`exec` into the datastore, its *contents*) no existing mechanism has |

**Prediction scorecard.** PAGES: right. Rule: right (`ServiceHighErrorRate`). **Service: wrong
again** — predicted `cart`, actual `checkout` (then `frontend`); `cart` did fire, but 12 min 20 s
in, four minutes after the window. Timing on the callers: 4:45 against "~8 min" — faster, for the
reason below. DISTINCT on (c): right, and this time read back rather than argued. **That is the
third of four paging attempts (A1, A2, A4b) where the page landed on a caller and not the
culprit.** It is not noise; it is ADR-0029 §4's flattening measured a third time, and it is the
shape a scenario on this world must expect.

## What the shape at minute twelve shows

| service | error ratio | req/s before → during | reading |
|---|---:|---|---|
| `checkout` | **19.05 %** | 2.058 → **1.050** | fired first; every order whose cart was hit fails at `GetCart` |
| `frontend-proxy` | **8.47 %** | 5.442 → 6.100 | Envoy's view of the failed `POST /api/cart` and `/api/checkout` |
| `frontend` | **8.05 %** | 11.796 → 12.842 | the direct caller |
| `cart` | **6.96 %** | 4.200 → 3.833 | **the culprit — over the line, but last** |
| `load-generator` | 4.75 % | 4.854 → 5.437 | the client's view, under the line |
| `payment`, `email`, `shipping`, `currency` | 0 % | 0.300→0.117, 0.583→0.250, 0.437→0.187, 0.408→0.150 | **starved: the order path halved** |

**Why `checkout` and not `cart`.** `cart`'s denominator is every call it serves, and most of them
cannot fail: `view_cart` reads an empty session id (the `GetCartAsync called with userId=` lines
in the tail — a key that never exists), and the first `AddItem` of every task creates a fresh
key. Only the reads of a cart that already exists can hit the corruption, and those are ~7 % of
its traffic — over the line, but barely and late. `checkout` has no such dilution: `PlaceOrder`
reads the cart *once, tens of milliseconds after it was last written*, which at 50 ms is inside
the sweep almost every time, and one failed read fails the order. Its ratio was over 5 % within a
minute of the loop starting, and `for: 3m` plus the evaluation interval put it at 4:45. The
downstream services went quiet not because anything was wrong with them but because a failed
order never reaches them: **a corrupted cart store presents as a checkout outage**, with the
payment and email services starved, and that is what an operator would see first.

**Why it was faster than predicted.** The registration reasoned from `cart`'s window filling to
5 %. `checkout`'s crossed immediately; the prediction named the wrong service and therefore the
wrong clock.

## What separates this from A4

Nothing in the mechanism. The same bytes, the same field, the same `HSET`, the same `FLUSHALL`.
A4 swept every five seconds and touched ~2 live carts per five minutes; A4b swept every fifty
milliseconds and touched most of them. **The class is `datastore_corruption`; the cadence is a
parameter of the injection, and this world's parameter is "faster than a checkout"** — the
`Fault` subclass must carry it, and a scenario author must know that a slow sweep is a no-op here.
A4's result stands beside this one unchanged.

## Collateral, recorded and not counted

`fraud-detection` 3.23 % (under the line): its Kafka consumer against a topic that `checkout`
had half stopped producing to — the `accounting` pattern (`2026-09-22-the-span-that-was-not-latency.md`).
`load-generator` 4.75 %: the client, under the line, would have crossed with a longer run.

## Still owed

**Terminal 2's paste** — the loop's `iter=… corrupted=…` lines (the cadence check) and the two
clock stamps — as an addendum to `transcript.txt` when it is retrieved. It bounds two numbers to
the second that are bounded to the minute above; it changes no verdict.

**Dimension (d)** — the span's status message — stated from source (`CartService.cs:70`), same
standing as A1's, deferred to the same place: the class's end-to-end rehearsal through the agent's
`trace_query`.

## Timeline

| clock (UTC) | event |
|---|---|
| ≤02:56:25 | loop started (inferred); `HGET` read-back shows the corrupted bytes |
| 02:56:25 | `watch.py 12` first poll — quiet |
| 03:00:55 | `ServiceHighErrorRate/checkout` — direct caller (≈+4:45) — **PAGES** |
| 03:01:55 | `ServiceHighErrorRate/frontend-proxy` (finding) |
| 03:02:25 | `ServiceHighErrorRate/frontend` — direct caller (≈+6:15) |
| 03:07:55 | last observation poll; shape captured; three alerts firing |
| ≈03:08 | loop self-terminates after 13,000 iterations (by construction; not pasted) |
| 03:08:35 | `ServiceHighErrorRate/cart` — the culprit, ≈+12:20 |
| 03:08:05–03:10:35 | `FLUSHALL` (inferred bracket) |
| 03:10:35 | `cart`, `frontend`, `frontend-proxy` cleared |
| 03:11:35 | all clear — **REVERTS** |
| 03:17:35 | recovery window ends; 6 min quiet |
| after | `logs.py cart "Can't access cart storage" 40` → 154 lines — **(c) read back** |

**Eight classes measured**: the four existing, `feature_flag`, `process_freeze`,
`network_partition`, `datastore_corruption`. A5–A8 remain.
