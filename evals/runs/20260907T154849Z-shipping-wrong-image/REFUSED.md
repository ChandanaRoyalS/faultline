# Refused run

**Reason:** baseline gate refused

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

baseline gate refused; nothing was injected.
  - incident 8bb7a7bf-1abb-4aa2-b2af-0dea3eb27dbb resolved at 2026-09-07T15:44:10.686556+00:00 and is still inside the orchestrator's 300s settle window - a firing episode now would reopen it rather than open a new incident, and this run's alerts would be attributed to the previous one. Wait 19s.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
