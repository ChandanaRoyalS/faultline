---
origin: scenario:cart-redis-misconfig
split: dev
fault_class: bad_config
injected_at: 2026-08-23T06:38:03+00:00
resolved_at: 2026-08-23T06:48:50+00:00
---

# Cart service points at the wrong Redis port

## What was observed

The page arrived at 06:40:48: `ServiceHighErrorRate` on **frontend** and **loadgenerator**,
both above the 5% threshold. Fifteen seconds later **checkoutservice** joined.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

At 06:44:03 the picture changed shape. Six services went quiet at once —
accountingservice, currencyservice, emailservice, frauddetectionservice, quoteservice,
shippingservice — all raising `ServiceNoTraffic`. **cartservice** joined them fifteen
seconds after that.

By 06:44:18 there were ten alerts across nine services, and it read as a broad platform
failure rather than a single broken component.

## What was checked

**Error rate by service.** frontend, loadgenerator and checkout were over threshold.
cartservice showed no errors at all — below every other service in the system. That
reading was wrong, but not obviously so at the time.

**loadgenerator.** Set aside quickly. It is the synthetic client, so its error rate
mirrors whatever the storefront is doing; it adds no information about cause. It stayed
in the alert list for the full eight minutes and never meant anything.

**Traces from frontend.** Checkout spans were failing on their call to cart. First real
narrowing, about three minutes in.

**The six quiet services.** These cost several minutes. They looked like a second,
wider failure spreading through the platform. They were not: all six sit downstream of
checkout, and checkout had stopped calling them because it was already failing earlier in
the flow. Their silence was a symptom of the same fault, one hop removed.

**cartservice container state.** Restarting repeatedly. Its logs showed the process
failing during startup on its Redis connection check, exiting, being restarted, and
failing again.

**Recent changes to cartservice.** Its environment had `REDIS_ADDR` set to
`redis-cart:6380`. Redis was listening on 6379 and was healthy throughout — every other
consumer of it was unaffected.

## Root cause

cartservice was configured with the wrong Redis port. The dependency itself was never
unhealthy; only the address was wrong.

Because cart validates its Redis connection during startup rather than on first use, the
wrong address stopped the process from ever coming up. Cart did not degrade — it
disappeared. Every downstream symptom followed from cart being **absent** rather than
failing, which is why it never appeared in the error-rate metric: a service that is not
running records no calls, and therefore no errored ones.

## Resolution

`REDIS_ADDR` restored to `redis-cart:6379`. cartservice came up on its next restart.
The no-traffic alerts cleared within about thirty seconds of traffic resuming; the
error-rate alerts took a further two minutes to fall back under threshold.

Class of fix: **config_revert**. Nothing had been deployed and there was no version to
roll back to — one environment value was wrong.

## Detection notes

- Time from onset to first firing alert: **166s**
- Services alerting at the page: **2**. Over the whole incident: **9**, across 11 alerts.
- **The broken service was named last.** cartservice's own `ServiceNoTraffic` fired at
  06:44:18 — fifteen seconds after six services downstream of it, and three and a half
  minutes after the first page. Nothing in the alerting named cart before that.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest, eight minutes each, and neither was broken.
- Would the page alone have been enough? **No.** It named two services, neither of them
  cart, and pointed at the edge of the system rather than at its cause.
- One late red herring: emailservice crossed the error threshold at 06:48:18 for thirty
  seconds during recovery, after the fix was already in place.
