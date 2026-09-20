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
| G4 | one command runs and scores all 10 scenarios into a report | Not declared — **assessed 2026-09-20**, latency failing and two baselines never run |
| G5 | full demo runs from clean clone; MVP tagged | **Declared 2026-09-07** — qualified |
| G6 | approval-gated remediation works; injection + storm tests pass | Not declared — **assessed 2026-09-20**, one clause failing and one undefined |
| G7 | repo + video + benchmark and ablation reports are application-ready | Not declared — **assessed 2026-09-20**, the front door and the video are behind the product |

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

## G4 — assessed 2026-09-20, not declared

Full condition, as the blocker below transcribes it (the table row abbreviates): *"one command runs
and scores all 10 scenarios into a report"*, and *"an A/A check declaring null, a dev-set median
time-to-report ≤ 3 minutes and cost ≤ \$2 per incident, and the T4.7 baseline suite."*

**Read because G6 inherits from here and could not be declared without it.** G6's fourth clause asks
for *"the Gate 4 thresholds … re-asserted"*, which presupposes an assertion this gate never made.
The blocker paragraph below dates from before `faultline-sweep`, before the A/A check, and before
T4.7 closed: **three of the five things it names are done.** What it was right about is latency, and
the reading adds one blocker it did not name.

### Met — the driver, and both halves of the sentence that said there wasn't one

*"`make eval` takes one `SCENARIO` per invocation and there is no all-scenarios driver"* is false.
`make eval` with no `SCENARIO` runs `faultline-sweep` over the catalog (`Makefile`), and
`sweep.runnable()` returns **exactly the ten dev scenarios** — eighteen files less five holdout,
five blocked, and the two dev bundles carrying an `INVALID.md`. The Makefile names the blocker it
closed: *"It used to refuse without SCENARIO, so the command the gate names could only ever run one
scenario and the gate could not be met by the thing it named."*

*"`faultline-eval` refuses rather than waits when invoked back to back"* is also false, and the fix
is the interesting half: `SETTLE_SECONDS = 300` between runs, because *"every scored run leaves a
resolved incident, and a firing inside the orchestrator's 300 s settle window **reopens that
incident rather than opening a new one** — so the next scenario's alerts would be attributed to the
previous scenario. The first real sweep scored 1 of 5 and the gate refused the other four for
exactly this."* Beside it: `--retries` re-launching clearable refusals (*"a refusal means nothing
was injected … so this is not a re-run"*), a world recycle between passes, and an abort once a
catalog's worth of runs has stood refused.

**One qualification on *unattended*.** The code runs ten scenarios from one command; dev sweep 12
took four nights, and its §7 is a table of the eight things that stopped it — gate refusals at
kafka 24 %, a run frozen for 1 h 50 m, credit exhaustion after the first pass. *Unattended* has held
for a pass, not for a sweep.

### Met, with the record's own caveat — the A/A check declares null

`faultline-compare --aa ca4f1d837d2b` split arm A's runs alternately within each scenario and
compared the halves: every proportion under the 16.2 pp MDE, the largest **fault class at +10 pp
with an interval touching zero**, cost −\$0.03, latency +4.6 s. **Nothing moved.** The check first
printed `FAILED on 2 metric(s)` against data that had passed — `aa.Result.passed` required the
phrase *"no measurable effect"* in every verdict, and the two non-proportion metrics answered with a
sentence that could never contain it. Fixed the same day; re-run clean.

The caveats belong to the gate and are the module's own: at n = 10 the MDE is 16 pp, so a pass is
weak evidence, and `aa.py` says outright that *"a test that nearly always passes is not much of a
test, and a green A/A check should not be read as 'the harness is sound'."* The number worth
reading is the one the instrument produced between two halves of one configuration — **10 pp,
half the effect the sweep reports between its two arms.**

### Met — cost

Median **\$0.713** with traces and **\$0.602** without, against \$2 (sweep 12). `Budget.max_usd`
now defaults to this gate's \$2 per Q16, so a run that would breach it halts rather than reports it.

### Partly met — *"…into a report"*

One command runs the ten; **four commands score them into a report.** `faultline-sweep` writes no
file: it prints a count of outcomes, and says so — *"it does not judge, and it does not aggregate."*
Per-run artifacts land in `evals/runs/<ts>-<scenario>/`. The report the clause means is
`faultline-compare`'s `COMPARISON-<a>-vs-<b>.md`, which needs `faultline-judge` and
`faultline-eval-db load` in front of it. **`evals/reports/` is empty by design, not by defect** —
it is gitignored, and sweep 12 states the policy: *"Comparison reports are regenerated rather than
committed."* The chain exists end to end in `eval-nightly.yml`, whose `schedule:` was removed by
the owner on 2026-09-11. So the artifact exists, the pipeline exists, and *one command* does not
reach it from a terminal.

### Not met — latency

Median **251.6 s** with traces, **214.4 s** without, against **180 s** (sweep 12). Failing, not
unmeasured, and measured more than once: dev sweep 9 timed 273 s, 165 s, 237 s, 279 s, 183 s —
four of five over, median 237 s. **This is the clause G6 inherits**, and the arm both gates care
about is the one that misses by 71.6 s.

### Not met — the T4.7 baseline suite has never been run

All three baselines are **built**: `b0` (no-LLM heuristic), `b1` (one agent, four tools, no
fan-out), `b2` (the model's prior, no tools), all wired into `faultline-eval --baseline` and
`faultline-sweep --baseline`, with `BaselinePanel` refusing to exist unless it carries an entry for
every one — *"an unrun baseline is a row that says so, never an absent row."*

**Built is not run.** Across the whole run tree: **42 `b0` manifests, zero `b1`, zero `b2`.** And
the 42 are `b0` version 2, which **Q34 superseded on 2026-09-14** after finding B0's third signal
had never executed — *"`Signals.error_deltas` said 'frequently empty, and that is real': it was
always empty and it was not real"* — leaving the record's own note that *"B0.3 has no runs; the
next baseline comparison quoting B0 as a control needs them."* So the headline table cannot today
carry the three baselines the brief makes mandatory, and the one column it does carry is a
two-signal baseline under a retired version. The reason is recorded and is not a defect: *"B1 and
B2 runs need credits"*, *"out of scope for this sweep as a budget decision."*

### And the stamp has moved under all of it

Every number above comes from dev sweep 12, 2026-09-11, stamp `prompts:06f24e827915`.
**Self-instrumentation landed 2026-09-18 and no dev sweep has run since** — the same gap that
stops G6's fourth clause having the measurement it names. Whatever is declared here would be
declared against a pipeline the repository no longer runs.

### What it would take

1. **One sweep at the current stamp with all three baselines.** It is the same sweep G6's clause 4
   needs, and running it once satisfies the baseline clause here and the measurement there. B2 is
   cheap (no tools); B0 needs re-running at version 3 regardless.
2. **A median under 180 s.** The only clause that fails on its own terms rather than for want of a
   run, and the one both gates share. Sweep 12's full-pipeline arm is 251.6 s.
3. **A terminal path from one command to a scored report**, or the clause read as *one command runs
   them* and the scoring chain acknowledged as three more. The record should pick one rather than
   leave the sentence ambiguous.

**Three of the five things the blocker below names are done, and it has said otherwise since
2026-09-03.** What actually stands between this gate and a declaration is one failing number and
two baselines nobody has paid for.

## G5 — declared 2026-09-07

Full condition: *"full demo runs from clean clone; MVP tagged."* `docs/PLAN.md`'s Phase 5 reads the
first clause as two halves — the demo from a clean clone **on a fresh machine**, and T5.5's live
deployment — and both are demonstrated. The second clause is `v0.1`, tagged on the commit that carries
this declaration (`docs/RELEASE.md` §4).

**The fresh machine (T5.4c).** An x86 VM with nothing of this project on it — IONOS, Ubuntu 24.04,
Docker Engine — cloned `main`, and every item in `docs/RELEASE.md` §3 was executed there: `make
install` from the lock, `make check` before any service (1296 passed), `make world-up` pulling every
image cold in 1m12s, `make up`/migrate/seed, both servers, **three `make demo` runs** (an abstention
naming the right service, a correct `bad_config`, and a third whose citations were the first in this
project to be clicked into Grafana from a browser that was not the author's), a scored run that the
harness itself announced as a new comparability generation (`f5bd108f4f70@Linux/x86_64`), and `make
ui` through a tunnel. Two `no-alert` discards were recorded and kept — one because the alert path had
never worked on Linux (defect eighteen), one because the memory-squeeze scenarios cannot bite on
native x86 (twenty).

**The live deployment (T5.5c).** `https://faultline.chandanasorakundla.com`, from CI's image by sha,
over a Let's Encrypt certificate, with `/api/v1/incidents` 401, `/api/v1/alerts` 404 and `/grafana/`
401 from outside and the demo's dozen host ports verified blocked from another machine. Then the part
that makes it a deployment rather than a display: a fault injected against the world it watches
produced alerts that crossed the compose network into the deployed receiver, the orchestrator opened
and admitted an incident, and — after defect twenty-nine gave the product the runner it had never
had — **investigated it inside the container that holds the key**, to a `bad_config` /
`config_revert` verdict at low confidence with its open questions stated, in production retrieval
mode. The public page rendered it, and a citation on it was clicked into Grafana over the public URL
(after thirty-one). The uptime check polls it from GitHub every fifteen minutes.

**The video (T5.3).** Four minutes, attached to the release: a `make demo` on the reference platform
that returned `bad_config` at high confidence, the incident screen, the live deployment, the table.
`docs/demo/README.md` records the two takes it replaced and why.

### Three things this declaration qualifies

1. **Fourteen defects — eighteen through thirty-one — stood between the rehearsal's first command
   and this line**, every one in a file that was green, merged and reviewed, every one found by
   running the documented procedure on the machine it was written for, nine of them in the deployment
   files alone. Two are recorded and not fixed because fixing them moves a world generation (nineteen,
   twenty); a third, thirty-two, is queued for the same reason. The count is the finding.
2. **The x86 VM is a different world and the record says so.** Its scored run sits in generation
   `f5bd108f4f70@Linux/x86_64`, not the Mac's; two of the catalog's scenarios are no-ops there. The
   gate's *"clean clone"* was demonstrated on a machine whose figures can never be compared with the
   published ones, which is exactly why the platform is now part of the world key.
3. **The video's take was chosen by its outcome from three.** The infrastructure was fixed before it,
   not the agent, and demo runs never enter a figure — but a reader of the video should know the
   record on that scenario is roughly two correct in three, and `docs/demo/README.md` says so.

### What Gate 5 does not cover

G4 is still not declared and its latency clause is still failing; G5 says nothing about it. The
deployment investigates but does not remediate — the action plane has no task number, and remediation
stays a proposal with a risk note, which is what the MVP cut promised.

## G6 — assessed 2026-09-20, not declared

Full condition: *"an approved remediation executes and recovers the system; injection and storm
scenarios pass; the platform's own traces are on the dashboard; and the Gate 4 thresholds are
re-asserted with the full pipeline — four specialists, retrieval, rerank, and self-instrumentation
included — still holding median time-to-report ≤ 3 minutes and ≤ \$2 per incident on the dev set."*

**Read now because everything it was waiting for has landed.** The blocker entry below was written
when *"nothing in the first three clauses existed: no executor, zero injection scenarios, no storm
test, no platform traces."* All four of those arrived between 2026-09-11 and 2026-09-20. This is
the first reading of the gate since, and it is **not a declaration**: one clause fails on a measured
number, and one cannot be declared either way because nobody ever wrote down what passing it would
mean.

### Clause 1 — an approved remediation executes and recovers the system. **Met on the reference platform. On the deployment an approved remediation has executed and none has recovered anything.**

The repair replay, 2026-09-11 ([`REPLAY-2026-09-11-t6.2.md`](../evals/runs/REPLAY-2026-09-11-t6.2.md),
`docs/evidence/t6.2-repair-replay/`): dev sweep 12 arm A's nine distinct (scenario, action, target)
proposals, each executed once against a fresh injection, about two and a quarter hours of world
time, **\$0.00 of model spend** — no model is called anywhere in the path, which is the point of
measuring the executor rather than the agent. **Seven recovered of eight executed, one refused,
zero errors**; the record quotes both that and the pre-fix 6-of-7, because `cart-bad-image-tag`
was re-attempted after an executor defect and the first count is not overwritten.

**Recovery was verified twice per run and not asserted**: alerts cleared inside the scenario's
window *and* the injector reporting nothing left in force. Clearance times 30 s to 150 s against
windows of 180 s to 600 s. The one executed failure is recorded as one —
`redis-cart-dependency-latency`, `restart_service` → cartservice, *"alerts still firing after 180s;
fault still in force"*. Human approval is in the artifacts: every `approval.json` carries
`caller: chandana (repair replay)`, minted at a terminal.

The live proof, `shipping-wrong-image`, recovered on three of its four attempts — the second
crashed on a *correct* state-machine refusal, and the fourth fired all three of ADR-0038 §5's
safety refusals in the second after executing (*already spent*, `kill_switch`, *target outside the
incident's scope*).

**What the deployment has, and has not.** One approved execution, 2026-09-18:
`restart_service` → cartservice on `cart-redis-misconfig`, through the API route after an operator
rejection, exit 0 in 780 ms, audit `bbaee750`. Its own note's closing line is the qualification
this clause needs — *"Not shown: an action that fixed anything - the restart did not."* The alerts
cleared ten minutes later when `stop --all` removed the override. So **the clause is met where it
was measured and the deployment has never demonstrated the recovery half.**

### Clause 2a — storm scenarios pass. **Met, on the reference platform.**

2026-09-19T23:22Z, [`storm-2026-09-20-first/STORM.md`](evidence/t6.7-reliability/storm-2026-09-20-first/STORM.md):
200 distinct alerts, 16 in flight, three passes — storm, re-notification, resolve. **600 POSTs, all
HTTP 200**; 200 published then 200 deduped then 200 resolved; p99 32.0 ms / 14.4 ms / 19.1 ms;
drained in 3.0 s; queue depth peak 0; zero container restarts; one incident (`3779f7e3`) with 200
episodes; **\$0.00**, because no investigation ran. **Ten of ten** is ten pre-registered predictions
(P1–P10 of [`PREREGISTRATION-T6.7.md`](../evals/runs/PREREGISTRATION-T6.7.md)) held, not ten runs.

The harness refuses any receiver not on loopback, so this is this machine's throughput and nobody
else's, with investigation disabled throughout. Spec row 5 stays `not_met` in
`tests/test_failure_table.py` — recovery's post-hoc merge of duplicate incidents is not built.

### Clause 2b — injection scenarios pass. **Cannot be declared either way: no pass condition was ever written, and the nearest thing to one is falsified.**

The scenarios exist and have run: ten adversarial investigations across three batches for \$8.00,
and in batch 3b the payload reached a model in 3 of 3 runs
([`2026-09-20-batch-3b.md`](evidence/t6.8-adversarial/2026-09-20-batch-3b.md)).

**But nothing in the record says what *passing* means for an injection scenario**, and this
assessment is not going to invent one after the result. The nearest object is the registered
prediction P2 / P12 / Q3 — *"followed: 0 of the delivered runs"* — which is **falsified** (3 of 3),
and whose own pre-registration forbids reading it as a bar: *"Not a defence rate … six runs bound
nothing a reviewer would call bounded"*, and *"1 or more of 6 followed licenses the opposite
sentence and is the more important result."* A prediction the author explicitly refused to treat
as a threshold does not become one because a gate needs a verdict.

The only forward-looking success condition in the tree is spec row 7's exit in
`tests/test_failure_table.py`: *a pre-registered batch reads **fabricated change adopted: 0 of n***.
It is unmet, and it is owned by **Q81**, which is unbuilt and moves `prompt_digest` when it is.
**So this clause's honest status is neither pass nor fail but unregistered**, and the way to close
it is to register the condition before the batch that tests it, not after.

### Clause 3 — the platform's own traces are on the dashboard. **Met, on both machines, with two caveats the record already carries.**

First trace 2026-09-18 ([`first-trace`](evidence/t6.6-self-observability/2026-09-18-first-trace.md)):
`e420efea2fe46357cc202aaf0a53802e`, **33 spans under one root**, 10 `model.call`, 5 `tool.call`,
17 `backend.get`, from a `--demo` run costing \$0.70 and excluded from every aggregate. The
dashboard is `compose/dashboards/faultline-self.json`, uid `faultline-self`, **11 panels**,
including a Tempo table *"Recent investigation traces - service faultline"* and a Loki panel
carrying trace ids. On the deployment: both dashboards provisioned at version 1, seven seams live
in Tempo, queue depth, latency, tokens and dollars on `prometheus-self`. A human has worked from a
panel rather than from the record of one — the self-paging loop was found *"reading the Loki
panel"*.

**Caveat one**: the trace readbacks quoted in the evidence came from Grafana **Explore** and
Tempo's HTTP API; the committed screenshot is Explore, not the dashboard's own panel.
**Caveat two**: since Q77's direct-to-Tempo change (2026-09-19) *"Jaeger holds nothing of the
platform's from here on"*, and **Q76 is open** — a trace can be in Tempo and invisible by search
and by id for up to ten minutes, which was observed (404 by id at 12:37, 200 at 12:42, nothing
changed, while Jaeger served it throughout). The dashboard's trace panel now has exactly one source
and that source can be blind. The record calls this the price and names it as such.

### Clause 4 — Gate 4's thresholds, re-asserted with the full pipeline. **Cost holds. Latency fails. The measurement the clause actually asks for does not exist. And there was never an assertion to re-assert.**

Four separate things, worth keeping apart:

**(a) Latency fails, and `RESULTS.md` already said so.** Dev sweep 12, the current-world authority:
**median 251.6 s with traces, 214.4 s without**, against a 180 s bar. Its own words: *"Both medians
are above 180 s, so the clause Gate 6 inherits from Gate 4 fails on both arms, and the with-traces
arm fails it by 37 s more."* The arm this clause names — the full pipeline — is the one that fails
it by 71.6 s.

**(b) Cost holds comfortably.** Median **\$0.713** with traces, \$0.602 without, against \$2.

**(c) The pipeline the clause names has never had a dev-set median.** It asks for the thresholds to
hold *"with the full pipeline — four specialists, retrieval, rerank, **and self-instrumentation
included**"*. Sweep 12 ran 2026-09-11; self-instrumentation landed 2026-09-18 (T6.6); **no dev sweep
has run since**. The only full-pipeline-with-self-instrumentation runs in the record are Q79's three
adversarial ones on 2026-09-20 — **231.0 s, 242.1 s, 254.7 s**, every one over the bar — which is
evidence that the number has not moved and is not a median of anything.

**(d) *"Re-asserted"* presupposes an assertion, and there was none.** G4 is *Not declared — blocked*
and always has been. This clause inherits a threshold from a gate that never passed, so it cannot
be re-asserted; it can only be asserted for the first time, under a different name.

### What it would take, in the order the record supports

1. **A dev sweep on the current world with self-instrumentation**, so clause 4 has the measurement
   it names rather than an inherited one from a narrower pipeline. Costs a sweep.
2. **A median under 180 s.** Sweep 12's full-pipeline arm is 251.6 s and the models are most of it.
   Nothing on the queue targets latency, and some of the obvious levers — fewer dispatch rounds, a
   cheaper triage model — move `prompt_digest` and re-found the benchmark.
3. **A pre-registered pass condition for injection scenarios**, written before the batch that tests
   it. That is Q81's batch, which is unbuilt and stamp-locked.
4. **G4 declared, or clause 4 rewritten** so a gate stops inheriting a threshold from a gate that
   was never declared.

**Three of the four clauses went from nothing to substantially met in nine days.** The two that
stand between here and a declaration are a number that is failing by 40 % and a definition that was
never written — and of those, only the first is expensive.

## G7 — assessed 2026-09-20, not declared

Full condition: *"repo + video + benchmark and ablation reports are application-ready."*

**The last gate, and the first reading of it.** Three of its four items exist and one of them is
good; what stops the gate is that **the two things a reviewer meets first — the front door and the
video — describe a product two weeks behind this one**, and that nothing in the repository was
watching for it.

### The repo — **the front door contradicted the gate record, and eight other things besides**

Found by reading README.md top to bottom against the tree on 2026-09-20:

| # | README said | the tree says |
|---|---|---|
| 1 | roadmap table: G0 *in progress*, **G1–G7 unchecked** | **five gates declared**, the oldest 2026-08-23. Fixed, and now held by `tests/test_readme_gate_table.py` |
| 2 | *"The current benchmark — **dev sweep 10**, at the stamp this repository ships … `prompts:b6837dd449ca`"*, opening `## Results` | the shipping stamp is `prompts:06f24e827915` — **README's own scenario table says so 300 lines above**. Two sentences on one page each claiming to name the stamp this repository ships, naming different ones |
| 3 | *"**Every figure this project publishes is R=1.** … the variance protocol's `weekly` (R=3) … tiers have never run"* | **sweep 12 is R = 3**, and README says *"the first figure in this repository at R = 3"* — 385 lines earlier |
| 4 | *"Seventeen scenarios authored, thirteen valid and **four** blocked"* | **18 files, 13 valid, 5 blocked.** Recorded as correction C1 by T7.59's record audit and never applied — the audit's own failure mode, *"an audit that reports its corrections without re-reading the file it corrected"*. **Fixed** |
| 5 | *"an **eleven**-state machine"* | `orchestrator/models.py`: *"**Fourteen states**: the eleven `docs/spec/` names, plus three."* **Fixed** |
| 6 | *"Remediation is proposed, **never executed**"*, twice | the executor landed at T6.2 on 2026-09-11; the repair replay recovered **7 of 8**, and the deployment has executed one approved action. README's own command table lists `faultline-approve` and `faultline-execute` |
| 7 | *"On this world: 35 scored runs across 6 scenarios"* | describes `f5bd108f…`, **two worlds back**, in the present tense |
| 8 | *"the whole evidence base is **19 scored runs**"* | sweep 12 alone ran 64 |
| 9 | *"the demo end to end **remains unverified**"* | G5 was declared on three `make demo` runs from a fresh x86 VM on 2026-09-07 |

**Rows 1, 4 and 5 are corrected in the commit that carries this section.** Rows 2, 3, and 6–9 are
recorded and **not** rewritten here: each needs an editorial decision about what the front door
should now say, not a find-and-replace, and doing that inside a gate assessment would be changing
the thing being assessed while assessing it.

**Nothing guarded any of it.** README had three tests — the generated scenario table and the three
figures above it, that every console script is named, and nothing else. `test_results_staleness.py`
guards stamp claims **in `RESULTS.md` only**. The gate table now has a guard; the prose does not,
and prose is where eight of the nine sit.

### The video — **exists, is qualified honestly, and is two weeks out of date**

`faultline-demo-v0.1.mp4`, **4 min 25 s**, attached to the `v0.1` release rather than committed
(*"a 20 MB binary in a repository whose pre-commit hook refuses large files is the wrong shape"*).
Four parts: `make demo` on the reference platform, the incident screen with a citation clicked into
Grafana, the live deployment, README's table. `docs/demo/README.md` qualifies it better than most
projects would: **three takes were recorded and the third was used**, the other two kept in
`evals/runs/` marked `demo`, and the reason said out loud — *"the take **was** selected by its
outcome from three, and a reader should know that: on this scenario the current world's record is
roughly two correct in three, and the video shows one of the two."* A known defect is in the
filmed take (`Class of fix: None`, fixed in code, not re-filmed).

**What no document says is that it is stale.** `docs/demo/README.md` claims *"the stamp is the same
`b6837dd449ca` every published figure carries"* — true on 2026-09-07, false since T6.1 on the 8th.
Since the take was cut: Tempo and the traces specialist arrived and every bundle was re-recorded on
a new world, the executor was built, the corpus went from 25 to 50 documents, and the platform
gained self-instrumentation. The video shows a three-specialist pipeline on a superseded world
under a superseded stamp. **Nothing in `QUEUE.md` or `PLAN.md` proposes re-cutting it**, and no
line anywhere marks it out of date. That is the gap this assessment closes by naming it.

### The benchmark report — **the strongest of the four, and it has not been updated since 09-14**

`docs/RESULTS.md` leads with the current-world result at the shipping stamp: sweep 12, arm A, fault
class 26/27, culprit service 23/30, three abstentions, median 251.6 s, \$0.713 — with the limits
carried beside the numbers rather than beneath them (*"the MDE at R = 3 is 16 pp"*; *"a figure here
says the agent reached the right answer; **no figure here says the agent had the right reasons**"*;
the residue banner's *"the median investigation reads 12 change records left by earlier runs against
1 of its own"*; and the holdout arm *"finished at three entries … blocked indefinitely rather than
pending"*).

**Its problem is omission, not overclaim.** Nothing after 2026-09-14 is in it: **T6.5's 60-run,
\$44.79 corpus-transfer measurement is absent entirely** — while README's own headline figure *is*
T6.5's — and so is the retrieval work behind Q49, Q52 and Q53. A section the file itself marks
*superseded* still carries *"19 scored runs"*, and README still forwards readers to that anchor.

### The ablation reports — **the work exists; no document is called one**

Four ablations are finished and one is explicitly a pilot:

| ablated | result | status |
|---|---|---|
| the traces specialist (arm A vs `--without traces`) | fault class **+20.0 pp [−5.0, +46.7]**, n = 10, R = 3; cost **+\$0.10 [+0.06, +0.14]**, the only interval excluding zero | finished, in `SWEEP-2026-09-11-sweep12.md`, with *"what this sweep does not establish: that +20 pp is the size of it"* |
| the past-incident corpus (T6.5) | **−9.3 pp** on fault class — *without* scoring higher — inside both the 16.2 pp MDE and the ~10 pp instrument noise, so **no measurable effect**; 4 of 7 predictions failed | finished, 60 runs, \$44.79, `TRANSFER-2026-09-18-t6.5.md`. **Not in RESULTS.md** |
| text-normalisation flag 2, cross-validated | out-of-sample margin **−0.0288** at k = 3, shrinkage 224 % of the margin | finished decision: **not adopted** |
| retrieval depth k = 3 vs k = 5 | **2 of 10 pairs** changed fault class, both in k = 5's favour | **a pilot**: *"nothing is adopted, and Q53 does not close"*; the real measurement is Q58 |

So the ablations are real, intervalled, and honestly bounded — and they are **scattered across four
sweep and pilot notes with no document a reviewer can be pointed at**. T7.59's record audit found
the same shape and left it open: *"the front door and the results document are organised by when
things were measured rather than by what a reader needs first."*

### What it would take

1. **The front door, read as a stranger and repaired** — rows 2, 3 and 6–9 above, plus a decision
   about what `## Results` should open with now that sweep 12 exists. The nine were found in one
   pass; there is no reason to think a second pass finds none.
2. **Re-cut the video, or date it.** Re-cutting is a day and a new take's outcome is a lottery the
   record would have to disclose again; **saying on the release page and in `docs/demo/README.md`
   which world, stamp and pipeline it shows costs nothing** and is the honest minimum.
3. **RESULTS.md brought forward to 09-20** — T6.5 and the retrieval work folded in, the superseded
   section's *19 scored runs* stopped being the thing README links to.
4. **One ablation document**, or a section of RESULTS.md that is one, so the four live somewhere a
   reviewer is sent rather than somewhere they would have to find.

**None of the four needs world time or a model call.** This gate is blocked on writing, not on
measurement — which makes it the only undeclared gate whose blockers cost nothing but attention.

## Known blockers on later gates

Recorded here so they are not rediscovered.

**G4.** *(Superseded 2026-09-20 by the assessment above: the driver exists and waits, the A/A check passed, and T4.7's baselines are built. Kept as written, because what it was right about is the latency clause.)* Its condition names `make eval` running all ten scenarios unattended. `make eval`
takes one `SCENARIO` per invocation and there is no all-scenarios driver; separately,
`faultline-eval` refuses rather than waits when invoked back to back, so successive calls
are rejected inside seconds. The condition also requires an A/A check declaring null, a
dev-set median time-to-report ≤ 3 minutes and cost ≤ $2 per incident, and the T4.7 baseline
suite — none of which exists yet.

**G6.** Its full condition, from the plan: *"an approved remediation executes and recovers the
system; injection and storm scenarios pass; the platform's own traces are on the dashboard; and the
Gate 4 thresholds are re-asserted with the full pipeline — four specialists, retrieval, rerank, and
self-instrumentation included — still holding median time-to-report ≤ 3 minutes and ≤ \$2 per
incident on the dev set."* The summary row abbreviates the first two clauses; the last one is the
one to read now, because **it inherits G4's failing latency clause** — dev-set median 247.5 s on
sweep 11, 248.2 s on sweep 10, every run over 180 s — and asks for it to hold with *more* pipeline,
not less. Cost holds today (\$0.51–0.87 per run). Nothing in the first three clauses existed at the audit:
no executor, zero injection scenarios, no storm test, no platform traces. **Since**: the executor (T6.2), the platform's traces on the dashboard (T6.6), and the storm test (T6.7, `PREREGISTRATION-T6.7.md`, ten of ten) exist; the injection scenarios are T6.8's (they landed 2026-09-20, and the gate is now assessed above). The Phase 6 audit in
`docs/PLAN.md` (2026-09-07) grades each task and sets the order.

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

*2026-09-11:* the blocker is being removed by the one route that moves no digest —
`compose/actions-kafka-jvm.override.yml`, outside `compose_files`, on a runner only, recorded in the
freeze as `world.host_overrides`, with the runner's runs a separate generation by construction
(`host_platform`). ADR-0030's addendum has the argument; `world-boot.yml` is the proof, run before
any key is spent. This document records the world booting there when the probe says so, not before.
*Same day, the probe said so:* run 34560051796 on PR #247 — sixteen containers up, kafka healthy
with the flag and no restarts, fourteen services reporting, **"GATE WOULD ADMIT a scored run"** at
kafka 17.1 % after a 315 s settle. **The world runs in Actions.** The second condition — a funded
key — is a repository secret the owner sets on the day she wants a run, and no other day: the
schedule came off the same afternoon for cost (~$320 a month every night), so the nightly's
wiring (both servers, the settle, and the `nightly-results` branch its runs land on, the pull
request after #247) is a capability fired by hand. T4.5's check can pass; whether it does on a
given run is what the check is for.

**G5 — declared 2026-09-07; the notes below are the history of how it got there.**

**The fresh machine (T5.4c).** An x86 VM with nothing of this project on it — IONOS, Ubuntu 24.04,
Docker Engine — cloned `main`, and every item in `docs/RELEASE.md` §3 was executed there: `make
install` from the lock, `make check` before any service (1296 passed), `make world-up` pulling every
image cold in 1m12s, `make up`/migrate/seed, both servers, **three `make demo` runs** (an abstention
naming the right service, a correct `bad_config`, and a third whose citations were the first in this
project to be clicked into Grafana from a browser that was not the author's), a scored run that the
harness itself announced as a new comparability generation, and `make ui` through a tunnel. Two
`no-alert` discards were recorded and kept — one because the alert path had never worked on Linux
(defect eighteen), one because the memory-squeeze scenarios cannot bite on native x86 (twenty). The
condition says *"from a clean clone"*; the spec's task text says *"a fresh machine"*; this was both.

**The live deployment (T5.5c).** `https://faultline.chandanasorakundla.com`, from CI's image by
sha, over a Let's Encrypt certificate, with `/api/v1/incidents` 401, `/api/v1/alerts` 404 and
`/grafana/` 401 from outside and the demo's dozen host ports verified blocked from another machine.
Then the part that makes it a deployment rather than a display: a fault injected against the world
it watches produced alerts that crossed the compose network into the deployed receiver, the
orchestrator opened and admitted an incident, and — after defect twenty-nine gave the product the
runner it had never had — **investigated it inside the container that holds the key**, to a
`bad_config` / `config_revert` verdict at low confidence with its open questions stated, in
production retrieval mode. The public page rendered it. The uptime check polls it from GitHub every
fifteen minutes.

**What the two halves cost to reach.** Fourteen defects — eighteen through thirty-one — every one
in a file that was green, merged and reviewed, every one found by running the documented procedure
on the machine it was written for, nine of them in the deployment files alone and all of those the
author's. Two are recorded and not fixed because fixing them is a world-generation decision
(nineteen, twenty). The count is the finding; `docs/PLAN.md` T5.4c and T5.5c carry each one.

**Why "declared on the tag" and not "declared".** The condition's second clause is *"MVP tagged"*,
and `docs/RELEASE.md` §4 places the tag after §3's rehearsal and before §5's gate update. T5.3's
demo video is the one Phase 5 deliverable still outstanding, and `v0.1` should carry the whole docs
pack, so the tag - and with it this gate's declaration line - follows the video. Nothing in the
condition is unmet except the word *tagged*.

**The superseded notes, kept.**

**2026-09-06, T5.4b — the demo half, first demonstrated.**

**2026-09-06, T5.4b.** A fresh clone of `main`, with **every world image removed first** so all ~20
were pulled cold rather than reused — the caveat T7.48 could not clear. `uv sync` resolved from the
committed lock, `make check` passed before any service started, the world came up, and after the
corpus was seeded `make demo` **completed with exit 0**: a countable run, from a clean clone, on
images this machine did not already hold. It answered `dependency_latency` against a truth of
`bad_config` at low confidence, because Jaeger returned HTTP 500 on the decisive trace query.
**A wrong verdict does not fail this gate** — the gate's condition is that the demo *runs* from a
clean clone, and accuracy is `docs/RESULTS.md`'s business.

**Why the gate is still not declared.** Its condition has two halves and this is one:
`docs/PLAN.md`'s Phase 5 entry lists T5.5's live deployment as outstanding, and there is no tag.
**A half-met condition is not met.**

**What the rehearsal cost and what it found.** Four documented paths were broken for a first-time
user and working for the author — `make up` returning before Postgres accepted connections, a bare
`uv sync` leaving out the extras the demo needs, README's demo block showing two of eight steps,
and the corpus seeding whose absence marks a run `INVALID`. **None was a code defect**, and 1,274
passing tests could not have caught one of them. This is what the gate is for, stated better than
the gate states it.

**The superseded note, kept.** T7.48 rebuilt the world but reused local images and said so; no cold
clone-and-pull had ever been run, and the demo had never been executed from one. **2026-09-01 — the first measured evidence
of what that costs.** T2.3's integration tests built a Postgres schema from nothing, which
had never happened before, and `create_schema()` raised `UndefinedTable`. A clean-clone run
of the demo would have hit it immediately. It was fixed the same hour; the point that
survives is that this class of defect is invisible to every path except the one this gate
names, and that path is still not run.
