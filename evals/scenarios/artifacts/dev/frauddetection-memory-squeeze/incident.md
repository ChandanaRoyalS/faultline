---
origin: scenario:frauddetection-memory-squeeze
split: dev
fault_class: resource_exhaustion
recorded_from: 2026-08-23T20:09:11+00:00
onset_to_page: 7m49s
page_to_fix: 6m23s
fix_to_all_clear: 1m15s
---

# Fraud detection service memory limit cut below its working set

## What was observed

One alert. `ServiceNoTraffic` on **frauddetectionservice**, 7m49s after onset. Nothing
else fired for the entire incident.

The storefront was perfect throughout. Product pages, search, basket, checkout, payment
— all normal, no errors anywhere, no latency anywhere. Orders were being placed and
completed successfully the whole time.

This is the slowest page recorded on this system and the smallest.

## What was checked

**Whether it was worth investigating at all.** A single no-traffic alert on a
low-volume service, with no customer impact and no other signal, is the shape of a
monitoring artifact. frauddetectionservice handles about one call every ten seconds; at
that rate a brief stall or a slow scrape can look like silence. The first instinct was
to treat it as a flaky alert on a sparse service, and nothing in the rest of the system
argued otherwise.

**Whether traffic had actually stopped.** It had, completely, and had stayed stopped
for minutes rather than for a scrape interval or two. Persistence is what separated
this from noise — the same discriminator that works for latency, applied to absence.

**Why nothing downstream complained.** frauddetectionservice does not sit in the request
path. It consumes order events from a queue rather than being called by checkout, so
its callers cannot fail when it stops: there are none. Orders continued to complete
because completing an order never depended on it.

**What that means for what was actually happening.** Orders were being placed and not
screened. The work was not failing — it was accumulating unprocessed, and nothing in
the alerting measures how much of it is waiting. The one alert that fired was reporting
the *only* externally visible consequence of the failure, and it was reporting it as an
absence of traffic rather than as a backlog.

**The container.** Restarting repeatedly, exiting 137 each time — killed by the kernel
for exceeding its memory allowance, never reaching a state where it could consume
anything.

**What changed on it.** Not the image, not the code, not the environment. Its container
memory ceiling had been reduced to 200 MiB against a steady-state working set of about
326 MiB. It is a JVM service, so the heap it was configured for no longer fit inside the
ceiling it was given, and the kernel killed it during startup every time.

## Root cause

frauddetectionservice's container memory limit was reduced below the footprint its JVM
requires. Nothing about the service changed — only the ceiling. The kernel killed it,
the orchestrator restarted it, and it hit the same wall.

## Resolution

The memory limit was restored. The service came up on its next restart, resumed
consuming, and worked through what had accumulated. Everything was clear **1m15s**
after the fix — the fastest recovery of any incident on this system, because nothing in
the request path had to drain or reconnect.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

## Detection notes

- Onset to first page: **7m49s**, the slowest on this system, and it is a function of
  traffic rate rather than of severity. At one call every ten seconds a two-minute rate
  window empties slowly and the persistence clause starts late. The same fault on a
  busy service pages in under three minutes.
- Services alerting at the page: **1**. Over the whole incident: **1**, across 1 alert.
- Alerts that fired only during recovery: **none**.
- **The page named the culprit directly, and it is the only incident here that does.**
  That is not a sign the alerting worked well — it is a consequence of the service
  having no callers to misdirect attention onto. Nothing else could have alerted,
  because nothing else was affected.
- **No user-visible symptom of any kind.** Every dashboard a responder reaches for
  first — error rate, latency, storefront behaviour — was clean for the whole incident.
  A responder trusting "customers are fine" as a severity signal would have deprioritised
  this indefinitely.
- **Absence of downstream symptoms is not evidence of low severity.** A synchronous
  dependency failing loudly stops work from happening. An asynchronous consumer failing
  quietly lets work happen *unprocessed*, which can be worse and is much harder to see.
  Every order placed during those fourteen minutes went through unscreened.
- The signal the alerting does not have is **queue depth**. Traffic to a consumer going
  to zero is a proxy for it, arriving late and saying nothing about how much has piled
  up. The one number that would have described the actual impact was not being collected.
