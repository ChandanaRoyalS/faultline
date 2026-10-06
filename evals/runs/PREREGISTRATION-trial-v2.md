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

## Addendum 1 - E7's revision and the two queues (2026-10-04)

- **E7's commit, resolved on the Mac by the owner**: `233902d25c440f23af6f7d6e94d2946bac0bee0a`
  for `cross-encoder/ms-marco-MiniLM-L-6-v2`, read by `huggingface_hub`'s `model_info` and
  downloaded at that commit, so no slot downloads it.
- **The queues, committed before any slot runs**, printed by `faultline-batch queue`:
  [`QUEUE-trial-headline-v2.tsv`](QUEUE-trial-headline-v2.tsv) (seed 20261004) and
  [`QUEUE-trial-t73-v2.tsv`](QUEUE-trial-t73-v2.tsv) (seed 20261007, E7's commit in its header).
  `tests/test_batch.py` holds each equal to what its seed prints.

## Addendum 2 - the first attempt ran nothing, and what it found (2026-10-04)

**No slot reached injection and no model call was billed**: every pre-flight failed on a missing
key, so the runner's $0.01 is its estimate for probes that never billed. Log:
[`docs/evidence/t7.3/trial/2026-10-04-attempt-1.log`](../../docs/evidence/t7.3/trial/2026-10-04-attempt-1.log).

| what refused | why | fixed by |
|---|---|---|
| the pre-flight, 62 times | `faultline-eval` reads `ANTHROPIC_API_KEY` only; the owner's key is in `~/.faultline-anthropic-key`, which only `make demo` read | the runner passes the file's key to every slot, never printing it, and refuses to start with no key |
| the runner, for 90 minutes | it retried each slot six times and went on to the next, through all twelve | a slot refused on every attempt stops the batch, as the sweep's `standing_refusal` does |
| the world lock, once | `make check` run beside the batch: `tests/test_rehearse.py` took the real lock | `tests/conftest.py` gives every test its own lock; a held lock is retried, not discarded |
| the gate, 24 times | **kafka serving no traffic**, then latency alerts on load-generator, frontend-proxy and checkout | **a world fault, not the harness's**: diagnosed read-only before anything is changed |

- **The dry run is now read-only**: it reports the world check and does not restart quote. The
  first dry run had restarted it.
- **Nothing in the frozen setup moved**: no stamp, digest, corpus, queue or stop. The queues run
  from slot 1 again under the same labels. Each refused attempt left a run directory recording its
  refusal; none carries the batch's label (a refusal comes before the label is written), so no
  tally or analysis reads them.

## Addendum 3 - kafka's silence was the gate's, not the world's (2026-10-04)

The read-only diagnosis
([output](../../docs/evidence/t7.3/trial/2026-10-04-kafka-diagnosis.txt)) found **the world
healthy**:

- **kafka's own span rate was 0.00 at every 30-minute point for twelve hours**, while checkout
  wrote orders at 1.0-2.5 a second and kafka's consumers read them, accounting at 0.2-0.5 and
  fraud-detection at 0.15-0.35. Nothing was firing at the reading.
- **Q118 had already measured why**: v2's broker emits no spans at rest. Its spans come only from a
  Kafka command-line tool run inside its container. A9 created a `kafka` series on 2026-09-30, and
  from then the gate read that series at zero as *"serving no traffic: kafka"*: every v2 run
  since would have been refused.

**Fixed as a harness defect, by addendum** (the same class as Addendum 1's growth rate):
`gate.EXPECTED_SILENT_BY_WORLD` excuses kafka on v2 only. v1 is unchanged, and a silent kafka
*consumer* still refuses on v2. kafka's health on v2 is read by the world check and by its
consumers' spans. In `docs/DEVIATIONS.md`.

**Two things the diagnosis did that it should not have**, both recorded:

- **its last step ran `kafka-consumer-groups.sh` inside kafka's container**: the thing Q118 says
  pages on itself. It failed to connect (the broker does not listen on `localhost` there) and
  read nothing. Any `kafka` alert it left is waited out by the world check's *nothing firing*
  before slot 1;
- checkout's last log lines are a panic stack in `sendToPostProcessor`, undated. With checkout's
  traffic normal for twelve hours and its consumers reading, it is history (two restarts, the last
  on 2026-09-29), not a live fault, and is noted rather than acted on.

The latency alerts that stopped the first attempt (load-generator, frontend-proxy, checkout) had
cleared by the diagnosis, and the world check before every slot still requires nothing firing.

## Addendum 4 - the second attempt: twelve slots ran, and F met a v1 corpus (2026-10-04)

All twelve slots ran (log: [`attempt-2.log`](../../docs/evidence/t7.3/trial/2026-10-04-attempt-2.log)).
**The runner's tally: $5.97**, inside the $8 stop; the owner's console reading is the authority.

| slot | arm | scenario | outcome | billed (cost × 1.26) |
|---|---|---|---|---|
| 1 | F | v2-cart-bad-image-tag | **invalid**: culprit `cart` right, class abstained | $0.89 |
| 2-4 | B0, B1, B2 | v2-cart-bad-image-tag | scored; B1 right on class and culprit | $0, $0.62, $0.05 |
| 5-7 | B0, B1, B2 | v2-product-catalog-freeze | scored | $0, $2.40, $0.05 |
| 8 | F | v2-product-catalog-freeze | **discarded**: failed mid-investigation | $0.20 |
| 9-10, 12 | B1, B2, B0 | v2-ad-bad-image-tag | scored; B1 right on class and culprit | $0.76, $0.05, $0 |
| 11 | F | v2-ad-bad-image-tag | **invalid**: class, culprit and fix all right | $0.96 |

**Faultline works end to end on v2**: two investigations reached cited verdicts, one fully right.
**Three findings, each blocking:**

1. **Both `invalid` runs were invalidated by the leave-one-out rule, and every holdout run would
   be.** The rule voids a run whose exclusion removes nothing. On a v1-only corpus no v2 narrative
   is there to remove, and a holdout narrative is never in any corpus (ADR-0008 axis 1). The
   harness has scored no holdout run since the rule landed. **Fixed** (`run.absence_assertion`): a
   silent exclusion is accepted only when it excluded exactly the scenario's own origin, the
   absence was decided before the run (`run.absence_by_design`: a holdout scenario, or one the
   seeder skips for this world's corpus), and the corpus holds no chunk of that origin, counted at
   run time. A dev narrative the seeder should have written and did not still invalidates.
2. **Slot 8's planner dispatched `productcatalogservice`, v1's name for `product-catalog`, twice**,
   and the plan had nothing legal left. The corpus was v1's alone: fifteen service runbooks with
   v1 names, v1's world runbooks, ten v1 postmortems and ten v1 narratives.
   **The owner's decision of 2026-10-04: a v2 corpus.** `faultline-seed --world v2 --replace`
   writes v2's 29 dev narratives and the 14 runbooks that describe no one world (the nine class,
   four action and `alert-high-error-rate`), and removes everything else. The two other alert
   runbooks state v1 facts and stay out. 43 documents, 200 chunks, no holdout document. **v1's
   corpus is unchanged** (65 documents, `b931588caf1d`), and so is the retrieval gate founded on
   it. v2's pins are set from the owner's ingest, in the commit that records it.
3. **The money, for the owner's go.** Measured per run, billed: F $0.89-0.96, B1 $0.62-2.40, B2
   about $0.05, B0 $0. **Projected over the 156: about $87, against the $60 cap and its $57
   stop.** As registered, the owner decides at the go: raise the cap or trim, and a trim goes in
   `docs/DEVIATIONS.md`. B1 rests on three runs, one of them $2.40.

**What runs again, and what stands.** The corpus does not touch the baselines, which retrieve
nothing, so **their nine trial runs stand**. Only F runs again, its three slots in the trial's order
([`QUEUE-trial-headline-f-v2.tsv`](QUEUE-trial-headline-f-v2.tsv), label `trial-headline-f-v2`,
stop $4, judged), after the v2 corpus is pinned. Both trial labels count inside the headline's $60.
The switch trial follows on the same corpus, its comparison the new F run on `v2-ad-bad-image-tag`.

**Also found**: after slot 12, `ad` sat at 90.3 % of its memory limit and the world check refused
the end-of-pass re-runs. A restart of `ad` (no digest moves) before the next slot, recorded when it
is made.

## Addendum 5 - the v2 corpus, pinned (2026-10-04)

Ingested on the Mac by the owner (`faultline-seed --world v2 --replace`: 43 documents, 200 chunks,
279 chunks of v1 documents removed) and read back
([record](../../docs/evidence/t7.3/corpus-of-record-v2.json)): shape `738e834925e0`, body
`8d75e8acc4b1`, `holdout_chunks` 0, agreeing with the tree. `generations.CORPUS_PINS_BY_WORLD["v2"]`
is set in this commit, and the runner refuses a v2 slot off either pin. **Frozen from here until
the last v2 scored run.** v1's pins and the retrieval gate founded on them are unchanged. `ad` had
fallen to 75 % of its limit by itself; no restart was made.

## Addendum 6 - F's three slots on the v2 corpus: all scored; the headline's trial is complete (2026-10-04)

Log: [`attempt-3-f.log`](../../docs/evidence/t7.3/trial/2026-10-04-attempt-3-f.log). **The runner's
tally: $2.79** (stop $4). With Addendum 4's nine baseline runs, every one of the trial's twelve
slots now has a counted run.

| slot | scenario | class | culprit | fix | billed | start to finish |
|---|---|---|---|---|---|---|
| 1 | v2-cart-bad-image-tag | right | right | right | $0.96 | 15 min |
| 2 | v2-product-catalog-freeze | wrong (`bad_deploy` on `cart`) | wrong | wrong | $0.92 | 15 min |
| 3 | v2-ad-bad-image-tag | right | right | right | $0.88 | 18 min |

- **The leave-one-out filter fired on every retrieval** (5 chunks removed each time), so the runs are
  valid by the rule as written, not by Addendum 4's absence clause. The judge scored all three
  (`same_mechanism`, `different`, `same_mechanism`).
- **Slot 2's miss is Q57's confound**: its planner read the cart hotfix change record that slot 1's
  injection had written twenty minutes earlier and named it the cause. The harness's own injections
  are the only writer of change records, and a run reads the ones before it. Measured on v1 (a
  median of 12 stale records against 1 of a run's own); the headline's randomized queue makes it part
  of what every arm meets, and the report reads it by position. Nothing is changed for it.
- **quote's clock** failed before slot 1 (24,487 s off after the Mac slept); the runner restarted
  quote and the check passed on a recheck, as registered (Q121).

**Measured, for the owner's go**: F $0.88-0.96 billed and 15-18 minutes a run; B1 $0.62-2.40;
B2 about $0.05; B0 $0 and about 12 minutes (the injection, the settle and the scoring are most of a
slot). The 156 project to **about $87 against the $60 cap**, which is the owner's decision at the go.
**Both stamps unchanged**; the v2 corpus at its pins throughout.

## Addendum 7 - the world went down, came back, and the switch trial began (2026-10-05 to 06)

**The world stopped.** On 2026-10-04 at about 22:49 UTC the storefront's proxy exited, the shop's
traffic fell to nothing and a Faultline incident opened on sixteen alerts; then every v2 container
exited at once, which is a Docker restart or a Mac reboot. The switch trial's first start (2026-10-05)
was refused at $0 by the world check (quote with no caller, cart at 0.07 spans/s, twelve no-traffic
alerts). **Nothing was injected.**

**What it took to come back, each step recorded:**

1. `make world-v2-up` failed on kafka's health check; kafka's JVM died 1.5 s after launch, silently,
   on every one of 77 restarts. A fresh copy of its image started cleanly with the same settings, so
   the fault was the container's own state. **kafka was recreated from its compose definition**
   (`up -d --force-recreate --no-deps kafka`): healthy, 0 restarts. No file changed, so **neither
   world digest moved**; kafka's orders data is ephemeral by design and was already gone.
2. The world then came up; Loki, Tempo and `product-reviews` settled on their own in 20 minutes.
3. **The incident stayed open.** Ten of its sixteen alerts cleared while Alertmanager was down, so
   their `resolved` webhooks were never sent and the orchestrator held the incident in `triaging`.
   The gate refused six times, and the runner stopped at slot 1 as it now does. The ten resolves
   were replayed through Faultline's own ingest
   ([`docs/evidence/t7.3/trial/replay-resolves.py.txt`](../../docs/evidence/t7.3/trial/replay-resolves.py.txt)),
   the orchestrator resolved the incident by its own rule, and nothing was edited by hand.

**The switch trial, first four slots** (log: [`attempt-4-t73.log`](../../docs/evidence/t7.3/trial/2026-10-06-attempt-4-t73.log)):
E3, E6, E9 and E7 scored, **$4.33** by the runner's tally; E7's transcript carries `reranker: ... at
revision 233902d25c44`. Then the world check stopped the batch before slot 5 on **`ad` at 93.3 % of
its 300 MB limit**, the second time (90.3 % after Addendum 4's slot 12).

**The memory rule, a runner change by addendum.** The bad-image fault's revert recreates `ad`, and a
fresh JVM climbs past 85 % while it warms up and settles in about twenty minutes (90.3 % → 75 % on
the 4th). A batch that runs one such scenario back to back meets this before every slot. The runner
now treats the memory line, when it is the only failure, as a warm-up: it rechecks every minute for
up to `MEMORY_RECHECKS` (20), then restarts that container once (the recorder's remedy; no digest
moves) and rechecks again. Any other failure, or memory beside another, still stops the batch. Tests
in `tests/test_batch.py`. **The four scored slots stand; the batch resumes at slot 5.**
