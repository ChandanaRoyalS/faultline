# ADR-0043: a fault class is individuated by injector mechanism, not by working fix

- **Status:** accepted
- **Date:** 2026-09-22
- **Task:** T7.1 (30+ scenarios across ~8 fault classes), built as the specification asks
- **Supersedes:** [ADR-0022](0022-evaluation-harness.md) §1.2's criterion, as a *class* criterion
- **Promotes:** [ADR-0029](0029-four-fault-classes-and-why-there-is-no-fifth.md) §3, from an
  observed property of the code to the stated rule
- **Relates to:** [ADR-0042](0042-the-world-moves-to-opentelemetry-demo-v2.md) (the world move),
  [ADR-0027](0027-two-working-fixes.md) (two fixes for one class),
  [ADR-0024](0024-the-scale-class-and-what-this-world-can-show.md) (a remediation the world cannot
  perform), CLAUDE.md rule 7

## Context

**Two criteria for individuating a fault class are written down in this repository, and they
disagree.**

- **ADR-0022 §1.2**, a marked decision: *"A fault's class is settled by which fix actually works."*
- **ADR-0029 §3**: *"fault class ≡ injector mechanism,"* one-to-one and enforced by
  `tests/test_scenario_schema.py::test_scenario_injections_match_the_fault_they_cite`.

They never had to be reconciled, because until the world moved no candidate reached the point where
they gave different answers. [The v2 assessment](../design/t7.1-v2-mechanisms-assessed.md) is that
point: fifteen new mechanisms, **nearly free** under §3 and **worth zero** under §1.2.

**The specification asks for ~8 fault classes.** CLAUDE.md rule 7 says the specification's tasks are
built as written, and that an alternative is admissible only after an attempt has failed or where a
better alternative has been argued. **Neither applies**: no attempt at an eighth class has been
made, and the fix criterion is not better — §5 below is the argument that it is worse.

## Decision

**A fault class is individuated by the injector mechanism that produces it.** ADR-0029 §3's binding
is promoted from a property the code happens to have to the rule the taxonomy is held to, and
`test_scenario_injections_match_the_fault_they_cite` becomes its enforcement rather than its
description.

**`remediation_class` remains a separate axis and is unchanged.** What an operator should do stays
a first-class, separately scored answer. What this ADR removes is its use as the criterion for a
*different* question.

## Why, in the order the reasons carry weight

### 1. Rule 7, and it would be enough on its own

The specification asks for eight classes. The fix criterion makes that impossible; the mechanism
criterion makes it reachable. Under rule 7 the specified deliverable is built unless an attempt has
failed — none has — or unless the alternative is argued better, which §5 says it is not.

### 2. The benchmark already scores the two axes separately, and this criterion folds them together

`RESULTS.md`'s panel reports **fault class** and **fix class** as separate rows — 26/27 and 23/27 on
the current record — and `Verdict` carries `fault_class` and `remediation_class` as separate
fields. **Individuating the first by the second makes one axis a function of the other**, and then
scores both as if they were independent evidence. That is a defect in the measurement, not only in
the taxonomy, and no document had noticed it because the two criteria had never disagreed.

### 3. Applied strictly, the fix criterion deletes three of the four classes that exist

ADR-0029 §1, in its own words: *"The criterion does not individuate the four classes that exist.
`config_revert` is a working fix for three of the four. It separates `bad_deploy` from the rest and
nothing else."*

So the fix criterion does not merely block an eighth class. **It licenses exactly two** —
`bad_deploy`, fixed by `rollback`, and everything else — and every figure this repository has
published over four classes would be over a taxonomy its own criterion rejects. A criterion whose
faithful application destroys the thing it is meant to govern is not the governing criterion; it is
a description of a property the taxonomy was hoped to have.

### 4. The external grader characterises faults by mechanism

SREGym's diagnosis judge scores dimension **D2, Fault Characterization**, on whether the diagnosis
*"identifies the same injected mechanism described in the ground-truth (e.g. wrong port, missing
env var, wrong image, wrong selector, memory limit, probe misconfiguration)"*
([the harness read](../design/t7.2-the-harness-read.md)). **Those are mechanisms.** A taxonomy built
on mechanisms is the one that reads against the benchmark T7.2 is about to enter; a taxonomy built
on remediations would have to be translated at the boundary, and something would be lost in the
translation that nobody would be able to see afterwards.

### 5. What the fix criterion is right about, and why it still loses

Its motivation is sound: a distinction that changes nothing an operator does is not worth carrying.
**That motivation is honoured by `remediation_class`, which is where it belongs**, and which the
brief already makes a scored axis. What ADR-0022 §1.2 did was borrow a remediation test to settle a
diagnostic question, and it survived four years' worth of decisions because the catalog was small
enough that mechanism and fix happened to agree.

## Consequences

**`fault_class` stops predicting `remediation_class`, and that has to be measured and published.**
The map from class to working fix becomes many-to-one and is recorded per class on the new world —
`dependency_latency` already has two (ADR-0027, 3/3 each), and v2's flag mechanisms will add more
collisions. **A reader must be able to see the map**, because a benchmark that scores two axes
should say when one constrains the other. This is the cost of the decision and it is not mitigated.

**The chance floor drops, which makes the headline figure more informative.** Fault-class accuracy
over eight classes has a 1/8 floor against four classes' 1/4, and the B2 baseline's 6/10 — much of
it *"the modal class plus what the alert shape gives away"*
([`BASELINES-2026-09-21.md`](../../evals/runs/BASELINES-2026-09-21.md)) — gets substantially harder
to reach by guessing. **T7.1's rationale is statistical credibility, and this serves it a second
way** beyond n.

**The stamp moves**, as any `FaultClass` change does — it is a `Literal` in a contract and
`runtime_version` hashes the contract schemas (ADR-0029 §6). It moves with the world move, which is
why ADR-0042 lands them together.

**ADR-0029 §5's candidate table is re-read under this rule and not discarded.** Its deaths were
adjudicated on the fix test; several were mechanisms the world did not have, which is still
disqualifying. The re-read is owed before the injector is extended and is T7.1's next step.

## What would change it

**A measurement showing mechanism-individuated classes are not separable by evidence.** If the
agent cannot tell two mechanisms apart from metrics, logs, traces and change history — if
`llmRateLimitError` and `kafkaQueueProblems` produce the same page and the same evidence — then
they are one class for every purpose the benchmark has, whatever the injector did. ADR-0029 §4's
topology finding says this is the live risk in this world, and **distinctness of alert shape is a
pre-registered acceptance criterion for the new catalog** (ADR-0042). A class that fails it is
merged, and the merge is recorded.
