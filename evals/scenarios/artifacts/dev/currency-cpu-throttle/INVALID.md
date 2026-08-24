# ⚠ THIS BUNDLE IS NOT EVIDENCE OF ANYTHING

The fault was injected, the quota was applied, and **nothing happened**. No alert fired,
no metric moved. What this bundle captured is a healthy world with a harmless setting
changed on one container.

## Why the fault could not fire

`currency-cpu-throttle` sets a 0.05 CPU quota — 5% of one core, 50ms of runtime per 100ms
period. Measured from this bundle's own captures, `currencyservice` serves **0.4 req/s at
roughly 2ms of CPU per request**, so its demand is about **0.8ms of CPU per second: 0.08%
of a core.**

The ceiling sits roughly **60× above the demand**. It could not bind, and it did not.

| | pre-fault | during fault | post-fault |
|---|---|---|---|
| call rate | 0.4 req/s | 0.4 req/s | 0.3 req/s |
| p95 latency | 1.9ms | 1.9ms (max 2.0) | 1.9ms |
| error ratio | no series — zero errors, so the ratio is `NaN` throughout | | |

`alerts_at_fire` is empty and `alerts_over_window` is empty. `seconds_to_alert` is null.

The dip in call rate near `t_inject` is load-generator variation: it begins 75 seconds
*before* the injection and recovers above the pre-fault level while the fault is still
running.

## What this is not

It is **not** evidence that the CPU mechanism is broken. The quota was independently
verified applied (`cpu.max` reading `5000 100000`). The mechanism worked; the number was
wrong by two orders of magnitude, and the catalog comment proposing it said
`NOT YET REHEARSED` at the time.

It is **not** a scenario. `evals/scenarios/currency-cpu-throttle.yaml` stays at
`rehearsed: false` and is marked BLOCKED.

## What happened next

Container CPU throttling was retired as a fault mechanism for this world — see
**ADR-0013**. A probe at 0.02 CPU on `frontend` bound completely and took the entire world
down, which established that no service here sits between "too idle to throttle" and "too
central to throttle".

Kept rather than deleted so the invalidation is auditable, per ADR-0009: an artifact that
still looks like evidence is worse than a missing one, and deleting this would remove the
record of why the mechanism was retired.
