# Faultline

[![ci](https://github.com/ChandanaRoyalS/faultline/actions/workflows/ci.yml/badge.svg)](https://github.com/ChandanaRoyalS/faultline/actions/workflows/ci.yml)

**An open, benchmarked incident-investigation agent system for the OpenTelemetry stack.**

When a production alert fires, Faultline's agents investigate it the way a good on-call engineer
would — querying logs, metrics, traces and recent deploys in parallel — and produce a root-cause
report in which **every claim cites verifiable evidence**. Remediation is proposed, never
executed. It is built measurement-first: the environment is broken on purpose with labelled,
reversible faults, held-out scenarios are quarantined from every prompt and corpus from the day
they are authored, and no figure leaves the repository without its n. The point is not that the
agent works; it is that you can find out whether it does, and so can we.

> **Status: pre-v0.1.** Built gate by gate against a published execution plan. Nothing is claimed
> that a clean clone cannot demonstrate.

## Prerequisites

- **Docker**, running, with room for ~20 containers. `make world-up` clones the pinned
  OpenTelemetry demo into `world/` and starts it.
- **[uv](https://docs.astral.sh/uv/)** and **Python 3.12**. `make install` gets the extras the
  demo and scored runs need; a bare `uv sync` is enough for `make check` and leaves them out.
- **git**, for the world clone.
- **An Anthropic API key** — only for the demo and for scored runs. `make check` is offline.

**Platform note.** Every figure in this repository was produced on **Apple Silicon (arm64)**, where
roughly twenty of the demo's images are amd64-only and run under Rosetta emulation
([ADR-0005](docs/adr/0005-arm64-emulation-and-feature-flag-service.md)). That is not incidental to
the numbers: emulation changes container memory behaviour measurably
([T7.30](docs/PLAN.md)). **A run on x86 hardware is a different world and its figures are not
comparable to these.**

## Demo

One command runs the whole system against the live world and narrates it for a first-time
viewer — baseline gate, injection, correlation, the planner's dispatches, the specialists'
queries, the verdict, the narrative, the revert, and the confirmed recovery.

**Three terminals, because two of these are servers.** From a clean clone, in order:

```bash
make install                     # deps + the agents and embeddings extras
make up                          # Postgres and Redis, waited on until healthy
uv run faultline-migrate         # the schema, on a database that has none yet
uv run faultline-seed            # the retrieval corpus — see below, this one is not optional
make world-up                    # the pinned OpenTelemetry demo; ~5 minutes to settle
```

**`faultline-seed` is not a nicety and skipping it does not merely weaken the run — it
invalidates it.** Every scored run asks retrieval to exclude the scenario's own recorded
narrative (ADR-0008 axis 2, the leave-one-out filter). Against an **empty** corpus that exclusion
removes nothing, so it has asserted nothing, and the harness marks the run `INVALID`: scored,
kept, and its numbers unusable. T5.4's rehearsal hit this with a **correct** verdict —
`bad_config` against a truth of `bad_config` — and the run still cannot be counted, because a
right answer nobody can prove was uncontaminated is not evidence.

Then leave these two running, each in its own terminal. **Nothing works without them** — the
world's Alertmanager posts to the first, and the second is what turns those alerts into an
incident for the agents to investigate:

```bash
uv run faultline-ingest          # terminal 2 — receives Alertmanager's webhooks on :8000
uv run faultline-orchestrate     # terminal 3 — correlates alert episodes into incidents
```

**On Linux,** `make world-up` layers one extra compose file so that Alertmanager's
`host.docker.internal` — a name Docker Desktop defines and Docker Engine does not — resolves to the
host where `faultline-ingest` listens ([why it is not in
`telemetry.yml`](compose/linux-host-gateway.override.yml)). If the host runs a default-deny
firewall, open the receiver's port **to the docker bridge only** — never `ufw allow 8000` on a
public machine — and verify with the check in [`docs/RELEASE.md`](docs/RELEASE.md) §3:

```bash
sudo ufw allow from "$(docker network inspect opentelemetry-demo -f '{{(index .IPAM.Config 0).Subnet}}')" to any port 8000 proto tcp
```

```bash
make demo                        # terminal 1 — ~15 minutes, real model calls
```

**If you skip one, you are told which.** T5.4's first clean-clone rehearsal ran `make demo` with
no orchestrator attached and got

```
REFUSED: the alert pipeline is not assembled: no consumer is attached to the
orchestrator's group - start it with `uv run faultline-orchestrate`. This is NOT
the world failing to alert...
```

— nothing injected, nothing spent, and the distinction from a genuine `no-alert` spelled out.
**This block used to show two of these seven commands**, so the refusal was doing the
documentation's job; it is written down here now as well.

**Watch it happen.** `make world-up` also provisions the shop-health dashboard —
[the world at a glance](http://localhost:3000/grafana/d/faultline-shop-health). Every panel
below the top row is one alert rule's own expression with its threshold drawn as a line, so
a firing alert is explicable on the screen where it is visible. Open it before you inject:
the demo's narration and the dashboard tell the same story from two ends.

**Five minutes, not two.** The baseline gate refuses to inject into a world whose containers are
younger than **300 seconds** — a container still warming up produces readings that are not a
baseline. Running `make demo` too early is refused with that reason, not broken.

**This world has known pathologies** — a checkout stall, kafka growing under emulation — that
produce refusals on a world you have not touched. They are properties of the environment, not
bugs in your setup: [what the refusals mean](docs/TROUBLESHOOTING.md).

It needs an Anthropic key in `~/.faultline-anthropic-key` or `ANTHROPIC_API_KEY`, and it
refuses with instructions if the world is down or the key is missing. Nothing else here needs
a key — `make check` runs offline.

**The recorded run cost $0.3978.** That is one draw, not a point estimate: repeats of this
scenario under the same configuration have ranged **$0.4794–$0.7017**
([`VARIANCE-2026-08-27.md`](evals/runs/VARIANCE-2026-08-27.md), n = 5).

The scenario is `cart-redis-misconfig`, chosen because it is the most watchable *and* the
best-evidenced: nine services alert, the blast radius narrows to a single hop, **the service
that alerts loudest is not the service that broke**, and the answer is a change record rather
than an inference. It is also the only scenario whose repeat behaviour has been measured.

**The recorded run declined to name a fault class.** Six prior runs under this exact
configuration answered correctly
([T4.10's table](evals/runs/VARIANCE-2026-08-27.md#the-five-repeats), n = 5, plus dev sweep 3's
row); this one localized correctly to the checkout→cart hop, then exhausted its metrics budget
without ever spending a change-history query on `cartservice`, which is where the answer was, and
returned `unknown`. **Saying `unknown` rather than guessing is a designed behaviour, not a
breakdown** — an abstention is reported as coverage and kept out of the accuracy figure entirely,
so the system is never rewarded for a confident wrong answer. What the run leaves open — why the
planner sometimes spends its budget without reaching the one service that holds the answer — is
recorded under *What remains* in
[`docs/RESULTS.md`](docs/RESULTS.md). *(Was "the next experiment queued in docs/PLAN.md"; the
register moved to [`docs/QUEUE.md`](docs/QUEUE.md) at T7.45 and this question is not in it —
corrected T7.59.)*

Counting it, the record at this configuration is **6 correct out of 8**. It is left as it fell
rather than re-run until it looked better: a demo that is re-rolled until it impresses is an
advertisement.

**The eighth is T5.4's clean-clone rehearsal, and it is worth more than the number it cost.** From
a cold clone with every image pulled fresh, the demo answered `dependency_latency` against a truth
of `bad_config` at **low** confidence — because the trace query, the one that would have named the
failing dependency, returned `HTTP Error 500` from Jaeger. The agent said so, reported what it
could not know, and did not guess.

**On this scenario, at this stamp, on one evening, three runs gave three answers:** dev sweep 10
abstained with `unknown`, one demo answered `bad_config` correctly, and this one answered
`dependency_latency` wrongly. The third has a cause that is not the model at all — the world's own
tracing backend failed. **Run-to-run variance here includes the environment's flakiness, not only
sampling**, which is a larger and more honest thing to have measured than either alone, and it is
the strongest argument in this repository for the repeat protocol that has never been run.

**Would rather read than run?** A full transcript of a real run, with the narrative the scribe
wrote, is in [`docs/demo/`](docs/demo/) — [`transcript.txt`](docs/demo/transcript.txt) and the
[`narrative.md`](docs/demo/narrative.md) beside it.

The demo run is an ordinary run — same gate, same revert, same recovery check, recorded in
`evals/runs/` like any other — but it is marked `demo` in its manifest and **no aggregate ever
counts it**, because a run made to be watched is not a sample. A test pins that exclusion.

## Scoring a scenario

The demo is one narrated run. **This is the command every figure in the results section came
from** — one scenario, gated, injected, investigated, reverted, scored.

```bash
make eval SCENARIO=cart-redis-misconfig INTENT=--single-run
uv run faultline-inject list        # the scenario ids
```

**`INTENT` is mandatory and has no default.** It is either `--single-run`, or
`--runs-remaining N` counting down across a sweep — 6 on the first of six, 1 on the last. The
baseline gate projects kafka's memory forward over the work still to come and cannot do that
unless told what the work is, and **defaulting silently to the weaker check would be a guard that
protects you only if you remembered it**. A run without it refuses having injected nothing.

**Exit codes:** `0` scored · `2` refused before anything was injected · `3` the baseline gate
refused · `4` discarded, with the reason in the run directory's `DISCARDED.md` · `5` paused on a
clearable precondition. **A refusal is not a failure of your setup** — see
[what the refusals mean](docs/TROUBLESHOOTING.md).

The run lands in `evals/runs/<timestamp>-<scenario>/` with its manifest, verdict, narrative and
score. **Recording a *new* scenario is a different job** with a contract worth reading first —
which steps wait and for how long, and why a recorder that looks stuck is usually working:
[the rehearsal contract](evals/scenarios/ARTIFACTS.md).

## The rest of the harness

`make eval` wraps `faultline-eval`. Everything else that produced a number in this repository is
below — **until T5.4 none of these were named here**, so every figure in the results section came
from a command the front door did not mention, and a reader could read the whole page and still be
unable to reproduce one.

| command | what it does |
|---|---|
| `faultline-eval` | one scored run. Needs `--single-run` or `--runs-remaining N`; refuses without |
| `faultline-sweep` | the whole catalog, unattended. Counts the runs down for the gate itself |
| `faultline-judge` | grades a run's narrative. Skips anything already judged unless `--rejudge` |
| `faultline-compare` | two arms side by side — a pipeline sweep against a baseline |
| `faultline-eval-db` | the run record as a queryable table: outcomes, stamps, costs |
| `faultline-calibrate` | the human grades that measure whether the judge can be trusted |
| `faultline-render` | a recorded bundle → the readable pages in [docs/bundles/](docs/bundles/) |
| `faultline-manual-rca` | times a human investigating, for the MTTR comparison's left-hand side |
| `faultline-blind-rca` | the same, drawn blind from a sealed pool |

And the platform itself, if you want to run it rather than measure it:

| command | what it does |
|---|---|
| `faultline-migrate` | applies the schema. A clean clone needs this before anything stores |
| `faultline-seed` | loads the retrieval corpus |
| `faultline-ingest` | the alert receiver, and with `--postgres-dsn` the incident screen |
| `faultline-orchestrate` | consumes alert events and opens incidents |
| `faultline-investigate` | runs one investigation against an open incident |
| `faultline-demo` | the narrated end-to-end run `make demo` calls |

Every one takes `--help`. To put the screen on a URL, see [`deploy/`](deploy/README.md); to cut a
release, [`docs/RELEASE.md`](docs/RELEASE.md). What this project claims and refuses to claim, in the
words an application needs: [`docs/MVP-CUT.md`](docs/MVP-CUT.md).

## Bundles

Every recorded rehearsal, rendered as a readable page — what broke, what paged and in what
order, what the capture set holds, and the narrative the responder wrote:
**[docs/bundles/](docs/bundles/)**. Seventeen scenarios authored, **thirteen valid and four blocked** — a blocked scenario is one that could not fire, kept with its `INVALID.md` rather than deleted.

## Architecture in brief

```
alert → ingest → orchestrator → triage → planner → specialists → synthesizer → scribe
                      │                      │          │            │
                  incidents             blast radius  4 tools    past incidents
```

| Piece | What it does | Decision record |
|---|---|---|
| **Ingest** | Alertmanager webhook, fingerprint dedupe, Redis Streams | [ADR-0015](docs/adr/0015-alert-ingest-identity-and-dedupe.md), [ADR-0001](docs/adr/0001-redis-streams-over-kafka.md) |
| **Orchestrator** | Correlates alert episodes into incidents; an eleven-state machine | [ADR-0016](docs/adr/0016-orchestrator-correlation-state-and-cap.md) |
| **Context** | Service graph, blast radius, past-incident corpus in pgvector | [ADR-0017](docs/adr/0017-context-layer-graph-and-dependency-policy.md), [ADR-0018](docs/adr/0018-past-incident-corpus.md), [ADR-0002](docs/adr/0002-pgvector-over-dedicated-vector-db.md) |
| **Tools** | PromQL, LogQL, traces, change history — every result in an untrusted envelope | [ADR-0019](docs/adr/0019-tool-layer.md) |
| **Agents** | Planner, four specialists, synthesizer, scribe; in-house runtime, bounded budget | [ADR-0020](docs/adr/0020-agent-layer.md), [ADR-0003](docs/adr/0003-in-house-agent-runtime.md) |
| **Injector** | Labelled, reversible faults with ground truth | [ADR-0007](docs/adr/0007-chaos-injector-mechanisms.md), [ADR-0010](docs/adr/0010-injector-second-wave-faults.md) |
| **Eval harness** | Baseline gate, one driver, scoring, judge, freeze | [ADR-0022](docs/adr/0022-evaluation-harness.md), [ADR-0009](docs/adr/0009-rehearsal-artifact-bundle.md) |
| **Contamination model** | Split quarantine and run-time self-exclusion | [ADR-0008](docs/adr/0008-contamination-model.md) |

Every non-obvious decision is in [`docs/adr/`](docs/adr/); the task-by-task record is
[`docs/PLAN.md`](docs/PLAN.md).

## Results

> **The current benchmark — dev sweep 10, at the stamp this repository ships.** Under
> `prompts:b6837dd449ca`, capability `cap:c4d52d00`, world generation `f5bd108f4f70`: five dev
> scenarios, R=1, both arms, **\$3.6366 all in**
> ([`SWEEP-2026-09-06-sweep10.md`](evals/runs/SWEEP-2026-09-06-sweep10.md), pre-registered before
> the run).
>
> | axis | pipeline | B0.2 |
> |---|---|---|
> | **culprit service** | **5 / 5** | not scored — B0 names no service |
> | fault class, top-1 | 3 / 5 | 1 / 5 |
> | fault class, top-3 | 4 / 5 *(depth 3 on four of five)* | 4 / 5 **by construction** — depth 1 on every run |
> | class of fix | 3 / 5 | 1 / 5 |
> | cost | \$3.5979 | **\$0.0000** |
>
> **Culprit service is the figure this project would defend, and it is the newest.** Until T4.2 the
> benchmark scored the mechanism and the fix and never *which service broke* — on a benchmark whose
> subject is finding out which service broke. `frontend` was the triage entry point on three of
> these five and was blamed on none of them; B0.2, which has no service axis at all, takes that trap
> by construction.
>
> **The top-3 column is only readable with its depth, which is why depth is in the table.** Four of
> five pipeline verdicts ranked three candidates; **B0.2 ranked one on every run**, so its top-3
> equals its top-1 and the two columns are not measuring the same thing.
>
> ### The most important thing on this page is not in that table
>
> **`cart-bad-image-tag` was scored correct on fault class at this exact stamp, and four hours later
> came back wrong** — same prompt digest, same capability, same world generation, with `bad_deploy`
> absent from all three of its ranked candidates.
>
> **Every figure this project publishes is R=1.** `repeat_count: 1` appears on every run ever
> recorded; the variance protocol's `weekly` (R=3) and `published` (R=5) tiers have never run. So
> run-to-run variance at a fixed stamp had never been measured here, and the first measurement
> arrived by accident, at n=2.
>
> It invalidates nothing above. It establishes that **a single run at this stamp is not reproducible
> to ±1 scenario on fault class** — which is a statement about all five figures above, about dev
> sweep 9's four, and about every per-scenario comparison a reader might draw between them. The
> repeat that would settle it costs about \$9 and has not been run.
>
> **Do not read these against dev sweep 7's `8 of 8 / 7 of 8`.** That sweep ran a different and
> larger scenario set, at `1b0e7cbb4c47`, three stamps back, before the service axis existed. The
> catalog, the contract and the scored axes have all moved since; the two are not a
> before-and-after and treating them as one compares scenario sets rather than pipelines.
> [`SWEEP-2026-08-30-refound-again.md`](evals/runs/SWEEP-2026-08-30-refound-again.md) stands
> unedited.
>
> **On this world: 35 scored runs across 6 scenarios, 11 of them at the current stamp.** Every
> earlier figure in this README describes a superseded world, a superseded stamp, or both, and says
> which.
>
> **On `n`: it is the number of slots filled, not the number allocated.** The catalog runs against
> **13 valid scenarios** (10 dev / 3 holdout) of 20 allocated slots. One dev slot, `bad_deploy-5`, is
> **deliberately empty** - the available mechanism space for that class is exhausted and a fourth
> entry would add a row without adding anything the benchmark can tell apart
> ([CATALOG.md](evals/scenarios/CATALOG.md)). Empty slots here are stated choices, not unfinished
> work, and are not to be closed by inventing a scenario to fill them.
>
> **The world these figures name can be rebuilt (T7.48).** The stack was torn down with
> `make world-down` and brought back with `make world-up`, and **all three digests came back
> identical** — `compose_digest`, `observability_digest`, `ffs_stub_source_digest`, plus the demo
> image digest and all 28 containers
> ([the comparison](docs/evidence/t7.48-rebuild/)). **`compose_digest f5bd108f…` therefore names a
> world that can be reconstructed, not merely one that was running.**
>
> **Three limits, in the same breath.** The teardown **reused local images**, so this shows a
> *rebuild* is identical and not that a cold clone-and-pull is; the registry tag was separately
> confirmed to still resolve to the image every bundle records, which is a **weaker substitute**
> for a cold pull, not a replacement. **No scored run has happened since the rebuild**, so the
> *world* is identical and whether it yields comparable *figures* is untested. And the demo end to
> end **remains unverified** — it has not been re-run since the rebuild.
> *(Was "for want of API credit"; credit has since been available and 19 scored runs have been made
> on this world. The demo simply has not been re-run — corrected T7.59.)*
>
> **Every figure below this banner, and in [`docs/RESULTS.md`](docs/RESULTS.md) except where it
> says otherwise, was measured on an earlier world and is labelled as such.** Comparing across
> those boundaries compares worlds, not agents. **The world most of them describe is
> `4a7690c6fdda…`, two generations back — 69 manifest-carrying runs against it, 12 against the
> immediately preceding `299d791c5e0d…` (dev sweep 6).** *(Corrected 2026-09-01, T7.54; the two
> were previously stated the wrong way round.)*
>
> **The world moved on 2026-08-28** (T7.1: kafka heap capped, `otel-col` raised, Prometheus
> retention 6h → 15d, stub variants renamed) **and again on 2026-08-30** (T7.28: kafka's glibc
> allocator bounded, a `maxmemory`/`allkeys-lru` bound on redis-cart, a `memory_limiter` on the
> collector). Each move re-recorded every runnable bundle. See
> [docs/RESULTS.md](docs/RESULTS.md) and the
> [reconciliation record](docs/evidence/t7.1-reconciliation/README.md).

**The current-world result — 19 scored runs, what each of the three assessments can see, and what
the label score cannot — leads [docs/RESULTS.md](docs/RESULTS.md#the-current-world-result).**
Everything below in this README describes earlier worlds and is labelled as such.

Full method and findings: **[docs/RESULTS.md](docs/RESULTS.md)**. Raw runs and reports:
[`evals/runs/`](evals/runs/).

Every figure below was produced by **agent `claude-opus-5`**, judged by **`claude-haiku-4-5`**.
The judge shares a vendor family with the agent, so **every judged figure carries a
`SHARED LINEAGE` label** — this repository holds one provider's credentials and the violation is
declared rather than hidden.

### Holdout — three scenarios, never run before, never in any corpus

Pipeline stamp **`prompts:53fafe9c12bc`**, frozen before the run
([`FREEZE-2026-08-26-holdout.json`](evals/runs/FREEZE-2026-08-26-holdout.json)).
**The holdout has been entered three times, under two stamps.** The figures above are entry 1,
under `53fafe9c12bc`. **Entry 3, under the current stamp `prompts:1b0e7cbb4c47`, answered all
three and got all three right** — 3/3 coverage, 3/3 fault class, 3/3 judged `same_mechanism`
([`HOLDOUT-2026-08-27-entry3.md`](evals/runs/HOLDOUT-2026-08-27-entry3.md)). Two caveats travel
with that number and are stated in full there: `email-wrong-image`'s row is corroborative rather
than confirmatory, and **n = 3 with no interval is not a benchmark**. Every entry is numbered and
counted in ADR-0022's ledger; entries 1 and 2 stand unedited.

> **Three things a reader should not have to infer, added T7.59.**
>
> **All three entries ran on `compose_digest 4a7690c6fdda…` — two worlds back.** Entry 3 shares the
> *stamp* with HEAD, which is what the line above says and all it says. **There are zero
> current-world holdout figures**, and every current-world run in this repository is a dev run
> (T7.54's reconstruction; the per-entry banners were corrected there).
>
> **Entry 4 is blocked indefinitely, not pending.** ADR-0022's T4.15 addendum permits a further
> entry only once the holdout set is re-authored or extended. T7.56 designed and gated a fifth
> `bad_config` scenario and **abandoned it at its first gate**; T7.57 established that **this world
> has no fifth fault class**
> ([ADR-0029](docs/adr/0029-four-fault-classes-and-why-there-is-no-fifth.md)). **No more holdout
> evidence is coming without a different demo world.**
>
> **So the holdout arm is what it is: three entries, seven agent-facing runs, four answered, on a
> world two generations superseded.** It cannot support a claim, and that is the claim.

| scenario | ground truth | fault class | class of fix | judge (SHARED LINEAGE) |
|---|---|---|---|---|
| email-wrong-image | `bad_deploy` / `rollback` | `unknown` — **abstained** | abstained | `different` |
| productcatalog-dependency-latency | `dependency_latency` / `restart` | **`dependency_latency`** ✔ | `config_revert` ✘ | `same_mechanism` |
| recommendation-memory-squeeze | `resource_exhaustion` / `config_revert` | `unknown` — **abstained** | abstained | `different` |

| per fault class | n | fault correct / answered | fix correct / answered | abstained |
|---|---|---|---|---|
| `bad_deploy` | 1 | — / 0 | — / 0 | 1 |
| `dependency_latency` | 1 | **1 / 1** | 0 / 1 | 0 |
| `resource_exhaustion` | 1 | — / 0 | — / 0 | 1 |
| `bad_config` | **0** | no holdout scenario | | |
| ~~`scale`~~ | — | **not a fault class.** `scale` is a *remediation* class, so this row is a remediation sitting in a fault-class table ([ADR-0024](docs/adr/0024-the-scale-class-and-what-this-world-can-show.md)). Struck T7.59, kept so the mislabel stays visible | | |

**n = 3 runs, 1 per class.** Triage recall **1.00** (n=3), precision 0.32. Cost $1.08 + $0.12
judged. Two of three runs exhausted their `changes` tool-call budget.
[`HOLDOUT-2026-08-26.md`](evals/runs/HOLDOUT-2026-08-26.md)

### Dev — where prompts and retrieval were fitted, so **not a benchmark**

Shown for context only. Same seven scenarios, two pipelines.

| | **dev sweep 1** | **dev sweep 2** |
|---|---|---|
| stamp | `prompts:59bf438b2a96` | `prompts:53fafe9c12bc` |
| difference | — | 28 lines added to the synthesizer's instructions |
| fault class, of answered | **4 / 7** | **4 / 4** |
| coverage (reached a class) | 7 / 7 | 4 / 7 |
| class of fix, of answered | 6 / 7 | 3 / 4 |
| triage recall / precision | ~~0.94 / 0.56~~ **0.94 / 0.60** | ~~0.95 / 0.57~~ **0.95 / 0.60** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_
| judge: same_mechanism / adjacent / different | **7 / 0 / 0** | 4 / 0 / 3 |
| budget exhausted | 1 of 7 | 2 of 7 |
| cost | $2.92 | $3.27 |
| **n** | **7 runs** | **7 runs** |

| per fault class | n | sweep 1 fault | sweep 2 fault | sweep 2 abstained |
|---|---|---|---|---|
| `bad_config` | 2 | 2 / 2 | 1 / 1 | 1 |
| `bad_deploy` | 2 | 2 / 2 | 1 / 1 | 1 |
| `dependency_latency` | 1 | **0 / 1** | **1 / 1** | 0 |
| `resource_exhaustion` | 2 | **0 / 2** | **1 / 1** | 1 |
| ~~`scale`~~ | — | **not a fault class** — see above ([ADR-0024](docs/adr/0024-the-scale-class-and-what-this-world-can-show.md)). Struck T7.59 | | |

[`SWEEP-2026-08-26.md`](evals/runs/SWEEP-2026-08-26.md) ·
[`SWEEP-2026-08-26-taxonomy.md`](evals/runs/SWEEP-2026-08-26-taxonomy.md)

### Coverage and abstention

A verdict of `unknown` is an **abstention, not a wrong answer**: it is excluded from the accuracy
ratio entirely and reported as coverage, because a system that says "I do not know" and one that
guesses confidently wrong should not produce the same number. **Accuracy and coverage are
therefore never quoted apart** — "4 / 4 of answered" and "coverage 4 / 7" are one figure in two
halves, and either alone is misleading.

### What these numbers are not

n is 3 on holdout and 7–8 per dev sweep, with 0–3 scenarios per fault class. **On the current world
the whole evidence base is 19 scored runs across 10 of the 13 valid scenarios, and none of them is a
holdout run** (T7.59). The two scenarios added at T7.36 and T7.38 are now at n = 5 and n = 3
respectively. A 95% confidence
interval on any cell above spans most of the unit interval. **The tables support direction, not
magnitude**, and no aggregate appears anywhere without the per-class table beside it.

## Roadmap (gates)

| Gate | Condition | Status |
|------|-----------|--------|
| G0 | CI green on the walking skeleton | 🔨 in progress |
| G1 | injected fault → alert fires → visible on dashboards (zero AI) | ⬜ |
| G2 | alert → agent → persisted, cited finding | ⬜ |
| G3 | full multi-agent pipeline on 3 of 4 fault classes | ⬜ |
| G4 | `make eval` scores 10 scenarios; A/A check declares null | ⬜ |
| G5 | MVP shipped: demo from clean clone + live deploy | ⬜ |
| G6 | approval-gated remediation; thresholds re-held | ⬜ |
| G7 | benchmark report + ablations + launch | ⬜ |

The gate marks above are deliberately not updated from the results section. A gate passes when
its condition is demonstrated **from a clean clone**, and that has not been re-run since these
measurements were taken. What the results show is what the results show.

## Layout

```
src/faultline/     the platform: ingest, orchestrator, agents, context, tools
src/injector/      chaos injector CLI — reversible faults with ground-truth labels
src/evalharness/   the measurement layer: scenarios, scoring, variance protocol
evals/scenarios/   the labeled scenario catalog (dev/holdout split at authoring)
deploy/            the trimmed deployment: compose, TLS, procedure and cost (T5.5)
docs/adr/          every non-obvious decision, recorded
```

### The incident screen

With the platform up (`make up`), one process serves the alert receiver and the incident view on
the same port:

```bash
FAULTLINE_API_PASSWORD=local-only make ui
```

Then `http://localhost:8000/api/v1/incidents` for the list, and
`http://localhost:8000/ui/incidents/<id>` for one incident's timeline, verdict, evidence cards and
citation deep-links. **The password is mandatory and has no default** — the screen serves every log
line an agent quoted and every query it ran. To put it on a URL, see
[`deploy/README.md`](deploy/README.md).

## Development

```bash
make install     # deps + the agents and embeddings extras
make check       # lint + types + tests — what CI runs
```

**`uv sync` alone is not enough to run anything that calls a model**, and it used to say
"install everything" here. Two optional extras are lazily imported and left out by default,
because `make check` never calls a model and one of them pulls torch:

| extra | needed by | without it |
|---|---|---|
| `agents` | `make demo`, every scored run | a refusal naming the fix |
| `embeddings` | retrieval, `faultline-seed` | a bare `ImportError` |

`make install` takes both. The clean-clone rehearsal found this the honest way: `make check`
passed and `make demo` could not start (T5.4b).

### Breaking the world on purpose

With the world up (`make world-up`), the injector applies labelled, reversible faults:

```bash
uv run faultline-inject list                     # the fault catalog
uv run faultline-inject start cart-redis-misconfig
uv run faultline-inject status                   # what is broken right now
uv run faultline-inject stop --all               # put everything back
```

Active injections live in `.faultline/`, so `status` and `stop --all` work from any shell.
Stopping something that is not active is a no-op that succeeds. See
[ADR-0007](docs/adr/0007-chaos-injector-mechanisms.md) for what each fault class does.

## License

MIT — see [LICENSE](LICENSE).
