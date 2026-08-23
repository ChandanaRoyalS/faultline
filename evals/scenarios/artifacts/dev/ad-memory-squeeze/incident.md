---
origin: scenario:ad-memory-squeeze
split: dev
fault_class: resource_exhaustion
recorded_from: 2026-08-23T08:45:41+00:00
onset_to_page: 3m30s
page_to_fix: 5m00s
fix_to_all_clear: 3m31s
---

# Ad service memory limit cut below the working set its JVM was sized for

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **loadgenerator**. Nothing else.
The synthetic client was seeing failures and no service was owning them.

**frontend** joined fifteen seconds later, also on error rate.

The storefront was mostly usable. Product pages loaded, baskets worked, checkout
completed. The advertisement panel was missing.

At **T+2m45s**, `ServiceNoTraffic` fired on **adservice** — the first time anything
named a service other than the frontend and its client.

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
an *absence* of traffic, and that took nearly three minutes longer to alert than the
downstream errors did.

## Resolution

The memory limit was restored to its previous value. adservice came back on its next
restart and the ad panel returned.

**Two new alerts fired fifteen seconds after the fix was applied** —
`ServiceHighLatency` on frontend and loadgenerator, lasting under a minute. These were
alarming and meant nothing: the JVM was warming up with a cold heap, and the first
requests through it were slow. Anyone treating post-fix alerts as evidence the fix had
failed would have made things worse.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

## Detection notes

- Onset to first page: **3m30s**.
- Services alerting at the page: **1**. Over the whole incident: **3**, across 5 alerts.
- Alerts that fired only during recovery: **2** — both latency, both on the JVM's cold
  start, both gone within a minute of appearing.
- **The page named a service two hops from the fault** and did not name the broken one
  for another 2m45s. The strongest early signal was not in the alerting at all: the
  storefront worked except for one panel.
- Did the loudest service turn out to be the culprit? **No.** loadgenerator alerted
  longest at 8m30s and is not a service in any meaningful sense.
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A service on the critical path taking others down with it produces a
  much wider spread; a leaf consumed by one caller produces exactly this. Where the
  damage stops says where the broken thing sits in the graph.
