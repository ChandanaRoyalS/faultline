# S1 — the four v1 mechanisms on the v2 world: inject / restore smokes — RESULT

**2026-09-24 09:57:10 → 10:03:40 UTC, \$0.** `docs/design/t7.1-candidates.md` §5 step 1: none of
the four old handlers had ever run against v2, so each was smoked on the first candidate of its
row to T1.4's bar - `start` changes what it says, `status` describes the revert, `stop` puts it
back, a second `stop` is a no-op - before any of their scenarios is authored. **A smoke is not a
rehearsal**: no page is sought and none is claimed. Terminal verbatim in `transcript.txt`.

| handler | definition | start did | stop did | second stop |
|---|---|---|---|---|
| compose env override | `v2-cart-valkey-misconfig` | cart recreated with `VALKEY_ADDR=valkey-cart:6380` (read back from the container's env); 40 cart log lines naming valkey/connect in 60 s | recreated from the base definition, override file removed; env back to `6379` | *not active* |
| image swap, tag that does not resolve | `v2-cart-bad-image-tag` | cart stopped, pointed at `2.2.0-cart-hotfix.2`, nothing came up - `Exited (0)` | recreated from base; `Up` on `ghcr.io/open-telemetry/demo:2.2.0-cart` | *not active* |
| memory limit | `v2-ad-memory-squeeze` | limit `201326592` (192m); ad **restarted twice** - its current run started at 09:59:22, 12 s after the squeeze | limit `314572800` (300M) | *not active* |
| pumba netem | `v2-cart-dependency-latency` | sidecar up; cart p95 **842 ms** (rests at ~6), checkout p95 1162 ms, checkout 1.80 % errors | sidecar stopped, delay reverted, no pumba container left | *not active* |

**All four pass.** Every handler carries to v2 unchanged; the v2 values the definitions needed
(`VALKEY_ADDR`, the 2.2.0 image repository, ad's 300M limit, cart's single `eth0`) were read off the
running world, not carried from v1.

## One finding for the memory row's scenario

**192m kills ad twice and then stops killing it.** `docker events` retained nothing for the
window, but the container settles it: `restarts=2`, current run started at 09:59:22, `oom=false`
on that run, and ad then served under 192m until the restore at ~10:00:40 - its memory history
reads 238-239 MiB for six hours and 199 MiB after. The JVM restarted under the smaller limit and
sized its heap to fit it. That is T7.20's *too gentle* edge on this world: two kills inside
fifteen seconds, far faster than any rule's `for:`, and a service that then runs normally. The
scenario's rehearsal decides whether it pages at all; if it does not, the value moves or the
candidate is `blocked`, and neither is decided here.

## What the smokes left behind

cart was recreated twice and ad restarted twice; nothing else. The first v2 bundle's pre-flight
(10:18) then refused on three *other* containers' memory, which is `compose/world-v2.override.yml`'s
T7.1 rows, not a smoke's doing: accounting and checkout restarted at 08:46-47 by R5's restore,
load-generator unrestarted since 2026-09-22.
