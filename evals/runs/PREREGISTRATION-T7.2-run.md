# Pre-registration - T7.2, the SREGym run (scoping step 6)

**Written before the adapter is built and before any attempt is run. Nothing here is a result.**
This is [`t7.2-scoping.md`](../../docs/design/t7.2-scoping.md) §5 step 6: *"pre-register the run,
with the per-application split, the modality gap and the diagnosis-only clause stated in advance
rather than beside the result."* The execution plan's T7.2 asks for *"a thin adapter presenting
Faultline's agent to an external benchmark … and run it; publish a results report centered on
per-scenario-class error analysis"*, structured as *"scores → error taxonomy → architecture
implications"*.

**What this registration fixes**:

- the problems;
- the two arms;
- the grader;
- the verdict-to-text rendering;
- what is claimed;
- the predictions;
- the order of work.

**What it does not fix**: two adapter designs, the incident's opening and the change-history
mapping. Each is registered with the adapter build, before the dev pilot, under the constraints
set below.

## The questions

1. **The score.** Faultline's diagnosis pass rate under SREGym's LLM judge, **per application**:
   Astronomy Shop, Hotel Reservation and Social Network.
2. **The comparison.** The paired difference against SREGym's own `claudecode` agent with Claude
   Sonnet 4.6, on the same problems, under the same conditions, per application.
3. **The error analysis.** Where Faultline fails, read by SREGym's problem family and by the
   judge's three dimensions (localisation, characterisation, scope), and what each failure says
   about the architecture.

## What may be claimed, fixed now

Every published sentence about the result carries these clauses, or it is not published:

1. **Diagnosis only.** Faultline proposes and never executes (ADR-0028 §2), so mitigation scores
   zero by construction. No combined score is reported.
2. **Per application, never pooled.** Astronomy Shop is the OpenTelemetry Demo at v2.2.0, the
   same application as Faultline's own v2 world. The two DeathStarBench applications are
   foreign. A pooled figure would mix the two kinds.
3. **A pass rate under SREGym's LLM judge at 0.70**, with Claude Sonnet 4.6 as the judge. It is
   never called *diagnosis accuracy*.
4. **The modalities, as run.**
   - Metrics and logs: SREGym's Prometheus and Loki.
   - **Traces: present on Astronomy Shop, and absent on Hotel Reservation and Social Network as
     SREGym ships them** (Q127, the owner's decision below). The baseline faces the same gap.
   - **Change history: mapped onto Kubernetes' own record** through SREGym's kubectl server,
     read-only (the owner's decision below). It is not a deploy log, and it says so.
   - **No general Kubernetes describe.** Faultline reads no object state beyond what the change
     mapping returns. Every other SREGym agent, the baseline included, has kubectl.
5. **Not comparable to SREGym's leaderboard or paper.** This is a different commit, a different
   problem set (108 scored against the paper's 90), and kind instead of a real cluster. The paired
   baseline is the comparison. The paper's figures are context only.

## Read before registration

- **SREGym at `46c853db3a79332ea1c0ada076d888cec7a02f7e`**, with `SREGym-applications` at
  `887d093e`, the same tree as the harness read and every topology run.
- **The problem table**, read offline: every registered problem was instantiated with a stub
  kubeconfig, and no cluster was touched. The script and outputs are in
  [`docs/evidence/t7.2-run/`](../../docs/evidence/t7.2-run/).
  - **125 registered, and 118 instantiated.** Six FleetCast problems lack their submodule. The
    seventh, `taint_no_toleration_social_network`, needs a cluster to construct, and is attributed
    to Social Network by its name.
  - **All 118 grade diagnosis with `LLMAsAJudgeOracle`.**
  - **By application**: Hotel Reservation 50, Astronomy Shop 42, Social Network 21 (+1 above),
    Blueprint Hotel Reservation 3, Train Ticket 2, FleetCast 6. This matches step 4's count.
  - **Not runnable on kind**:
    - `latent_sector_error` and `silent_data_corruption` need Khaos, which SREGym skips on
      emulated clusters (`conductor.py`);
    - `node_clock_drift_hotel_reservation` is listed in `non_emulated_cluster_problems`.

    All three are Hotel Reservation's.
- **SREGym's paper** ([arXiv 2605.07161](https://arxiv.org/abs/2605.07161)), read 2026-10-02:
  - 90 problems on a real cluster, three runs per problem;
  - Claude Sonnet 4.6 as the diagnosis judge, at Cohen's κ 0.90 against a domain expert on 100
    sampled diagnoses;
  - diagnosis rates from 38.9 % to 72.6 %. The highest is Claude Code with Sonnet 4.6: 72.6 %
    without noise, 62.6 % with it;
  - **no per-application figures**;
  - it describes Jaeger traces as available to agents. **This repository measured the opposite**
    for both DeathStarBench applications at this commit (Q127).
- **What an agent receives** (`clients/claudecode/driver.py`, `conductor_api.py`):
  - the application's name, namespace(s) and a prose description from `/get_app`;
  - an instruction that a fault exists;
  - no alert. SREGym's Prometheus carries no alert rules (README, *Deployment Profiles*).
- **The snapshots of record**, all loaded by `FAULTLINE_CONTEXT_APPLICATION` since Q125 and Q128:
  `sregym-astronomy-shop` (`g3-deps-60m.json`), `sregym-hotel-reservation`
  (`g4-hotel-deps-5m.json`) and `sregym-social-network` (`g4-social-deps-30m.json`).
- **The stamps at `4e180a6`**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`.
- **Faultline's model**: `AgentSettings.model` is `claude-opus-5`, with no per-role override.
  `ContextSettings.hop_radius` is 2.

## The owner's decisions, 2026-10-02

| decision | chosen | why, in one line |
|---|---|---|
| the problems | **every eligible problem, R = 3** | per-application n large enough for an interval, and the paper's R |
| Q127, the DeathStarBench traces | **as shipped, and stated** | the benchmark is not changed to suit the agent measured on it |
| the baseline | **paired: SREGym's `claudecode` with Claude Sonnet 4.6** | the only comparison under identical conditions; the paper's strongest pair |
| Kubernetes state | **Faultline's `changes` tool implemented over Kubernetes' own record, read-only** | an existing modality given a backend, not a new tool; the adapter build checks the stamp |
| the grader | **Claude Sonnet 4.6**, as the paper | the paper validated it against a human; Opus grading Opus is closer to self-grading |
| the verdict-to-text rendering | **the whole verdict, in the fixed template below, with no model call** | the checklist's D2 and D3 ask for detail a one-line root cause cannot hold |
| Q126, accounting's OOM loop | **as shipped, and its neighbours flagged** | the same rule as Q127; both arms face it |
| adapter development | **three dev problems, one per application, by a seeded draw, never scored** | the adapter must be debugged on something, and that something cannot count |

**Two things followed from the plan rather than asked**, both because the plan wants *"the agent
under test is the real one"*:

- **The hop radius stays 2 on every application.** It is close to no filter on Social Network
  (93 % of pairs, Q128), and that is recorded rather than tuned.
- **Noise stays off**, which is SREGym's default and the paper's first column.

## The problems

**111 eligible**: every registered problem on the three applications with a snapshot, less the
three that cannot run on kind. **The dev draw**: `random.Random(20261002).choice` over each
application's sorted list, in the order Astronomy Shop, Hotel Reservation, Social Network
(`eligible_and_draw.py.txt`):

| application | eligible | dev problem (never scored) | scored |
|---|---|---|---|
| `sregym-astronomy-shop` | 42 | `edge_request_filter_cpu_saturation` | **41** |
| `sregym-hotel-reservation` | 47 | `update_incompatible_correlated` | **46** |
| `sregym-social-network` | 22 | `k8s_target_port-misconfig` | **21** |
| **total** | 111 | 3 | **108** |

The full list, with each problem's family and flags, is `run-table.tsv`.

- **Out of scope, and named**:
  - Blueprint Hotel Reservation (3), Train Ticket (2) and FleetCast (6), which have no snapshot;
  - the three kind-incompatible Hotel Reservation problems.
- **A problem that will not run** (SREGym skips it, or its deploy or injection fails twice) is
  named in the result and **removed from both arms' denominators**. It is never scored as a fail
  for either arm.
- **Q126's flag**: `kafka_producer_leak`, `kafka_queue_problems`, `kafka_poison_pill_hol_block`
  and `secret_rotation_stale_env_credentials_astronomy_shop`.
  - These are the four eligible problems whose definitions name Kafka or accounting.
  - They are scored as every other problem is, and their results are also read separately in the
    error analysis.

**The families**, as SREGym's registry groups them (`families.tsv`: its section comments,
title-cased as parsed), over the 108 scored:

| family | Astronomy Shop | Hotel Reservation | Social Network | total |
|---|---|---|---|---|
| Virtualization Fault Injector / Regular Virtualization Problems | 17 | 26 | 20 | 63 |
| Application Fault Injector / Regular Application Problems | 8 | 6 | 0 | 14 |
| Direct K8S Api | 1 | 12 | 1 | 14 |
| Opentelemetry Fault Injector | 12 | 0 | 0 | 12 |
| Ad Hoc | 3 | 0 | 0 | 3 |
| Application Fault Injector / Correlated Problems | 0 | 1 | 0 | 1 |
| Virtualization Fault Injector / Metastable Failures | 0 | 1 | 0 | 1 |

**Most of the 63 *virtualization* problems are Kubernetes object misconfigurations**: probes,
selectors, PVCs, DNS policy, ports, taints. That is where clause 4's missing describe is expected
to cost the most.

**A finer class per problem**, if the error analysis needs one, is assigned from the problem
definitions alone, in an addendum committed **before the first scored attempt**. It is never
assigned after a result is seen.

## The setup, frozen

**SREGym, identical for both arms:**

- `main.py --agent <arm> --model <arm's model> --judge-model <Sonnet 4.6> --judge-backend api
  --stages diagnosis --n-attempts 3 --profile full`;
- noise off, `--internet-access filtered`, `--container-hardening on`, `--agent-timeout 1800`;
- on a four-node kind cluster made by `kind/setup_kind_cluster.sh`, on the deployment, as 1c and
  the topology runs did, with the world running beside it.

**The judge's exact model string** is fixed in the adapter build's registration and checked by
SREGym's own judge validation (`main.py`). It is the same string for both arms, and for the
baseline's agent model.

**Arm F, Faultline:**

- the agent at `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, model `claude-opus-5`;
- `FAULTLINE_CONTEXT_APPLICATION` set to the problem's application. Astronomy Shop also needs
  `FAULTLINE_TOOLS_WORLD=v2`, as Q125 requires;
- hop radius 2, and retrieval as in production.

**A stamp that differs at run time invalidates the run until this registration is amended.**

**Arm C, the baseline:** SREGym's `claudecode` row as shipped, with Claude Sonnet 4.6.

**Constraints on the adapter, binding on its build:**

1. **Thin.** It implements `ToolSet` over SREGym's MCP servers (Prometheus, Loki, Jaeger, and
   kubectl for `changes`). It opens the incident, runs the investigation and submits the
   rendering. It holds no reasoning of its own and makes no model call.
2. **No answer leaks in.**
   - Faultline's model sees only what SREGym gives every agent (`/get_app`, the instruction's
     facts) and what Faultline's tools return.
   - `SREGYM_PROBLEM_ID` and `SREGYM_ARTIFACT_ID` name the fault, so they are used for artifact
     naming only and never reach a prompt.
   - No SREGym source, oracle or checklist is reachable from Faultline's model.
3. **The incident's opening** is designed in the adapter build, within constraint 2. There is no
   alert to seed triage, so the build states how the incident is opened, what triage's blast
   radius starts from, and that design's effect on triage. It is frozen before the dev pilot.
4. **The change mapping**:
   - read-only Kubernetes record (revisions, rollout history, events);
   - designed and frozen in the same build;
   - the build checks whether `cap:` holds. **If it moves, this registration is amended before
     the pilot**, not after.
5. **Benchmark state never enters the product.**
   - No SREGym incident, trajectory or narrative is written to the deployment's own database or
     to Faultline's retrieval corpus (ADR-0004's carve-out).
   - **The corpus is frozen for the whole run.** Nothing one attempt produces is retrievable by
     another, so attempt 2 can never read attempt 1's narrative of the same problem.

**The rendering, frozen.** The adapter submits exactly this text, built from the `Verdict` with
no model call. `{…}` are fields; a list prints one line per item, and an empty list prints
`none`:

```text
Root cause: {root_cause}
Faulty component: {service, or "not named"}
Fault type: {fault_class}
Confidence: {confidence}

Evidence:
- {claim} ({kind}, from {tool} on {service}{"; why: " + note if note}{"; query: " + query if query})
  [one line per Evidence entry whose result_id the verdict cites, in the verdict's citation order;
   samples are never included]

Reasoning:
{reasoning}

Alternatives considered:
{n}. {service}: {root_cause} ({fault_class}). Ranked lower because: {why_not}

Open questions:
- {open_question}
```

- **`remediation_class` is left out.** This is diagnosis only.
- **An attempt that ends with no verdict** submits `Faultline reached no verdict.` It is graded,
  and it fails.

## The analysis, fixed now

- **The unit** is an attempt: one problem, one arm, one of three.
- **The pass rate per application and arm** is passes over attempts, with a **95 % interval by a
  bootstrap over problems**, which keeps a problem's three attempts together (rule 6: n, R and the
  interval).
- **The paired difference** (F − C) per application is the mean over problems of each problem's
  pass fraction difference, with a bootstrap 95 % interval over problems.
- **Minimum detectable effect**: assuming a per-problem difference SD of 0.5, at 80 % power and
  α 0.05 (an assumption, stated):

  | application | MDE |
  |---|---|
  | Astronomy Shop (n = 41) | about **22 points** |
  | Hotel Reservation (n = 46) | about **21 points** |
  | Social Network (n = 21) | about **31 points** |

  A difference inside these is reported as *no measurable effect at this n*.
- **The error analysis**:
  - by family (the table above);
  - by the judge's three dimension scores, which SREGym records per attempt;
  - by the categories below, assigned per failed attempt from its trajectory and the judge's
    record:
    1. **localisation miss**: the wrong component;
    2. **characterisation miss**: the right component, the wrong mechanism or no concrete detail;
    3. **scope miss**: over- or under-attribution;
    4. **no verdict or timeout**;
    5. **adapter or harness failure**: excluded from the score, counted, and re-run once.

  The architecture implications are read from these categories, not added beside them.
- **Excluded and named**: an attempt the harness lost (crash, a judge error) is re-run once, and
  the original is kept in the record. A second loss removes the attempt from both arms.

## Predictions

1. **Faultline's pass rate**:

   | application | predicted |
   |---|---|
   | Astronomy Shop | 25 to 55 % |
   | Hotel Reservation | 10 to 40 % |
   | Social Network | 10 to 40 % |

2. **The baseline passes more often than Faultline on every application.** The difference is at
   or beyond the MDE on Hotel Reservation and Social Network, where Faultline has no traces and
   no describe.
3. **By family**: Faultline's rate on *Regular Virtualization Problems* is below its rate on the
   *OpenTelemetry Fault Injector* problems, on Astronomy Shop, where both occur.
4. **By dimension**: Faultline's D1 (localisation) mean is its highest of the three.
5. **On both DeathStarBench applications every trace-tool call returns no trace** (Q127, as
   shipped).
6. **No verdict or timeout** in at most 10 % of Faultline's attempts.
7. **Cost and time**, measured by the pilot first. These are not measured yet:

   | arm | per attempt | 333 attempts |
   |---|---|---|
   | Faultline | $0.30 to $1.50 (its own world's median is $0.53) | about $100 to $500 |
   | the baseline | $0.50 to $3.00 | about $170 to $1,000 |
   | the judge (Sonnet 4.6) | about $0.02 to $0.10 | over 666 attempts |

   Cluster time per attempt: 10 to 40 minutes (deploy 1.5 to 6 minutes as measured, the agent up
   to 30), so **80 to 220 hours per arm**.

## The order

1. **This registration.**
2. **The adapter build**, registered before it is coded:
   - the `ToolSet` over MCP;
   - the Jaeger repr parsed with `ast.literal_eval` (the harness read);
   - constraints 3 and 4's designs;
   - the rendering;
   - the `agents.yaml` row;
   - the stamp check.
3. **The dev pilot**, registered with the build's result:
   - the three dev problems, R = 1, both arms;
   - it measures cost, time and that every piece works;
   - its result is reported and never scored;
   - **it sets nothing in the frozen setup.** A change it forces is an addendum committed before
     the scored run.
4. **The owner's go**, on the pilot's measured per-attempt cost and time projected to the full
   run (rule 8). It is a checkpoint, not a departure. **How the run is operated** (batching over
   days, the watch on the world, the firewall, the kill switch) is registered with that projection.
5. **The scored run**: 108 problems × 3 attempts × 2 arms. The arms' order is interleaved per
   problem, so drift does not fall on one arm.
6. **The report**: scores, then error taxonomy, then architecture implications.

## What this does not touch

- **Q121, Q123 and Q124 stay open with their own triggers.** All three concern Faultline's own v2
  world on the Mac, which this run does not use. Q124's *"or T7.2's"* is answered here: the run
  opens no incident through the Mac's Alertmanager.
- **Q126 and Q127 are decided** (above), and their rows say so.
- **No code, no stamp and no world** changes with this registration.
