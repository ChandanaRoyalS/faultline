---
id: alert-high-error-rate
title: ServiceHighErrorRate has fired
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate]
actions: []
---

`sum by (service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by
(service_name) (rate(calls_total[2m])) > 0.05`, held for 2 minutes. Severity `critical`.

**The baseline is zero.** ADR-0012 measured a quiet world at 0% errors on every service, so
this rule does not fire on noise. A firing rule means real failed calls.

## What the label means

The alert's `service_name` label names where errors are **counted**. That is not the same thing
as where they originate: the metric counts a span's status code, and a caller whose downstream
call returns an error records an error span of its own. One failure can be counted on more than
one service.

## It is a ratio, so traffic volume changes what it reads

Two services can record the same number of failed calls and different ratios, because the
denominator is each service's own call rate over the same 2-minute window. A service taking a
few hundred calls in the window shows a larger ratio for the same absolute number of failures
than one taking several thousand.

That is arithmetic about the rule. The ratio measures a service's own traffic and it does not
measure anything else.

## Several of these at once

One fault can put this rule into `firing` on more than one service inside the same window. The
orchestrator's correlation is what decides whether that is one incident or several, which is
why the alert set arrives as a set.
