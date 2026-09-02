---
id: alert-high-error-rate
title: ServiceHighErrorRate has fired
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate]
actions: [rollback_image, revert_config]
---

`sum by (service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by
(service_name) (rate(calls_total[2m])) > 0.05`, held for 2 minutes. Severity `critical`.

**The baseline is zero.** ADR-0012 measured a quiet world at 0% errors on every service, so
this rule does not fire on noise. A firing rule means real failed calls.

## Confirm before scoping

- The alert's `service_name` label names where errors are *counted*, not necessarily where
  they originate. A dependency returning errors shows up on its caller's ratio too.
- Rank the affected services by ratio. The one with the highest ratio and the fewest inbound
  edges in the dependency graph is the likelier origin.
- Check change history over the incident window before reading logs. Most incidents in this
  world are change-induced, and a change found first makes the log query narrower.

## What it usually is here

Errors at this magnitude come from `bad_deploy` (a wrong image tag) or `bad_config` (an
environment value pointing somewhere that no longer answers). Both are visible in change
history; neither needs a trace to identify.

## What this alert cannot tell you

One fault frequently fires this rule on several services at once, and the service with the
highest ratio is often not the one that broke - errors propagate to callers, and a caller with
less traffic shows a higher ratio for the same absolute number of failures. Treat the alert set
as one incident, let correlation group it, and rank by topology rather than by loudness.
