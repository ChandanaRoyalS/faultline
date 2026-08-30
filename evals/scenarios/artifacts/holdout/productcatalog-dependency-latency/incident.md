---
origin: scenario:productcatalog-dependency-latency
split: holdout
fault_class: dependency_latency
recorded_from: 2026-08-30T00:47:36+00:00
capability: cap:9c416e0a
onset_to_page: 3m49s
page_to_fix: 5m00s
fix_to_all_clear: 2m01s
---

# Product catalog network path acquires 300ms of delay, slowing every caller

## What was observed

The page was a single alert: `ServiceHighLatency` on **loadgenerator**. **frontend**,
**productcatalogservice** and **recommendationservice** joined fifteen seconds later, and
**checkoutservice** fifteen seconds after that — five alerts across five services. The page arrived 3m49s after things
started slowing.

**productcatalogservice** — the service the delay was actually on — joined a full minute
after the others, last of the five.

No errors anywhere. Every request succeeded; they took longer. The storefront worked
end to end, sluggishly. Product pages were slow to render and the recommendation strip
was slower still.

Five alerts across five services, and the blast radius never grew beyond them.

## What was checked

**The page, and what it implied.** Three services slow at once, none of them obviously
upstream or downstream of the others at a glance. frontend and loadgenerator are the
edge; recommendationservice looked like a third, separate problem.

**Whether this was noise.** It persisted through a three-minute clause and kept
persisting. Duration ruled out the world's own variability before any single reading
did.

**The error dashboards.** Clean throughout. Nothing failing, nothing retrying, nothing
timing out — which argues against most causes at once and against urgency too.

**Direction of propagation, which is where the page misled.** recommendationservice was
among the loudest, and it is a caller of product catalog, not a dependency of it.
Reading the page as "three peers are slow" invites looking for something all three
share — the network, the collector, the host. The actual shape is one leaf with several
callers, and the callers were louder than the leaf.

**Why the culprit was quietest.** productcatalogservice's own p95 rose by roughly the
per-hop delay. Its callers rose by a multiple of it, because a single page render makes
several catalog lookups and each one pays the delay separately. The service with the
largest absolute latency was the one making the most calls to the slow thing — not the
slow thing. That is why it crossed the threshold last.

**What changed on productcatalogservice, which is where it breaks open.** No deploy, no
image change, no environment difference, no configuration edit — and one record that is
none of those: a **container created**, described as a traffic-shaping container attached
to product-catalog-service's network namespace, carrying `eth0 delay=300ms jitter=0ms`.

The trap is that the first four answers are all "nothing" and the fifth is the whole
incident. The change sat one level below anything a service specification describes, so
inspecting the service found nothing — while the change record, under the service's own
name, described it directly.

## Root cause

An unauthorized container was shaping productcatalogservice's egress traffic, adding
300ms of delay per packet leaving the container. The service's own code, image and
configuration were untouched.

## Resolution

Recreating the container cleared the shaping — the rule binds to the container
instance, so a replacement comes up on a clean network path. Everything was quiet 2m32s
later, which is the metric window emptying rather than a gradual recovery.

Class of fix: **restart**. Nothing was deployed and no configuration was wrong, so
there was nothing to roll back or revert.

## Detection notes

- Onset to first page: **3m49s**, against a three-minute persistence clause. Detection
  is dominated by the clause.
- Services alerting at the page: **4**. Over the whole incident: **5**. The blast radius
  never grew.
- Alerts that fired only during recovery: **none**.
- **The culprit alerted last**, a full minute after the page and after all four of its
  own callers. A slow service does report its own latency, but it reports the smallest
  number in the incident, so it crosses the threshold last and looks least urgent. The
  gap is wide enough that a responder triaging on arrival order would have spent a
  minute with the culprit entirely absent from the incident.
- Did the loudest service turn out to be the culprit? **No** — and the reason
  generalises. Latency accumulates upward through fan-out: a caller that makes N calls
  to a slow dependency is N times slower than the dependency is. **Rank by position in
  the call graph, not by magnitude.**
- The clearing order said nothing useful here. The culprit cleared fourth of five, ahead
  of the edge services and behind checkout — a spread of forty-five seconds with no
  structure to it. Recovery ordering is dominated by how full each service's rolling
  window happened to be, and reading causation into it would have been guessing.
- The signal that mattered was **persistence**, and after that, the **shape of the
  affected set**: one leaf and its callers, with nothing beside them touched.
