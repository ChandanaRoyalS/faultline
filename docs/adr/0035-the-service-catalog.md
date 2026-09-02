# ADR-0035 — the service catalog

**Status:** accepted, 2026-09-01
**Task:** T2.4

## Context

T2.4 asks for *"a git-versioned catalog of the demo's services: owners, tiers, SLOs, runbook
links, declared dependencies — exposed as a dependency-graph API"*. The graph API exists and
is good. `src/faultline/context/catalog.py` exists too, and answers a narrower question well:
whether a service is `present`, `uninstrumented` or `artifact_only` for graph reasoning, with
a measured reason attached to every absence. **The catalog document itself did not exist**, in
any file — found on 2026-09-01 while auditing something else.

The obvious way to write one is to sit down and type owners, tiers and SLO targets. That
produces a document full of numbers with nothing behind them, in a repository that refused a
fifth fault class rather than manufacture one (Q11) and grounded its alert thresholds in a
measured quiet baseline rather than copying a tutorial (ADR-0012).

## Decision

`knowledge/services.yaml`, generated once from sources that already exist, with **every field
traceable to what produced it** — and the one exception marked in the data rather than in
prose.

| Field | Grounded in |
|---|---|
| `name`, `container` | `injector.world.SERVICE_CONTAINERS`, the world's own two naming schemes |
| `kind`, `tier` | a stated role rule — edge / core / async / platform / infrastructure / telemetry / harness |
| `depends_on` | the measured graph in `docs/evidence/t2.4-dependency-graph/` |
| `slo` | the thresholds in `compose/prometheus/alert-rules.yml`, which ADR-0012 set against a measured baseline |
| `runbooks` | empty — the corpus does not exist yet, and Q15 queues it |
| `owner` | **nothing. Synthetic, and prefixed `demo/` so the file says so.** |

**The SLO numbers are not targets someone chose.** They are the thresholds that actually page:
p95 ≤ 250 ms and error ratio ≤ 5%. `tests/test_services.py` parses the alert rules and fails
if either moves without the other, so the catalog cannot promise something the alerting does
not enforce.

**Dependencies are checked in one direction only.** Declared edges must be a subset of
measured ones; the reverse is deliberately not asserted. A span-derived graph holds the edges
exercised during its capture window, so an absent edge means *not seen*, never *not there*.
Checking the other way would demand the catalog declare everything ever measured; checking
this way stops it inventing architecture, which is the failure that matters.

**Owners are the one invented field, and the invention is visible.** This world is a demo
application and its teams do not exist. Every owner is `demo/<something>`, and a test asserts
the prefix — so a reader, and an interviewer, can see at a glance which column is furniture.
The alternative was omitting owners entirely, which would have left a named deliverable
unmet to avoid admitting a limitation.

## Consequences

**The dependency list is thin, and honestly so.** Five services of twenty-six have measured
outbound edges. That is what the snapshot holds, and the catalog does not pad it. Completing
it needs either a longer capture window or hand-declaration against the demo's source, and
the difference between *declared* and *measured* is itself worth reporting once both exist —
it is the same shape as the plan-versus-repo gap this project's audits keep finding.

**Two catalogs now exist and they are not duplicates.** `context/catalog.py` answers *can I
reason about this service in the graph*; `context/services.py` answers *what is this service,
who owns it, what does it promise*. Merging them would put a graph-presence judgement and a
git-versioned document in one object with two lifecycles.

**No digest moves.** `knowledge/` is in no digest input list, and the Dockerfile already ships
it — `tests/test_packaging.py` has asserted that since the migrations change.

T3.1's triage and T3.2's planner are the intended consumers; neither reads it yet.
