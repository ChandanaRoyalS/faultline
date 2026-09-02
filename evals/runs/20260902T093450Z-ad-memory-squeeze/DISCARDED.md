# Discarded run

**Reason:** pipeline-down

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

baseline gate refused; nothing was injected.
  - the alert pipeline is not assembled: no consumer is attached to the orchestrator's group - start it with `uv run faultline-orchestrate`. This is NOT the world failing to alert - the fault would fire and no incident would open, which records as `no-alert` and reads as a fact about the scenario (T7.24).
  - aborting before injection: 5 container(s) have been up for less than 300s and are still settling.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
