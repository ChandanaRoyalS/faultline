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

## Addendum 2 (T6.4, 2026-09-12): the original fifteen were read against Addendum 1, and six failed

Addendum 1 was written to govern documents not yet authored. Applying it to the fifteen that
already existed was not part of that task and should have been: they were accepted under the
rule Addendum 1 replaced, so nothing had ever read them against the sharpened one.

An independent sweep found **six failing materially**, a seventh in one section, and three with a
framing problem this ADR caused (it first said four; see below).
`docs/evidence/t6.4-runbook-review/ORIGINAL-FIFTEEN.md` records each with the source it collides
with. Two facts make this heavier than the batch Addendum 1 was
written about:

- **They are seeded.** 167 of 537 recorded run manifests carry all fifteen at one corpus hash.
  The removed batch's write-up could say *no measurement is affected*; that sentence is not
  available here.
- **Two of the offending sentences were also false of this world.** `class-dependency-latency`
  and `alert-high-latency` both said the callee's own p95 stays flat under a delay, and every
  recorded `dependency_latency` measurement in this catalog has the shaped service's own p95
  move. The corpus was handing over a discriminator *and* the wrong one.

### The framing question this ADR left open, decided

§Decision puts *"fault classes and the remediation class each resolves by"* in bounds, and
Addendum 1 puts *"a property of the catalog rather than of the world"* out of them. Three
documents sat in the gap, stating a true mapping as a census of the answer key — *"every
`resource_exhaustion` scenario carries `expected_remediation_class: config_revert"*. (The sweep
first listed four; `action-restart-service` was grouped wrongly and never carried a census
sentence. It says *"That is the whole mechanism"*, which is the framing the other three were
moved to.)

**The fact is in bounds and the census framing is not.** A runbook says what the mechanism is and
what undoes it — *the squeeze is a limit applied to the container, so restoring the
configuration removes it* — because that is true of the world and would be true if the catalog
were empty. Counting labels in the catalog is a claim about the answer key, and it is also the
weaker statement: it tells a reader what the scoring expects rather than why.

### What did not change

Five documents were not touched — `action-rollback-image`, `action-restart-service`,
`world-saturation-is-invisible`, `world-tracing-artifact-edges` and `world-warm-up-latency` as
edited earlier the same day. Each states a property of the world or of the instrument and none
tells a reader what a shape of evidence means; they are the model the other ten were repaired
towards.

**The repair was not only deletion, and saying so matters.** Ten documents lost a sentence and
**all ten gained new factual claims** — what a rule actually reads, what the `dependency_latency`
mechanism does and does not do to its target, the measured band a memory squeeze has to fit in.
That new prose is unreviewed material of exactly the kind this ADR exists to govern, so it went
through three review rounds of its own, returning **nine blocking findings: four in replacement
prose, three in the write-ups, one on the removal side, one in text the repair never touched.**
Not one was in a deletion. **No document lost the world fact it exists to carry**, and that claim
was checked document by document rather than asserted.

The generalisable lesson is not about runbooks, and it is not the narrow one this paragraph first
drew. **Deleting a sentence was safe every time. Everything written around the deletion was not**,
and that includes the record: a third of the findings were in the write-up rather than in the
corpus, and one was in a sentence nobody edited, which a change elsewhere turned false. So: review
replacement prose as new authoring, review the write-up as new authoring too, and when a change
makes a claim somewhere else stale, go and read what you did not touch.
