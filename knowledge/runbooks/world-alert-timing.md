---
id: world-alert-timing
title: Why an alert fires minutes after the fault that caused it
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: []
---

An alert's `activeAt` is not the time the fault started. Every rule here composes a sampling
interval, a rate window and a `for:` clause, and the sum is minutes.

## The instrument's constants

Prometheus scrapes at **5s** and evaluates at **15s**; the `faultline-slo` rule group carries its
own `interval: 15s`. Both live in `compose/prometheus/prometheus-config.yaml`, which is under
`observability_digest` precisely because it sets the sampling resolution of every capture.

## The decomposition

**An onset is the time for the rule's condition to become true, plus that rule's `for:` clause.**
The first part depends on the fault and on the service; the second is a constant per rule.

| rule | window in the expression | `for:` |
|---|---|---|
| `ServiceHighErrorRate` | `rate(...[2m])`, both sides of the ratio | 2m |
| `ServiceHighLatency` | `rate(latency_bucket[2m])` under the quantile | 3m |
| `ServiceNoTraffic` | `rate(calls_total[3m]) == 0`, plus a 30m lookback offset by 10m | 3m |

The longest `for:` clause in the file is **3m**, on the latter two.

## The floor on a recovery alert

A recovery-caused alert cannot appear sooner than its rule's `for:` clause after the remediation:
**2m** for `ServiceHighErrorRate`, **3m** for `ServiceHighLatency`, and **about 6m** for
`ServiceNoTraffic` - three minutes of `for:` on top of a three-minute zero-rate window that has to
empty first. Those figures are arithmetic from the rule file, and the orchestrator's settle window
is sized against them.

## The zero-rate case is predictable to the second

`ServiceNoTraffic`'s window drains first and its `for:` clause runs after. The two add: the moment
the rule goes `pending` predicts the moment it goes `firing`, and a measurement of that path hit
the prediction within a second. **The paging path on this world is arithmetic rather than
marginal.**

## Onset scales with the target's traffic rate

A rate window over a sparse service fills slowly. `ServiceNoTraffic` reads a three-minute rate
against a lookback baseline and then holds for three more; fed a call every ten seconds or so,
those windows empty late and the clause starts late. **The fault bites immediately and the rule
takes minutes longer to agree**, and the gap is a property of the service's traffic rate rather
than of the fault. A single global timeout applied across services of different rates will
misreport the sparse ones.

## A recorded detection time is an observation, not a property

Every `seconds_to_alert` in every recording is a **single draw from a distribution nobody has
characterised.** The same fault injected twice does not page at the same second, because the
sampling interval, the window's contents and the rule's evaluation tick all move.

So: treat a detection time as an observation of one run, never as a property of a fault or of a
service, and do not compare two of them without saying how many runs each rests on.
