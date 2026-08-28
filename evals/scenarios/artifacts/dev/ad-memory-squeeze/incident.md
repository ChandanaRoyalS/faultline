---
origin: scenario:ad-memory-squeeze
split: dev
fault_class: resource_exhaustion
recorded_from: 2026-08-28T02:41:26+00:00
capability: cap:9c416e0a
onset_to_page: 3m45s
page_to_fix: 5m00s
fix_to_all_clear: 1m45s
---

# Ad service memory limit cut below the working set its JVM was sized for

## What was observed

The page was `ServiceHighErrorRate` on **frontend** and **loadgenerator** together,
3m45s after onset. No service between them and the edge was named, and both alerts then
stayed up continuously for the rest of the incident.

Two and a half minutes later, at **T+6m00s**, `ServiceNoTraffic` fired on **adservice** —
the first time anything named a service other than the edge, and the only alert in this
incident that points inward.

Three alerts across three services. The storefront was mostly usable throughout:
product pages loaded, baskets worked, checkout completed. The advertisement panel was
missing.

## What was checked

**loadgenerator.** The page named it and it explains nothing. It is the synthetic
client; its error rate restates whatever the storefront is failing to do.

**Error rate by service.** frontend intermittently over threshold, loadgenerator over,
everything else flat. adservice itself: zero errors, then no data at all.

**Which page elements were failing.** The store worked apart from the ad panel. That
narrowed it faster than any metric did — frontend's errors were confined to one
dependency, and the storefront said which one before the alerting did.

**adservice's logs, which is where this one breaks open.** Ordinary request lines up to
eighteen seconds before onset, and then, from T+0 onward, **sixteen startup attempts**
inside the fault window — each a JVM banner, the OpenTelemetry agent announcing itself,
and then nothing. The last begins at T+8m27s, eighteen seconds before the fix. No line
explains a failure, because the process is being stopped before it can form an opinion
about anything. **A truncated, repeating startup is a process being killed from
outside**, and it is the strongest evidence in this incident.

**Whether adservice was idle or absent.** `ServiceNoTraffic` cannot tell those apart:
both look like a call rate of zero. The runtime metrics can, with a caveat that matters.
adservice exports its own JVM heap series, and a process that is merely idle keeps
exporting them; these cease. **What they cannot do is date it.** The series remain
visible until T+4m30s and then stop — but the metrics store serves a scrape forward for
five minutes after the last one, so the true stop is anywhere in the five minutes before
that, and the logs place the first kill at T+0. **The series answer *whether*, the logs
answer *when*, and reading a stop time off a series overstates by up to five minutes.**

**What changed.** Not the image, not the environment, not the code, not any
dependency. The change history shows one edit: the container's memory ceiling was
reduced to 256 MiB. Steady-state usage is around 350 MiB, and the JVM's heap was sized
against the previous ceiling of 700 MiB — so the runtime ran until it grew into the
new wall, was killed, and never got back up.

## Root cause

adservice's container memory limit was reduced below the footprint its JVM was
configured for. Nothing about the service changed — only the ceiling it was allowed to
occupy. From the first restart after the change, the runtime could not complete a startup
inside the new limit: it was killed during initialisation, sixteen times over, and never
served a request again until the ceiling was restored.

This is why it produced no errors of its own: a process that dies before it serves records
no calls, and therefore no errored ones. Its evidence was absence in the metrics and
repetition in the logs — nothing failing, and the same startup over and over.

## Resolution

The memory limit was restored to its previous value. adservice came back and the ad
panel returned. Everything was clear 1m45s after the fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

## Detection notes

- Onset to first page: **3m45s**.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 3
  alerts.
- Alerts that fired only during recovery: **none**.
- **The page named the edge, twice over, and the culprit only as an absence two and a
  half minutes later.** The strongest early signal was not in the alerting at all: the
  storefront worked except for one panel.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 6.8 minutes each, and one of them is not a service in any meaningful
  sense.
- **A partial failure can look completely ordinary in the alerting.** Only the requests
  touching the ad panel were failing, and frontend's error ratio crossed the threshold
  and stayed there like any total outage would. Nothing in the shape of that alert says
  "one dependency out of many" — the storefront's own behaviour said it, and the metric
  did not.
- **A service's own runtime metrics disappearing is stronger evidence than its traffic
  disappearing.** An idle service still reports its heap; a dead one reports nothing.
- **But a series' end is a soft edge, and this bundle shows how soft.** The heap series
  remain visible until T+4m30s while the logs place the first kill at T+0 — because the
  metrics store serves the last scrape forward for five minutes. **A series appearing is
  sharp to one scrape; a series disappearing is late by up to five minutes.** Anything
  dated off a disappearance carries that error, here and everywhere else.
- **A truncated, repeating startup names the shape of the failure and not its cause.**
  Sixteen JVM banners with nothing after them say the process is being killed from
  outside. That is all they say: it does not distinguish "the ceiling came down" from
  "the thing inside it got bigger", and those have opposite fixes. Only the change
  history separates them.
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A leaf consumed by one caller produces exactly this narrow spread;
  nothing on the critical path can.
