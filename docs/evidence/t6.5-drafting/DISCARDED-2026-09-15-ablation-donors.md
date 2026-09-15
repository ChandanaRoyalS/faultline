# The first drafting run, discarded: every donor was an ablation run

**2026-09-15. $0.797 spent, nine postmortems written, none kept.** Recorded rather than deleted,
on ADR-0022 §3.3's rule that the number of runs is a fact nobody can hide by tidying.

## What happened

`faultline-postmortem` drafted nine of ten dev scenarios at a cost of $0.797, with **five guard
refusals** across fourteen calls. `cart-redis-misconfig` was refused twice and produced nothing.

Then the drafts were read. `cart-bad-image-tag` — a bad image tag on **cartservice** — concluded:

> *"Blame sits on a checkout dependency on that path; the stage where the log trail first goes
> dark is payment, but that hop could not be confirmed."*

Scoring all nine against their manifests: **4 of 9 correct on fault class, 4 of 9 on culprit
service.**

## Why

**Every one of the nine donors carried `ablation: ["traces"]`.** They are the `--without traces`
arm of dev sweep 12 — a deliberately degraded pipeline with the trace analyst withheld — and they
were selected because `donor_runs` takes the *newest* run per scenario and that arm ran last.

`record_from_run` refused a baseline and said nothing about an ablation.

**README already predicts the number.** Its own text on the trace ablation: *"nine of nine with
traces, three of eleven without."* The 4-of-9 is that gap, drafted into documents.

## The hole, and its three predecessors

`scenario_table._qualifies` excludes ablation runs from every published figure, and its comment
records the history:

> *"T6.1 put `ablation` in `evaldb.FINGERPRINT_INPUTS` so an ablation run can never pool with a
> full run, and this table had its own filter that did not know about it. Arm B's first six runs
> landed straight into arm A's column on 2026-09-10 … **Third time**: the same hole took
> `observability_digest` two days earlier and the B0 arm before that."*

**This is the fourth.** A new consumer of the run archive wrote its own filter and did not
inherit that one. The pattern is now four for four: every component that selects runs from
`evals/runs/` has had to learn the exclusion separately.

## What changes

`record_from_run` refuses an ablation run with the same standing it refuses a baseline, and two
tests hold it — one on the archive's ablation directories, one asserting no donor the walk would
pick is either. A third test closes a smaller gap the same reading found: `recorded_from` was
empty on all nine drafts, so the postmortems carried no tie to the recording they were about and
nothing could have told they were stale.

## What this does to prediction 6

**The five refusals are not prediction 6's score.** The registration drafts postmortems from *the
recorded incident*, and a `--without traces` arm is a different pipeline — its records are not
what the prediction is about. This run is invalid as a measurement in exactly the way T4.1b calls
a run with a silent filter invalid: it produced numbers, and they do not answer the question.

The re-draft against full-pipeline donors is what scores prediction 6. **This run's five refusals
are recorded here and pooled with nothing.**

## Cost

| | |
|---|---|
| spent, discarded | **$0.797** |
| drafting budget (§6) | $5.00 |
| remaining for the re-draft | **$4.20** |

The task ceiling is $70 (Amendment 3) and this comes out of the $5 drafting line inside it.
