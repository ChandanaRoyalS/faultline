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
