# ADR-0036 — what may be written in a runbook

**Status:** accepted, 2026-09-01
**Task:** T2.4b (the first of its three deliverables)

## Context

T2.4b asks for *"~15 runbooks"*. An audit on 2026-09-01 found the corpus held seven documents
and every one was a scenario narrative: **not one carried `origin: authored`**, and no runbook
existed anywhere in the tree. The count had made the gap hard to see — seven against "~15"
reads as a shortfall, when in fact the seven are the *past-incident store*, a different
deliverable on the same line.

Two later tasks depend on authored documents existing. T3.9's proposer is specified to consume
runbooks. And T4.1b turns on the rule that *"hand-authored runbooks stay `authored` and are
never excluded — they're legitimate institutional knowledge"*: with no authored document, that
branch of the exclusion filter cannot be exercised by any live run.

## The problem that exemption creates

ADR-0008's second axis excludes a scenario's own rehearsal from its retrieval. Runbooks are
deliberately outside that filter. **So anything written in a runbook reaches every scored run,
forever, through the one channel the quarantine does not check.** A runbook containing a
holdout scenario's root cause would not be caught by the split, by `exclude_origin`, or by any
existing test — it would simply make that scenario easier, permanently and invisibly.

This is not hypothetical carelessness. Two of the fifteen runbooks were drafted citing *"Gate 1
recorded…"*, and Gate 1's fault was `flag-service-bad-deploy`, a holdout scenario. Neither
named it, so an id-matching test would have passed. Both were rewritten before landing.

## Decision

**A runbook may say what is true of the world. It may not name a scenario.**

Alert rules and their thresholds, fault classes and the remediation class each resolves by,
allowlist actions and their preconditions, measured limits of this world — all of these are
institutional knowledge and belong here. A specific incident, its origin service, or its root
cause does not, whichever split it sits in.

**The rule covers dev scenarios too, not only holdout.** The dev/holdout line is the wrong
place to draw this one: a runbook written around a dev scenario is a template for writing one
around a holdout scenario, and the discipline is easier to keep when there is no exception to
reason about.

`tests/test_runbooks.py` enforces it mechanically against every scenario id in the catalog, so
the boundary survives an author who has not read this ADR.

## Consequences

Fifteen runbooks: three keyed to the alert rules that page, four to the fault classes the
injector produces, four to the allowlist actions, and four to properties of this world that
change how a signal should be read — no saturation signal (ADR-0024), an uninstrumented
service that cannot page on its own behalf (ADR-0006), dependency edges that are tracing
artifacts (ADR-0017), and a warm-up window in which a p95 is not a baseline (ADR-0012).

Two of them carry facts that are counter-intuitive and that the catalog's labels settle:
`resource_exhaustion` resolves by **config revert**, not restart, because the squeeze is a
limit applied to the container; `dependency_latency` resolves by **restart**, not config
revert, because the delay lives in the container's network namespace. An invented runbook would
have got both backwards.

**They are inert until seeded.** Writing the files moves no digest; putting them in
`incident_chunks` moves `corpus_state()` and re-founds comparability for every scored run. Q15
now covers only the seeding, which is one command rather than a project.

Two services carry a runbook link in `knowledge/services.yaml` — the two with a measured
property that changes how they are read. The rest link nothing, because a link that exists to
look complete is a link a proposer will follow to no purpose.

## Addendum 1 (T6.4, 2026-09-12): the rule was not tight enough, and five documents proved it

The rule above forbids **naming** a scenario, its origin service or its root cause. T6.4's first
five service runbooks named none of those and were contaminated anyway. Two of them jointly
carried the discriminator that separates a pair of dev scenarios; a third carried a holdout
scenario's method *and* the service it converges on. `docs/evidence/t6.4-runbook-review/REVIEW.md`
quotes all of it against the scenario files.

The gap is that a scenario's identity is not the thing worth protecting. **What the scenarios
score is the discrimination step** — the reader is given a set of signals consistent with more
than one cause and has to decide which. A runbook that hands over that decision has given away
the answer without using a single word from the answer key.

**The sharpened rule: a runbook may state what is true of the world. It may not state how to tell
two possible candidate causes apart.**

- *In*: what a service does, who calls it and whom it calls, what it emits, whether an alert rule
  can fire for it at all, what a threshold is, what an action's preconditions are, what this
  world has been measured to do.
- *Out*: "if X and not Y, look here"; "the question that distinguishes these two is…"; any
  statement of which cause a given shape of evidence points to; and any prior over how often a
  service turns out to be at fault, which is a property of the catalog rather than of the world.

The test is not whether the sentence is true — all of the removed ones were — but whether a
reader who had it would skip a step an investigation is supposed to perform.

**This is a review rule, not a test rule, and pretending otherwise is what went wrong.** All nine
mechanical guards in `tests/test_runbooks.py` passed on all five removed documents, including the
scenario-name check added in the same PR. The guards catch the spelling of a scenario id; nothing
mechanical catches a paraphrase of a method. So the control is a human one and it has a shape:
**the per-document review happens before merge, and is performed by a reader who did not write
the document.** The author's own review passed all five.

**Revisit if** a mechanical check for this ever becomes plausible, or if the service runbooks'
factual half is generated from `knowledge/services.yaml` and `EDGE_KINDS` rather than written by
hand — six of the errors in the removed batch were restatements of catalog facts that the catalog
could have supplied.
