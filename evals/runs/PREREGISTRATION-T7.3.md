# Pre-registration - T7.3, the ablation studies on the v2 catalog

**Written before the build it needs and before any run. Nothing here is a result.**

The execution plan's T7.3, verbatim:

> Controlled experiments on your own harness: single-agent-all-tools vs. parallel specialists;
> topology scoping on/off; evidence compression vs. raw context; model tier per role; the
> retrieval series — on/off, hybrid vs. dense-only, rerank on/off; temporal scoping on/off
> (unbounded windows); and progressive disclosure vs. push-everything briefings.
>
> One config dimension varied at a time over the full catalog, at R=5 paired per T4.6, with run
> order randomized across configs to avoid confounding with provider-side drift; every report
> states its MDE before its result, and a below-MDE delta is reported as "no measurable effect at
> this catalog size"; dated experiment reports checked into the repo.
>
> Deliverable: **Ablation report series — the architecture-science story.**

## The plan and the repository, checked first (CLAUDE.md rule 9)

| | |
|---|---|
| **the deliverable** | a dated report per experiment, nine experiments, each with its MDE stated before its result |
| **what is delivered** | **none on v2.** `docs/ABLATIONS.md` holds four v1 ablations (traces specialist, past-incident corpus, text normalisation, retrieval depth) at `prompts:06f24e827915` on world `90e9f29e…`. Of the plan's nine, only *retrieval on/off* overlaps (the corpus study withheld same-class documents, not the whole corpus), and *single agent* partly (B1, 10 v1 runs). A different world and stamp: **none is reused** |
| **what is left** | all nine experiments on v2, and the build that eight of them need (below) |

## The questions

**For each of the nine dimensions**: what does varying it, and only it, do to Faultline's
fault-class accuracy, culprit-service accuracy, cost and time to report on the same 12 scenarios?

## What may be claimed, fixed now

1. **12 dev scenarios, R = 1**, by the owner's decisions of 2026-10-03 and 2026-10-04. The plan
   asks for the full catalog at R = 5, and this is registered in `docs/DEVIATIONS.md`.
2. **The MDE is 26 points** (below). **A difference inside it is *no measurable effect at this
   catalog size*.** At this size that will be most of them, and each report says so first.
3. **Dev scenarios only.** ADR-0008 forbids tuning against holdout, and an ablation's result is
   what tuning reads.
4. **Faultline's own world** (OTel Demo 2.2.0 on the Mac). Nothing here is about SREGym.
5. **Experiment 1 uses B1**, which differs from Faultline in more than the fan-out:
   - it has no retrieval, no proposer and no scribe (`baseline_agent.py:57-64`);
   - **it is never gated** (`cli.py:268-281`).

   Its result is about all of those together, and says so.

## Read before registration

**What each dimension needs** (read from the code at `90a5a666`; nothing run):

| # | dimension | in the system today | switch today |
|---|---|---|---|
| 1 | single agent vs specialists | B1 | **yes**: `--baseline b1` on `faultline-eval` and `faultline-sweep` |
| 2 | topology scoping | `hop_radius` 2 sets the blast radius (`context/settings.py:15`) | **no off switch**; `hop_radius` is not in the config fingerprint |
| 3 | evidence compression | the synthesizer reads an evidence board with 400-character samples (`evidence.py:66`, `roles.py:743-770`) | **none** |
| 4 | model tier per role | `FAULTLINE_AGENT_ROLE_MODELS` is recorded in the manifest and the fingerprint | **recorded but not applied**: `cli.py:312` builds one model and gives it to every role (`cli.py:321-343`). A run with it set would be fingerprinted as a different config and behave identically |
| 5 | retrieval on/off | the past-incident corpus | `--no-corpus` on `faultline-investigate` only; **the harness does not pass it** (`run.py:1247-1271`) |
| 6 | hybrid vs dense-only | hybrid, both arms always (`store.py:374-406`) | **none** |
| 7 | rerank on/off | **not built**: deferred by name at T6.4 (Q42) | none |
| 8 | temporal scoping | windows are always bounded, and an out-of-ceiling window is refused (`window.py:161-178`) | **no unbounded mode** |
| 9 | progressive disclosure vs push-everything | disclosure built (`briefing.py`); pull rate recorded *"so T7.3 reads it"* | **no push mode**; the briefing budget setting is recorded and not applied (`Budget.briefing_tokens_for` has no callers) |

- **No setting is inside either stamp.** The prompt digest hashes the system prompts and six
  contract schemas, and *"budget bounds are deliberately outside the stamp"*
  (`stamp.py:20`). The capability stamp hashes the tool surface (`capability.py:61-73`).
  **So an ablation arm changes no stamp, and the build must prove the default changes nothing.**
- **The config fingerprint** (`evaldb.FINGERPRINT_INPUTS`) holds `baseline` and `ablation` (the
  withheld specialists), but **not** `hop_radius`, retrieval switches, window policy or briefing
  mode. Each arm needs its own recorded key, or two arms read as one config.
- **The run order is not randomized today.** `faultline-sweep` keeps a stable order
  (`sweep.py:150-151`).
- **The A/A floor on v1**: dev sweep 12's arm split against itself measured 10.0 points on fault
  class (`docs/ABLATIONS.md`).

## The owner's decisions, 2026-10-03 and 2026-10-04

| decision | chosen |
|---|---|
| the scale | **12 scenarios, R = 1, all nine experiments**: about $100 for the eight new arms |
| the control | **normal Faultline and B1 re-run inside T7.3's randomized batch** (about $16 more), as the plan's *"run order randomized across configs"* requires. The headline run is done first as T7.3's first step, and its runs are not this control |
| re-ranking | **built, off by default, then tested on vs off.** The plan's list stays complete, and production does not change |
| model tier | **the four specialists on Claude Sonnet 4.6**; triage, planner, synthesizer, scribe and proposer stay on Claude Opus 5 |

## The scenarios

**12 of the 26 dev fault scenarios**:

- one per class, by `random.Random(20261007).choice`, then three more by `.sample` over the rest;
- injection rows and holdout excluded;
- the script and output are in [`docs/evidence/t7.3/`](../../docs/evidence/t7.3/).

| scenario | class |
|---|---|
| `v2-frontend-cart-misconfig` | bad_config |
| `v2-cart-bad-image-tag` | bad_deploy |
| `v2-cart-store-corruption` | datastore_corruption |
| `v2-payment-dependency-latency` | dependency_latency |
| `v2-kafka-disk-fill` | disk_fill |
| `v2-fraud-detection-flag-queue-lag` | feature_flag |
| `v2-ad-partition` | network_partition |
| `v2-product-catalog-freeze` | process_freeze |
| `v2-payment-memory-squeeze` | resource_exhaustion |
| `v2-ad-memory-squeeze` | resource_exhaustion |
| `v2-valkey-cart-dependency-latency` | dependency_latency |
| `v2-currency-freeze` | process_freeze |

**Six of the 12 recorded pages were warning-only latency.** Five of them were a single service at
first firing, which is triage's written noise case (the headline registration's finding). The
gate is part of every Faultline arm and not of B1, so the gate rate is reported per arm, and
experiment 1 is also read with gated runs set aside.

## The ten configurations

**The control, F**: Faultline exactly as the headline run has it: `cap:91279a09`,
`prompts:9ce16b66bbcc`, every default.

**Each arm varies one dimension from F and nothing else**:

| config | dimension | what changes from F |
|---|---|---|
| **F** | control | nothing |
| **E1** | single agent vs specialists | B1 investigates (`--baseline b1`) |
| **E2** | topology scoping off | the blast radius is the whole graph: no hop limit, so every service in the catalog is in scope for triage, the planner's brief and the proposal check |
| **E3** | raw context | the synthesizer receives each cited tool result's full envelope instead of the evidence board's 400-character samples |
| **E4** | model tier per role | the four specialists on `claude-sonnet-4-6`; every other role on `claude-opus-5` |
| **E5** | retrieval off | no past-incident or runbook retrieval (`--no-corpus`) |
| **E6** | dense-only retrieval | hybrid's text arm off, dense only |
| **E7** | rerank on | a reranking step over the retrieved candidates, built for this and off by default |
| **E8** | temporal scoping off | every tool call reads from the earliest sample its store holds to the incident's end, instead of the incident window |
| **E9** | push-everything briefings | every role gets every briefing section in full at the start; nothing is disclosed on request |

**10 configurations × 12 scenarios = 120 runs.**

## The build, before any run

Shared with the headline run's build (that registration's *The order*, step 2), plus T7.3's own:

1. **A switch per dimension, E2 to E9**:
   - each is a setting whose default is today's behaviour;
   - each is recorded in the run manifest under its own key and in the config fingerprint;
   - each is passed through by `faultline-eval` and `faultline-sweep`.
2. **Two defects fixed, because two arms depend on them**: role models applied per role (E4),
   and the briefing budget applied (E9). With nothing set, both behave as today.
3. **The reranker (E7)**: its design registered in the build's addendum before it is coded
   (what reranks, at what cost, on which candidates). It is off by default.
4. **A randomized queue**: the 120 runs in one order, shuffled by a seed fixed in the operation
   addendum, so no configuration's runs fall together in time.
5. **The proof that F is unchanged**:
   - with every switch at its default, both stamps and the fingerprint inputs are as today;
   - a test per switch shows the default path takes the old code.

   **If either stamp moves, this registration is amended before any run.**

## Scoring and analysis, fixed now

- **Scoring is the headline registration's**: answered, abstained, gated (a miss on every axis)
  and no verdict, with the same discard and re-run rule.
- **Per experiment, the paired difference E − F over the 12 scenarios**, on:
  - fault-class accuracy, with coverage beside it;
  - culprit service;
  - cost;
  - time to report.

  Each has a 95 % interval by a bootstrap over scenarios (10,000 resamples, fixed seed). The gate
  rate is given per arm.
- **The MDE**, by the harness's own formula (`variance.mde`, paired, 80 % power, two-sided α 0.05,
  worst case p = 0.5, R = 1, n = 12):
  - **26 points at ρ 0.8**, the harness's assumption;
  - 40 points at ρ 0.5;
  - beside it, the v1 A/A floor of 10.0 points.

  Every report states this before its result.
- **A free A/A check**: F's 12 runs here against the headline run's F on the same 12 scenarios.
  A difference beyond the MDE between two runs of the same configuration says the instrument
  drifted, and every experiment is read in that light.
- **By class**: no class has five scenarios here, so nothing is read as a rate by class. The 12
  are described scenario by scenario.
- **The script is committed with the reports** and reproduces every figure from committed files.

## Predictions

Most differences are predicted inside the MDE, because 12 scenarios cannot resolve less than
26 points. **The costs are where this size can see something.**

| # | experiment | fault class and service | cost and time |
|---|---|---|---|
| E1 | single agent (B1) | **inside the MDE** (v1: 9 of 9 against 26 of 27) | **B1 costs 30-70 % less** and reports faster |
| E2 | topology off | inside the MDE | cost **0-30 % higher** |
| E3 | raw context | inside the MDE | cost **at least 15 % higher** |
| E4 | specialists on Sonnet | inside the MDE | cost **20-45 % lower** |
| E5 | retrieval off | inside the MDE (v1's corpus study: −9.3 points, sign reversed) | cost within ±15 % |
| E6 | dense-only | inside the MDE | cost within ±10 % |
| E7 | rerank on | inside the MDE | cost within +15 % |
| E8 | unbounded windows | inside the MDE, and **if a difference shows, it is negative** | cost **at least 10 % higher** |
| E9 | push-everything | inside the MDE | cost **at least 20 % higher** |

- **A/A**: F here and the headline's F on the same 12 differ by less than the MDE on fault
  class.
- **Nothing else moves**: both stamps are the same at the last run as at the first.

## The budget, as a hard stop

- **$120 for T7.3's switch trial and its 120 runs**: the owner's about $100 plus about $16 for the
  re-run control.
- **The estimate, unmeasured on v2**, in billed dollars from the v1 medians × 1.26: F $0.90, B1
  $0.43, and E2-E9 between $0.60 (E4) and $1.30 (E3). That is about $111 for the 120, plus about
  $8 for the trial.
- **Tallied after every run** by the headline registration's rule. **The batch stops when the
  tally passes $114.** The unfinished runs are named, and each experiment is reported on the
  scenarios where both it and F finished.
- **The estimate (about $119) is above the stop.** So the switch trial's measured costs are
  projected over the 120 at the owner's go (*The order*, step 4). **If the projection passes $114,
  the owner decides before any scored run**: raise the cap, or trim, and the trim is registered
  in `docs/DEVIATIONS.md`.
- **The owner's console reading is the authority.**
- **This is separate from the headline run's $60.**

## The order

1. **This registration**, with the headline run's, `docs/DEVIATIONS.md` and CLAUDE.md rule 9.
2. **The build**: the headline's items and T7.3's above, registered as an addendum before coding.
   The world decisions are asked one at a time.
3. **The trial**, never scored:
   - the headline's (3 dev scenarios × 4 arms);
   - T7.3's: one dev scenario outside the 12 under each of E2 to E9, 8 runs, proving each switch
     does what it says.
4. **The owner's go**, on both trials' measured cost and time, with the operation addendum: the
   queue, its seed, the nights, the world check.
5. **The headline run** (156 runs).
6. **T7.3's batch** (120 runs, randomized).
7. **The reports**:
   - **one dated report per experiment**, `evals/runs/ABLATION-<date>-E<n>-<name>.md`, each with
     its MDE first, then its result and the A/A reading;
   - `docs/ABLATIONS.md` gains the v2 series beside the v1 four;
   - `docs/DEVIATIONS.md` and the plan entry updated.

**T7.3 is finished when all nine reports are committed**, or when each missing one is registered
in `docs/DEVIATIONS.md` with the reason.
