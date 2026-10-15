# ADR-0045: Online evaluation is deferred beyond the plan, and its seams are named

- **Status:** accepted
- **Date:** 2026-10-15
- **Task:** Phase 4's closing note in the execution plan (REV 9, §7), written late
- **Relates to:** [ADR-0022](0022-evaluation-harness.md) (the offline harness this complements),
  [ADR-0039](0039-the-approval-surface-and-the-rejection-loop.md) (the rejection loop),
  [ADR-0038](0038-the-executor.md) (the action audit)

## Context

The execution plan closes Phase 4 with a cut it asks to be recorded, verbatim:

> Deliberately cut, not forgotten: the spec's online-evaluation block — per-incident thumbs,
> sampled judge scoring of live reports, canary drift alarms — is deferred beyond this plan,
> because online signals only mean something under sustained real usage a portfolio system
> doesn't have. The seams exist (every report, approval, and rejection is already persisted),
> and an ADR records the cut so it reads as a scoping decision, not an omission.

**No ADR recorded it until now.** The repository audit of 2026-10-13 found the gap: none of the 44
ADRs, `PLAN.md`, `QUEUE.md` or `MVP-CUT.md` mentions online evaluation, thumbs, sampled live
judging or canary drift. The cut was made - nothing of it was built - but it read as an omission,
which is the outcome the plan's sentence exists to prevent.

## Decision

**The three online signals are not built in this plan**, for the plan's reason: each is a rate
over live incidents, and the deployed instance sees the incidents its own demo world raises,
not a population of real ones. A thumbs-up rate over a handful of self-inflicted incidents, a
judge score sampled from them, or a drift alarm on their verdict mix would be a number with no
denominator worth the name - the class of figure this repository's rules exist to keep out of
its records.

**The seams the plan says exist, checked against the tree on 2026-10-15** - each is persisted
today, so an online loop would read rather than retrofit:

| online signal | what it would read | where it is persisted |
|---|---|---|
| per-incident feedback | the report a person saw, and their reaction to it | the verdict and narrative per trajectory (`trajectories`, `trajectory_steps`, migration 0001); approvals and executions (`action_audit`, migration 0005); rejections with their required reason (`incident_rejections`, migration 0006); sev-1 acknowledgements (`incident_acknowledgements`, migration 0007) |
| sampled judge scoring of live reports | a live report's narrative and the evidence it cites | the same trajectory rows, with every cited result's raw payload archivable (`archive.py`, ADR-0034); the offline judge (`src/evalharness/judge.py`) already scores a narrative against labels |
| canary drift alarms | the verdict mix and cost over time, per stamp | every investigation records its runtime stamp (`trajectories.runtime_version`) and each step's tokens (`trajectory_steps`), and the platform exports `faultline_model_usd` and `faultline_investigation_seconds` (`observability/metrics.py`, T6.6) |

**What is not a seam, said so**: a *thumbs* control does not exist on the incident screen, and no
table holds one. Approve and reject are decisions about an action, not ratings of a report, and
are not to be read as one; a rejection's reason is the nearest thing, and it is free text.

## Consequences

- The offline harness (T4.1-T4.7) and the published runs remain the only evaluation evidence,
  which is what every report in `evals/runs/` already says.
- Nothing is removed and no figure moves; this ADR records a scope that was already the case.

## Revisit if

The deployed instance is pointed at a system that raises incidents it did not inject - then the
three signals have a population, and the seams above are where they would start.
