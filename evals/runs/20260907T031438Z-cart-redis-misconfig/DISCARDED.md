# Discarded run

**Reason:** no-alert

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

no incident reached 2 episode(s) within 180 scrapes (901s wall clock, no telemetry gap seen - the world was reporting throughout). The fault may not alert on this world - check the bundle's alerts_over_window, and note that a sparse service can take far longer than a busy one to trip a rule (evals/scenarios/CATALOG.md).
