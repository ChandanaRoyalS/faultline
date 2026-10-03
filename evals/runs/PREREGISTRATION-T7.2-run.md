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

## Addendum 1 - the owner's go: the run scaled to the budget, and the pilot's fixes

**Written 2026-10-03, after the pilot's result
([`evals/attempts/T7.2-pilot/RESULT.md`](../attempts/T7.2-pilot/RESULT.md)) and before anything
is built or run.** This is the order's step 4. The pilot projected the registered run, 108 × 3 × 2
= 648 attempts, at about $420 and 154 hours. **The owner declined that cost**, and decided the
following, asked one at a time with the pilot's findings explained.

### The owner's decisions, 2026-10-03

| decision | chosen | why, in one line |
|---|---|---|
| the two adapter defects | **both fixed**: the log selector, and the change commands | they failed Faultline's tools on every pilot problem; neither is Faultline's behaviour |
| the missing metric history | **Faultline unchanged; the limitation is stated in the report** | T7.2 requires *"the agent under test is the real one"* |
| the slow opening | **the delay found and fixed**, the opening's design unchanged | about 15 s per MCP call put attempt 5 at 1,329 s of 1,800 |
| the scale | **11 problems per application, R = 1, both arms**: 66 attempts, about $43 | the owner's budget. **Every deliverable is kept; the evidence behind each is smaller** |

**The scale is a departure from the plan as well as from this registration, and is the owner's
explicit decision.**

- The execution plan's T4.6 sets R = 5 for scored comparisons, and this registration chose R = 3.
  The run is now R = 1.
- **What it costs is precision, not deliverables.** The report keeps its structure: scores, then
  the error taxonomy, then the architecture implications. More of its comparisons will read *no
  measurable effect at this n*, as the plan's rule requires.

The same decision sets the rest of Phase 7 at about $135 in total. That is recorded in `PLAN.md`,
and each of those tasks registers its own scale before it runs.

### The problems

**33 of the 108 scored problems**, 11 per application, by `random.Random(20261003).sample` over
each application's sorted scored list, in the registered order
([`scaled_draw.py.txt`](../../docs/evidence/t7.2-run/scaled_draw.py.txt), output
`scaled-sample.tsv`):

| application | problems |
|---|---|
| Astronomy Shop | `astronomy_shop_ad_service_failure`, `astronomy_shop_ad_service_high_cpu`, `astronomy_shop_payment_service_failure`, `duplicate_pvc_mounts_astronomy_shop`, `kafka_poison_pill_hol_block`, `kafka_queue_problems`, `liveness_probe_misconfiguration_astronomy_shop`, `missing_env_variable_astronomy_shop`, `service_port_conflict_astronomy_shop`, `stale_coredns_config_astronomy_shop`, `wrong_dns_policy_astronomy_shop` |
| Hotel Reservation | `admission_webhook_tls_mismatch_hotel_reservation`, `cfs_cpu_throttling_hotel_reservation`, `dev_shm_exhaustion_hotel_reservation`, `duplicate_pvc_mounts_hotel_reservation`, `finalizer_deadlock_controller_hotel_reservation`, `liveness_probe_too_aggressive_hotel_reservation`, `network_policy_block`, `pvc_claim_mismatch`, `resource_request_too_large`, `storage_user_unregistered-2`, `wrong_dns_policy_hotel_reservation` |
| Social Network | `assign_to_non_existent_node`, `duplicate_pvc_mounts_social_network`, `liveness_probe_misconfiguration_social_network`, `liveness_probe_too_aggressive_social_network`, `missing_service_social_network`, `persistent_volume_affinity_violation`, `pod_anti_affinity_deadlock`, `service_port_conflict_social_network`, `stale_coredns_config_social_network`, `taint_no_toleration_social_network`, `wrong_dns_policy_social_network` |

- **By family**: 23 virtualization problems, 5 OpenTelemetry injector, 3 Direct K8S API and 2
  application. The 108 had 63, 12, 14 and 15 (application problems counted together), plus 3
  ad hoc and 1 metastable, none of which was drawn.
- **Two of Q126's four flagged problems were drawn**: `kafka_poison_pill_hol_block` and
  `kafka_queue_problems`. They are read separately, as registered.
- **The dev problems stay unscored.** No pilot problem is in the sample.
- **The rule for a problem that will not run is unchanged**: it is named and removed from both
  arms. **No replacement is drawn.**

### What changes in the analysis

- **The unit** is an attempt: one problem, one arm, R = 1.
- **The primary comparison is the paired difference over all 33 problems.** The per-application
  rates and differences are still reported, each with its bootstrap interval. The bootstrap is over
  problems, as registered.
- **Minimum detectable effect**, with the registered assumption (per-problem difference SD 0.5,
  80 % power, α 0.05):

  | comparison | n | MDE |
  |---|---|---|
  | all three applications | 33 | about **24 points** |
  | one application | 11 | about **42 points** |

  A difference inside these is reported as *no measurable effect at this n*.
- **The predictions stand as registered.** They are read against these n, and a prediction whose
  range is narrower than its interval is reported as *not testable at this n*, never as held.
- **The error analysis is unchanged**: by family, by the judge's dimensions, and by the five
  categories. **Any family below five problems is described attempt by attempt, not as a rate.**

### The spend cap

- **$50 for everything T7.2 still runs**: the re-check of the fixes and the scored run.
- **Tallied after every attempt** from the tokens each agent records (Faultline's trajectory
  steps, Claude Code's session log), at the published prices, the pilot's method. Each judge call
  is counted at $0.10, the registered ceiling.
- **The run stops when the tally passes $47.** Whatever is unfinished is named, and the result is
  reported on the problems both arms completed.
- **The owner's reading of the key's spend in the console is the authority**, taken once the run
  ends.

### What comes next, in order

1. **The fixes**, registered as an addendum to the adapter's registration before they are coded:
   - the selector;
   - the change commands, asking for named fields so that every answer fits 10,000 characters;
   - the opening's delay, found first;
   - a read-only look at `latency-p95`'s bounds.
2. **The re-check**: Faultline alone on the three dev problems, R = 1, never scored, about $2-3.
   **It goes on only if every tool returns data or a true absence.**
3. **The scored run's operation**, registered with the re-check's result: batching, the world
   watch, the record after each Faultline attempt, and the arms alternating which goes first per
   problem.
4. **The scored run**, then **the report**.

**Everything else in this registration stands**: the baseline, the judge, the rendering, Q126 and
Q127, the frozen setup, and the stamps, which the fixes must not move.

## Addendum 2 - how the scored run is operated

**Written 2026-10-03, after the re-check
([`evals/attempts/T7.2-recheck/RESULT.md`](../attempts/T7.2-recheck/RESULT.md)) and before any
scored attempt.** This is the order's step 4, *how the run is operated*. The design is
Addendum 1's: 33 problems, R = 1, both arms, a $50 cap.

### The queue

- **66 slots** ([`scored_queue.py.txt`](../../docs/evidence/t7.2-run/scored_queue.py.txt), output
  `scored-queue.tsv`).
- The 33 problems are shuffled by `random.Random(20261004)`, so that no application's problems
  fall together in time. Each problem gets two slots, back to back.
- **The arm that goes first alternates**: odd positions Faultline first, even positions Claude
  Code first. So drift inside a session falls on neither arm.
- The queue is fixed now and run in order. Nothing in it is changed after a result.

### One slot (`pilot_vm.sh scored N`)

- **Every frozen setting, as the pilot's attempts had them**:
  - `--stages diagnosis --n-attempts 1 --profile full --internet-access filtered
    --container-hardening on --agent-timeout 1800 --force-build`;
  - Faultline on `anthropic/claude-opus-5`, Claude Code on the judge's model;
  - the judge `anthropic/claude-sonnet-4-6`;
  - `claudecode` pinned to `install`'s version.
- **A slot whose run did not complete** (no results file, or a status other than `complete`) is
  **re-run once**. A second failure is named, and the problem is removed from both arms, as
  registered.
- **A Faultline slot is followed by `record`**, before the next Faultline slot wipes the
  trajectory.
- The outcome goes to `done.tsv`: slot, problem, arm, status, success, accuracy, start and end.

### Batches (`pilot_vm.sh batch FIRST LAST`, run with `nohup`)

- **Three sessions**, as planned: slots 1-22, 23-44 and 45-66, each about four to five hours.
- **A batch can be started again after an interruption**: a slot already in `done.tsv` is
  skipped.
- **The tally is read after every slot** (`pilot_vm.sh tally`), the re-check's method:
  - Faultline's trajectory tokens and Claude Code's session tokens, at the published prices;
  - every judged slot at $0.10;
  - a Faultline slot with no trajectory at $0.05;
  - the re-check's $1.80.
- **Once the tally passes $47, the batch stops for good** (a `STOP` file). The run is then reported
  on the problems both arms completed. The owner's console reading at the end is the authority.
- `pilot_vm.sh status` reads progress at any time, and changes nothing.

### The VM across the sessions

- **Set up once**, with part B's stages as the re-check ran them, `scored-queue.tsv` copied
  beside the script.
- **Kept up between sessions, for at most 48 hours**:
  - the kill switch on;
  - the rules in place;
  - the key on the VM at mode 600;
  - `hold`, the sampler, restarted each session.
- **Closed once**, with part B's close: `collect`, then each record archive copied to the Mac,
  `teardown`, `host-off`, `cleanup` with `sudo`, `killswitch-off`, `incidents`.
- **The run pauses at the next `status` check**, for the owner's decision, if any of these happens:
  - the live system opens an incident;
  - MemAvailable falls below 2 GiB;
  - a world container restarts.

### Expected

- **Time**: about 66 × 12 minutes, so 13 hours of slots. The re-check's attempts took 10 to 14
  minutes, and the pilot's Claude Code attempts 7 to 12.
- **Cost**: about $43 for the slots, plus the re-check's $1.80.

**Nothing else changes.** The analysis is Addendum 1's, and the report follows it.
