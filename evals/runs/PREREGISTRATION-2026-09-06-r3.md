# Pre-registration — R=3 on the five, the first repeat this project has ever run

**Written and committed before the run.** Same discipline as every sweep before it, and here it
matters more than usual: **this experiment exists to measure disagreement**, and a protocol written
after the disagreements are visible is a protocol chosen to explain them.

---

## 1. Why this is different from every prior run, and what it is not for

**Every scored run in this repository declares `repeat_count: 1` and `tier: manual`.** The variance
protocol's `weekly` (R=3) and `published` (R=5) tiers have existed since T4.6 and **neither has
ever been exercised.** So the project has published accuracy figures for months without a single
measurement of whether the same input twice gives the same answer.

**Two accidental measurements on 2026-09-06 say it does not.**

| scenario | runs at `b6837dd449ca` | outcomes |
|---|---|---|
| `cart-bad-image-tag` | 2 | **correct**, then **wrong** — and `bad_deploy` absent from all three ranked candidates on the second |
| `cart-redis-misconfig` | 3 | **abstained** (`unknown`), **correct** (`bad_config`), **wrong** (`dependency_latency`) |

The third of those has a cause that is **not the model**: Jaeger returned `HTTP 500` on the trace
query, so the decisive evidence never arrived and the agent said so at low confidence. **Whatever
this run measures therefore includes the world's flakiness as well as the model's sampling**, and
this document does not pretend to separate them.

**What this run is for:** the `weekly` tier's stated purpose — *"consolidation"*. A per-scenario
answer to *how often does this scenario change its answer*.

**What it is explicitly not for.** `variance.TIERS` says `published` (R=5) is *"the only tier a
printed comparison may come from"*. **This run may not back a pipeline-versus-baseline claim**, and
the writeup will say so rather than leaving a reader to check the tier table. The MDE is the reason
as well as the rule:

| scenarios | R | effective n | MDE (80% power) | at rho=0.5 |
|---|---|---|---|---|
| 5 | 1 | 5 | 39.6pp | 62.6pp |
| **5** | **3** | **15** | **22.9pp** | **36.2pp** |
| 5 | 5 | 25 | 17.7pp | 28.0pp |

Even at R=5 a five-scenario comparison needs a 17.7pp gap to resolve. **R=3 improves the variance
estimate, not the comparison.**

---

## 2. Scope, fixed here

**The same five, R=3, pipeline arm only.** `ad-memory-squeeze`, `cart-bad-image-tag`,
`cart-dependency-latency`, `cart-redis-misconfig`, `frauddetection-memory-squeeze` — dev sweep 10's
set, so every consistency figure sits beside an accuracy figure on the same scenario at the same
stamp and world generation.

**No B0.2 arm.** It is free, and it is still excluded: B0.2 is a deterministic heuristic over the
same alert set, so repeating it measures the world's variation and nothing about the arm. Running
it would put five identical rows in the record and invite a reader to read them as agreement.

**Interleaved, not blocked.** `faultline-sweep --tier weekly` runs pass 1 over all five, then pass
2, then pass 3 — deliberately. Three repeats of one scenario back to back would measure it against
three nearly identical worlds and understate exactly the variance this run exists to find.

**Stamp `b6837dd449ca`, capability `cap:c4d52d00`, world generation `f5bd108f4f70`** — unchanged
from dev sweep 10, so the 5 runs already recorded there are a fourth observation per scenario for
anyone who wants them. **They are not pooled into this run's figures**: they were taken under a
different declared tier, and pooling `manual` with `weekly` would report a repeat count no run
carries.

---

## 3. Predictions

### 1. At least one scenario answers differently across its three runs

**Registered: ≥1 of 5 shows within-scenario disagreement on fault class.**

This is close to certain given §1 and is registered anyway, because the interesting outcome is the
one that would falsify it: **if all five are internally consistent, then both of 2026-09-06's
disagreements were the world rather than the pipeline**, and the right next experiment is about
Jaeger's reliability rather than about the model.

### 2. `cart-redis-misconfig` and `cart-bad-image-tag` are among the disagreeing

**Registered: both show ≥2 distinct answers across their three runs.**

They are the two with observed disagreement. If either comes back three-for-three consistent, the
earlier observation was a rare event and the variance estimate from this run is the better one.

### 3. `frauddetection-memory-squeeze` is consistent, 3 of 3 correct

**Registered.** It has answered `resource_exhaustion` correctly on every attempt in the record —
one alert, one service, no callers, the change log names the cause. **This is the control.** If the
easiest scenario in the catalog is also inconsistent, the finding is about the harness or the world
rather than about difficulty, and that reading outranks everything else in the writeup.

### 4. Cost lands between \$9.00 and \$13.00

Sweep 10's mean was **\$0.7196/run** over a \$0.5071–\$0.8662 spread; 15 runs at that mean is
**\$10.79**, and the spread alone spans \$7.61–\$12.99.

**Materially above \$13.00 is a finding about repeated runs**, not noise — most plausibly a
scenario whose planner spends more when its first evidence path fails.

### 5. At least one run is lost to something other than the model

**Registered: ≥1 of the 15 is refused, discarded, or returns a verdict crippled by a failed tool
call.** Fifteen runs is four hours of world time; the world produced a Jaeger 500 within one hour
tonight and kafka's memory has forced a recycle twice this week.

**This is registered as an expectation, not a hazard.** If all 15 complete cleanly, the world is
more stable than two days of evidence suggests and the \$0.00 refusals in the record are
overweighted in my estimate of it.

### 6. Nothing else moves

**Registered: `cap:c4d52d00` and `f5bd108f4f70` unchanged on all 15**, and every manifest carries
`repeat_count: 3`, `tier: weekly` — **the first runs in this project's history to carry either.**

A run in this sweep declaring `repeat_count: 1` would mean the tier did not reach the manifest, and
would invalidate the whole job's labelling rather than one run's.

---

## 4. What would surprise me

1. **All five internally consistent** — prediction 1, and it would redirect the next experiment
   from the model to the world.
2. **`frauddetection-memory-squeeze` inconsistent** — prediction 3, and it would outrank everything
   else here.
3. **All 15 completing with no refusal, discard or failed tool call** — prediction 5.
4. **Cost above \$13.00** — prediction 4.

---

## 5. Cost and time

| | |
|---|---|
| registered cost | **\$9.00–\$13.00** |
| wall clock | **~4 hours** — sweep 10's five took 81 minutes |
| kafka | recycle before starting. 4 hours at the measured 151MB/h is ~29% of the 2048MB limit, so the gate's projected threshold will be near 59% and a fresh restart sits at ~26% |

---

## 6. Order of operations

1. **Confirm the stamp reads `b6837dd449ca`** before anything is injected.
2. **Recycle kafka and its consumers**, then wait 300s. The gate projects memory over *fifteen*
   runs, so it will refuse a start that a five-run sweep would have allowed.
3. **Export the key** — `faultline-eval` does not read `~/.faultline-anthropic-key`.
4. **`faultline-ingest` and `faultline-orchestrate` running**, each in its own terminal.
5. **`faultline-sweep --only <the five> --tier weekly`.** No `--baseline`.
6. **Judge the narratives** afterwards, same `claude-haiku-4-5`, same lineage opt-in.
7. **Write the result against all six predictions, including the ones that fail** — and report
   consistency **per scenario**, never as a single pooled rate, because a pooled rate over five
   scenarios of differing difficulty is the figure this document exists to avoid.
