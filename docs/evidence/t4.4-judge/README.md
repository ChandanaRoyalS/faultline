# T4.4 — the judge, run over the first dev sweep

Eight runs offered, seven judged, one correctly declined. No injections and no world: the
narratives were already on disk, so this is the cheapest measurement in the project.

    $ faultline-judge <seven sweep runs> 20260826T055345Z-cart-redis-misconfig --out judged-table.md

`transcript.txt` is the run verbatim; `judged-table.md` is the judged column set as the CLI
wrote it; each run's manifest now carries a `judge` block beside its `score`.

## Configuration, and the violation it carries

| | |
|---|---|
| agent under test | `claude-opus-5` |
| judge | `claude-haiku-4-5` |
| **lineage** | **SHARED — every figure below carries the violation** |
| cost | in 38,973 / out 2,955 tokens — **$0.2687** |

**The lineage violation is real, deliberate, and was opted into by name.** This project holds
Anthropic credentials only, and lineage is judged at the vendor-family level (§ below), so *every
available judge* shares a lineage with the agent. The options were to refuse until a second
provider exists, or to judge and stamp. The implementation refuses by default and requires
`FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE=1`, so this figure could not have been produced by
accident — and every table it appears in says so.

## The judged table

| scenario | root cause | dead ends closed / missed | traps |
|---|---|---|---|
| ad-memory-squeeze | **same_mechanism** | 6 / 6 | 2 avoided, 2 not engaged |
| cart-bad-image-tag | **same_mechanism** | 4 / 6 | 2 avoided, 1 not engaged |
| cart-dependency-latency | **same_mechanism** | 6 / 2 | 3 avoided, 1 not engaged |
| cart-redis-misconfig | **same_mechanism** | 8 / 4 | 2 avoided, 2 not engaged |
| frauddetection-memory-squeeze | **same_mechanism** | 7 / 6 | 2 avoided, 1 not engaged |
| product-catalog-flag-failure | **same_mechanism** | 5 / 6 | 1 avoided, **1 TOOK** |
| shipping-wrong-image | **same_mechanism** | 6 / 5 | 2 avoided |
| _cart-redis-misconfig (run 3)_ | _not judged_ | — | the run wrote no narrative |

Full trap phrasings are in `judged-table.md`.

## Read this beside the deterministic table, not instead of it

| | deterministic (T4.2) | judged (T4.4) |
|---|---|---|
| fault class | **4/7** | — |
| class of fix | 6/7 | — |
| root-cause agreement | — | **7/7 `same_mechanism`** |

**These do not contradict each other; together they are the same finding twice.** T4.3 concluded
from the verdicts that the agent *understands the mechanism and mislabels the class* — it
returned only `bad_deploy` or `bad_config` across the whole sweep and never a symptom class. The
judge grades mechanism agreement and does not see labels at all, and it says the narratives
describe the same mechanism as the recorded ones in every case, including all three the
deterministic scorer marks wrong.

Two independent measurements, one made from structured labels and one from prose by a different
model, agreeing that **the gap is taxonomy rather than comprehension**. That is the most useful
thing this task produced.

### And 7/7 is weak evidence, for three reasons

1. **No variance.** A judge that returns the top level for every input has not been shown to
   discriminate between levels. `adjacent` and `different` were never exercised. Until one of
   them is, "7/7 `same_mechanism`" is compatible with a working grader and with a generous one.
2. **The lineage violation.** A Claude model grading Claude prose, on a rubric about what makes
   a good incident narrative.
3. **n=1 per scenario**, and seven scenarios over four fault classes.

The honest reading is: *the judge did not find a narrative that named the wrong mechanism*, which
is a weaker claim than *the narratives all named the right one* and is what the data supports.

## What the judge did find

**One trap taken**, on `product-catalog-flag-failure`:

> trap: "the cause lives in productcatalogservice's change history or config" — **took**

with the note: the agent "correctly identifies the mechanism but arrives there primarily via
frontend logs naming the flag, and explicitly acknowledges it did not verify the flag state
directly". Right answer, and the recorded narrative names the route it took as one of the ways
to be confidently wrong here — a distinction the deterministic scorer cannot make, because the
label came out correct.

**Dead ends are where the narratives are thinnest.** Closed-versus-missed runs from 8/4 down to
4/6; five of seven miss more than they close. `ARTIFACTS.md` calls dead ends "the most useful
thing in the document", and this is the first measurement of them.

## A contamination defect the tests caught before any live call

`test_the_judge_is_never_told_the_label` failed on its first run. Every recorded `incident.md`
opens with YAML front matter:

    ---
    origin: scenario:cart-redis-misconfig
    split: dev
    fault_class: bad_config
    ...
    ---

Passing the file verbatim would have violated ADR-0022 §1.3's marked decision **twice in one
document**: `fault_class` is the label the judge is explicitly not told, and `origin` carries the
scenario id that ADR-0019 bans separately as the answer key. Every judged figure this project
ever produced would have been contaminated, and the contamination would have been invisible in
the output.

The front matter is stripped before wrapping, and the prose below it — which is what ADR-0022
meant by "the recorded narrative" — is passed intact.

## Marked decisions

- **Lineage is judged at the vendor-family level, not by model id.** Reading ADR-0020's "same
  instance, prompt, or tuning lineage" as id-equality would clear `claude-haiku-4-5` grading
  `claude-opus-5`: two models, one lab, one pretraining lineage, one post-training methodology.
  Family-level is the reading that matches the words, and it is the reading that makes the check
  bite on this project rather than wave it through.
- **A violation refuses by default and must be opted into by name.** ADR-0008's "invalid rather
  than annotated" exists to stop a contamination defence failing *silently*; a violation that has
  to be requested and is then stamped on every figure is not silent.
- **An unrecognised model id resolves to `unknown`**, which matches no vendor — so an id the
  table does not know can never *clear* a lineage check by pairing with a known one.
- **The judge's configuration lives in `evalharness`, not beside `AgentSettings`.** ADR-0020 put
  `judge_model` on the product's settings and argued it must inherit nothing; taking it out of
  the product entirely is the stronger form of the same argument, and removes the one field
  someone could set while thinking they were configuring the agent. The product field is marked
  superseded and is no longer read.
- **The judge brings its own model client** (`JudgeModel`). Found live: `AnthropicModel`
  hard-codes `thinking={"type": "adaptive"}`, which the smaller models predate and reject with a
  400. Making the product's boundary configurable to suit the harness would put a judge-shaped
  requirement inside the runtime. The judge's client speaks the same `ModelRequest`/`ModelResponse`
  contract and sends no thinking block — which is also right on its own terms: comparing two
  documents against three fixed questions does not want extended reasoning.
- **A reply with an out-of-range agreement level is not scored**, rather than being coerced.
  Three levels, and a judge inventing a fourth is a failed judgement, not a new category.

## Not decided here

**Whether a second provider gets wired up.** The recommendation is yes, and it is the single
cheapest thing that would improve every judged figure in this project — but it needs credentials
this repository does not hold, and inventing a provider abstraction with nothing to test it
against would be building for a hypothetical. Until then the violation label is the honest
alternative, and it is doing its job: it appears on every line of the table above.
