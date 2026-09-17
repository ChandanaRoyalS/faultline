# Refused run

**Reason:** baseline gate refused

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

baseline gate refused; nothing was injected.
  - incident d502c601-def0-4853-a247-32dd6e3a4b73 resolved at 2026-09-17T03:27:43.471368+00:00 and is still inside the orchestrator's 300s settle window - a firing episode now would reopen it rather than open a new incident, and this run's alerts would be attributed to the previous one. Wait 55s.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
