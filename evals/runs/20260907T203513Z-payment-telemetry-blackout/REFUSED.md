# Refused run

**Reason:** baseline gate refused

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

baseline gate refused; nothing was injected.
  - incident 1ba4a456-f17e-4dac-b55c-98f365f6be2f resolved at 2026-09-07T20:31:42.157857+00:00 and is still inside the orchestrator's 300s settle window - a firing episode now would reopen it rather than open a new incident, and this run's alerts would be attributed to the previous one. Wait 88s.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
