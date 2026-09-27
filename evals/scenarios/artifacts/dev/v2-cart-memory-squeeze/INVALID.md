# ⚠ THIS BUNDLE IS NOT EVIDENCE OF THE SCENARIO IT WAS RECORDED FOR

The fault was applied and held for twenty minutes, and nothing paged. The scenario describes a
cart killed and killed again until the storefront and every order lose it. On v2, at the limit
the row's rule gave, **cart kept coming back faster than any rule could notice it was gone**.

## What the recording and the read-backs show

**Cart died at once and was serving again three seconds later.** The limit went from 160M to
48m at onset. Its log shows the start-up sequence - `Successfully connected to Redis`, the
feature provider, `Now listening on: http://[::]:7070`, `Application started` - beginning 1.5 s
after onset and complete at 4.1 s. Then the same sequence at +52 s, +114 s, +186 s, +248 s: 23
starts in the twenty minutes of the fault, 34 to 75 s apart (median 55 s), the last at +19:35.
Every one of the 23 reached `Application started`. Not one logged a shutdown line or an
exception; the container's restart count went from 0 to 23 with no restart after the fix (the
23rd instance was the one that survived the revert). The probe caught one kill in the act -
`state=restarting exit=137 oom=true` at +9:00, restart count 11 - and 105 samples of the
process running under the new limit, at 41.4 to 45.7 MiB of 48.

**Its callers paid a second or two per restart, and no more.** Nine checkout error traces in
the whole fault, all `PlaceOrder` failing at `GetCart` with `dial tcp 172.18.0.17:7070:
connect: connection refused`; 45 frontend error traces (25 `AddItem`, 12 `GetCart`, 8 checkouts);
the frontend logged `UNAVAILABLE` 37 times and `ECONNREFUSED` 72. Checkout's five-minute error
ratio ran 0.4 to 1.4 %, the frontend's 0.9 to 2.2 %, frontend-proxy's the same and the load
generator's under 1.6 %, against `ServiceHighErrorRate`'s 5 % line. Cart's own error ratio was
zero throughout. 151 orders completed under the fault, each with a payment span.

**Cart was never absent.** Its call rate fell from 5.1 a second to between 2.5 and 4.0 and never
to nothing - a 500-trace sample of cart server spans lands in every minute of the fault - so
`ServiceNoTraffic`, which needs a five-minute rate of zero for three minutes, had nothing to fire
on. Its request lines ran 46 to 101 a minute against about 120 before.

**What moved was latency, and not enough.** Cart's p95 rose from 3 ms to 35 ms in the first
minute and 50 to 90 ms after; checkout's from 33 ms to 122 ms at +3 and 85 to 95 ms after; the
frontend's from 42 ms to about 90 ms. A runtime running its garbage collector flat out inside
48 MiB, and nowhere near `ServiceHighLatency`'s 250.

**The runtime capture holds five instances, not none.** 176 series: the original instance's 35,
which the store served forward for four minutes after the first kill, and 35 (once 36) for each
of four later instances that lived long enough to be scraped. T7.20's "a crash-looping cart
exports nothing" is not what happened here either: nineteen of the 23 instances exported
nothing, four did.

## Why the scenario is blocked rather than re-recorded

- The pre-registration (`docs/design/t7.1-candidates.md`, resource_exhaustion row 3) named this
  outcome and its consequence before recording: *if cart's restarts come back and hold so that
  nothing fires inside 900 s - the 200m shape - the design is blocked without a second value,
  and `v2/resource_exhaustion-3` stays empty, this row having no reserve.* That is what the
  recording shows, and the pre-registration is followed.
- A second value now would be a limit chosen after seeing what the first did, which is the
  tuning the row's rule exists to forbid: a page found by search is not a fault's own shape.
- **The rule restated for .NET measured the wrong quantity.** It took the running process's
  memory outside its managed heap - working set at its eight-hour low less the GC's committed
  high, 58.5 MiB - for what a fresh process needs before it serves, and predicted that a
  restarted cart could not settle in under 48m. A fresh cart starts and listens in 41 MiB, and
  .NET's container-aware garbage collector sizes its heap to the cgroup limit it finds, so each
  new instance runs inside 48 MiB until it grows into the wall about a minute later. What the
  restated rule measured was what a warm process had accumulated - JIT-compiled code, GC
  bookkeeping, thread stacks - not what a cold one needs. The JVM rows' rule held because a JVM
  with a fixed heap ceiling and a loaded agent needs more to start than it is ever allowed under
  the squeeze; a runtime that resizes to its container does not.
- This is T7.20's first finding on v1's cart, "killed, back before detection", reproduced on v2
  at a quarter of the limit that produced it there. Whether a band exists on v2's cart between
  a limit it restarts under faster than detection and one it cannot start under at all is not
  answered by this recording, and the row's rule does not allow a second try to find out.

The scenario is `blocked: true` and claims no slot. `v2/resource_exhaustion-3` stays empty; the
row has no reserve. The bundle is kept, because what it shows about a container-aware runtime
under a memory squeeze is a finding: the failure mode is a restart every minute, paid for by the
callers as a one-second refusal each, and the rules on this world do not see it.
