# Holdout entry 2 — declared before the run

Written and committed **before any scenario ran**. Permitted by
[ADR-0022's T4.8 addendum](../../docs/adr/0022-evaluation-harness.md); this file is condition 3
of the four that separate a new entry from a re-run in costume.

## Entitlement

This entry belongs to **T4.7's raised-bound configuration**
([`SWEEP-2026-08-26-budget.md`](SWEEP-2026-08-26-budget.md)), a reported dev result that did not
exist when entry 1 ran. Entry 1 belongs to T4.5's pipeline and **stands unedited**.

## Configuration, declared

| | entry 1 | **entry 2** |
|---|---|---|
| stamp | `faultline/0.0.1+prompts:53fafe9c12bc` | **identical** |
| `max_tool_calls_per_specialist` | 4 | 4 |
| **`per_specialist_tool_calls`** | — | **`{"changes": 8}`** |
| max tokens | 120,000 | 120,000 |
| wall clock | 600s | 600s |
| dispatch rounds | 2 | 2 |
| agent | `claude-opus-5`, effort `high` | identical |
| judge | `claude-haiku-4-5`, SHARED LINEAGE | identical |
| corpus | 35 rows, 7 documents, **0 holdout chunks** | identical |

Freeze manifest: [`FREEZE-2026-08-26-holdout-entry2.json`](FREEZE-2026-08-26-holdout-entry2.json).

**Exactly one thing differs from entry 1: the `changes` bound, 4 → 8.**

## The prediction

Registered in advance. The dev result that entitles this entry showed the bound change dissolving
*starvation-owned* abstentions and leaving an *instruction-owned* one untouched.

Entry 1's three runs, with their signatures:

| scenario | entry 1 | exhausted | signature |
|---|---|---|---|
| email-wrong-image | `unknown` abstained | **`changes` 4/4** | starved — `emailservice` was dispatch #5 of a 5-dispatch plan |
| productcatalog-dependency-latency | `dependency_latency` ✔ | — | answered with budget to spare |
| recommendation-memory-squeeze | `unknown` abstained | **`changes` 4/4** | starved — `recommendationservice` was #6 of a 6-dispatch plan |

**P1. `changes` exhaustion goes to zero.** No run exhausts the `changes` bound. *This is the
mechanical prediction and the one most likely to hold; if it fails, nothing else here is
interpretable.*

**P2. Both starved abstentions produce a class.** `email-wrong-image` and
`recommendation-memory-squeeze` return something other than `unknown`. Coverage 1/3 → **3/3**.

**P3. Those classes are correct.** `bad_deploy` and `resource_exhaustion` respectively. Weaker
than P2: dev showed every previously-starved run answering *correctly* once fed, but that is
n=1 per class.

**P4. `productcatalog-dependency-latency` stays `dependency_latency` and its class of fix stays
wrong** (`config_revert` against `restart`). The fix-class error is the dispute-register boundary,
which no bound touches.

**P5. Exhaustion moves rather than disappearing.** Dev showed two runs exhausting `metrics` 4/4
once `changes` was freed. Some entry-2 run exhausts a bound other than `changes`.

### What would falsify the T4.7 reading

An abstention that persists **with `changes` unexhausted** is instruction-owned, not starved —
the `product-catalog-flag-failure` shape. If either of the two starved scenarios abstains again
while exhausting nothing, the dev conclusion does not carry to holdout, and this entry says so.

### What is not predicted

Whether an instruction-owned abstention appears at all. Entry 1's third scenario answered, and
there is no holdout analogue of `product-catalog-flag-failure` identified in advance. If one
appears, it is a finding, not a failed prediction.

## Protocol

Three scenarios, **once each**, `--holdout`, gate before every injection, one driver, revert and
confirmed recovery between. **No re-runs.** Discards recorded with reasons and left. Judged with
the same configuration and the same lineage label. Entry 1 is not edited.
