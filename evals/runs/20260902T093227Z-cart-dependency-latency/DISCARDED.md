# Discarded run

**Reason:** pipeline-down

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

baseline gate refused; nothing was injected.
  - the alert pipeline is not assembled: no consumer is attached to the orchestrator's group - start it with `uv run faultline-orchestrate`. This is NOT the world failing to alert - the fault would fire and no incident would open, which records as `no-alert` and reads as a fact about the scenario (T7.24).
  - aborting before injection: 1 container(s) have been up for less than 300s and are still settling.
  - kafka is at 99.5% of its 2048MB limit and would reach ~120.0% across the 8 run(s) still to come (2.78h), past the 90% guard the recorder refuses at.
    threshold 69.5% = 90% - (151MB/h x 2.78h / 2048MB), growth measured under load at T7.29.
    Recycle it first, and its consumers with it or they never reconnect (T7.27):
      docker restart kafka && docker restart accounting-service frauddetection-service checkout-service
    A restart clears this completely - T7.30 measured 99.87% -> 26.27%. Raising the limit is not the remedy: the growth is Rosetta translation cache and is driven by work, not bounded by a ceiling (ADR-0005's T7.30 addendum).
    THIS IS A PAUSE, NOT A DISCARD - nothing was injected and this scenario has not been attempted. Recycle, then start again from here.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
