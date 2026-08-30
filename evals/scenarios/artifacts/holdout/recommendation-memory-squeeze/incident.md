---
origin: scenario:recommendation-memory-squeeze
split: holdout
fault_class: resource_exhaustion
recorded_from: 2026-08-30T01:03:52+00:00
capability: cap:9c416e0a
onset_to_page: 4m45s
page_to_fix: 5m00s
fix_to_all_clear: 1m45s
---

# Recommendation service memory limit cut below what its runtime needs to start

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **loadgenerator**, with **frontend**
joining fifteen seconds later.
It arrived 4m45s after onset.

`ServiceNoTraffic` fired on **recommendationservice** at **T+6m15s**, a minute and
three-quarters after the page and the only alert naming the broken service.

Three alerts across three services. The storefront loaded, product pages rendered, the
basket and checkout worked. The recommendation strip on the home page was empty, and
pages finished rendering without it — nothing in this incident crossed a latency
threshold anywhere in the system.

## What was checked

**Why detection was so slow.** frontend does not fail when recommendations fail; it
waits, then renders without them. Only a fraction of its requests error, so the ratio
climbed toward the five percent threshold slowly rather than jumping. The latency alert
followed for the same reason — the time is frontend waiting on something that never
answers.

**Error rate by service.** frontend and loadgenerator over threshold, everything else
flat. recommendationservice itself: no errors at all, then no data.

**Whether recommendationservice was idle or gone.** `ServiceNoTraffic` cannot tell those
apart. Its runtime metrics can: the service publishes its own interpreter memory usage,
and an idle process keeps publishing. **Those series stop and do not resume until after
the fix.** A service that has stopped reporting its own memory is not a service that is
waiting for work.

Read the stop as a fact and not as a timestamp. The series remain *visible* for up to five minutes past the moment they stop being scraped, because the metrics store serves the last sample forward — so this dates the death only to within that window, and the direction of the error is always late. Nothing else here dates
it either — this service leaves no logs when it dies — so on this incident the onset is
known from the alerting and the death only to within five minutes of it.

**recommendationservice's logs, which say nothing at all.** This is the hardest part of
this incident. There is no error, no traceback, no truncated startup banner — the stream
simply ends mid-traffic and the next line is a clean startup twelve minutes later, after
the fix. Nothing was written because nothing got far enough to write it, and because the
runtime buffers its output and lost whatever was pending when it was killed. **An empty
log is not evidence of a healthy service; it is evidence that nothing survived long
enough to speak.**

**What that combination rules out.** No errors, no traffic, no logs, no runtime metrics,
and callers that time out rather than receive failures. Nothing is refusing requests —
there is nothing there to refuse them. That eliminates every explanation involving the
service's own behaviour and leaves only explanations about its existence.

**What changed.** Not the image, not the code, not the environment, not any dependency.
The change history shows one edit: the container's memory ceiling was lowered to 32 MiB.
Steady-state usage is around 55 MiB, and the runtime needs more than the new ceiling
merely to finish starting — so the process was killed during initialisation, restarted,
and killed again, without ever reaching a serving state.

## Root cause

recommendationservice's container memory limit was reduced below the footprint its
runtime requires to start. Nothing about the service changed — only the ceiling it was
allowed to occupy — and the effect was not degradation but non-existence.

This is why it produced no errors of its own: a process that never finishes starting
records no calls, and therefore no errored ones. Its only signal was absence, and that
absence arrived a full minute after the downstream errors did.

## Resolution

The memory limit was restored. recommendationservice completed startup on its next
attempt and the recommendation strip returned. Everything was clear 2m30s after the
fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

## Detection notes

- Onset to first page: **4m45s**. A dependency whose failure is tolerated by its caller
  takes longer to page than one whose failure is fatal — partial degradation crosses a
  ratio threshold slowly.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 3 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named neither the broken service nor anything adjacent to it.** frontend
  and loadgenerator are the edge; the culprit appeared a minute and three-quarters later,
  and only as an absence.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 8.0 minutes each and neither was broken.
- **Nothing here was slow, only missing.** No latency rule fired on any service. A
  dependency that vanishes cheaply — one its caller can skip rather than wait for —
  produces a failure with no latency signature at all, so a responder scanning latency
  dashboards for the cause of a degraded storefront would find every one of them clean.
- **Absence is the only alert this service can ever produce.** Its healthy p95 is around
  4ms against a 250ms threshold — sixty times of headroom. No amount of slowing down
  can reach the rule. If a fault on this service does not stop it serving, nothing in
  the alerting will ever see it.
- **This service leaves no logs when it dies**, unlike a runtime that prints a banner on
  every start. Its silence is total, and the absence of a crash message must not be read
  as the absence of a crash. What filled that gap was the runtime metrics stopping.
- **Blast radius shape.** One leaf and one caller, nothing else. A narrow, two-service
  spread points at something with a single consumer; it cannot be produced by anything
  on the critical path.
- Both an error-rate and a latency alert fired on the same two services. That pairing
  is what waiting on a dead dependency looks like: some requests fail, the rest are
  slow because they waited first.
- **The signature does not name its cause.** Everything above establishes that the
  process is gone. Nothing in it says *why* the ceiling and the footprint stopped
  fitting — only the change history distinguishes a lowered limit from a service that
  grew.
