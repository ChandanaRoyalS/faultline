# ADR-0009: One recorded bundle per rehearsal, with the narrative written blind

- **Status:** accepted
- **Date:** 2026-08-23

## Context

T1.5 rehearses ten scenarios by hand. Each rehearsal produces evidence, and that evidence
has two consumers that pull in opposite directions.

T2.4b seeds the past-incident store from these rehearsals, so part of the output must be
prose an agent can retrieve and reason over. T4.2 scores runs against them, and T5.3
records a demo from them, so another part must be raw, timestamped, re-queryable data.

Left unspecified, ten hand-run rehearsals produce ten differently-shaped piles — some with
screenshots, some with pasted terminal output, some with nothing but memory. Building a
retrieval corpus out of that later means redoing the rehearsals, and rehearsals are the
most expensive manual step in the whole plan.

There is also a subtler failure available. Because we inject the faults, every narrative is
written by someone who already knows the answer. A write-up that opens with the root cause
is not an incident report; it is an answer key. Seeded into retrieval, it teaches the agent
to look up rather than diagnose — and the leak is invisible in the scores, because the
scores go up.

## Decision

One bundle per rehearsal, at `evals/scenarios/artifacts/<split>/<id>/`, with a fixed
shape: `manifest.json`, `incident.md`, `queries.md`, `metrics/*.json`, `logs/*.txt`. The
format is specified in `evals/scenarios/ARTIFACTS.md`.

Everything mechanical is recorded by `evalharness.rehearse`, which drives the injector
through its CLI, polls Prometheus for the alert transition, holds a steady-state window,
reverts, and captures the metric range. Using the CLI rather than the injector's internals
is deliberate: T4.1's harness is specified to work through public interfaces only, and this
recorder is its ancestor.

`incident.md` is hand-written, under two rules that the format enforces socially and the
tests enforce mechanically where they can:

1. **Written from the responder's chair.** Observed symptoms first; root cause only in its
   own section, at the end. No mention of the injector, the scenario id, or the fault class
   anywhere in the prose.
2. **Dead ends preserved.** The checks that led nowhere stay in the document. They are what
   makes a retrieved incident read as experience rather than as a solution manual.

`rehearsed: true` in a scenario YAML is a claim that a complete bundle exists. The guard
tests treat it as one: a rehearsed scenario must have a bundle, and its `incident.md` must
have no template comments left unfilled.

## Consequences

Easier: the corpus at T2.4b is assembled rather than authored, every accuracy claim traces
back to a re-runnable query, and the demo at T5.3 has real captured incidents to draw on.
The recorder also removes the two mistakes hand-running invites — forgetting to note the
inject timestamp, and reverting before the metric window is long enough to be readable.

Harder: rehearsal is now a fifteen-minute commitment per scenario rather than a five-minute
one, and the narrative discipline is genuinely difficult — writing blind about a fault you
designed takes real effort, and there is no test that can prove you did it honestly.

Accepted risk: rule 1 is unenforceable by machine. A narrative that leaks the answer in its
opening paragraph passes every test. The mitigation is that the leak is visible on reading,
and the bundles are in the repo where a reviewer — or an interviewer — can check.

Revisit if: T4.1's harness needs fields the manifest does not carry, or the corpus turns
out to want a different granularity than one document per incident (for example, one per
hypothesis rather than one per incident).
