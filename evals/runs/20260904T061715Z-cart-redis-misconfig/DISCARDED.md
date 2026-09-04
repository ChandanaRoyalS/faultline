# Discarded run

**Reason:** pipeline-down

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

baseline gate refused; nothing was injected.
  - the alert pipeline is not assembled: the orchestrator's consumer last spoke to Redis 486065ms ago, over the 30000ms ceiling - it is attached but not polling. Restart it with `uv run faultline-orchestrate`. This is NOT the world failing to alert - the fault would fire and no incident would open, which records as `no-alert` and reads as a fact about the scenario (T7.24).
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
