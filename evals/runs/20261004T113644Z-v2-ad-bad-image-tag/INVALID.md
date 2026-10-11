# Invalid run

**Reason:** leave-one-out filter did not fire

The run completed and was scored. **Its numbers must not be used**, and it is kept rather than deleted so that the count of invalid runs is itself a fact (T4.1b, ADR-0008 axis 2).

the leave-one-out filter was asked for and removed nothing. ADR-0008 axis 2 is the assertion that a scenario's own artifacts are unreachable while it is scored, and a retrieval that excluded an origin the corpus does not hold has asserted nothing. The run is marked invalid rather than annotated, per T4.1b: silent non-enforcement is how this defect returns. Usually the corpus was never seeded, or was seeded without this scenario's narrative - check `faultline-seed` and the corpus row count, then run the scenario again.
