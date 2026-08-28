# Pre-registration — holdout entry 3

**Written and committed before any scenario of this entry ran.** Condition 3 of the T4.8
addendum's four; the argument for the entry as a whole is
[ADR-0022's T4.15 addendum](../../docs/adr/0022-evaluation-harness.md).

## Configuration

| | |
|---|---|
| stamp | `faultline/0.0.1+prompts:1b0e7cbb4c47` |
| entitled by | dev sweep 5 ([`SWEEP-2026-08-27-locus.md`](SWEEP-2026-08-27-locus.md)) — coverage 7/7, fault class 7/7 |
| budget | `changes` **8**, others 4, 120k tokens, 600s, 2 rounds — the T4.7 configuration, identical to entry 2's |
| agent | `claude-opus-5` |
| judge | `claude-haiku-4-5` — **SHARED LINEAGE**, as every judged figure here carries |
| protocol | all three scenarios, once each, `--holdout`, full gate/revert/recovery, discards recorded, **no re-runs** |

Same budget as entry 2 and the same bound as dev sweep 5, so the only thing that has moved since
entry 2 is the stamp.

## What the record predicts

### The two starvation abstentions should now resolve

Entry 1's `email-wrong-image` and `recommendation-memory-squeeze` both abstained with `changes`
exhausted at 4 of 4. Two things have happened since, and they address the two halves of that
failure:

- **T4.7's bound fixed the starvation.** With eight calls the plan is not cut off at four.
- **T4.14's instruction fixed the abandonment the bound exposed.** Entry 2 showed that removing
  the starvation did not produce the dispatch — the planner simply never asked. The instruction
  says a localized service keeps its claim until its evidence classes are exhausted.

**Registered: `recommendation-memory-squeeze` answers `resource_exhaustion`.** It is the cleaner
of the two tests, because it has never been read for a mechanism by anyone and is not in the
instruction's lineage.

### `email-wrong-image` is the hard case, and its result is corroborative only

Entry 2's finding on this scenario is **in the lineage of the instruction being tested** (T4.15
addendum, condition 2). Its result is reported as corroboration, not as independent evidence,
whichever way it falls.

What the instruction **should** fix: the specific gap entry 2 recorded. Its own traces named
`emailservice` as having vanished, and no dispatch was ever sent there. If "a localized service
keeps its claim on your dispatches" reaches the behaviour, `emailservice` should appear in the
plan and its change history should be asked for.

What the instruction **should not** be expected to fix: whether the answer is *findable* once
asked. Entry 2's run identified the mechanism precisely — an outbound POST failing at DNS
resolution before any TCP dial — and declined only the initiating act. If the change record for
whatever removed `emailservice` from DNS is not in the change log at all, then dispatching at
`emailservice` returns an empty stream and a correct abstention follows. **The instruction moves
dispatches, not evidence into existence.**

**Registered: `emailservice` appears in the plan and is dispatched on.** That is the endpoint for
this scenario. The fault class is secondary and an abstention with the dispatch made is **not** a
falsification.

### The falsifier

**`emailservice` is again never dispatched on.** Then the instruction did not reach this
behaviour on a scenario outside dev, and the dev result generalises less far than S5 suggests —
regardless of what the fault-class column says.

A second, weaker falsifier: **`productcatalog-dependency-latency` regresses.** It answered
correctly in entry 1 under the *older, worse* stamp and a tighter bound. Losing it would mean the
instruction costs something on holdout that it did not cost on dev.

## Coverage floor

Entry 1 scored 1 of 3 answered, all three run. **Registered floor: at least 2 of 3 answered, and
no answered scenario returns a wrong class.** Below that, the dev result did not carry.

## What this entry cannot show

n = 1 per scenario, three scenarios, one entry. No interval is claimed on any of it. Two of the
three scenarios have now been seen by an agent twice and one three times; the T4.15 addendum
records that this should be the last entry before the set is re-authored or extended.
