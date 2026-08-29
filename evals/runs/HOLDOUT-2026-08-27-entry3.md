# Holdout entry 3 — 2026-08-27/28, the return-to-locus pipeline

**Entries [1](HOLDOUT-2026-08-26.md) and [2](HOLDOUT-2026-08-26-entry2.md) stand unedited.** This
is a third entry, not a replacement. The argument for it — and the condition it meets only under
strain — is [ADR-0022's T4.15 addendum](../../docs/adr/0022-evaluation-harness.md); the prediction
is [`PREREGISTRATION-2026-08-27-entry3.md`](PREREGISTRATION-2026-08-27-entry3.md), committed
before any scenario ran, with the pipeline frozen in its own commit before that
([`FREEZE-2026-08-27-entry3.json`](FREEZE-2026-08-27-entry3.json), `holdout_chunks: 0`).

| | entry 1 | entry 2 | **entry 3** |
|---|---|---|---|
| entitled by | T4.5's taxonomy instruction | T4.7's raised bound | **T4.14's return-to-locus pipeline (dev sweep 5)** |
| stamp | `prompts:53fafe9c12bc` | `prompts:53fafe9c12bc` | **`prompts:1b0e7cbb4c47`** |
| `changes` bound | 4 | 8 | **8** |
| other three bounds | 4 / 120k / 600s / 2 rounds | identical | **identical** |
| agent · judge | `claude-opus-5` · `claude-haiku-4-5` (SHARED LINEAGE) | agent identical, no judge | **both identical, SHARED LINEAGE** |
| corpus | 35 rows, 7 docs, **0 holdout chunks** | identical | **identical** |
| scenarios scored | 3 of 3 | **1 of 3** | **3 of 3** |
| cost | $1.0774 + $0.1203 judged | $0.4175, no judge | **$1.6758 + $0.1086 judged** |

## The table

| scenario | truth | entry 1 | entry 2 | **entry 3** | dispatches at the failing service |
|---|---|---|---|---|---|
| email-wrong-image | `bad_deploy` / `rollback` | `unknown` **ABST**, `changes` 4/4 | `unknown` **ABST**, exhausted nothing | **`bad_deploy` ✔ / `rollback` ✔** | #5 cut off → **0** → **3** |
| productcatalog-dependency-latency | `dependency_latency` / `restart` | `dependency_latency` ✔ / `config_revert` ✘ | discarded | **`dependency_latency` ✔ / `config_revert` ✘** | — → — → **4** |
| recommendation-memory-squeeze | `resource_exhaustion` / `config_revert` | `unknown` **ABST**, `changes` 4/4 | discarded | **`resource_exhaustion` ✔ / `config_revert` ✔** | — → — → **3** |

| | entry 1 | entry 3 |
|---|---|---|
| **coverage** | 1 / 3 | **3 / 3** |
| fault class, of answered | 1 / 1 | **3 / 3** |
| class of fix, of answered | ~~0 / 1~~ **1 / 1** | ~~**2 / 3**~~ **3 / 3** | _(rescored 2026-08-29 under T7.17: `config_revert` is a **measured** working fix for `dependency_latency`, so it is no longer a miss. Originals struck. See ADR-0027.)_
| judge `same_mechanism` | 1 / 3 | **3 / 3** |
| runs exhausting a bound | **2** | **0** |
| triage recall | 0.93 avg | **1.00 on all three** |

| per fault class | n | entry 1 answered | **entry 3 answered** |
|---|---|---|---|
| `bad_deploy` | 1 | 0 / 0, abstained | **1 / 1** |
| `dependency_latency` | 1 | 1 / 1 | **1 / 1** |
| `resource_exhaustion` | 1 | 0 / 0, abstained | **1 / 1** |
| `bad_config` | **0** | — | — |

## The prediction ledger, scored

| # | registered before the run | outcome |
|---|---|---|
| 1 | **`recommendation-memory-squeeze` answers `resource_exhaustion`** — the clean test, never read for a mechanism and not in the instruction's lineage | **HIT.** Correct class, correct fix, judge `same_mechanism`, three dispatches across three evidence classes at `recommendationservice`. |
| 2 | **`emailservice` appears in the plan and is dispatched on** — the behavioural endpoint for the hard case | **HIT.** Round 1 exhausted all four evidence classes at `checkoutservice`; **round 2 went to `emailservice`** with changes, metrics and logs. Entry 2 sent **zero**. |
| 3 | Falsifier: **`emailservice` again never dispatched on** | **Did not fire.** |
| 4 | Weaker falsifier: **`productcatalog-dependency-latency` regresses** | **Did not fire.** Answered correctly again, and its fix class is wrong in exactly the way it was wrong in entry 1. |
| 5 | Floor: **≥ 2 of 3 answered, no answered scenario wrong** | **MET and exceeded.** 3 of 3, none wrong. |

## What this does and does not license

**`email-wrong-image`'s row is corroborative, not confirmatory.** Registered in advance and
restated here: entry 2's finding on this scenario is in the lineage of the instruction being
tested, so a hypothesis tested on the case that generated it is not independent evidence about
that case — however it comes out, and it came out well. **`recommendation-memory-squeeze` is the
row that carries weight**: never read for a mechanism by anyone, abstained on starvation in entry
1, and answered here.

**n = 3, one run each, no interval.** Three scenarios is not a benchmark and this document does
not pretend it is one. What can be said: under this pipeline, on a set never fitted against, every
scenario was answered and every answer was right, and the two abstentions entry 1 recorded both
resolved.

**`bad_config` has n = 0 on holdout** and always has. The class the dev sweeps exercise most is
the one holdout cannot speak to at all.

~~**The fix class is 2 of 3.**~~ **Corrected at T7.17: 3 of 3.** Left as written below because
it was the reading at the time; T7.17 measured `config_revert` to be a working fix for this
fault class, so it was never a miss (ADR-0027). Original:
`productcatalog-dependency-latency` returned `config_revert` where
the truth is `restart` — the same miss as entry 1, and the same miss `cart-dependency-latency`
makes on dev in every sweep. Unmoved by three stamps.

**Every judged figure carries the shared-lineage violation**, as all of them do.

## Operational note: the world broke between scenarios, and the gate caught it

Recorded because it cost this entry a batch and because it is the same finding twice.

`email-wrong-image` ran first and scored. Its revert restored the image correctly — `email-service`
back on `v1.2.1-emailservice`, zero restarts — but **its recovery check did not pass**:
`checkoutservice` stayed pinned at 15000ms p95 and `accountingservice` fell to zero traffic. The
run was still scored, with the failed recovery recorded in its manifest.

The next two scenarios were then **refused by the baseline gate, and nothing was injected** —
firing alerts, the degraded p95, the silent service, and a non-terminal incident. That is T4.13's
gate doing exactly its job one task after being built, and the refusal is why this entry has three
scored rows rather than one scored row and two contaminated ones.

**Two services, one failure mode.** `checkoutservice` held broken state after `emailservice` was
recreated beneath it; `accountingservice` never reconnected to Kafka and claimed no message for
**four hours**. CATALOG.md already documents this class for the maintenance path — *"do not
reconnect on their own… produces a world that looks up and silently is not, which is exactly the
state the pre-flight gates exist to keep out of a bundle"* — and this entry is the same failure
arriving through a different door: **a scenario's own revert rather than a maintenance restart.**
The documented repair applied unchanged.

**The repair.** `kafka` at 69% and `otel-col` at 45%, neither near its ceiling, so neither was
cycled; only the wedged consumers were restarted, per CATALOG.md. `accounting-service` resumed
claiming messages within 30 seconds. The stranded incident needed no intervention — it reached
`resolved` on its own once the alerts cleared, and was confirmed terminal through the store API
rather than assumed. The gate was then left to pass **on its own**, which it did at 01:34:21Z once
the restarted containers cleared the 300s settle rule.

**Why the two refused scenarios were run as firsts, not re-runs.** A gate refusal is upstream of
any exposure: nothing was injected and no model call was made, so no agent saw either scenario.
This repository's own accounting already works this way — the T4.15 addendum counts entry 2's two
discards as **zero** exposures because they died at their first model call, and a gate refusal is
further upstream still. The pre-registration's "once each, no re-runs" is satisfied: for these two
scenarios this *was* the once.

## Exposure after this entry

| scenario | entry 1 | entry 2 | entry 3 | total |
|---|---|---|---|---|
| email-wrong-image | 1 | 1 | 1 | **3** |
| productcatalog-dependency-latency | 1 | 0 (discarded pre-call) | 1 | **2** |
| recommendation-memory-squeeze | 1 | 0 (discarded pre-call) | 1 | **2** |

The T4.15 addendum records that **this should be the last entry before the set is re-authored or
extended**. A three-scenario set read a fourth time is not a holdout in any sense a reader would
recognise, and T7.0's four further fault classes are the honest way to buy more.
