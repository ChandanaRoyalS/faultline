# Pre-registration - the headline run on the v2 catalog (T7.3's first step)

**Written before the build it needs and before any run. Nothing here is a result.**

**Why this run exists.** The execution plan's T7.1 delivered the catalog, *"30+ scenario catalog,
the project's headline dataset"*: 39 valid v2 scenarios, 29 dev and 10 holdout
([`SPLIT-V2.md`](../scenarios/SPLIT-V2.md)). **The scored run that makes it the headline is asked
for by four other rows**:

- **T1.6**: *"holdout-only headline thereafter"* once the catalog reaches 30+;
- **T5.3**: switched on *"when T7.1 brings the holdout to ~9–10 scenarios"*;
- **T4.7**: three baselines *"scored by the same judge, at the same R, on the same catalog,
  appearing in every headline table"*;
- **T7.5**: the writeup carries the number.

No scored run exists on v2.

**Where it sits.** By the owner's decision of 2026-10-04 this run is **T7.3's first step**, done
before T7.3's ablations ([`PREREGISTRATION-T7.3.md`](PREREGISTRATION-T7.3.md)), at the owner's
scale of 2026-10-03 (R = 1, with B0, B1 and B2).

- It was first written under the name "T7.1 headline", a cost row's label that is not the plan's
  T7.1. That is corrected here before anything ran (`docs/DEVIATIONS.md`).
- **Its runs are not T7.3's control.** T7.3 re-runs its control and B1 inside its own randomized
  batch, as the plan's T7.3 row requires.

**What this registration fixes**:

- the scenarios and the split;
- the four arms;
- how a run is scored, including a run triage declines;
- the analysis;
- the predictions;
- the budget;
- the order of work.

**What it does not fix**:

- the build's designs;
- the four v2 world decisions the queue owes before a scored run;
- how the batch is operated.

Each is registered before it is coded or run (*The order*).

## The questions

1. **The headline.** Faultline's fault-class accuracy (with coverage) and culprit-service accuracy
   on the **10 holdout scenarios** of the v2 catalog, at R = 1.
2. **The baselines.** The same figures for B0, B1 and B2 on the same 10, and the paired
   difference against each.
3. **The diagnostic set.** The same on the 29 dev scenarios, reported apart and labelled
   diagnostic.
4. **The gate.** How often Faultline's triage declines a real incident on its own world. T7.2's
   report asks this: 20 of 33 were declined under SREGym.

## What may be claimed, fixed now

Every published sentence about the result carries these, or it is not published:

1. **Holdout-only headline, n = 10, R = 1.** The 29 dev scenarios are diagnostic. Faultline's
   prompts were fitted on v1's dev scenarios, and three v2 holdout scenarios repeat v1 holdout
   designs (*Read before registration*).
2. **Faultline's own world**: the OpenTelemetry Demo 2.2.0 on the owner's Mac, with Faultline's
   telemetry, alert rules and injector. It is not an external benchmark; T7.2 is that.
3. **R = 1, below the plan's R = 5** (T4.6), by the owner's decision of 2026-10-03. Every figure
   carries n, R and its interval. A difference inside its MDE is *no measurable effect at this n*.
4. **The baselines know nine classes** from this run's build on, and their figures are not
   comparable with the four-class figures of 2026-09-21.
5. **Two classes have no holdout scenario**: `datastore_corruption` (2 dev) and `disk_fill`
   (2 dev, one of them the injection row). Nothing here tests generalisation to either.

## Read before registration

- **The catalog** (`evals/scenarios/v2/`, `SPLIT-V2.md:120-162`): 39 valid scenarios, each
  `rehearsed: true` with a bundle and no `INVALID.md`. Every bundle is on one world:
  - `compose_digest` `5a2bc6d912f9…`;
  - `observability_digest` `7d6097ab0f00…`;
  - `Darwin/arm64`;
  - recorded 2026-09-27 to 09-30.

  Four further files are `blocked: true` and kept for history. Five of the 44 slots are empty and
  named as gaps (PLAN, 2026-09-30).
- **No scored run exists on the v2 world**, at any stamp:
  - Q86, Q123 and Q124 say so;
  - the newest run directory is `20260921T121603Z-shipping-wrong-image`, a v1 run;
  - README: *"no runs yet at `prompts:9ce16b66bbcc`"*.
- **The harness cannot run v2 as it stands.** Read from the code, not yet run:
  - `faultline-sweep` lists `evals/scenarios/*.yaml` only (`sweep.py:184`), so it sees v1 alone,
    as `SPLIT-V2.md:13-15` says;
  - the freeze reads its world from `cart-service` (`freeze.py:183`). v2's container is `cart`,
    and `rehearse.py:139-141` records that asking for `cart-service` on v2 *"returns nothing and
    records `None`"*. A `None` freeze field refuses the run (`run.py:1501-1513`);
  - `generations.py` names no v2 world, and `compare` counts the catalog from v1's `runnable()`;
  - the holdout-headline branch (`compare.py:287-293`) has never run (`pragma: no cover`).
- **Triage in the harness.**
  - The agent arm runs triage's gate (`cli.py:352-355`; the harness never passes `--no-gate`).
  - A `noise` disposition exits `GATED = 5` (`runner.py:64`, `:222-244`) and writes no verdict. The
    harness then records it as a **discard**, `run failed` (`run.py:235`, `:1822-1827`).
  - No v1 harness run was ever gated: 202 of 202 `triage judged:` lines say `investigate`.
  - The baselines return before the gate (`cli.py:268-281`).
  - **12 of the 39 recorded pages were warning-only**: `ServiceHighLatency` alone, the rules'
    only warning (`alert-rules-v2.yml:130`). **9 of them were on a single service at first
    firing** (`alerts_at_fire` in each manifest). That is triage's written noise case: *"a single
    warning-severity latency alert on one service with no error-rate alert anywhere"*
    (`roles.py:257-260`).
    - Three of the 12 are holdout: `v2-email-flag-memory-leak`,
      `v2-product-catalog-dependency-latency` and `v2-recommendation-partition`.
    - No recorded page was on `load-generator` alone.
- **The baselines** (`baselines.py`, `baseline_agent.py`, `baseline_prior.py`):
  - they name four classes (Q92), so on the five new classes a baseline can at best abstain;
  - their verdicts carry no `service`, though B1's and B2's prompts ask for one
    (`baseline_agent.py:399`, `:455-463`; `baseline_prior.py:116`, `:308-316`);
  - their one measurement (`BASELINES-2026-09-21.md`, v1, 10 dev, R = 1): fault class B0.3 4/10,
    B2 6/10, B1 9/9; median cost $0, $0.036 and $0.341.
- **The agent's last costs and times**, all on v1 at `prompts:06f24e827915`:
  - dev sweep 12 arm A, median $0.713 and 251.6 s to report;
  - T6.5's WITH arm, median $0.698;
  - one run start to finish, median 925-941 s;
  - the sweep's settle, 300 s.
- **Cost counting** (T7.2's console reading, 2026-10-04):
  - trajectory tokens are 21 % below the bill, because triage's call and others are not
    persisted, so the counted figure is multiplied by 1.26;
  - the sweep's own `--max-usd` reads trajectory tokens alone (`spend.py:86-110`).
- **The holdout rule** (ADR-0022 §3.3 and its T4.8 addendum):
  - a holdout run happens *"once per reported result"* and is never re-run to fix a number;
  - an entry needs four things: validated on dev first, justified by a mechanism, a prediction
    registered before the run, and earlier entries left as published.
  - **This is the v2 holdout's first entry.** The v1 ledger (entries 1-3; entry 4 not opened)
    belongs to another world.
- **The headline policy.**
  - ADR-0008's T1.6 addendum made the full-set headline permanent under v1, because the holdout
    could not pass three scenarios there.
  - Its own condition for changing that was *"a different demo world"*. v2 is that world
    (ADR-0042), and its holdout is 10.
- **Three v2 holdout scenarios repeat v1 holdout designs** (`t7.1-candidates.md:19-30`):
  `v2-email-wrong-image`, `v2-product-catalog-dependency-latency` and
  `v2-recommendation-memory-squeeze`. Their v1 versions had 3, 2 and 2 agent exposures
  (ADR-0022:717-718).
- **The stamps**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, unchanged since T7.2
  (`evals/attempts/T7.2-adapter-fixes/RESULT.md`).
- **The queue items that say *before any scored v2 run***:
  - Q121: quote's clock after the Mac sleeps;
  - Q123: `frontend-proxy`'s `ServiceNoTraffic` exclusion;
  - Q124: Alertmanager is not running on the Mac's v2 world, so no alert reaches Faultline;
  - Q108: the flagd stream reconnect pages when orders stop.

  Also Q92 (the baselines, decided below) and Q86 (the capability stamp does not encode the world).

## The owner's decisions, 2026-10-03 and 2026-10-04

| decision | chosen | why, in one line |
|---|---|---|
| the scale (2026-10-03) | **the 39 scenarios, R = 1, the agent with B0, B1 and B2** | the owner's budget; every deliverable kept, the evidence smaller |
| where it sits (2026-10-04) | **T7.3's first step**, before the ablations | the headline numbers T4.7 and T7.5 need, done on the way; nothing labelled T7.1 that is not T7.1 |
| the headline | **holdout only, as the plan says**: the 10, with the 29 dev reported apart as diagnostic | T1.6 and T5.3; the v1 addendum's own condition, a different world, is met |
| the baselines | **updated to the nine classes** before the run | T4.7's *"on the same catalog"*; a four-class baseline loses five classes by construction (Q92) |
| a run triage declines | **scored as a miss, with the gate on** | the agent under test is the real one; a declined real incident is a failure, and this measures how often |
| the budget | **$60 for the build's trial and the run**, raised from $45 | the measured per-run cost and T7.2's correction give about $55-60 for 156 runs |

**Two things followed from those decisions rather than being asked separately:**

- **The baselines' `service` is carried into their verdicts** in the same build. Their prompts
  already ask for it, and without it the headline's culprit axis has no baseline column.
- **ADR-0008 gains an addendum** recording that the headline is holdout-only on v2. It is
  committed with this registration.

## The scenarios

**All 39**, by fault class. The injection rows count under their base's class, as `SCHEMA.md`
says:

| class | dev | holdout | holdout scenarios |
|---|---|---|---|
| `bad_config` | 4 | 2 | `v2-accounting-kafka-misconfig`, `v2-checkout-currency-misconfig` |
| `feature_flag` | 5 | 2 | `v2-payment-flag-unreachable`, `v2-email-flag-memory-leak` |
| `bad_deploy` | 3 | 2 | `v2-email-wrong-image`, `v2-inj-email-wrong-image-log-checkout` |
| `dependency_latency` | 4 | 1 | `v2-product-catalog-dependency-latency` |
| `resource_exhaustion` | 3 | 1 | `v2-recommendation-memory-squeeze` |
| `process_freeze` | 3 | 1 | `v2-payment-freeze` |
| `network_partition` | 3 | 1 | `v2-recommendation-partition` |
| `datastore_corruption` | 2 | 0 | none |
| `disk_fill` | 2 | 0 | none |
| **total** | **29** | **10** | |

- **The ids, slots and bundles are `SPLIT-V2.md:120-162`'s**, and nothing here changes them.
- **A scenario that will not run** is named and removed from every arm's denominator, never
  scored as a miss for any arm. Not running means the gate refuses it twice, or its injection or
  alert fails on both tries (*Scoring*).
- **The four injection scenarios** are scored on the same axes as the others. T6.8's own record
  (whether the decoy was named, whether the canary was disclosed) is read as recorded, and they
  are described one by one.

## The arms

| arm | what investigates | model | gated? |
|---|---|---|---|
| **F, Faultline** | the agent as it stands: triage, planner, four specialists, synthesizer, scribe | `claude-opus-5`, as `AgentSettings` has it | yes |
| **B0** | no model: alert attribution, most recent change, largest error delta | none | no |
| **B1** | one agent, all four tools, no fan-out | the baseline's configured model | no |
| **B2** | the alert text and the service catalog, no tools | the baseline's configured model | no |

- **Every arm runs its own live injection** of the same scenario, through the same gate, recorder
  and scorer. That is the harness's design: *"the only difference is what investigates"*
  (`run.py:1076-1077`).
- **The baselines' models are what their code configures today.** The build records them, and
  changes nothing but the class list and the service field.

## The setup, frozen

- **The world**:
  - the v2 world at the bundles' `compose_digest` `5a2bc6d912f9…` and `observability_digest`
    `7d6097ab0f00…`, on the Mac, `FAULTLINE_TOOLS_WORLD=v2`;
  - **if any world decision below changes either digest**, the precedent of 2026-09-27 applies:
    the affected bundles are re-recorded and this registration is amended before the run.
- **Faultline**: `cap:91279a09` and `prompts:9ce16b66bbcc`, hop radius 2, retrieval as in
  production. **A stamp that differs at run time invalidates the run until this registration is
  amended.** The build must leave both unchanged.
- **The corpus**: frozen for the whole run, holding no holdout chunk (the harness refuses one,
  `run.py:1518-1526`). Which corpus is the build's to state. Nothing a run produces is retrievable
  by a later run.
- **The per-incident budget**: `Budget.max_usd` $2, as it stands.
- **The judge**: `faultline-judge` on the agent arm's narratives, on `claude-haiku-4-5` with
  `FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE=1`, as all 79 judged runs so far. **It is not a headline
  axis.**
- **Nothing is tuned** between the trial and the run, or during the run, except the harness's own
  defects. Any of those is named, and fixed only by an addendum.

## Scoring, fixed now

- **The axes** are the harness's own (`run.py:983-1029`), from each scenario's labels:
  - **fault class**, the headline;
  - **culprit service**, the plan's root-cause top-1;
  - **fix class**;
  - top-3 class and service.
- **Each run is one of four outcomes**:

  | outcome | what it is | how it counts |
  |---|---|---|
  | **answered** | a verdict naming a class | right or wrong on each axis |
  | **abstained** | a verdict of `unknown` | as ADR-0022 §1.2: outside the accuracy ratio, inside coverage |
  | **gated** | triage declined: exit `GATED`, no verdict | **a wrong answer on every axis**, in every denominator, and counted apart as the gate rate (the owner's decision). The build makes the harness record it as `gated`, not as a discard |
  | **no verdict** | the investigation ended without one for its own reasons (its budget, its timeout, a crash in the agent) | a wrong answer on every axis, counted apart |

- **Accuracy is quoted with coverage, never apart**, as the README requires:
  - accuracy = right ÷ (answered + gated + no verdict);
  - coverage = (answered + gated + no verdict) ÷ scored.

  So a gate lowers accuracy, and an abstention lowers coverage.
- **A discard is the harness's or the world's**: refused before injecting, `no-alert`,
  `metrics-gap`, the incident resolved before investigation, a lost model connection before the
  investigation started.
  - A discarded run is **re-run once**, at the end of its pass.
  - A second discard removes that scenario from every arm, and it is named.
  - **This holds for holdout scenarios too**: re-running a run that never reached an
    investigation does not fix a number.
- **Holdout runs need `--holdout`**, as the harness requires (`run.py:1348-1350`). The holdout pass
  runs only after the whole dev pass, which meets ADR-0022's *"validated on dev before holdout is touched"*.

## The analysis, fixed now

- **The unit** is a run: one scenario, one arm, R = 1.
- **The headline table**: the 10 holdout scenarios, the four arms side by side. For each arm:
  - fault-class accuracy with coverage;
  - culprit service;
  - fix class;
  - the gate rate (F only);
  - median cost and median time to report.

  Every rate carries a **95 % interval by a bootstrap over scenarios** (10,000 resamples, fixed
  seed) and a Wilson interval beside it.
- **The paired differences**: F − B0, F − B1 and F − B2 on fault class and service, each a mean
  over scenarios with a bootstrap interval.
- **The diagnostic table**: the same on the 29 dev scenarios, labelled diagnostic.
- **The minimum detectable effect**, by the harness's own formula (`variance.mde`: paired, 80 %
  power, two-sided α 0.05, the worst case p = 0.5, R = 1):

  | set | n | MDE at ρ 0.8 (the harness's assumption) | at ρ 0.5 |
  |---|---|---|---|
  | holdout (the headline) | 10 | **28 points** | 44 points |
  | dev (diagnostic) | 29 | **16 points** | 26 points |
  | all 39 | 39 | 14 points | 22 points |

  A difference inside these is *no measurable effect at this n*.
- **By class**: per class and split, as counts. **No class has five holdout scenarios, so none is
  read as a rate**; the holdout is described scenario by scenario, as T7.2's Addendum 1 required.
- **Read separately**:
  - the gated runs (alarms, triage's reason, and whether an alarm named the true service);
  - the four injection scenarios;
  - the three holdout scenarios with v1 holdout designs, as corroborative, not confirmatory
    (ADR-0022:663).
- **Non-headline**: the judge's root-cause agreement on F's narratives; cost and time per arm.
- **A prediction whose range is narrower than its interval** is reported as *not testable at
  this n*, never as held.
- **The script is committed with the result**, standard library, and reproduces every figure from
  committed files.

## Predictions

| # | prediction | falsified by |
|---|---|---|
| 1 | **F's fault-class accuracy**: dev 50-85 %, holdout 40-90 % | outside either range |
| 2 | **F's culprit service**: dev 50-80 %, holdout 40-90 % | outside either range |
| 3 | **Triage gates at most 4 of F's 39 runs, and only among the 12 warning-only pages.** On v1 it gated 0 of 202 harness runs at the same noise rule, warning-only latency pages included. The 9 single-service latency pages match its written noise case at first firing, but more alerts usually join in the 90 s settle before triage runs | 5 or more gated, or a gate on a page with a critical alert |
| 4 | **F abstains on at most 25 % of its runs** | more |
| 5 | **Among the baselines, B1 scores highest on fault class and B0 lowest**, on the 39 | any other order |
| 6 | **F − B1 on holdout fault class is inside the 28-point MDE.** On v1, B1 scored 9 of 9 against the agent's 26 of 27, so the fan-out's advantage, if any, is smaller than this n resolves | a difference beyond the MDE in either direction |
| 7 | **F − B0 and F − B2 on the 39 are positive.** Read against the 14-point MDE | either at or below zero |
| 8 | **Cost per run, billed** (counted × 1.26): F $0.60-1.10, B1 $0.25-0.60, B2 at most $0.10, B0 $0. **The whole trial and run within $60** | outside a range, or over $60 |
| 9 | **Time per run** start to finish 10-18 minutes, plus the 300 s settle. **Discards** at most 10 % of runs (`DISCARD_RATE` is 0.09) | outside either |
| 10 | **Nothing else moves**: both stamps and both world digests the same at the last run as at the first | any change |

**Prediction 6 is the one worth watching.** If it holds, the headline cannot say the multi-agent
pipeline beats one agent with the same tools on this catalog. That is what T4.7's B1 exists to
expose.

## The budget, as a hard stop

- **$60 for the trial and the scored run**, the owner's decision of 2026-10-04.
- **Tallied after every run** from recorded tokens at the published prices:
  - agent and baseline tokens × 1.26 (T7.2's correction);
  - each judge call from its own tokens;
  - each pre-flight probe at its token.
- **The batch stops when the tally passes $57.** The unfinished runs are named, and the result is
  reported on the scenarios where every arm finished.
- **The estimate ($55-60) reaches the stop.** So the trial's measured costs are projected over
  the 156 at the owner's go. **If the projection passes $57, the owner decides before any scored
  run**: raise the cap, or trim, and the trim is registered in `docs/DEVIATIONS.md`.
- **The owner's console reading is the authority**, taken once the run ends.

## The order

1. **This registration**, with T7.3's, ADR-0008's addendum, Q92's row marked decided, and `docs/DEVIATIONS.md`.
2. **The build**, shared with T7.3's and registered as an addendum here before it is coded:
   - `faultline-sweep` lists the v2 catalog when asked, and v1's consumers see what they see
     today;
   - the freeze reads v2's world from its own container;
   - `generations` and `compare` know the v2 world and its catalog size, and the holdout-headline
     branch runs;
   - a gated run is recorded and scored as `gated`;
   - **B0, B1 and B2 name the nine classes and carry `service`**, each with its new version or
     digest recorded;
   - the batch's tally and stop rule;
   - **the four world decisions, each the owner's, asked one at a time with a recommendation**:
     Q124 (start Alertmanager), Q121 (quote's clock), Q123 and Q108 (two alert rules);
   - the corpus of record.

   Both stamps must be unchanged at the end. If a world decision moves a digest, the bundles it
   touches are re-recorded first.
3. **The trial**, registered with the build's result, shared with T7.3's trial:
   - three dev scenarios by `random.Random(20261004).sample` over the sorted dev ids, all four
     arms: 12 runs, about $5 and four hours;
   - it measures that every piece works, the cost and the time;
   - **it is never scored**, and it sets nothing in the frozen setup. A change it forces is an
     addendum.
4. **The owner's go**, on the trial's measured cost and time, with **how the batch is operated**:
   - the queue: dev pass then holdout pass, each scenario's four arms back to back in a rotating
     order, the scenario order shuffled by a seed fixed then;
   - the nights;
   - keeping the Mac awake;
   - the world check before each batch.
5. **The scored run**: 156 runs.
6. **The report**: the headline table with its baselines, the diagnostic table, the gate, the
   error analysis by class, and what it means for the architecture. README's results section
   moves to the holdout headline.

## What this does not touch

- **No code, no stamp and no world** changes with this registration.
- **T7.2's result stands as published.** Nothing here re-scores it.
- **The v1 holdout ledger stays closed** (ADR-0029, entry 4 not opened). This is a different
  world's first entry.
- **T7.3's ablations** are registered beside this ([`PREREGISTRATION-T7.3.md`](PREREGISTRATION-T7.3.md)). They share this run's build and run after it, with their own control.
