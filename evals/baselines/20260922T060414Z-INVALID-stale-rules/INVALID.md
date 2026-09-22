# ⚠ THIS IS NOT A BASELINE

The alert rules evaluating during this window were **not** the rules in the repository at the time
it was taken. `git am` replaced `compose/prometheus/alert-rules-v2.yml` by rename two hours earlier,
which detached the running container's single-file bind mount; the reload that followed failed with
`open /etc/prometheus/alert-rules.yml: no such file or directory`, and Prometheus did what it
documents — **`error loading rules, previous rule set restored`**.

So the rules in force for all 45 minutes were the `[2m]` ones loaded at **04:18:22Z**, before the
widening merged. This capture was taken specifically to test that widening and **it did not test
it.**

Mechanism, timeline and fix:
[`docs/evidence/world-v2-trial/2026-09-22-the-mount-that-detached.md`](../../../docs/evidence/world-v2-trial/2026-09-22-the-mount-that-detached.md).

## What must not be cited

**`alerts-firing`, and every conclusion drawn from it.** Its headline — `ServiceHighLatency` on
`accounting` firing continuously for the full 45 minutes — reads as evidence that widening the rate
windows failed to quiet the world. **It is not.** It is the `[2m]` rules behaving exactly as the
first baseline predicted they would, recorded by a capture that believed it was measuring something
else.

**`summary.md`'s Queries section is honest and that is what makes it misleading.** It prints the
expressions the *capture* sent, which were correct. It says nothing about the expressions the
*rules* were evaluating, because the recorder had no way to know they differed — and on
2026-09-22 the recorder's own window was hard-coded anyway.

## What is usable, with a caveat

The `error-ratio`, `latency-p95` and `call-rate` JSON under `metrics/` were taken by querying
Prometheus directly and **do not depend on which rules were loaded.** As a measurement of the
world's traffic they stand.

**The caveat is that they are `[2m]` figures**, so they carry the same sampling noise the first
baseline diagnosed — 15000 ms p95s and error ratios to 100% on services running at 0.1–0.3 req/s.
They describe six-to-eight-sample windows, which is a fact about the instrument rather than about
the world. Nothing here may be compared with a `[5m]` capture.

## Why the tool did not catch it

It could not. `evalharness.baseline` polls the injector, checks the world is quiet and records what
it queried — **it has never compared its own queries against the rules Prometheus is evaluating**,
and nothing else did either. Four independent signals reported a healthy world that day: compose
said `Running`, `make check` parsed the rule file on the host, `promtool check config` resolved a
container path against the host filesystem and reported `SUCCESS`, and `/api/v1/rules` answered
with the stale windows.

**Two guards now exist**, both in `tests/test_world_v2.py`: one removes the single-file mount that
made a detachment possible, and one asserts that the capture window and the rules' detection window
are the same value. A capture taken today could still be taken against stale rules if a container
were left running across a merge — **that is checked at the world, before the clock starts, not by
the recorder**, and the procedure is at the end of the mount note.

## Why it is kept

ADR-0009: *an artifact which still looks like evidence is worse than a missing one, and deleting
this one would remove the record of how it went wrong.* Kept and labelled, on the same terms as
`20260823T061632Z-INVALID-contaminated/`.
