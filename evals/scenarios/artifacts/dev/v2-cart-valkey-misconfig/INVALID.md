# ⚠ THIS BUNDLE IS NOT EVIDENCE OF THE SCENARIO IT WAS RECORDED FOR

The fault was applied and something happened, but not what `v2-cart-valkey-misconfig` claims.
The scenario describes cart running and failing every call to a store it cannot reach. On v2,
**cart never ran**.

## What the recording and the read-backs show

**Cart exits at startup.** Its log over the fault holds `Unhandled exception.
System.ApplicationException: Wasn't able to connect to redis`, with 44 lines naming an
exception across the fault: the container restarting and failing each time it tries to connect
to the store at the wrong port. Its restart count read 0 afterwards only because the revert
recreated the container.

**Callers are refused before they reach it.** Every checkout error trace in the fault ends at
`checkout/oteldemo.CartService/GetCart` with `connection error: … dial tcp 172.18.0.17:7070:
connect: connection refused`, and `PlaceOrder` carries `cart failure: failed to get user cart
during checkout: rpc error: code = Unavailable …`.

**The page is the callers', and cart only goes quiet.**

- The page, at +3:46, was `ServiceHighErrorRate` on checkout, frontend, frontend-proxy and
  load-generator. Cart never fired an error alert.
- Cart's request rate fell from 4.1 to about 0.05 req/s. It appeared only as
  `ServiceNoTraffic/cart` at +8:45, a minute after the six services behind checkout starved.

**The recorded log shows none of this.** The recorder keeps the first 500 lines from five
minutes before the fault. Cart logs every call, about 130 lines a minute, so `logs/cart.txt` is
entirely from before the fault (23:36:57 to 23:40:04 for a fault starting at 23:41:56). The
reachability record says `logs`, because it counts talkativeness, which this capture shows. It
does not mean the capture holds the fault. The recorder's capture is split at the fault's start
from the next recording on.

## Why the scenario is blocked rather than corrected

- v1's cart connected to its store lazily and failed each call. v2's cart connects at startup
  and exits when it cannot, so this design is a crashloop on v2.
- `docs/design/t7.1-candidates.md` carries T7.56's rule over: a service that exits fatally and
  crashloops is `bad_deploy`'s page, not `bad_config`'s.
- It would also nearly duplicate `v2-cart-bad-image-tag`'s "never starts" page, on the same
  target, in the `bad_deploy` row.

Correcting the ground truth to describe a crashloop would move the fingerprint, and it would
fill a `bad_config` slot with `bad_deploy`'s page.

The scenario is `blocked: true` and claims no slot. `v2/bad_config-2` goes to the next candidate
in the list's order. The bundle is kept, because what it shows about v2's cart is a finding.
