# Discarded run

**Reason:** metrics-gap

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

the world stopped reporting: 137 of 180 scrapes in 1802s wall clock, longest gap 761s. This run measured nothing about its scenario and is NOT evidence that the fault does not alert - T7.11 found a sixteen-minute telemetry gap behind exactly this shape, on a scenario that pages reliably at T+390s. Check whether the host suspended.
