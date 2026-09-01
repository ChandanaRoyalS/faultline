# T7.52 — judged mechanism agreement across the whole recorded corpus

**Question.** T7.51 found `redis-cart-dependency-latency` scoring **3/3** on fault class while the
judge rated **2 of those 3** as `adjacent` — right subsystem, wrong mechanism. Every published
figure in this project is label-level, and T7.44 concluded that was acceptable because the figures
are named as such. This measures whether that gap is **a curiosity or a systematic overstatement**.

**Answer, in one line.** Across every judged run that counts toward an aggregate, **class-label
accuracy and judged mechanism agreement are the same number — 52 of 56 answered runs each — but
they are not the same 52 runs.** Six runs disagree, three in each direction. **The label score is
not optimistic; it is noisy, symmetrically.** The T7.51 gap is confined to one scenario.

---

## 1. Survey before spending

| | count |
|---|---:|
| run directories carrying a `manifest.json` | 97 |
| …scored (the rest are discards; no discard carries a score) | 76 |
| …of those, counting toward aggregates (2 are demo runs, T5.3) | 74 |
| …already carrying a `judge` block before this task | 72 |
| **scored but unjudged** | **4** |

Manifests carrying a judge block also come in **one** shape — all 72 shared an identical key set,
all judged by `claude-haiku-4-5` against agent `claude-opus-5`. The *run* manifests vary widely (16
distinct key sets across 97 files, from 2 keys to 22), which is what a record written across four
months of harness changes looks like; the judge block does not vary.

### The four unjudged runs

| run | split | demo | class |
|---|---|---|---|
| `20260826T043356Z-cart-redis-misconfig` | dev | no | abstained |
| `20260826T214314Z-email-wrong-image` | **holdout** | no | abstained |
| `20260827T112506Z-cart-redis-misconfig` | dev | **yes** | abstained |
| `20260827T120348Z-cart-redis-misconfig` | dev | **yes** | abstained |

All four abstained, which is why nothing downstream ever missed them. **Two are demo runs**, and no
aggregate counts a demo (T5.3) — judging those would buy a field that by rule may not be used, so
they were left alone. **The two non-demo runs were judged**, and with them **every run that counts
toward an aggregate and can be judged now is**.

## 2. Would judging alter anything?

T7.51 established that judging writes `manifest["judge"]` and touches nothing else. Two things
were checked rather than carried over:

- **Older manifest shapes.** For each of the four targets, the manifest was parsed and re-serialised
  exactly as `judge_cli` would (`json.dumps(..., indent=2, default=str)`) and compared to the bytes
  on disk. **All four round-tripped byte-identically**, so the write adds a key and rewrites nothing.
  Confirmed again afterwards: the diff on both judged manifests is `added: {'judge'}`, nothing
  removed, nothing changed.
- **The default sweep would alter.** `faultline-judge` with no run ids judges **every** scored run
  and overwrites `manifest["judge"]` — for the 72 already-judged runs that **replaces a recorded
  verdict.** That is an alteration, not an addition. **The run ids were therefore named explicitly**
  and only the two unjudged non-demo runs were touched.

## 3. The holdout decision, taken explicitly

**Judging a holdout entry spends nothing.** Stated confidently, on four grounds:

1. **It is not a run.** `judge.load_run` reads the run's own `manifest.json` and its recorded
   `*-narrative.md` from disk. No world, no injection, no agent, no tools. What is consumed by a
   holdout run is the unrepeatable observation of an agent meeting the scenario for the first time;
   judging consumes none of it and is repeatable at will.
2. **Nothing enters a retrieval corpus.** The contamination rule bans holdout scenarios from
   retrieval corpora. The judge's ground truth is `incident.md` *prose only* — `FRONT_MATTER` strips
   the header carrying `fault_class`, `split` and `origin` before the text reaches the model, so the
   judge is never told the label. It goes into one prompt to a model that is not the agent under
   test, and comes back as a field.
3. **Nothing reads it back.** No file under `src/faultline/` — the product — reads `evals/runs/` at
   all. `manifest["judge"]` is written in exactly one place and read by no code path the agent
   touches.
4. **It is settled practice, not a new decision.** **10 of the 11 holdout runs already carried judge
   blocks**, written by this same path. Judging the eleventh does not open a question; leaving it
   unjudged would have left the holdout split measured inconsistently with itself.

## 4. Cost

Estimated from T7.51 — six runs for \$0.2555, so **\$0.043/run**, and two runs ≈ **\$0.09**. Nowhere
near the couple-of-dollars ceiling, so no scope reduction was needed. **Actual: \$0.0715** (10,550
in / 751 out). Both new verdicts came back `different`, which is the mechanical result for an
abstention: a verdict with no root cause cannot match the narrative's mechanism.

## 5. The corpus comparison

**n = 73** judged runs that count toward aggregates. One further run — `20260826T055345Z-cart-redis-misconfig`
— carries a judge block marked `scored: false, "the run wrote no narrative"`, and is excluded from
every figure below rather than counted as a disagreement.

**Abstentions are excluded from the agreement figures, and this matters.** All **17** abstentions in
the corpus judge `different`, necessarily and without exception. Counting them would make judged
agreement look far worse than class accuracy purely as an artifact of how abstention is judged —
`same/adjacent/different` over all 73 runs is `52 / 3 / 18`, and 17 of those 18 are abstentions.
Class accuracy is already reported over answered runs with coverage beside it; agreement is reported
the same way here.

| scenario | split | runs | answered | class of answered | `same_mechanism` | `adjacent` | `different` |
|---|---|---:|---:|---:|---:|---:|---:|
| `ad-memory-squeeze` | dev | 7 | 6 | 5 / 6 | 6 | 0 | 0 |
| `cart-bad-image-tag` | dev | 7 | 6 | 6 / 6 | 5 | 0 | 1 |
| `cart-dependency-latency` | dev | 7 | 7 | 6 / 7 | 7 | 0 | 0 |
| `cart-redis-misconfig` | dev | 13 | 11 | 11 / 11 | 11 | 0 | 0 |
| `email-wrong-image` | holdout | 3 | 1 | 1 / 1 | 1 | 0 | 0 |
| `frauddetection-memory-squeeze` | dev | 6 | 6 | 5 / 6 | 6 | 0 | 0 |
| `payment-telemetry-blackout` | dev | 3 | 2 | 2 / 2 | 2 | 0 | 0 |
| `product-catalog-flag-failure` | dev | 11 | 5 | 5 / 5 | 5 | 0 | 0 |
| `productcatalog-dependency-latency` | holdout | 2 | 2 | 2 / 2 | 2 | 0 | 0 |
| `recommendation-memory-squeeze` | holdout | 2 | 1 | 1 / 1 | 1 | 0 | 0 |
| `redis-cart-dependency-latency` | dev | 3 | 3 | 3 / 3 | **1** | **2** | 0 |
| `shipping-quote-misconfig` | dev | 2 | 2 | 1 / 2 | 1 | **1** | 0 |
| `shipping-wrong-image` | dev | 7 | 4 | 4 / 4 | 4 | 0 | 0 |
| **all** | | **73** | **56** | **52 / 56** | **52** | **3** | **1** |

By split, answered runs only: **dev** 52 answered, class 48/52, agreement `48 / 3 / 1`; **holdout**
4 answered, class 4/4, agreement `4 / 0 / 0`. **The holdout comparison rests on four observations**
and settles nothing on its own.

**These are counts over an unbalanced, opportunistically accumulated record, not a rate.** The 73
runs are what four months of sweeps, re-records, single runs and pre-registered experiments left
behind; `cart-redis-misconfig` contributes 13 and `shipping-quote-misconfig` 2. No interval is
quoted because there is no sampling design here to support one.

## 6. Where they disagree — both directions, three each

**52 answered runs score the class correct. 52 answered runs judge `same_mechanism`. Only 49 are
both.**

| | `same_mechanism` | `adjacent` | `different` |
|---|---:|---:|---:|
| class **correct** (52) | 49 | 2 | 1 |
| class **wrong** (4) | **3** | 1 | 0 |

### Direction A — the label over-credits (3 runs)

| run | truth → returned | judge | why |
|---|---|---|---|
| `20260831T053815Z-redis-cart-dependency-latency` | `dependency_latency` ✔ | `adjacent` | *"identifies a slow datastore dependency … but does not name Redis specifically or the network delay mechanism, stopping at 'slow dependency'"* |
| `20260901T062150Z-redis-cart-dependency-latency` | `dependency_latency` ✔ | `adjacent` | *"leaves the root cause open among saturation, network path, or configured delay"* |
| `20260827T164231Z-cart-bad-image-tag` | `bad_deploy` ✔ | `different` | *"attributes the failure to a broken GetCart implementation in a deployed hotfix build that is actively running"* — a wrong story that lands in the right bucket |

**Two of the three are the runs T7.51 already reported.** The third is a single run of one scenario.

### Direction B — the label under-credits (3 runs)

| run | truth → returned | judge | why |
|---|---|---|---|
| `20260826T063503Z-ad-memory-squeeze` | `resource_exhaustion` → `bad_config` | `same_mechanism` | *"the memory limit reduction to 256m as causing adservice to run out of memory and be killed"* |
| `20260826T083359Z-frauddetection-memory-squeeze` | `resource_exhaustion` → `bad_config` | `same_mechanism` | *"the container memory limit being reduced below the JVM's working set … kernel OOM kills and a crash/restart loop"* |
| `20260826T071611Z-cart-dependency-latency` | `dependency_latency` → `bad_config` | `same_mechanism` | *"an unauthorized traffic-shaping container attached to cartservice's network namespace imposing 300ms egress delay"* |

**All three are already in `CLASS_DISPUTES`** — the register `scoring.py` keeps for exactly this
boundary, where a change to a configuration produces a symptom and the label set names one of them.
**The judge, which is never told the label, independently agrees with the agent on precisely the
three runs the register flags as contested.** That is corroboration the register is naming a real
ambiguity rather than excusing a miss, and it arrives from a direction that could not have been
tuned to produce it. **It does not make them right** — ADR-0022 §1.2's rule stands, a disputed miss
is still a miss.

### The fourth non-abstained miss agrees with the judge

`20260830T051304Z-shipping-quote-misconfig` returned `bad_deploy` for `bad_config` and judges
`adjacent` — *"identifies shipping's GetQuote call as the failure point … but infers a wrong artifact
from trace shape without observing shipping's actual state."* Label and judge concur it is wrong.

## 7. What should change in the published record: nothing

**Recommendation: leave RESULTS.md and README as they are.** Five reasons, in order of weight:

1. **There is no net overstatement to correct.** 52/56 by label, 52/56 by judge. A reader taking the
   corpus-level class figure at face value is not misled about how often the agent named the
   mechanism.
2. **The error is bidirectional.** Three runs each way. A caveat saying "the label figure flatters"
   would itself be a misstatement, and a single "judged agreement" number appended beside class
   accuracy would hide that by collapsing three levels into one — the exact move that produced the
   original overstatement.
3. **The systematic part is one scenario.** `redis-cart-dependency-latency` holds 2 of the 3
   over-credits, and **T7.51 already published that gap for that scenario.**
4. **The record already does the recommended thing.** README and RESULTS.md report `judge: same_mechanism /
   adjacent / different` as a three-way distribution beside class accuracy for both sweeps
   (`7 / 0 / 0` and `4 / 0 / 3`), and every judged figure already carries SHARED LINEAGE. There is no
   published figure here that lacks its judged companion.
5. **The holdout arm cannot support a new headline.** Four answered runs.

**What T7.51's conclusion becomes.** *"The label score overstates D1, and the judge is what shows
it"* stands as written — it was about D1, and it is still true of D1. What this task adds is that
**D1 is the outlier, not the sample**: at corpus scale the same comparison finds no net
overstatement. T7.44's conclusion — that label-level figures are acceptable *because they are named
as such* — survives the check it invited.

## 8. Reproducing this

```
uv run faultline-judge <run-id> [<run-id> …]     # named ids only; a bare sweep re-judges everything
```
with `FAULTLINE_JUDGE_MODEL=claude-haiku-4-5` and `FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE=1`.
The roster this report is computed from is committed beside it as `roster.json`, one row per
aggregate-counting judged run.
