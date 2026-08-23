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

**The two one-sample latency alerts.** They fired in the same evaluation adservice went
quiet, and they are the moment of transition rather than a condition: frontend's calls
were hanging against a dying process, and once it was gone they failed immediately
instead of slowly. A single-sample latency alert is a state change, not a state.

**adservice, once it went quiet.** Zero errors and zero traffic together do not mean a
healthy idle service on this system; adservice is called on every product page. The
container had restarted twice, exiting 137 each time — killed by the kernel for
exceeding its memory allowance, not crashing on its own.

**What changed on adservice.** Not the image, not the environment, not the code. The
container's memory ceiling had been reduced to 256 MiB. Its steady-state working set is
around 350 MiB, and the JVM's heap settings were sized against the previous ceiling of
700 MiB, so the runtime kept trying to grow into memory that no longer existed.

## Root cause

adservice's container memory limit was reduced below the footprint its JVM was
configured for. Nothing about the service changed — only the ceiling it was allowed to
occupy. The kernel killed it, the orchestrator restarted it, and it grew back into the
same wall.

This is why it never appeared in the error metric: a process that is being killed and
restarted records no calls, and therefore no errored ones. The only evidence of it was
an *absence* of traffic, and that took three minutes longer to alert than the
downstream errors did.

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
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A service on the critical path taking others down with it produces a
  much wider spread; a leaf consumed by one caller produces exactly this. Where the
  damage stops says where the broken thing sits in the graph.
