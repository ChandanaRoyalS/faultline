# Refused run

**Reason:** baseline gate refused

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

baseline gate refused; nothing was injected.
  - aborting before injection: 1 container(s) have been up for less than 300s and are still settling.
  - incident 083cd2de-8a2f-4b29-93da-1c43beb154a3 resolved at 2026-10-14T18:02:45.732326+00:00 and is still inside the orchestrator's 300s settle window - a firing episode now would reopen it rather than open a new incident, and this run's alerts would be attributed to the previous one. Wait 90s.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
