# The re-backfill was a no-op, and Amendment 6 §6 said it would not be

**2026-09-15. $0.00.** One `faultline-eval-db load` over 548 manifests.

```
loaded 548 run(s), 0 new configuration(s)
548 run(s) across 38 configuration(s)
  outcomes: 28 discarded, 1 invalid, 73 paused, 202 refused, 244 scored
```

Identical to the reading taken immediately before it. **Not one configuration renamed.**

---

## 1. What was expected, and why it was wrong

[T6.5 Amendment 6](../../../evals/runs/PREREGISTRATION-T6.5.md) §6 registered the re-backfill as
necessary:

> *"Q69 renames every `corpus_sha256`, which `FINGERPRINT_INPUTS` carries, so a half-loaded
> database holds one configuration under two names."*

**`corpus_sha256` is a string recorded in a manifest, not a value recomputed at load.** Q69
changed `freeze.corpus_state`, which is what *writes* that string when a run is made. Every
manifest on disk was written before the change and still carries the digest it recorded at the
time, so every fingerprint derived from those manifests is byte-identical to what it was.

**The rename is prospective only, and the first run to carry a Q69-computed digest has not been
made yet.** It will be the first run of the T6.5 sweep.

The confusion was with [Q61](../../QUEUE.md), where the change was to `FINGERPRINT_INPUTS`
itself — a *read-time* recomputation over unchanged manifests, which really did rename all 38
groups and really did need the re-backfill that measured 24 new configuration rows. Q69 is the
other shape, and the two were treated as one.

## 2. What the no-op is evidence of

It is the check that Q69 touched nothing archived. A shape-digest change that had reached back
into the eval database would have shown here as new configuration rows, and it did not. So the
183 corpus-carrying runs are grouped exactly as they were this morning, on digests computed the
old way, and they stay that way permanently — which is correct, because that is what those runs
actually read.

## 3. The consequence that does need saying

**A digest computed before Q69 and one computed after are not comparable, and nothing marks the
boundary.** An archived `corpus_sha256` and a future one for the *same corpus* are different
strings. Today that costs nothing — `CURRENT_CORPUS_SHAPE` had never matched any corpus a run
could read, so no archived run was ever going to compare equal to it. But it means the archive's
shape digests can only ever be compared with each other, never with anything recorded from here
on, and the only thing recording that is this file.

It is not worth a queue row on its own: it is one more axis of the naming question the two
corpus digests already joined, which is **Q31**.

## 4. Why this is a file and not an edit

Amendment 6 is not corrected in place. **A pre-registration amended after the fact is not one**,
and that rule holds for a sentence that turned out to be wrong about the mechanism as much as for
one that would have changed a number. This is where the correction lives, and Q69's row points at
it.
