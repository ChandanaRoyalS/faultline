---
origin: scenario:cart-dependency-latency
split: dev
fault_class: dependency_latency
recorded_from: 2026-08-23T15:16:15+00:00
onset_to_page: 3m45s
page_to_fix: 5m00s
fix_to_all_clear: 2m16s
---

# Cart service network path acquires 300ms of delay

## What was observed

Four `ServiceHighLatency` alerts fired in the same evaluation: **cartservice**,
**checkoutservice**, **frontend** and **loadgenerator**. The page arrived 3m45s after
things started slowing.

No errors. Not one. Every request succeeded; they simply took longer. The storefront
worked end to end — adding to a basket returned normally, just sluggishly.

cart's p95 sat around 650ms for the duration. Its callers were elevated in proportion
to how much of their work went through cart.

## What was checked

**Whether the reading was real.** cartservice runs at 2ms. Not approximately 2ms —
across forty-five minutes of measured quiet operation its minimum, mean and maximum are
all 2ms, and it has never been observed above 3ms on an undisturbed system. A reading of
650ms is not an excursion on this service; it is three hundred times its entire
operating range. There was nothing ambiguous to weigh.

**Whether anything had restarted recently.** This is the one check that could have made
the reading meaningless, and it is worth doing first. cartservice takes about four
minutes to settle after being recreated, decaying monotonically from around 100ms back
to 2ms. A p95 sampled inside that window looks alarming and means nothing. Nothing had
been deployed or restarted, and the elevation was flat at 650ms rather than decaying, so
this was not a warm-up.

**The error dashboards.** Clean throughout, which is misleading in both directions. It
argues against a serious problem, and it rules out most of the usual causes at once —
nothing is failing, timing out, or retrying.

**Direction of propagation.** frontend, checkout and cart all slowed together, but
frontend calls checkout and checkout calls cart. The leaf of that chain is where the
time is being spent; the other two are waiting on it. That narrowed the search to cart
within a couple of minutes.

**What changed on cartservice.** Nothing. No deploy, no image change, no environment
difference, no config edit. Its container specification was byte-identical to the
previous day's. This is the dead end that cost the most time, because "what changed" is
the first question and it returned an empty answer.

**Running containers.** A container was attached to cart's network namespace that is
not part of any service definition — nothing in the compose files creates it. It was
applying traffic shaping to cart's interface. The change was at the network layer, one
level below anything a service specification describes, which is why looking at cart's
own configuration found nothing.

## Root cause

An unauthorized container was shaping cartservice's egress traffic, adding 300ms of
delay per packet leaving the container. Cart's own code, image and configuration were
untouched.

The observed p95 was roughly double the added per-hop delay, because a cart operation
makes two round trips to Redis and each pays the delay separately. Anyone expecting the
p95 to rise by exactly 300ms would have doubted a correct measurement.

## Resolution

Recreating the cart container cleared the shaping — the rule is bound to the container
instance, so a new one comes up on a clean network path. Everything was quiet 2m16s
later.

Class of fix: **restart**. Nothing was deployed and no configuration was wrong, so
there was nothing to roll back or revert; the container simply needed replacing.

## Detection notes

- Onset to first page: **3m45s**, against a three-minute persistence clause. Detection
  is dominated by the clause, not by how long the signal took to appear — the underlying
  measurement crossed the threshold almost immediately.
- Services alerting at the page: **4**. Over the whole incident: **4**. The blast radius
  never grew, and all four alerts began in the same evaluation.
- Alerts that fired only during recovery: **none**.
- **The culprit was named in the page**, unlike a fault that removes a service entirely
  — a slow service still reports its own latency, so it appears in its own alert.
- Did the loudest service turn out to be the culprit? **Yes**, and that is worth noting
  precisely because it is unusual. Latency propagates upward through callers, so the
  slowest service in the chain is the source.
- **Detection was never the hard part; attribution was.** On a service whose entire
  operating range is 2ms, the alert is unambiguous the moment it fires. What cost time
  was that the change had been made below the level any service specification describes,
  so every question about cart itself came back clean.
- **A latency reading taken shortly after a restart is not a baseline reading.** cart
  decays from about 100ms to 2ms over roughly four minutes after being recreated. Any
  comparison against "normal" must exclude that window, and a responder who samples
  inside it will conclude the service is far noisier than it is.
- On clearing order: cart's alert cleared about fifteen seconds after its callers' did.
  That is an observation about this incident and not a rule — clearing order is
  dominated by how full each service's rolling window happens to be when the fault
  stops, which has more to do with traffic rate than with causation. Do not read
  causation into what cleared when.
