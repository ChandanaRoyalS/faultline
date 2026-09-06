# Refused run

**Reason:** pipeline-down

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

baseline gate refused; nothing was injected.
  - the alert pipeline is not assembled: the orchestrator's consumer last spoke to Redis 938141ms ago, over the 30000ms ceiling - it is attached but not polling. Restart it with `uv run faultline-orchestrate`. This is NOT the world failing to alert - the fault would fire and no incident would open, which records as `no-alert` and reads as a fact about the scenario (T7.24).
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
