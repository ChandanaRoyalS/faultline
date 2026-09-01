# Gates

`CLAUDE.md` rule 4: *"Gates are hard — a task is done when its gate condition passes from
a clean clone."* Until 2026-09-01 nothing in this repository recorded whether any gate had
ever passed, so the rule was enforced by memory. This file is that record.

A gate is **declared** only when its condition has been observed, from a clean clone, with
the evidence written down here. "Not declared" does not mean failed — it means nobody has
checked, or a known blocker stands in the way.

Conditions below are transcribed from `docs/spec/execution-plan-rev9.pdf` §1. That PDF is
authoritative; verify wording against it before relying on it.

| Gate | Condition (§1) | Status |
|---|---|---|
| G0 | CI green on an empty walking skeleton | **Declared 2026-09-01** |
| G1 | injected fault → alert fires → visible on dashboards, zero AI | **Declared 2026-08-23** |
| G2 | one alert → one agent → one persisted, rendered finding | Not declared |
| G3 | end-to-end investigation passes on 3 scenario classes | Not declared |
| G4 | one command runs and scores all 10 scenarios into a report | Not declared — blocked |
| G5 | full demo runs from clean clone; MVP tagged | Not declared — unverified |
| G6 | approval-gated remediation works; injection + storm tests pass | Not declared |
| G7 | repo + video + benchmark and ablation reports are application-ready | Not declared |

## G0 — declared 2026-09-01

Full condition: *"CI is green on the walking skeleton; a clean clone brings up an (empty)
platform with one command."*

Tested by cloning `https://github.com/ChandanaRoyalS/faultline.git` into an empty directory
and running the documented commands, with the working copy's platform brought down first so
the fixed ports (5432, 6379) were free.

- `make up` — one command. Both services reached `Up (healthy)`: `pgvector/pgvector:pg16`
  and `redis:7-alpine`.
- `uv sync` from cold — 46 packages, CPython 3.12.14, no manual step beyond what the
  README's prerequisites list.
- `make check` — ruff, `ruff format --check`, `mypy --strict`, pytest: **565 passed,
  5 skipped**.
- CI green on `main` at the commit tested.

**One thing the evidence qualifies.** A clean clone runs 565 tests where a developer's
working copy runs 569. The five skips are correct and each states its own reason: four
depend on `world/`, which is gitignored because it is a pinned clone of somebody else's
repository (ADR-0026), and one needs `FAULTLINE_GRAPH_DRIFT_URL` for a live drift check.
So "green from a clean clone" is true, and it tests slightly less than a local run does.
That is a property of the world being external, not a gap in the suite.

## G1 — declared 2026-08-23

Full condition: *"Run one injector command → the right alert fires → the failure is visible
on the Grafana dashboard. All deterministic, all yours, no AI anywhere yet."*

Evidence: `docs/evidence/gate-1/` — a dated README, a timing table, and three screenshots.
Fault `flag-service-bad-deploy` (class `bad_deploy`, target `featureflagservice`), injected
by one injector command, with no model call anywhere in the loop.

| Event | Time (UTC) | Delta |
|---|---|---|
| injected | 00:50:48 | — |
| alert condition first true | 00:51:15 | +27s |
| alert FIRING | 00:53:15 | +2m27s |
| reverted | 01:14:23 | — |
| alert cleared | ~01:16 | — |

Detection latency splits cleanly into 27s of real signal propagation (span → spanmetrics →
scrape) and the rule's deliberate 2m `for` guard. One fault produced four firing alerts —
recommendationservice 66.7%, frontend 9.7%, loadgenerator 9.7%, productcatalogservice 8.1%
— which is the alert-storm-to-one-incident case T2.1's fingerprint dedupe was built for.

**Two things this declaration qualifies.**

The scenario used now carries `blocked: true`. It was blocked because `featureflagservice`
emits no span metrics, so two of the three alert rules cannot evaluate for it and no fault
targeting it can page on its own behalf — which makes it unfit for a holdout slot. That
does not retract what Gate 1 observed: the alerts recorded here fired on its *callers*, the
cascade is real, and ADR-0006 measured it independently. The scenario file says as much in
its own blocking note.

The dashboard in the evidence is the OpenTelemetry demo's own Grafana, not a Faultline
dashboard. The gate's condition says "visible on the Grafana dashboard" and that is
satisfied — but T1.2's deliverable names a "shop health" overview dashboard that does not
exist in this repository. The gate is declared on its own wording; T1.2 remains
incompletely delivered until that dashboard is built.

## Known blockers on later gates

Recorded here so they are not rediscovered.

**G4.** Its condition names `make eval` running all ten scenarios unattended. `make eval`
takes one `SCENARIO` per invocation and there is no all-scenarios driver; separately,
`faultline-eval` refuses rather than waits when invoked back to back, so successive calls
are rejected inside seconds. The condition also requires an A/A check declaring null, a
dev-set median time-to-report ≤ 3 minutes and cost ≤ $2 per incident, and the T4.7 baseline
suite — none of which exists yet.

**G5.** Its condition requires the full demo from a clean clone. T7.48 rebuilt the world
but reused local images and said so; no cold clone-and-pull has ever been run, and the demo
has never been executed from one.
