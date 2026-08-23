---
origin: scenario:cart-dependency-latency
split: dev
fault_class: dependency_latency
onset_to_page: 3m30s
page_to_fix: 5m00s
fix_to_all_clear: 2m01s
---

# Cart service network path acquires 300ms of delay

## What was observed

Four `ServiceHighLatency` alerts fired in the same evaluation: **cartservice**,
**checkoutservice**, **frontend** and **loadgenerator**. The page arrived 3m30s after
things started slowing.

No errors. Not one. Every request succeeded; they simply took longer. The storefront
worked end to end — adding to a basket returned normally, just sluggishly.

cart's p95 sat around 650ms for the duration. Its callers were elevated in proportion
to how much of their work went through cart.

## What was checked

**Whether this was an incident at all.** cartservice is bimodal in normal operation:
around 2ms most of the time, but it reaches 353ms unprompted, and healthy excursions
have been measured lasting up to 105 seconds. 650ms is under twice the top of that
range. On a single sample there is nothing to distinguish this from the world's own
noise, and the first instinct was to wait for it to pass.

It did not pass. That is the whole discriminator: the alert has a three-minute
persistence clause, and normal excursions have never survived it. **Duration separated
this from the baseline, not magnitude** — a point-in-time reading of 650ms proves
nothing on this service.

**The error dashboards.** Clean throughout, which is misleading in both directions. It
argues against a serious problem, and it rules out most of the usual causes at once —
nothing is failing, timing out, or retrying.

**Direction of propagation.** frontend, checkout and cart all slowed together, but
frontend calls checkout and checkout calls cart. The leaf of that chain is where the
time is being spent; the other two are just waiting. That narrowed it to cart within a
couple of minutes.

**What changed on cartservice.** Nothing. No deploy, no image change, no environment
difference, no config edit. Its container specification was byte-identical to the
previous day's. This is the dead end that cost the most time, because "what changed"
is the first question and it returned an empty answer.

**Running containers.** A container was attached to cart's network namespace that is
not part of any service definition — nothing in the compose files creates it. It was
applying traffic shaping to cart's interface. The change was at the network layer, one
level below anything a service specification describes, which is why looking at cart's
own configuration found nothing.

## Root cause

An unauthorized container was shaping cartservice's egress traffic, adding 300ms of
delay per packet leaving the container. Cart's own code, image and configuration were
untouched.

The observed p95 was roughly double the added per-hop delay, because a cart
operation makes two round trips to Redis and each pays the delay separately. Anyone
expecting the p95 to rise by 300ms would have doubted a correct measurement.

## Resolution

Recreating the cart container cleared the shaping — the rule is bound to the container
instance, so a new one comes up on a clean network path. Latency returned to baseline
within two minutes, which is the metric window emptying rather than a gradual recovery.

Class of fix: **restart**. Nothing was deployed and no configuration was wrong, so
there was nothing to roll back or revert; the container simply needed replacing.

## Detection notes

- Onset to first page: **3m30s**, against a three-minute persistence clause. Detection
  is dominated by the clause, not by how long the signal took to appear.
- Services alerting at the page: **4**. Over the whole incident: **4**. The blast radius
  never grew.
- Alerts that fired only during recovery: **none**.
- **The culprit was named in the page**, unlike a fault that removes a service entirely
  — a slow service still reports its own latency, so it appears in its own alert.
- Did the loudest service turn out to be the culprit? **Yes**, and that is worth noting
  precisely because it is unusual. Latency propagates upward through callers, so the
  slowest service in the chain is the source.
- The signal that mattered was **persistence**. Magnitude alone was ambiguous against
  this service's known behaviour, and any investigation resting on a single latency
  reading would have been guessing.
