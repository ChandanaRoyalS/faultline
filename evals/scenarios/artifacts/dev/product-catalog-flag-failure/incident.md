---
origin: scenario:product-catalog-flag-failure
split: dev
fault_class: bad_config
recorded_from: 2026-08-28T03:53:07+00:00
capability: cap:9c416e0a
onset_to_page: 4m04s
page_to_fix: 5m00s
fix_to_all_clear: 1m34s
---

# A feature flag turned on at the flag service makes product catalog fail one product

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **loadgenerator**, 4m04s after
onset. Fifteen seconds later **frontend** and **productcatalogservice** joined it.

Three services alerted during the failure and the set never grew. A fourth alert fired
after the fix: frontend crossed the threshold again for about twelve seconds during
recovery, on a service that had already been alerting throughout.

On the storefront most product pages rendered normally. One did not — it returned an
error every time, while everything around it worked. Baskets, checkout and payment were
unaffected.

## What was checked

**productcatalogservice, which was the obvious place to look.** Unlike most incidents on
this system, the failing service was named in the alerting and was genuinely returning
errors from its own code. It was up, serving, and reporting a healthy call rate — the
errors were a fraction of its traffic, not all of it.

**Which requests were failing.** Not all catalog lookups. One product identifier failed
consistently; every other lookup succeeded. A partial failure with a stable boundary is
not resource pressure, not a dependency outage and not a network problem — all of those
degrade traffic in aggregate rather than singling out one input.

**What changed on productcatalogservice.** Nothing. Image unchanged, environment
unchanged, configuration unchanged, resource limits unchanged, dependencies healthy.
This is the dead end, and it is a convincing one, because the service really was
producing the errors. Everything about it looked correct because everything about it
*was* correct.

**Its dependencies.** The database and cache were fine and every other consumer of them
was unaffected.

**The service list.** This is where it turns. productcatalogservice consults a feature
flag service on each request. That service does not appear in the metrics at all — it
has no call-rate series, no latency series and no error series, under any spelling of
its name. There is no dashboard for it, and no alert can fire on it, because nothing
about it is recorded.

**The flag service's own configuration.** A flag had been enabled that instructs product
catalog to fail requests for a specific product. The service was doing exactly what it
was told.

## Root cause

A feature flag was switched on at the flag service, and productcatalogservice honoured
it by returning errors for one product. The failing service was working correctly; the
configuration that made it fail lived somewhere else entirely, in a component with no
telemetry of any kind.

The errors were real and were attributable to product catalog. The *cause* was not, and
no amount of investigating product catalog would have found it.

## Resolution

The flag was turned off. The next request for that product succeeded. Everything was
clear **1m34s** after the fix. Nothing had to restart, drain or reconnect — a flag flip
takes effect on the following request — and the remaining time is the alerting's own
rolling windows emptying rather than the system recovering.

Class of fix: **config_revert**. Nothing was deployed and there was no version to roll
back to; one configuration value was wrong and was set back.

## Detection notes

- Onset to first page: **4m04s**.
- Services alerting at the page: **1**. Over the whole incident: **3**, across 4 alerts.
- Alerts that fired only during recovery: **1** — frontend, about twelve seconds, after
  the fix had already gone in. It names a service that was genuinely part of the failure,
  which makes it harder to dismiss than a recovery alert on an uninvolved service.
- **The service that errors is not the service that is misconfigured.** This is the
  inverse of a failure where the broken service goes silent. Here the broken-looking
  service is healthy and correct, and the alerting points at it with complete accuracy
  and no useful information.
- **A partial failure with a stable boundary is a configuration signature.** Resource
  exhaustion, dependency latency and outages all degrade traffic in aggregate. One input
  failing consistently while every other input succeeds means something is deciding, and
  something that decides is configured.
- **The cause was in a component with no telemetry.** Nothing in the metrics stack could
  have surfaced it — not a dashboard, not an alert, not a trace attribute. The only route
  to it was knowing that product catalog consults it, and then going to look at
  something the observability stack does not know exists.
- Did the loudest service turn out to be the culprit? **No**, but for an unusual reason:
  the loudest service was loadgenerator as always, and the *second* loudest was the
  service actually producing the errors — which was still not the cause.
