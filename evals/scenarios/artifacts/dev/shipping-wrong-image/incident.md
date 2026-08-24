---
origin: scenario:shipping-wrong-image
split: dev
fault_class: bad_deploy
recorded_from: 2026-08-23T18:29:29+00:00
onset_to_page: 2m49s
page_to_fix: 5m00s
fix_to_all_clear: 2m01s
---

# Shipping service deployed with another service's image

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **checkoutservice**, 2m49s after
onset. The fastest page this system has produced, and unusually it named a service one
hop from the problem rather than the edge.

**frontend** and **loadgenerator** crossed the error threshold about a minute later and
dropped back under it within a minute — the storefront was failing on checkout only, so
its overall error ratio hovered around the threshold rather than sitting above it.

At **T+3m26s**, five services raised `ServiceNoTraffic` together: accountingservice,
emailservice, frauddetectionservice, quoteservice and **shippingservice**.

Ten alerts across eight services. On the storefront, browsing and basket operations
worked normally. Checkout failed every time.

## What was checked

**checkoutservice, named in the page.** Errors on its calls to shipping. Its own
process was healthy, its configuration unchanged, its other dependencies fine.

**shippingservice.** The container was in a restart loop, **exiting 137 each time** —
killed by the kernel for exceeding its memory allowance. Restart count climbing, never
reaching a serving state, never recording a call.

**And this is where a confident wrong answer is available.** Exit 137, a restart loop,
a container that cannot stay up: that is the signature of a memory limit set below what
a service needs. The diagnosis writes itself, the evidence supports it, and the obvious
fix is to raise the ceiling.

**The memory limit, which had not changed.** Its container ceiling was the same value
it had been for weeks. Nothing had reduced it. A service does not start exceeding a
limit it has lived comfortably inside unless something about the service changed.

**What changed on shippingservice.** Its image reference. A deployment had pointed it
at a different service's image — one built on a JVM, where the previous image was a
small native binary. The new image needs several times the memory the old one did, and
the container ceiling was sized for the old one. The kernel killed it during startup
every time.

**The five quiet services.** Four of them sit downstream of checkout and went silent
because checkout had stopped calling them. Only shippingservice was broken, and it
appears in that list as one name among five.

## Root cause

A deployment put the wrong image on shippingservice. The image resolved and pulled
cleanly, so the deploy itself reported success; the failure is entirely in what the
container did afterwards. It could not start inside a memory ceiling sized for the
service that was supposed to be there.

The observable symptom belongs to resource exhaustion. The cause is a deployment, and
the two are distinguished only by what changed: the image moved, the limit did not.

## Resolution

The image reference was restored. shippingservice came up on the next reconciliation
and checkout succeeded immediately. The no-traffic alerts cleared as those services
resumed. A brief `ServiceHighErrorRate` appeared on frontend fifteen seconds *after*
the fix and lasted half a minute — queued work draining through a path that had been
failing. Everything was clear at **T+7m01s**.

Class of fix: **rollback**. A deployment moved the service to the wrong artifact, and
the fix was to put the previous one back.

**Raising the memory limit would also have stopped the alert, and would have been
worse.** The container would have started, stayed up, and answered on the wrong
protocol — a service reporting healthy while every caller fails, which is harder to
diagnose than a container that cannot start.

## Detection notes

- Onset to first page: **2m49s**, the fastest on this system. A dependency whose failure
  is fatal to its caller pages quickly; one whose failure is tolerated does not.
- Services alerting at the page: **1**. Over the whole incident: **8**, across 10 alerts.
- Alerts that fired only during recovery: **1** — frontend, thirty seconds, after the
  fix.
- **The page named the caller, not the edge and not the culprit.** checkoutservice fails
  outright when shipping is unavailable, so its error ratio crosses the threshold before
  the frontend's diluted one does. Being one hop from the fault made it the earliest and
  most specific signal available.
- **frontend and loadgenerator alerted intermittently.** An error ratio that crosses a
  threshold, falls back, and crosses again describes a partial failure — one path broken
  out of several — and is worth reading as such rather than as flapping.
- **The exit code names a symptom, not a cause.** Exit 137 means the kernel killed the
  process for memory. It does not say why the process wanted more memory than it used
  to, and that question has two very different answers: the limit came down, or the
  thing inside it got bigger. Only the change history separates them.
- The strongest single question was **"what changed on this service?"** — and the answer
  was available immediately, in the same place it always is. Any investigation that
  started from the exit code and stopped there would have shipped a fix that made the
  system quieter and worse.
