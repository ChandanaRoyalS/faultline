# Dev sweep 7 — 2026-08-30, the benchmark re-founded again

**These are current-world figures.** Measured against `compose_digest f5bd108f4f70f460…` /
`observability_digest 857d95b4d174ec43…`, the world T7.28 built. This is the first measurement of
any kind on the bounded world.

Pre-registered in [`PREREGISTRATION-2026-08-30-refound-again.md`](PREREGISTRATION-2026-08-30-refound-again.md),
committed before any scenario ran.

## S6 and S7 are not the same experiment

**They differ in the world, and only in the world.** The stamp is identical, the budget is
identical, the harness is identical. T7.28 bounded kafka's glibc allocator, put a
`maxmemory`/`allkeys-lru` bound on redis-cart, added a `memory_limiter` to the collector, and
re-recorded every runnable bundle against the result.

**Every comparison below crosses a world boundary.** It is not a comparison of agents — the agent
is byte-identical — and it cannot separate the world's effect from run-to-run variance, because
n = 1 per scenario on each side. Read it as *"does the benchmark still stand up on the bounded
world"*, never as *"the agent got better or worse"*.

| | dev sweep 6 (old world) | **dev sweep 7 (bounded world)** |
|---|---|---|
| stamp | `1b0e7cbb4c47` | **identical** |
| budget | `changes` 8, others 4, 120k, 600s, 2 rounds | **identical** |
| world | `299d791c5e0d…` | **`f5bd108f4f70f460…`** |
| scenarios runnable | 7 | **8** |
| scenarios scored | 6 (two discards) | **8 (no discards)** |
| cost | $3.3650 + $0.2229 judge | **$4.3652 + $0.3218 judge** |

**Eight scenarios, not seven.** `shipping-quote-misconfig` did not exist when S6 ran; T7.22 recorded
it and T7.24 ran it once outside any sweep. The three dev scenarios that are not runnable —
`ad-dependency-latency` (disqualified at T7.22) and `currency-cpu-throttle` /
`flag-service-crashloop` (each carrying an `INVALID.md` since T7.1) — are unchanged and were not
blocked by T7.28.

## The two tables

**The S6 column is rescored.** `scoring.py` moved at T7.17, after every S6 run, so the stored
figures were computed by a scorer that did not know two fixes work for `dependency_latency`.
Comparing them raw would credit the world with a scorer fix — the confound T7.10 caught between S5
and S6. See [`s6-rescore.md`](../../docs/evidence/t7.29-refound-again/s6-rescore.md).

| scenario | S6 — old world (rescored) | **S7 — bounded world** | judge |
|---|---|---|---|
| `ad-memory-squeeze` | `resource_exhaustion` ✔ | **`resource_exhaustion` ✔** | same → same |
| `cart-bad-image-tag` | `bad_deploy` ✔ | **`bad_deploy` ✔** | same → same |
| `cart-dependency-latency` | `dependency_latency` ✔ | **`dependency_latency` ✔** | same → same |
| `cart-redis-misconfig` | `bad_config` ✔ | **`bad_config` ✔** | same → same |
| `frauddetection-memory-squeeze` | **DISCARD** — no incident in 900s | **`resource_exhaustion` ✔** | — → same |
| `product-catalog-flag-failure` | `bad_config` ✔ | **`bad_config` ✔** | same → same |
| `shipping-quote-misconfig` | *(not in S6; T7.24 returned `bad_config` ✔)* | **`bad_deploy` ✘** | — → **adjacent** |
| `shipping-wrong-image` | `unknown` **ABSTAINED** | **`bad_deploy` ✔** | different → **same** |

| | S6 (rescored) | **S7** |
|---|---|---|
| scenarios scored | 6 | **8** |
| discards | 2 | **0** |
| coverage | 5 / 6 | **8 / 8** |
| fault class, of answered | 5 / 5 | **7 / 8** |
| class of fix, of answered | 5 / 5 | **7 / 8** |
| judge `same_mechanism` | 5 / 6 | **7 / 8** |
| runs exhausting a bound | 0 | **0** |

**Coverage 8/8 with no discards is the cleanest sweep the project has run.** Every scenario opened
an incident, produced a verdict and was scored.

## The prediction failed, in one place

Registered: *all eight scenarios return the fault class they last returned, coverage 7/8 or better.*

**Coverage beat the registration at 8/8.** The falsifier was "any scenario returning a different
fault class", and **one did**.

## Movement 1: `shipping-quote-misconfig` returned the wrong class — **attribution genuinely open**

The registered surprise #2, and the only wrong verdict in the sweep.

| | T7.24 (old capture) | **S7 (new capture)** |
|---|---|---|
| fault class | `bad_config` ✔ | **`bad_deploy` ✘** |
| fix class | `config_revert` ✔ | **`rollback` ✘** |
| faulty service | `shippingservice` ✔ | localized to the same boundary |
| confidence | high | **low** |
| judge | `same_mechanism` | **`adjacent`** |
| dispatches at `shippingservice` | — | **0** |

**The agent named its own error.** It localized correctly — every failing trace terminates at
checkout's `GetQuote` client span, with cart, catalog, flag and currency clean — and then wrote:

> "No dispatch touched shippingservice itself — its change history, error rate, and logs are
> entirely unobserved, so the wrong-artifact mechanism is inferred, not confirmed; **a bad config
> value or contract mismatch on shippingservice would look identical from the caller.**"

It named `bad_config` — the truth — as indistinguishable from where it stood, and returned **low**
confidence. The judge scored it `adjacent` rather than `different`, which is the same reading.

**This is the failing-service dispatch collapse T4.12 identified**, at n = 1. It is the same
mechanism that produced S6's `shipping-wrong-image` abstention (also 0 dispatches at the failing
service) — but it exited differently: **a wrong answer with low confidence instead of an
abstention.** That the same collapse can produce either is worth more attention than either result
alone, and this sweep cannot say what selects between them.

**Attribution is open and is left open.** This scenario's capture changed most in the set (2 → 7
alerting services), and T7.24's single correct run was against the old capture — so a capture
effect is available. So is planner allocation, which T4.9/T4.10 measured as the least stable thing
in this system and which S6 already showed producing exactly this signature. **n = 1 on each side
cannot separate them**, and no claim is made.

## Movement 2: `frauddetection-memory-squeeze` recovered — **and it settles an old hypothesis further**

S6 discarded it after no incident formed in 900s. **Here it paged, scored, and returned a perfect
triage** — 1 predicted, 1 alerted, the same one — for the cheapest run of the sweep at $0.4203.

S6 originally offered a kafka-heap-cap hypothesis for that discard. **T7.11 tested it directly and
falsified it**, reattributing the discard to the host suspending mid-run. This result is a second,
independent line of evidence in the same direction: if a kafka memory mechanism were suppressing
this scenario's alert, a **more** memory-constrained kafka is where it should have shown, and
instead the scenario ran clean.

## Movement 3: `shipping-wrong-image` recovered from its abstention

S6 abstained with **0** dispatches at `shippingservice`; S7 answered `bad_deploy` ✔, judged
`same_mechanism`. S6 attributed that abstention to planner allocation rather than the world, and
this is consistent with it. **At n = 1 per side it is not evidence that the world fixed anything.**

## Which triage figures moved, and whether the capture explains them

Measured against each bundle's own `superseded/` archive — see
[`capture-differences.md`](../../docs/evidence/t7.29-refound-again/capture-differences.md).

| scenario | S6 | **S7** | traces to a capture difference? |
|---|---|---|---|
| `ad-memory-squeeze` | 1.00 / 0.43 | **1.00 / 0.43** | — unchanged |
| `cart-bad-image-tag` | 0.80 / 0.67 | **0.80 / 0.67** | — unchanged |
| `cart-dependency-latency` | 1.00 / 0.33 | **1.00 / 0.33** | — unchanged |
| `cart-redis-misconfig` | 0.80 / 0.67 | **0.80 / 0.67** | — unchanged |
| `frauddetection-memory-squeeze` | — | **1.00 / 1.00** | no S6 side |
| **`product-catalog-flag-failure`** | 1.00 / 0.43 | **1.00 / 0.57** | **yes** |
| `shipping-quote-misconfig` | — | **0.83 / 0.45** | no sweep side |
| **`shipping-wrong-image`** | 0.75 / 0.60 | **0.71 / 0.42** | **no** |

**Four of the six comparable scenarios are identical to two decimal places**, on the same captures.

**`product-catalog-flag-failure` — yes, and it is arithmetic.** `checkoutservice` joined the
alerting set, so `n_alerted` went 3 → 4. The agent predicted **the same 7 services both times** and
recall stayed 1.00 with nothing missed; 3 of 7 were in the old truth set and 4 of 7 are in the new
one. **Precision rose on an unchanged prediction.** Reporting this as the world or the agent
improving would be wrong.

**`shipping-wrong-image` — no.** Its alerting-service set is unchanged at 8. The movement is
run-level: `n_predicted` 10 → 12 (a wider radius), and `n_alerted` 8 → 7 because **one alert began
after the revert and T7.3's exclusion removed it**. It is also comparing an *abstention's* predicted
radius to an *answer's*. Nothing about the capture changed.

**One movement traces to a documented capture difference; the other does not, and neither is a
world effect.**

## The kafka observation — the lever does not bound the growth

Passive, alongside the sweep. No injection. T7.27 showed `MALLOC_ARENA_MAX=2` **engages** — 68 arena
regions → 0 — but explicitly did not show that it **bounds long-run growth**, and queued the
re-measure.

**The premise that it had been live a day or more did not hold.** kafka started
`2026-08-29T22:12:26Z`; arena state is a property of process lifetime and a restart clears it. This
is a **~5h → ~8h observation, not the 24h one.**

| | start 03:05Z | **end 05:52Z** | delta |
|---|---:|---:|---|
| uptime | 4h53m | **7h40m** | +2h47m |
| container | 1.399 GiB — 69.95% | **1.814 GiB — 90.69%** | **+20.7 points** |
| cgroup `anon` | 1,462,681,600 | **1,903,943,680** | **+421 MB** |
| **64 MB arena regions** | **0** | **0** | **unchanged** |
| total mapped anon | 3,134 MB | **3,553 MB** | +419 MB |

**The setting engaged once and stayed engaged; it does not bound long-run growth.** The arena
signature is gone and stays gone — 0 regions at both ends — and anon still grew **421 MB in 2h47m,
≈151 MB/hour**, reaching **90.69%**. The recorder's headroom guard refuses at 90%, so **kafka
crossed the refusal threshold during the sweep**, which the pre-registration named as a risk before
it happened.

**What this does and does not settle.** It settles the queued question in the direction T7.27 could
not: the growth is *not* bounded by the lever. It does **not** establish a rate comparable to
T7.27's ~55 MB/h, because that figure was the anon-versus-NMT gap measured on a near-idle world and
this window ran eight fault injections. **Load is not controlled between the two, and no rate
comparison is claimed.** What is claimed is the qualitative result: arenas at 0 throughout, growth
continuing, guard threshold reached.

**A consequence worth naming:** the next recording session will refuse on this container unless
kafka is recycled first. That is the guard working, and it makes recycling kafka a precondition of
recording rather than an occasional fix.

## Cost

**$4.3652 agent + $0.3218 judge = $4.6870** for eight scored runs — in 293,015 / out 116,009 agent
tokens, in 47,918 / out 3,288 judge tokens. Mean **$0.546/scenario** against a $0.55 budget.

No discards, so nothing was spent on a run that produced no result — the first sweep of which that
is true.

## What this sweep establishes, and what it does not

**Establishes:** the benchmark stands on the bounded world. **Eight of eight scenarios scored with
no discards** — the cleanest run to date — and **seven of eight verdicts are correct**, with every
scenario that had a comparable S6 result returning the same class. Triage is unchanged to two
decimals on four of six comparable scenarios, and the one capture-driven movement is accounted for
arithmetically.

**Does not establish:** the size of the world change's effect, or that any movement was caused by
it. n = 1 per scenario per side. The one wrong verdict has two available explanations — a changed
capture and a known planner instability — and this sweep separates neither.

**Holdout was not re-entered**, and nothing here licenses it.
