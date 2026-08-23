# ADR-0008: Two-axis contamination model for the scenario catalog

- **Status:** accepted
- **Date:** 2026-08-23

## Context

The scenario catalog is simultaneously the eval dataset, the regression suite, and the
demo script library. It is also self-labeled: we inject every fault ourselves, so the
answer key exists before the question does. That makes two distinct leakage paths
available, and they are not the same problem.

**Axis 1 — cross-scenario leakage.** Prompt text, context-window tuning, retrieval
configuration, and the runbook corpus are all hill-climbed against measured accuracy.
Anything tuned against a scenario has been fitted to it. Reported accuracy over scenarios
used for tuning is training accuracy, and will not survive an interviewer who asks how the
split was drawn.

**Axis 2 — self-reference.** Scenario rehearsals (T1.5) seed the past-incident store
(T2.4b). When scoring scenario S, the nearest neighbour in that store is the rehearsal of
S — a document containing S's true root cause, written in the label author's own words.
The retrieval agent does not diagnose the incident; it looks up the answer key. This is
*within-split* leakage: a dev-set scenario retrieving its own dev-set rehearsal violates no
split rule at all. Axis 1's defence is structurally blind to it.

Both axes must be closed, and each is closed by a different mechanism at a different
phase. Conflating them is how one of them silently goes unenforced.

## Decision

**Axis 1 — split quarantine (this ADR, enforced from T1.6 onward).**
Every scenario carries a `split` field of `dev` or `holdout`, assigned at authoring time,
before the scenario has been rehearsed even once. Target ratio ~70/30, allocated across
fault classes by the table in `evals/scenarios/SPLIT.md`.

The allocation is made against *unnamed slots* — `bad_deploy-1`, `bad_deploy-2`, and so on
— and committed before authoring begins. Authoring fills slots in order. This removes the
selection bias available when a split is drawn over scenarios that already exist: with
named scenarios in front of you, it is very easy to route the awkward one to dev and keep
the clean one for the headline.

No corpus content, prompt revision, context-engineering change, or retrieval setting may
ever be tuned against a holdout scenario. Rehearsal artifacts land in
`evals/scenarios/artifacts/<split>/<id>/`, so quarantine is a path property rather than a
remembered rule. T2.4b seeds the knowledge stores from the dev split only. T4.1's harness
enforces this by checksum and refuses to score a holdout scenario whose artifacts appear in
any corpus.

**Axis 2 — run-time self-exclusion (specified here, enforced at T4.1b).**
Every knowledge artifact carries a provenance stamp: `origin: authored` or
`origin: scenario:<id>`. Retrieval tools accept `exclude_origin`. The harness sets it to
the scenario under test on every scored run and then asserts the filter actually fired; a
scored run where the filter did not fire is marked **invalid**, not annotated. Silent
non-enforcement is precisely how this defect returns after being fixed once.

Hand-authored runbooks (`origin: authored`) are never excluded. They are legitimate
institutional knowledge, which is exactly what a real on-call engineer would have.

**Headline policy.** Until the catalog reaches 30+ scenarios, published numbers are
full-set with the dev/holdout breakdown shown and `n` stated explicitly. A 3-scenario
holdout is an anecdote and will not be headlined as anything else. Once T7.1 brings the
holdout to ~9–10 scenarios, the headline switches to holdout-only.

## Consequences

Easier: accuracy claims are defensible under direct questioning, and the two most common
self-labeled-benchmark failures have named owners and mechanical enforcement rather than
good intentions. The ablation work in P7 inherits a clean measurement substrate for free.

Harder: the holdout is unusable for debugging, so roughly a third of the catalog cannot
help when accuracy is disappointing and the reason is unclear. Authoring is slower, because
slot allocation is fixed before the scenarios are known and an interesting scenario cannot
be moved to the split where it would be more convenient.

Accepted asymmetry: at n=10 a 3-scenario holdout cannot cover four fault classes. One class
is dev-only, recorded in `SPLIT.md` with its reason. Full class coverage in the holdout
arrives at T7.1.

Revisit if: the catalog grows past ~30 and the ~70/30 ratio starts wasting scenarios that
would be worth more as dev-set signal, or if a fifth contamination axis appears (the
likeliest candidate is judge contamination — an LLM judge that has seen the label rubric
during its own prompt tuning).
