# ADR-0023: a freeze manifest outlives the pipeline it froze

**Status:** accepted
**Date:** 2026-08-27
**Context:** T4.12, forced by the first prompt change to land after a holdout was frozen - a
change that was then measured, rejected, and reverted, which is why this ADR's consequences are
written for supersession as a reversible state.

## Context

T4.6 froze the pipeline before the holdout ran and committed
`evals/runs/FREEZE-2026-08-26-holdout.json`. Its guard,
`test_the_committed_freeze_manifest_matches_the_pipeline_it_names`, asserted the committed
manifest equals `runtime_version()` at HEAD, reasoning that a mismatch means "either the
manifest was not regenerated or the pipeline moved - and both invalidate the holdout."

That reasoning conflated two failures with opposite meanings, and T4.12 is the first change
to separate them. T4.12 adds one instruction to the planner. The stamp moves
`53fafe9c12bc` → `bf7605651ef2` **on purpose** - that is the measurement. Under the old
assertion the holdout guard fails, and the only ways to make it pass are to abandon the
experiment or to regenerate the manifest, which would silently rewrite the record of what the
holdout actually ran under. Both are worse than the failure.

## Decision

**A freeze manifest is a historical record, not a claim about HEAD.** The guard checks that
the manifest is internally consistent and names a pipeline this repository knows, not that it
names the current one.

Two conditions replace the equality:

1. **Completeness of the record.** The manifest carries its prompt hash and records
   `corpus.holdout_chunks` as 0 - the contamination invariant the freeze exists to attest.
   Note what cannot be checked: `runtime_version`'s digest covers prompts *and* contract
   schemas while `prompts.sha256` covers prompt text alone, so the two fields are different
   functions over overlapping inputs and neither validates the other. A guard that claimed to
   cross-check them would be asserting a relationship that does not exist.
2. **Known lineage.** The stamp it names is one of the digests recorded in the test suite. A
   manifest naming a pipeline nothing in the repository describes is an untraceable record.

**What replaces the lost check is a reporting obligation, not another assertion.** While the
pipeline sits past a frozen run, the numbers that run produced do not describe the current agent,
and `docs/RESULTS.md` must say so next to those numbers - and must say so in the tense the
situation is actually in, since a pipeline can move away from a frozen stamp and back again. A
test cannot enforce a sentence in a report; pretending otherwise is what the old assertion did.

## Consequences

**Every holdout number carries the stamp it was produced under**, in `docs/RESULTS.md` and
`README.md`, whether or not that stamp is currently HEAD.

**What actually happened in T4.12 is the case this ADR was written for, and it resolved the
other way.** The pipeline was superseded by `bf7605651ef2` for the length of one dev sweep, the
sweep measured that pipeline as net harmful against a floor registered in advance, and the
instruction was reverted. HEAD is `53fafe9c12bc` again - the stamp the holdout ran under - so the
holdout figures describe the current agent once more.

That is the point rather than a footnote. Under the old assertion the guard would have passed
before the experiment and after it, and failed only in the middle, while the holdout record was
never in any danger at any of those three moments. A guard that fires on the deliberate act and
goes quiet on the outcome was measuring the wrong thing. **Supersession is a state a pipeline can
enter and leave**, and the record of the rejected stamp survives in
`evals/runs/SWEEP-2026-08-27-evidence.md` and in `SWEEP_4_DIGEST` regardless of which stamp is
HEAD.

**Re-freezing is a deliberate act with a new file.** A frozen manifest is never regenerated in
place. A new experiment writes `FREEZE-<date>-<name>.json`; the old files stay as they are.
Four already exist and none of them will be touched again.

**A holdout re-entry under the new pipeline is a separate decision** with its own
pre-registration under ADR-0022's protocol. Nothing here licenses one, and the S4 sweep is dev
only.

**The risk accepted:** the guard no longer catches "somebody forgot to regenerate the manifest
before freezing." That case is now caught by the freeze command writing the manifest at freeze
time rather than by a test at HEAD, which is where it belonged - the manifest and the run it
describes are produced in one act.
