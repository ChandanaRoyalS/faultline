# What shipped, in the words an application needs (T5.3)

**Every number here is measured, sourced, and carries what it cannot support.** That is the point of
the document. A bullet that overstates by one word is worse than no bullet, because the whole claim
of this project is that it reports honestly about a system that is easy to report dishonestly about.

Figures are from [`SWEEP-2026-09-06-sweep10.md`](../evals/runs/SWEEP-2026-09-06-sweep10.md) at stamp
`prompts:b6837dd449ca`, world generation `f5bd108f4f70`, unless stated.

---

## The bullets

**Built an open benchmark for LLM incident investigation on the OpenTelemetry demo stack:
17 authored fault scenarios with ground-truth labels, a reversible chaos injector, and a scored
harness that refuses to run when the world is not quiet.** 13 scenarios valid, 4 blocked and kept
with their `INVALID.md` rather than deleted.

**Measured a multi-agent pipeline against a zero-cost heuristic baseline on five scenarios:
the pipeline identified the culprit service 5 of 5 where the baseline names no service at all, at
\$0.72 per investigation.** The trap is that the loudest service is not the broken one —
`frontend` was the entry point on three of the five and was blamed on none.

**Found and reported that the pipeline's own fault-class accuracy is not reproducible at n=1:
the same scenario, at the same prompt digest and world generation, scored correct and then
incorrect four hours apart.** Every published figure in the project was R=1; this was the first
measurement of run-to-run variance, and it is on the front page rather than in a footnote.

**Designed the measurement layer so that the failures are visible: pre-registered predictions
before every sweep, a baseline gate that refuses rather than measures a dirty world, discards
recorded and never deleted, and a contamination model that declares the judge shares a vendor
lineage with the agent under test.** 22 discarded runs of 121 that started, and the discard rate
is published.

**Shipped the platform end to end — alert ingestion, incident correlation, a multi-agent
investigation, and an incident view whose every citation deep-links to the query that actually
ran — deployable behind TLS and a credential for \$6.49/month.**

---

## Two-line version

> Built and benchmarked an incident-investigation agent on a live OpenTelemetry stack: 13 labelled
> fault scenarios, a scored harness with pre-registration and a refusing baseline gate, and a
> multi-agent pipeline that identified the culprit service 5 of 5 against a \$0.00 heuristic
> baseline that scores none. Also measured, and published, the point at which its own fault-class
> accuracy stops being reproducible.

---

## What a bullet here may not say, and why

**Not "state of the art", "production-ready", or any accuracy figure without its denominator.**
n=5, R=1, 0–2 scenarios per fault class, no confidence interval anywhere. The MDE is roughly 28
percentage points at n=10; nothing in this project separates two arms on fault class and nothing
claims to.

**Not "reduces MTTR by X".** The MTTR claim has no measured left-hand side. T4.7's manual-RCA
reference is 0 of 4 attempts, and its design ceiling is a responder who authored every scenario —
a floor on human time produced by the most advantaged possible responder, not a comparison to a
working on-call engineer.

**Not "99% uptime" or any operational claim.** The deployment serves a snapshot and runs no
investigation.

**Not "passes its gates".** `docs/GATES.md` declares G0 only. G5 needs the demo from a clean clone
and a live deployment; the clean-clone rehearsal has never been run, and `docs/RELEASE.md` §3 is the
script for it. **A gate is not passed by the results looking good.**

**Not "benchmarked against 17 scenarios".** 17 authored, 13 valid, and the current world has 35
scored runs across **6** distinct scenarios. The number a reader will check is the last one.

---

## The line that is worth more than any of the bullets

Nine defects in this system were found by running something that had been built, reviewed, merged
and green: an incident view no process served, a Slack notifier linking to a 404, a judge that
silently re-graded 79 manifests, a `CMD` that printed a version string instead of starting a
server, a deployment that joined the developer's database, a scoring axis computed into every
manifest and printed nowhere. **Each was invisible to the test suite and obvious within seconds of
first use.** That is the finding this project would put in front of an interviewer, because it is
the one that generalises past this codebase.
