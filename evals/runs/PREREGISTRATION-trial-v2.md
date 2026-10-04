# Pre-registration - the trial before the headline run and T7.3 (T7.3's step 3)

**Written 2026-10-04, before any trial slot runs.** This is step 3 of both registrations:
[the headline run's](PREREGISTRATION-headline-v2.md) (*"the trial, registered with the build's
result, shared with T7.3's trial"*) and [T7.3's](PREREGISTRATION-T7.3.md) (*"T7.3's: one dev
scenario outside the 12 under each of E2 to E9, 8 runs, proving each switch does what it says"*).

**The trial is never scored.** It measures that every piece works, what each arm costs and how
long it takes, and that each switch takes effect. Nothing it shows sets anything in the frozen
setup; a change it forces is an addendum, named, before the owner's go.

## The build's result

| part | merged | what |
|---|---|---|
| A | #650 | the world check in the repository (Alertmanager, quote's clock), the v2 catalog in the sweep, the freeze's v2 container, the v2 world's digests, a gated run scored as a miss |
| B | #650 | B0.4, B1 `aa84c9051695`, B2 `904de7de5fc5`: nine classes and the culprit service |
| C | #651 | the switches E2-E9, each off by default, recorded under `ablation_config` |
| D1 | #652 | `faultline-batch`: the queue, the checks before each slot, the registered tally and the stop; Q124 answered and the receiver check added |
| D2 | #653 | the corpus of record, pinned: 334 chunks, 65 documents, shape `b931588caf1d`, body `a6de378e3b55`, no holdout chunk; the retrieval gate re-founded on it |
| T7.1 | #654 | the storm label on 7 scenarios |

- **Faultline's stamps are unchanged**: `cap:91279a09`, `prompts:9ce16b66bbcc` (item 7).
- **Neither world digest moved**: no alert rule, compose file or injector definition changed.
  Alertmanager was started (Q124), which changes no file.
- **The corpus is frozen** from #653 until the last scored run, and the runner refuses a slot whose
  store is off either pin.

## Two corrections and one defect, found before anything ran

1. **The harness's kafka projection used v1's growth rate on v2** (the owner's decision of
   2026-10-04: use v2's measured rate). The gate projected kafka at 151 MB/h, T7.29's v1 figure.
   On v2 that refused any horizon over about ten runs with kafka at 38.6 % of its 1 GiB limit:
   this trial at its first slot, and the headline at every slot. v2's rate, measured off the
   world's own `container_memory_usage_total_bytes{container_name="kafka"}` over 24 hours
   ([reading](../../docs/evidence/t7.3/kafka/2026-10-04-kafka-24-hours.txt)), is **1.3 MB/h**: v2
   commits kafka's heap at start, and what can grow, the log directory's tmpfs, is capped at
   256 MiB. `gate.HEADROOM_GROWTH_MB_PER_HOUR_BY_WORLD` now gives each world its own rate, and v1's
   is unchanged. This is a harness defect fixed by addendum, as both registrations allow, and it
   is in `docs/DEVIATIONS.md`.
2. **E9's check, corrected.** T7.3's Addendum 1 says the switch trial shows *"a pull rate of zero
   for E9"*. That cannot hold: the pull rate counts every tool envelope a specialist reads
   (`Disclosure`), and push leaves the specialists unchanged (part C). **The check is**: E9's
   briefings carry the push sections with nothing dropped, and E9's pull rate is below F's on the
   same scenario.
3. **E7's revision, pinned before the queue is printed.** Part C refuses an unpinned reranker. The
   owner resolves the commit on the Mac (*Before the trial*) and it is written into the switch
   trial's queue header, which is committed before the slot runs.

## The scenarios

- **The headline's trial**: *"three dev scenarios by `random.Random(20261004).sample` over the
  sorted dev ids"*, which draws **`v2-cart-bad-image-tag`, `v2-ad-bad-image-tag` and
  `v2-product-catalog-freeze`**, all four arms each: 12 slots.
- **T7.3's switch trial**: one dev scenario outside T7.3's 12. **The first of the three above that
  is outside them**, so the headline trial's F run on it is each switch's comparison at no extra
  run: **`v2-ad-bad-image-tag`**. Its page is two critical `ServiceHighErrorRate` alerts, so
  triage's noise rule for a warning-only page cannot gate it. E2 to E9 once each: 8 slots.
- Two of the three (`v2-cart-bad-image-tag`, `v2-product-catalog-freeze`) are among T7.3's 12 and
  all three are dev scenarios the headline run scores. **That is the design** (*"three dev
  scenarios"*): a trial run is never scored and is never retrievable by a later run.

## The queues

Printed by `faultline-batch queue` and committed before the trial:

| queue | kind | seed | slots | label | stop |
|---|---|---|---|---|---|
| `QUEUE-trial-headline-v2.tsv` | `trial-headline` | 20261004 | 12 | `trial-headline-v2` | **$8** |
| `QUEUE-trial-t73-v2.tsv` | `trial-t73` | 20261007 | 8 | `trial-t73-v2` | **$12** |

- **The stops are new, and each is about one and a half times its estimate**: the headline's trial
  was registered at about $5 (F at most $1.10, B1 $0.60, B2 $0.10, three times), and the switch
  trial at about $8 (E2-E9 between $0.60 and $1.30). The worst case for both is about $20 and one
  run of overshoot.
- **Each trial counts inside its own task's cap**: the headline's trial inside the $60 (the
  headline batch passes `--also-count trial-headline-v2`), the switch trial inside T7.3's $120
  (`--also-count trial-t73-v2`).
- **The headline's trial judges its F runs** on `claude-haiku-4-5`, to measure the judge's cost.
  The switch trial judges nothing.

## What the trial measures

**Every piece works.** Each slot passes its checks, launches, exits with a recorded outcome
(scored, gated or a discard with its reason), and is tallied. The runner's dry run happens first.

**Cost and time per arm**: the tally per slot, by the registered rule, and each manifest's start
to finish. These are what the owner's go projects over the 156 and the 120.

**kafka under runs**: the gate records kafka's percent before every slot. If it rises faster than
1.3 MB/h of run time across the 20 slots, the go is told before any scored run.

**Each switch takes effect**, read off its run's record against F's run on the same scenario:

| arm | what shows the switch took effect |
|---|---|
| E2 | `ablation_config.hop_radius` 99, and triage's blast radius holds more services than F's, some past 2 hops |
| E3 | the synthesizer's briefing larger than F's |
| E4 | the trajectory's `role_models` names `claude-sonnet-4-6` for the four specialists |
| E5 | no retrieval record in the trajectory; F's has one |
| E6 | every retrieval score at or below one arm's maximum, 1/(60+1), which a hybrid hit seen by both arms exceeds |
| E7 | the transcript's `reranker: ... at revision <the pinned commit>` line |
| E8 | the tool results' windows reach back about 7 days; F's cover the incident window |
| E9 | the briefings carry the push sections with nothing dropped, and the pull rate is below F's |

**An arm whose switch does not show is a defect**, fixed by addendum before the go, and its arm
does not run in T7.3 until the fix is shown on one more trial slot.

## Before the trial (the owner's steps, $0)

1. **Funds** on the Anthropic account, and a monthly spend limit on the console.
2. **E7's commit**: `huggingface_hub`'s `model_info("cross-encoder/ms-marco-MiniLM-L-6-v2").sha`,
   and the model downloaded at that commit so no slot downloads it.
3. **The platform**: Postgres, Redis and MinIO up (`docker compose --profile eval up -d --wait`),
   and in two terminals, each with `FAULTLINE_TOOLS_WORLD=v2` (the orchestrator correlates on the
   v2 graph only when told the world): `faultline-ingest` and `faultline-orchestrate`, without
   `--investigate`.
4. **The world check passes**, with the receiver now answering.
5. **The dry run**: `faultline-batch run ... --dry-run` on both queues.
6. **The Mac kept awake**: `caffeinate -is` around each batch command.

## What this does not touch

- No stamp, no world digest, no corpus.
- No scored figure: the trial's runs carry their own labels, and no analysis reads them.
- The owner's go (step 4) comes after the trial, on its measured cost and time, with the operation
  addendum (the headline's queue seed, the nights, the blocks).
