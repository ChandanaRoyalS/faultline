---
origin: scenario:ad-memory-squeeze
split: dev
fault_class: resource_exhaustion
recorded_from: 2026-08-23T15:40:58+00:00
onset_to_page: 3m15s
page_to_fix: 5m00s
fix_to_all_clear: 1m00s
---

# Ad service memory limit cut below the working set its JVM was sized for

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **loadgenerator**. Nothing else.
The synthetic client was seeing failures and no service was owning them.

**frontend** joined fifteen seconds later, also on error rate.

The storefront was mostly usable. Product pages loaded, baskets worked, checkout
completed. The advertisement panel was missing.

At **T+3m00s**, `ServiceNoTraffic` fired on **adservice** — the first time anything
named a service other than the frontend and its client.

Fifteen seconds after that, two `ServiceHighLatency` alerts appeared on frontend and
loadgenerator and vanished again within a single evaluation. They lasted one sample.

## What was checked

**loadgenerator.** The page named it and it explains nothing. It is the synthetic
client; its error rate is a restatement of whatever the storefront is failing to do.
Useful only as confirmation that a user would have noticed.

**Error rate by service.** frontend over threshold, loadgenerator over threshold,
everything else flat. adservice in particular: zero errors, cleanly below every
healthy service. Read at the time as evidence adservice was fine.

**Which page elements were failing.** The store worked apart from the ad panel. That
narrowed it faster than any metric did — frontend's errors were confined to one
dependency, and the storefront told us which one before the alerting did.

**Whether adservice was idle or absent.** `ServiceNoTraffic` cannot tell those apart:
both look like a call rate of zero. The runtime metrics can. adservice exports its own
JVM heap series, and a process that is merely idle keeps exporting them. **Those series
disappeared entirely at onset and did not return until the fix.** A service that has
stopped reporting how much heap it is using does not have a heap. That is the moment the
investigation stopped being about traffic and started being about the process.

**adservice's logs.** Fifteen startup attempts inside the fault window, each exactly
three lines — a JVM banner, a class-loading warning, an instrumentation agent announcing
its version — and then nothing. The gaps between attempts lengthen from three seconds to
over a minute, which is a supervisor backing off a container that will not stay up. Not
one line explains why. A process that fails on its own configuration says so, because it
got far enough to read the configuration; this one is being stopped before it reaches
that point.

**What changed.** Not the image, not the environment, not the code, not any dependency.
The change history shows one edit: the container's memory ceiling was reduced to 256 MiB.
Steady-state usage is around 350 MiB, and the JVM's heap was sized against the previous
ceiling of 700 MiB, so the runtime kept trying to grow into memory that no longer
existed.

## Root cause

adservice's container memory limit was reduced below the footprint its JVM was
configured for. Nothing about the service changed — only the ceiling it was allowed to
occupy. The kernel killed it, the orchestrator restarted it, and it grew back into the
same wall.

This is why it never appeared in the error metric: a process that is killed before it
finishes starting records no calls, and therefore no errored ones. The only evidence of
it was an *absence* — of traffic, of logs beyond a truncated banner, and of the runtime
metrics it publishes about itself.

## Resolution

The memory limit was restored to its previous value. adservice came back on its next
restart and the ad panel returned. Everything was clear a minute after the fix — the
fastest recovery of any incident on this system, because nothing had to drain or
reconnect; a process simply stopped being killed.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

## Detection notes

- Onset to first page: **3m15s**.
- Services alerting at the page: **1**. Over the whole incident: **3**, across 5 alerts.
- Alerts that fired only during recovery: **none**. Two of the five lasted a single
  evaluation each and marked the instant the service died rather than any ongoing
  condition — duration is what separates a signal from a transition.
- **The page named a service two hops from the fault** and did not name the broken one
  for another three minutes. The strongest early signal was not in the alerting at all:
  the storefront worked except for one panel.
- Did the loudest service turn out to be the culprit? **No.** loadgenerator alerted
  longest at six minutes and is not a service in any meaningful sense.
- **A service's own runtime metrics disappearing is stronger evidence than its traffic
  disappearing.** An idle service still reports its heap; a dead one reports nothing.
  That distinction is not available from the alert, which sees a rate of zero either way.
- **The failure signature does not name its cause.** A repeating truncated startup on a
  lengthening backoff means the process is being stopped from outside. It does not say
  whether the ceiling came down or the thing beneath it grew, and those have opposite
  fixes. Only the change history separates them.
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A service on the critical path taking others down with it produces a
  much wider spread; a leaf consumed by one caller produces exactly this. Where the
  damage stops says where the broken thing sits in the graph.
