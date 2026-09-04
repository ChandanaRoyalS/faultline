# Discarded run

**Reason:** pipeline-down

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

baseline gate refused; nothing was injected.
  - the alert pipeline is not assembled: the orchestrator's consumer last spoke to Redis 472565ms ago, over the 30000ms ceiling - it is attached but not polling. Restart it with `uv run faultline-orchestrate`. This is NOT the world failing to alert - the fault would fire and no incident would open, which records as `no-alert` and reads as a fact about the scenario (T7.24).
  - kafka is at 78.0% of its 2048MB limit and would reach ~90.8% across the 5 run(s) still to come (1.74h), past the 90% guard the recorder refuses at.
    threshold 77.2% = 90% - (151MB/h x 1.74h / 2048MB), growth measured under load at T7.29.
    Recycle it first, and its consumers with it or they never reconnect (T7.27):
      docker restart kafka && docker restart accounting-service frauddetection-service checkout-service
    A restart clears this completely - T7.30 measured 99.87% -> 26.27%. Raising the limit is not the remedy: the growth is Rosetta translation cache and is driven by work, not bounded by a ceiling (ADR-0005's T7.30 addendum).
    THIS IS A PAUSE, NOT A DISCARD - nothing was injected and this scenario has not been attempted. Recycle, then start again from here.
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
