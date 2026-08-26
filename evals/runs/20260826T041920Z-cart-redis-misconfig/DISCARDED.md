# Discarded run — recorded by hand, after the fact

**Reason:** the harness process was killed externally, ten minutes into the protocol, by the
tool timeout of the shell that started it. It had passed the gate, injected, correlated,
investigated and reverted; it was inside `confirm_recovery` when it died.

**This file was written by a human, not by the harness**, and that is itself the finding: a
process killed with SIGKILL runs no `except` and no `finally`, so it writes no `DISCARDED.md`
and no `manifest.json`. What it leaves is exactly what is in this directory — the artifacts of
every step that completed, and nothing that says the run is not a result.

The design's rule holds for every failure the process can observe (ADR-0022 §3.3, implemented in
`evalharness.run.RunDir.discard`). It does not hold for one it cannot. **A directory with no
`manifest.json` is an incomplete run**, and a reader — or a later aggregation step — has to treat
it as one. Recorded as a gap rather than papered over.

The world was left clean: the revert completed, `faultline-inject status` reported no active
injections, and the stale `.faultline/harness.lock` was removed by hand before the next run.

The replacement run is `20260826T043356Z-cart-redis-misconfig`.
