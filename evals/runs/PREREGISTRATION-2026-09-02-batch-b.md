# Pre-registration — dev sweep 8, the Phase 3 pipeline as the specification describes it

**Written and committed before any scenario runs.**

## What this measures, and the thing that makes it weaker than sweep 7

Phase 3's Batch B closed today. Six tasks and five queue items landed between #143 and #148, and
**every one of them changed the agent**. The stamp moved three times, the budget block moved once,
the capability set moved once, and the corpus moves when the seeding command is run.

| frozen key | before Batch B | now |
|---|---|---|
| `prompts` | `1b0e7cbb4c47` | **`bc222a353936`** (via `20088b22cede`, `a7330c098770`) |
| `budget` | four bounds | **eight** — briefing cap, dollar cap, and the two prices it is computed at |
| `world.capability_version` | `cap:9c416e0a` | **`cap:c4d52d00`** — a fifth tool, `TOOL_BEHAVIOUR_REVISION` 1 → 2 |
| `corpus` | seven documents, all `scenario:*` | **twenty-two** — the fifteen authored runbooks join, at seeding |
| `world.compose_digest` / `observability_digest` | `f5bd108f…` / `857d95b4…` | **unchanged.** Q13 was assessed and declined |

**Dev sweep 7 could say what it was measuring; this one cannot.** S7 moved the world and nothing
else, so a difference was the world, variance, or both. Here six changes land together, and a
sweep of `n = 1` per scenario **cannot attribute any difference to any one of them.** Saying so
first is the point of writing this before running anything.

> **The registered question is therefore: does the pipeline the specification describes still
> work end to end — and what do its two new stages do?**

Not *"is it better"*. Nothing here is powered to answer that, and any table comparing S7 to S8
that reads as an improvement claim is misreading it.

## What is actually new in the run

Two stages that have never executed, and four changes to stages that have.

| | change | first observation? |
|---|---|---|
| **Triage gate** | A model decides `investigate` / `noise` / `duplicate` **before** any specialist runs | **yes** |
| **Proposer** | A remediation proposal, or a recorded abstention, after the citation gate | **yes** |
| Evidence board | Every claim carries its provenance and a bounded sample; the synthesizer and proposer see samples, the scribe does not | no — a changed brief |
| Briefing budget | Each role's brief is packed under 4,000 estimated tokens, lowest priority dropped first | no |
| Metrics specialist | A baseline comparison and change points, not a bare error ratio | no |
| Corpus | Retrieval can now return authored runbooks, which `exclude_origin` never removes | no |

## The scenario set: eight, unchanged

The compose and observability digests did not move, so every bundle that was runnable for S7 is
runnable now, and the three that were not still are not — `ad-dependency-latency` (disqualified at
T7.22, never recorded), `currency-cpu-throttle` and `flag-service-crashloop` (each carrying an
`INVALID.md` since T7.1). **Eight scenarios, one run each.**

## The predictions

### 1. The gate does not close on a real incident

**Registered: zero of the eight scenarios are gated.** Every scenario in this catalog is a real
injected fault that produced a real alert, so a `noise` disposition is a false negative of the
worst kind — the pipeline declining to investigate something that is wrong. A `duplicate`
disposition is equally wrong: the sweep runs one incident at a time.

**This is the strongest falsifier in the document.** One gated scenario means the gate is wrong,
not that the scenario is quiet, and the finding would be that a cheap model asked to decline
things will decline things.

### 2. The verdicts hold

**Registered: all eight return the fault class they returned in S7**, and coverage is **7/8 or
better**. The evidence reaching the synthesizer is strictly richer than S7's — the same envelopes,
plus provenance, plus a baseline comparison. A class that moves *down* on richer evidence is a
finding about the briefing change, not about the world.

| scenario | S7 returned |
|---|---|
| `ad-memory-squeeze` | `resource_exhaustion` ✔ |
| `cart-bad-image-tag` | `bad_deploy` ✔ |
| `cart-dependency-latency` | `dependency_latency` ✔ |
| `cart-redis-misconfig` | `bad_config` ✔ |
| `frauddetection-memory-squeeze` | `resource_exhaustion` ✔ |
| `product-catalog-flag-failure` | `bad_config` ✔ |
| `shipping-quote-misconfig` | `bad_deploy` ✘ (label `bad_config`, judged adjacent) |
| `shipping-wrong-image` | `bad_deploy` ✔ |

`shipping-quote-misconfig` is registered as **unsettled rather than predicted**: it has been wrong
once and right once, at `n = 1` each, and either outcome here is consistent with both.

### 3. The proposer is observed, not predicted

**Nothing is registered about what the proposals say.** This is the stage's first execution and
there is no prior. What *is* registered:

- **Every scored run produces a proposal object** — an action or an abstention. A run with no
  proposal at all means the proposer was refused twice, which is a defect rather than an outcome.
- **Zero proposals name an action outside the allowlist, a target outside the blast radius, or a
  `rests_on` id the store cannot resolve.** All three are contract-checked with one re-ask, so a
  failure here is a failure of the check, not of the model.
- **Abstention rate is reported, never scored.** ADR-0022 §1.2: an abstention is neither right nor
  wrong. A high rate is a finding about the brief, not a bad result.
- **The prediction axis is reported as `not measured`** on every proposal, because no executor
  exists (ADR-0028 §4). Not passed. Not omitted.

### 4. No run exhausts a bound

**Registered: zero runs exhaust the token bound, the wall clock, the dispatch rounds, or the new
dollar cap.** Six sweeps have never exhausted one. The dollar cap is new and is Gate 4's own \$2;
S7 cost \$4.687 across eight scenarios, about \$0.59 each, and this pipeline adds two model calls
per run plus a larger synthesizer brief. **If a run halts on cost, that is the most useful single
result in the sweep** — it would mean the Gate 4 threshold and the pipeline disagree, and the
threshold was written first.

**Cost estimate, registered so an overrun is visible as one: \$8–\$12 for the eight runs**, plus
judge. Materially above that is a finding.

### 5. Briefings fit

**Registered: no role reports `over_budget`, and the only section dropped, if any, is
`past-incidents`.** The 4,000-token cap was derived, not measured — the derivation is in
`Budget.briefing_tokens` — and this sweep is the first evidence about whether it is right. A
dropped `evidence-board` cannot happen (it is `essential`), so an `over_budget` synthesizer would
say the cap is too small for a wide fan-out and should move.

### 6. The corpus change has an expected direction and no expected size

Retrieval is `k = 3` and the corpus goes from seven documents to twenty-two. **Fifteen of the new
documents are authored runbooks, which `exclude_origin` never removes** — that is ADR-0036's whole
point, and ADR-0008's axis-2 exclusion still removes the scenario's own narrative.

**Registered: retrieval returns at least one runbook on most runs, and this is not contamination.**
No runbook names any catalog scenario, dev or holdout, and `tests/test_runbooks.py` asserts it.
What it does mean is that the synthesizer's retrieved context is materially different from S7's,
which is one more reason this sweep cannot isolate anything.

## What would surprise me

1. **Any scenario gated.** See prediction 1.
2. **A fault class moving on richer evidence.** The board is a superset of what S7's synthesizer saw.
3. **A proposal refused twice.** The contract checks are deterministic and the brief lists every
   legal action with its preconditions.
4. **A run halting on the dollar cap**, per prediction 4.
5. **A change point that disagrees with the alert.** The floors are the alert rules' own thresholds,
   so a scenario whose alert fired and whose change point is absent means the rule and the
   arithmetic disagree about the same series.
6. **Triage movement on any scenario.** Nothing in Batch B touched the blast-radius traversal —
   D4 moved it to the graph and proved it identical over all 91 seed sets — so triage precision and
   recall should be **exactly** S7's. A difference is a defect, not variance.

## Gate 3

**Gate 3 is declarable from this sweep and is not declared in advance.** Its condition is *"the
full pipeline — triage, plan, parallel specialists, synthesis, validated citations, proposal —
completes successfully on at least 3 of the 4 fault classes"*. The sixth stage now exists; whether
it completes is what the sweep observes. **If the gate passes, the declaration cites this
document**; if it does not, the reason is recorded and the gate stays undeclared.

## Order of operations

1. Seed the corpus — `faultline-seed --create-schema`. **This moves the `corpus` key**, so it
   happens before the freeze manifest is taken, not between runs.
2. Confirm the stamp is `bc222a353936` and the capability is `cap:c4d52d00`. A move after this
   document is committed means the sweep is measuring something nobody planned to measure, and the
   sweep stops rather than proceeding.
3. Run the eight scenarios, one each, no re-runs. **A discard is recorded and never re-run to
   improve a number.**
4. Score, judge, and write the sweep document against these predictions — including the ones that
   fail, which is the only reason to write them down first.
