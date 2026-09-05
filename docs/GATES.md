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
| G2 | one alert → one agent → one persisted, rendered finding | **Declared 2026-09-01** — qualified |
| G3 | end-to-end investigation passes on 3 scenario classes | **Declared 2026-09-02** — qualified |
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

## G2 — declared 2026-09-01

Full condition: *"Inject a fault → alert lands → an agent investigates → a persisted,
rendered finding exists in the database and on screen. […] And the machine must express its
own failure table: every failure-scenario row names a reachable state, property-tested across
all eleven — a state machine validated against a failure table it cannot express is a test
suite validating the wrong artifact."*

The condition has two halves and they were satisfied five weeks apart.

**The investigation half** — `docs/evidence/t3.4-first-investigation/`. Scenario
`shipping-wrong-image` injected onto the live world at 01:39:24Z and reverted at 02:02:00Z.
One incident (`fb7ad21e-1e76-4ef6-9efa-35f45902a029`), 8 episodes across 7 services, triage
over 12 services, one trajectory (`e7739dec-8ad2-453d-9ab7-8fd1f039f435`) of 17 steps and 6
tool calls across 2 planning rounds, a synthesizer verdict, and a narrative rendered by the
scribe. 45,015 tokens, $0.4829. Both the incident and the trajectory are rows in Postgres;
the narrative is committed beside the run output.

**The failure-table half** — `tests/test_orchestrator.py`, landed 2026-09-01. Every row of
the specification's failure-scenario table whose Mitigation or Recovery column names a
lifecycle outcome now maps to a state, and every state is reachable from `OPEN` by
breadth-first search over the transition table. Before today, three rows named states this
repository did not have. See ADR-0016, Addenda 1 and 2.

**The eval track** required by the condition is running: `evals/runs/` holds dated scored
runs from 2026-08-26 onward, and `evals/scenarios/artifacts/` separates dev from holdout.

### Three things this declaration qualifies

**"On screen" is a rendered report, not a UI.** The finding is persisted and rendered — the
scribe's narrative — but it is read as a file, not in an incident timeline. That timeline is
T5.1 and does not exist. The gate is declared on "a persisted, rendered finding exists";
whether a terminal-rendered narrative satisfies "on screen" is a judgement, and it is
recorded here rather than assumed.

**"Across all eleven" is now across fourteen.** The specification names eleven states; this
machine has those eleven plus three its own agent table and failure table argue for
(ADR-0016 Addendum 2). Six of the fourteen have no runtime writer yet — `PROPOSING`,
`AWAITING_APPROVAL`, `EXECUTING`, `REJECTED`, `BUDGET_EXHAUSTED`, `DUPLICATE_MERGED` — so
three failure rows name states that are reachable in the machine and not yet enterable by
running code. The set is asserted in `NO_RUNTIME_WRITER` so it cannot shrink unnoticed.

**The run had no baseline gate.** The evidence README says so itself: the world was degraded
before that injection, the check that found it was manual, and the agent-run path has no
equivalent of T1.5's refusal to record against a dirty world. The repair was applied and the
injection went onto a clean world — but nothing would have stopped it otherwise.

### What Gate 2 does not cover

T2.3's deliverable line reads *"Schema + migrations + tested state machine + report/evidence
archive"*. There are no migrations and no object-storage archive, and no integration tests
against real Postgres and Redis, so `PostgresIncidentStore` is untested. T2.4b delivered one
of its three stores. T2.5's verified self-hosted seam is unbuilt. The gate's condition names
none of these, so they do not block it — they are recorded here so the declaration is not
read as saying Phase 2 is complete.

## G3 — declared 2026-09-02

Full condition: *"The full pipeline — triage, plan, parallel specialists, synthesis, validated
citations, proposal — completes successfully on at least 3 of the 4 fault classes."*

Declared from [`SWEEP-2026-09-02-batch-b.md`](../evals/runs/SWEEP-2026-09-02-batch-b.md), which
was scored against a pre-registration committed before any scenario ran.

**All six stages executed on every scored run**, across all four fault classes. The sixth stage —
the remediation proposer — did not exist before #143 and is why this gate was undeclarable until
Batch B closed.

| reading of *"completes successfully"* | result |
|---|---|
| the pipeline runs to completion | **4 of 4 classes** — zero gated, zero narratives refused, zero bounds exhausted |
| and returns the correct fault class | **3 of 4 classes** — `resource_exhaustion`, `dependency_latency`, `bad_config` |

The stricter reading passes **at exactly the threshold**, which is worth stating rather than
resting on the weaker one: `bad_deploy` completed and was wrong.

### Four things this declaration qualifies

**The sweep is five of the eight runs it registered.** `product-catalog-flag-failure` was injected
and discarded four times when the API returned a credit-balance error at the triage call, and
`shipping-quote-misconfig` and `shipping-wrong-image` never started for the same reason. The gate's
condition is over fault classes rather than scenario count and all four are represented — but this
declaration does not rest on the sweep as registered, and §5 of the sweep document says which
scenarios are unmeasured on this pipeline.

**Two of the sweep's six predictions were falsified**, and neither falsification touches the gate's
condition. `cart-bad-image-tag` returned `dependency_latency` against a `bad_deploy` label, and
triage moved on that same scenario from `0.80 / 0.67` to `1.00 / 0.71` — the blast radius proving
unstable across sweeps even when its seeds are identical, which is a finding the gate does not
assess and Phase 4 should.

**Accuracy is not what this gate measures.** *"Completes successfully"* is a pipeline condition;
accuracy thresholds are Gate 4's and T4.2's. A reader taking 3-of-4 here as an accuracy claim
would be reading a completion gate as a scoring one.

**Nothing here attributes anything to Batch B.** Six changes landed together at `n = 1` per
scenario, and the pre-registration says in its own words that the sweep cannot attribute a
difference to any one of them.

### What Gate 3 does not cover

Phase 3 is **98.2% of its clauses** after Batch C (`docs/PLAN.md`, Phase 3 audit). Two are
undelivered and neither blocks this gate: T3.1's cheap-model routing tier, deferred to T4.2's
measured accuracy, and T3.4's repo-compare, declined as **Q19** because this world runs pulled
images rather than checkouts.

## Known blockers on later gates

Recorded here so they are not rediscovered.

**G4.** Its condition names `make eval` running all ten scenarios unattended. `make eval`
takes one `SCENARIO` per invocation and there is no all-scenarios driver; separately,
`faultline-eval` refuses rather than waits when invoked back to back, so successive calls
are rejected inside seconds. The condition also requires an A/A check declaring null, a
dev-set median time-to-report ≤ 3 minutes and cost ≤ $2 per incident, and the T4.7 baseline
suite — none of which exists yet.

**2026-09-03, the Phase 4 audit.** Every clause of the plan's §7 graded against the tree, now
that both specification documents are in the repository and T7.62's blocking condition is
lifted: **23.5 of 55 clauses delivered, 43%.** This is a completion figure and not a deviation
figure — Phase 4 was never declared, unlike Phase 3. The grading is in `docs/PLAN.md`. What it
adds to the list above: ~~**T4.3 does not measure latency at all**, so this gate's own
*"median time-to-report ≤ 3 minutes"* has no measurement behind it~~ - **closed 2026-09-03**: the
panel records wall-clock latency per run and compares it to the 3-minute threshold, though the
gate's condition is the **dev-set median** and a median needs a catalog, so the gate still waits
on runs; **there is no eval database**
— every `CREATE TABLE` in the tree is a platform table and eval runs persist as JSON manifests,
so T4.4's comparison generator has nothing to read and `evals/reports/` is empty; **T4.5 is
entirely absent** — one workflow file, three jobs, no eval smoke and no `schedule:`; and
**T4.1b's exclusion filter is asked to fire but never checked** — the SQL removes rows and counts
nothing, so a run where the filter matched nothing is indistinguishable from one where it worked.
The plan's own words on that last one: *"silent non-enforcement is how this defect returns."*

**2026-09-04, G4's latency clause and T4.5's runner, both measured.** Dev sweep 9 timed five
runs against the gate's own three-minute bar: **273s, 165s, 237s, 279s, 183s — four of five over
it**, and the one inside it is the run that died before synthesis. The gate's condition is the
dev-set median, and the median of those five is 237s. **G4's latency clause is failing, not
merely unmeasured**, and it is the first time this document can say which.

The same day, **T4.5's CI smoke was run for the first time** and the reason it cannot pass is now
a captured log rather than an assumption. The key was funded and set; that condition cleared. The
world then booted fifteen services clean on `ubuntu-latest` — the arm64 override was not the
obstacle — and **kafka's JVM threw `NullPointerException` in
`jdk.internal.platform.cgroupv2.CgroupV2Subsystem.getInstance`**, a 2022-vintage JDK failing to
parse the runner's cgroup v2 layout. Every dependant refused. The runner had 13.7 GB free of
15.9, 74 GB of disk and 4 cores, so this is not resource pressure.

**Of the two conditions this document has listed for a year — "a world running in Actions" and
"a key with credit" — it was the world, and the obstacle is one image's JDK.** Every route past
it moves `compose_digest` and re-founds the world, which is the most expensive action available
to this project; `docs/PLAN.md`'s T4.5 section prices the four routes and takes none of them.
**T4.5's check is built, correct, and blocked on the runner for a stated reason.**

**G5.** Its condition requires the full demo from a clean clone. T7.48 rebuilt the world
but reused local images and said so; no cold clone-and-pull has ever been run, and the demo
has never been executed from one. **2026-09-01 — the first measured evidence
of what that costs.** T2.3's integration tests built a Postgres schema from nothing, which
had never happened before, and `create_schema()` raised `UndefinedTable`. A clean-clone run
of the demo would have hit it immediately. It was fixed the same hour; the point that
survives is that this class of defect is invisible to every path except the one this gate
names, and that path is still not run.
