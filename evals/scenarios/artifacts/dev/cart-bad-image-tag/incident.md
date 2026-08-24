---
origin: scenario:cart-bad-image-tag
split: dev
fault_class: bad_deploy
recorded_from: 2026-08-23T18:53:53+00:00
onset_to_page: 5m01s
page_to_fix: 5m51s
fix_to_all_clear: 3m00s
---

# Cart service deployed on an image tag that was never published

## What was observed

The page named three services in the same evaluation: `ServiceHighErrorRate` on
**frontend**, **loadgenerator** and **checkoutservice**. It arrived 5m01s after onset.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

Seven services then went quiet in two waves fifteen seconds apart. **currencyservice**
and **quoteservice** first, at T+1m15s; then **accountingservice**, **cartservice**,
**emailservice**, **frauddetectionservice** and **shippingservice** at T+1m30s. All
`ServiceNoTraffic`.

Eleven alerts across ten services.

## What was checked

**Error rate by service.** frontend, loadgenerator and checkout were over threshold.
cartservice showed no errors at all — flat zero. Read, wrongly, as evidence cart was
healthy.

**loadgenerator.** Set aside. It is the synthetic client; its error rate restates what
the storefront is failing to do and says nothing about cause.

**Traces from frontend.** Checkout spans failing on their call to cart. The first real
narrowing.

**The two waves of silence.** Tempting to read as a spreading failure — one thing
knocking over another, which knocks over more. It is not. Both waves are the same
event seen at two evaluation boundaries: services stopped being called at the same
moment, and their rate windows emptied a scrape apart. **Fifteen seconds of separation
between groups is scrape granularity, not causal ordering.**

**cartservice container state.** There was no container. Not a restarting one, not a
crashed one — no cartservice process existed on the host, and therefore no logs, no
exit code, no restart count. Every diagnostic that begins "check the service's logs"
returns nothing, because nothing exists to have written them.

**The orchestrator's output, which is the only place the answer lives.** The deployment
had been asked for an image tag that does not exist in the registry. The pull failed,
so the container was never created. That failure is recorded where scheduling failures
are recorded, not where application failures are.

**What changed on cartservice.** Its image reference, and nothing else. Environment,
configuration, dependencies and resource limits were untouched, and the previously
deployed image was still present locally and still healthy.

## Root cause

cartservice was pointed at an image tag that had never been published. The pull could
not resolve, the container was never created, and the service ceased to exist. Redis
was fine, the network was fine, the code was fine — there was no running copy of the
code for any of that to matter to.

Its apparent zero error rate was an absence of data. A service that is not running
records no calls, and therefore no errored ones.

## Resolution

The image reference was restored to the previously deployed tag. cartservice came up on
the next reconciliation and the no-traffic alerts cleared eight seconds later — those
six services had never been broken, only starved.

A brief `ServiceHighErrorRate` appeared on **emailservice** more than two minutes after
the fix and lasted half a minute, on a service that had not errored once during the
incident. It is a recovery artifact: checkout resumed and pushed queued work through a
service that had been idle. Everything was clear at **T+8m51s**.

Class of fix: **rollback**. A deployment moved the service to a version that does not
exist; the fix was to put the previous version back.

## Detection notes

- Onset to first page: **5m01s**.
- Services alerting at the page: **3**. Over the whole incident: **10**, across 11
  alerts.
- Alerts that fired only during recovery: **1** — emailservice, thirty seconds, on a
  service that was never part of the failure.
- **The broken service was indistinguishable from six healthy ones.** cartservice
  appeared in the second wave of `ServiceNoTraffic` alongside five services that were
  merely downstream of it, and was never singled out by any alert.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at nine minutes each and neither was broken.
- **The absence of a container is the strongest evidence available.** A service that
  keeps dying leaves logs, an exit code and a restart count. A service that was never
  created leaves none of those, and the silence in the usual places is what points at
  scheduling rather than at the application. Looking harder at cart's logs would have
  produced nothing, indefinitely.
- **Do not read scrape granularity as causation.** The seven quiet services split into
  two groups fifteen seconds apart, which looks like propagation and is an artifact of
  when each rate window happened to empty.
