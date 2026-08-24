---
origin: scenario:recommendation-memory-squeeze
split: holdout
fault_class: resource_exhaustion
recorded_from: 2026-08-23T17:30:59+00:00
onset_to_page: 5m26s
page_to_fix: 6m52s
fix_to_all_clear: 2m30s
---

# Recommendation service memory limit cut below what its runtime needs to start

## What was observed

The page was two alerts: `ServiceHighErrorRate` on **frontend** and **loadgenerator**.
It arrived 5m26s after onset — the slowest detection of any incident recorded on this
system.

Thirty seconds later both services also crossed `ServiceHighLatency`, and stayed over
it for seven minutes.

At **T+1m00s**, `ServiceNoTraffic` fired on **recommendationservice**.

Five alerts across three services. The storefront loaded, product pages rendered, the
basket and checkout worked. The recommendation strip on the home page was empty and
each page took noticeably longer to finish rendering.

## What was checked

**Why detection was so slow.** frontend does not fail when recommendations fail; it
waits, then renders without them. Only a fraction of its requests error, so the ratio
climbed toward the five percent threshold slowly rather than jumping. The latency alert
followed for the same reason — the time is frontend waiting on something that never
answers.

**Error rate by service.** frontend and loadgenerator over threshold, everything else
flat. recommendationservice itself: no errors at all, then no data.

**recommendationservice, once it went quiet.** The container was not running. It was in
a restart loop, exiting 137 each time — killed by the kernel for exceeding its memory
allowance. It never reached a serving state, so it never recorded a single call, and it
appeared healthy right up to the point where it appeared not at all.

**What changed on it.** Not the image, not the code, not the environment, not any
dependency. Its container memory ceiling had been lowered to 32 MiB. Steady-state usage
is around 55 MiB, and the runtime needs more than the new ceiling merely to finish
starting — so the process was killed during initialisation, restarted, and killed
again.

**Whether anything else was affected.** No. Only recommendationservice and the frontend
that calls it. Nothing in the product, cart, checkout or payment path moved at all.

## Root cause

recommendationservice's container memory limit was reduced below the footprint its
runtime requires to start. Nothing about the service changed — only the ceiling it was
allowed to occupy — and the effect was not degradation but non-existence.

This is why it produced no errors of its own: a process that never finishes starting
records no calls, and therefore no errored ones. Its only signal was the absence of
traffic, and that absence arrived a full minute after the downstream errors did.

## Resolution

The memory limit was restored. recommendationservice completed startup on its next
attempt and the recommendation strip returned. Everything was clear 2m30s after the
fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

## Detection notes

- Onset to first page: **5m26s**, the slowest on this system. A dependency whose
  failure is tolerated by its caller takes longer to page than one whose failure is
  fatal — partial degradation crosses a ratio threshold slowly.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 5 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named neither the broken service nor anything adjacent to it.** frontend
  and loadgenerator are the edge; the culprit appeared a minute later, and only as an
  absence.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 9m30s each and neither was broken.
- **Absence is the only alert this service can ever produce.** Its healthy p95 is around
  4ms against a 250ms threshold — sixty times of headroom. No amount of slowing down
  can reach the rule. If a fault on this service does not stop it serving, nothing in
  the alerting will ever see it.
- **Blast radius shape.** One leaf and one caller, nothing else. A narrow, two-service
  spread points at something with a single consumer; it cannot be produced by anything
  on the critical path.
- Both an error-rate and a latency alert fired on the same two services. That pairing
  is what waiting on a dead dependency looks like: some requests fail, the rest are
  slow because they waited first.
