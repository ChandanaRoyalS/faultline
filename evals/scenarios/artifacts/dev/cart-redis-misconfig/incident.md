---
origin: scenario:cart-redis-misconfig
split: dev
fault_class: bad_config
recorded_from: 2026-08-23T11:49:47+00:00
onset_to_page: 3m38s
page_to_fix: 5m00s
fix_to_all_clear: 4m30s
---

# Cart service pointed at the wrong Redis port

## What was observed

The page named three services in the same evaluation: `ServiceHighErrorRate` on
**frontend**, **loadgenerator** and **checkoutservice**. It arrived 3m38s after the
first bad request.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

At **T+2m52s** the shape changed. Seven services went quiet simultaneously —
accountingservice, cartservice, currencyservice, emailservice, frauddetectionservice,
quoteservice and shippingservice — all raising `ServiceNoTraffic` in one evaluation.

Eleven alerts across ten services. Nothing in that list pointed at one service more
than any other.

## What was checked

**Error rate by service.** frontend, loadgenerator and checkout were over threshold.
cartservice showed no errors at all — flat zero, below every healthy service in the
system. That reading was taken as evidence cart was fine.

**loadgenerator.** Set aside. It is the synthetic client, so its error rate is a mirror
of whatever the storefront is doing and carries no information about cause. It stayed in
the alert list for eight minutes and never meant anything.

**Traces from frontend.** Checkout spans failing on their call to cart. First real
narrowing, roughly four minutes in.

**The seven quiet services.** This is where the time went. Seven services going silent
at once reads as a platform-wide event, and cartservice is one entry in an alphabetical
list of seven — no more conspicuous than accountingservice. Six of the seven are
downstream of checkout and went quiet because checkout had stopped calling them; only
one was the cause. Nothing in the alert distinguishes them.

**cartservice container state.** Restarting repeatedly. Its logs show the process
failing during startup on its Redis connection check, exiting, being restarted, and
failing again.

**Recent changes to cartservice.** `REDIS_ADDR` set to `redis-cart:6380`. Redis was
listening on 6379 and healthy throughout — every other consumer of it was unaffected.

## Root cause

cartservice was configured with the wrong Redis port. The dependency was never
unhealthy; only the address was wrong.

Because cart validates its Redis connection during startup rather than on first use, the
wrong address stopped the process coming up at all. Cart did not degrade — it
disappeared. That is why it never appeared in the error-rate metric: a service that is
not running records no calls, and therefore no errored ones. Its apparent good health
was an absence of data, not an absence of problems.

## Resolution

`REDIS_ADDR` restored to `redis-cart:6379`. cartservice came up on its next restart.
The no-traffic alerts cleared seven seconds after the fix — those services had never
been broken, only starved.

**An alert appeared 2m22s after the fix and stayed for two minutes**: `ServiceHighErrorRate`
on **emailservice**, a service that had not errored once during the incident itself. It
is a recovery artifact — checkout resumed and pushed a burst of queued work through a
service that had been idle for eight minutes. Anyone reading it as the fix having failed,
or as a second fault emerging, would have started over on a system that was already
healing. Everything was clear at **T+9m30s**.

Class of fix: **config_revert**. Nothing had been deployed and there was no version to
roll back to — one environment value was wrong.

## Detection notes

- Onset to first page: **3m38s**.
- Services alerting at the page: **3**. Over the whole incident: **10**, across 11 alerts.
- Alerts that fired only during recovery: **1** — emailservice, two minutes, on a service
  that was never part of the failure.
- **The broken service was indistinguishable from six healthy ones.** cartservice
  appeared in the same `ServiceNoTraffic` batch as six services that were merely
  downstream of it. It was never singled out by any alert.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at eight minutes each, and neither was broken.
- Would the page alone have been enough? **No.** It named three services, none of them
  cart, and pointed at the edge of the system rather than at its cause.
- The most misleading signal was cart's own error rate: a flat zero throughout, read as
  health when it meant absence.
- The second most misleading was the post-fix alert. **Alert activity after a fix is not
  evidence the fix failed** — a system resuming work is a system doing work it had
  queued.
