# Discarded run

**Reason:** baseline gate refused

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

baseline gate refused; nothing was injected.
  - incident 51ad54fa-ea64-4363-b695-f1f369e2ba68 resolved at 2026-09-04T06:39:11.461131+00:00 and is still inside the orchestrator's 300s settle window - a firing episode now would reopen it rather than open a new incident, and this run's alerts would be attributed to the previous one. Wait 91s.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
