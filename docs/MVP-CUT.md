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

**Measured a multi-agent pipeline against a zero-cost heuristic baseline on ten scenarios:
the pipeline identified the culprit service 24 of 26 where the baseline names no service at all, at
about \$0.70 per investigation.** The trap is that the loudest service is not the broken one —
`frontend` was the triage entry point on five of the ten and was blamed on none. **Both misses are
structural and named as such**: their targets are a service that emits no telemetry and a datastore
the dependency graph has no node for, so no blast radius could contain either.

**Found and reported that the pipeline's own fault-class accuracy is not reproducible at n=1:
the same scenario, at the same prompt digest and world generation, scored correct and then
incorrect four hours apart.** Every published figure in the project was R=1; this was the first
measurement of run-to-run variance, and it is on the front page rather than in a footnote.

**Designed the measurement layer so that the failures are visible: pre-registered predictions
before every sweep, a baseline gate that refuses rather than measures a dirty world, discards
recorded and never deleted, and a contamination model that declares the judge shares a vendor
lineage with the agent under test.** 22 discarded runs of 147 that injected a fault, 87 refused by
the gate before injecting anything, 10 paused — every one recorded, and the discard rate is
published. *(Counts by `evalharness.evaldb.outcome_of` over `evals/runs/` on 2026-09-07, demos
excluded.)*

**Shipped the platform end to end — alert ingestion, incident correlation, a multi-agent
investigation, and an incident view whose every citation deep-links to the query that actually
ran — and deployed it: one VM, TLS and a credential at the edge, the receiver off the internet, and
an orchestrator that opened and investigated a real incident on its own, on the public URL.**
\$44/month month-to-month, which is the price of the machine the monitored world needs, not of this
platform; the \$6.49 figure quoted before deployment was for the platform alone, and the platform
alone investigates nothing.

**Remediation is proposed, never executed, and the proposal is shown with its risk note.** Every
investigation ends in a proposal — action from an allowlist, target service, expected effect, how
long to wait, what would falsify it, risk and blast radius — validated against the allowlist and
rendered on the incident screen with the line that says it was not run. There is no executor. The
approval plane that would act on a proposal is designed ([ADR-0028](adr/0028-the-proposer-and-the-action-plane.md))
and is Gate 6's to build; nothing in this cut claims the second half of that sentence.

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

**Not "99% uptime" or any operational claim.** One VM, no replicas, no backups beyond a manual
snapshot, a fifteen-minute uptime check that emails rather than pages, and a month-to-month contract
that ends on 2026-10-07 unless renewed. The deployment investigates — one incident, once, watched —
and that is the whole of its operational record.

**Not "passes its gates".** `docs/GATES.md` declares G0–G3 and G5, each with its qualification
written beside it; G4 is blocked on a latency clause that is failing and says so; G6 and G7 are not
declared. G5's qualifications are written under its declaration: fourteen defects stood between the
rehearsal's first command and the declaration; the fresh machine was an x86 VM whose figures can never
be compared with the published ones; and the video's take was chosen by its outcome from three.
**A gate is not passed by the results looking good.**

**Not "benchmarked against 17 scenarios".** 17 authored, 13 valid, and at the stamp this repository
ships the pipeline has been measured on **10** of them — every dev scenario, 26 runs, R=1 each
(README, *Results at a glance*). **The three holdout scenarios have no run at this stamp and will
not get one**: the set has been entered three times and a fourth entry is blocked by ADR-0029. So
the honest sentence is *ten dev scenarios at R=1, no current holdout figure at all*, and the number
a reader will check is the R.

---

## The line that is worth more than any of the bullets

Thirty-four defects in this system were found by running something that had been built, reviewed,
merged and green (`docs/PLAN.md`, findings one to thirty-four): an incident view no process served, a
Slack notifier linking to a 404, a judge that silently re-graded 79 manifests, a `CMD` that printed a
version string instead of starting a server, a deployment that joined the developer's database, a
scoring axis computed into every manifest and printed nowhere, a `make up` that returned before
Postgres could accept a connection, a hostname that exists only on Docker Desktop, a credential that
Caddy checked and then forwarded to Grafana as a failed login, a deployment that remembered incidents
and investigated none, a demo that narrated *"Class of fix: None"* over a verdict that named one, a sweep catalog that listed
fifteen scenarios where thirteen exist.
**Each was invisible to the test suite and obvious within seconds of first use.** Thirty-one are fixed;
two are recorded and not fixed because the fix would move the world generation under published
figures (nineteen, twenty); one is queued behind the same digest (thirty-two, Q26). That
is the finding this project would put in front of an interviewer, because it is the one that
generalises past this codebase.
