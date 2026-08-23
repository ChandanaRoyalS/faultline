---
origin: scenario:cart-bad-image-tag
split: dev
fault_class: bad_deploy
recorded_from: 2026-08-23T16:07:17+00:00
onset_to_page: 3m17s
page_to_fix: 5m00s
fix_to_all_clear: 3m46s
---

# Cart service deployed on an image tag that was never published

## What was observed

The page named three services in the same evaluation: `ServiceHighErrorRate` on
**loadgenerator**, **checkoutservice** and **frontend**. It arrived 3m17s after the
first bad request.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

At **T+2m43s** seven services went quiet simultaneously — accountingservice,
cartservice, currencyservice, emailservice, frauddetectionservice, quoteservice and
shippingservice — all raising `ServiceNoTraffic` in one evaluation.

Two `ServiceHighLatency` alerts appeared on frontend and loadgenerator shortly before
the fix and lasted well under a minute.

Thirteen alerts across ten services.

## What was checked

**Error rate by service.** frontend, loadgenerator and checkout were over threshold.
cartservice showed no errors at all — flat zero. Taken, wrongly, as evidence cart was
healthy.

**loadgenerator.** Set aside. It is the synthetic client; its error rate restates
whatever the storefront is failing to do and carries no information about cause.

**Traces from frontend.** Checkout spans failing on their call to cart. First real
narrowing, roughly four minutes in.

**The seven quiet services.** Seven services going silent at once reads as a
platform-wide event, and cartservice is one entry in an alphabetical list of seven. Six
of them are downstream of checkout and went quiet because checkout had stopped calling
them. Nothing in the alert distinguishes the cause from its consequences.

**cartservice container state.** This is where it diverges from anything that looks
like it. There was no container. Not a restarting one, not a crashed one — no
cartservice process existed on the host at all, and therefore no logs, no exit code,
and no stack trace. Every diagnostic that begins "check the service's logs" returns
nothing, because there is nothing to have written them.

**The orchestrator's own output, which is the only place the answer lives.** The
deployment had been asked for an image tag that does not exist in the registry. The
pull failed, so the container was never created. The failure is recorded where
scheduling failures are recorded, not where application failures are.

**What changed on cartservice.** Its image reference. Everything else — environment,
configuration, dependencies, resource limits — was untouched, and the previous image
was still present locally and still healthy.

## Root cause

cartservice was pointed at an image tag that had never been published. The pull could
not resolve, the container was never created, and the service simply ceased to exist.
Redis was fine, the network was fine, the code was fine; there was no running copy of
the code to be fine or otherwise.

Its apparent zero error rate was an absence of data. A service that is not running
records no calls, and therefore no errored ones.

## Resolution

The image reference was restored to the previously deployed tag. cartservice came up
on the next reconciliation. The no-traffic alerts cleared as the fix took effect —
those six services had never been broken, only starved.

`ServiceHighErrorRate` fired on **emailservice** more than two minutes *after* the fix
and stayed for a minute, on a service that had not errored once during the incident
itself. It is a recovery artifact: checkout resumed and pushed a burst of queued work
through a service that had been idle for eight minutes. Everything was clear at
**T+8m46s**.

Class of fix: **rollback**. A deployment moved the service to a version that does not
exist, and the fix was to put the previous version back — nothing was misconfigured
and no resource was wrong.

## Detection notes

- Onset to first page: **3m17s**.
- Services alerting at the page: **3**. Over the whole incident: **10**, across 13
  alerts.
- Alerts that fired only during recovery: **1** — emailservice, on a service that was
  never part of the failure.
- **The broken service was indistinguishable from six healthy ones** in the alerting,
  and was never singled out.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 8m30s each and neither was broken.
- **The absence of a container is itself the strongest evidence.** A service that keeps
  dying leaves logs, exit codes and a restart count; a service that was never created
  leaves none of those, and the silence in the usual places is what points at
  scheduling rather than at the application. Looking harder at cart's logs would have
  produced nothing, indefinitely.
- The two brief latency alerts near the end lasted a single evaluation or two. Duration
  is what separates a signal from a transition.
