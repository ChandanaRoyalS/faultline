# Variance on the abstention path — `product-catalog-flag-failure`, five repeats

T4.11. The complement to [T4.10](VARIANCE-2026-08-27.md), which measured run-to-run
variance on a scenario the agent answers. This measures it on a scenario the agent
does not.

## Why this scenario and not `email-wrong-image`

T4.10 named `email-wrong-image` as the untested case. It stays untested. It is a
**holdout** scenario, and five development repeats of a holdout scenario is repeated
holdout use wearing a costume — the split exists precisely to stop that, and running it
five times "for variance" would spend the holdout while calling the spending something
else. `product-catalog-flag-failure` is the dev-legal instrument: same abstention
behaviour, no contamination cost.

## Configuration, declared before the first run

| | |
|---|---|
| stamp | `faultline/0.0.1+prompts:53fafe9c12bc` |
| budget | `changes` 8, all other specialists 4; `max_tokens` 120,000; `wall_clock` 600s; `max_dispatch_rounds` 2 |
| freeze | [`FREEZE-2026-08-27-abstention.json`](FREEZE-2026-08-27-abstention.json), committed before any repeat ran |
| repeats | **5, one at a time**, full protocol between each (baseline gate → inject → settle → investigate → revert → recovery gate) |
| discards | **1** — no replacement run. Five attempts is the experiment. |
| cost | **$1.7472** agent + $0.1477 judge |

Identical to T4.10 in every field, so the two experiments differ only in scenario.

**Prior byte-identical observation.** The T4.7 sweep's `product-catalog-flag-failure`
row (`20260826T203657Z`) ran under this exact stamp and all four bounds — verified
field by field, not by description. It counts as a prior observation, as T4.10 counted
its own.

## The five repeats

| # | run | round-1 breadth | rounds | tool calls | fault class | confidence | exhausted | tokens | judge |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `20260827T044827Z` | 4 | 2 | 8 | **`unknown` / `none` — abstained** | low | — | 34,739 | `different` |
| 2 | `20260827T050940Z` | 4 | 2 | 7 | **`unknown` / `none` — abstained** | low | — | 28,846 | `different` |
| 3 | `20260827T052853Z` | — | — | — | **DISCARD** — 529 mid-run, exit 4, no verdict artifact | — | — | — | — |
| 4 | `20260827T054617Z` | 5 | 2 | 8 | **`unknown` / `none` — abstained** | low | — | 34,584 | `different` |
| 5 | `20260827T060533Z` | 5 | 2 | 9 | **`unknown` / `none` — abstained** | low | — | 39,055 | `different` |

Both gates passed on the discarded attempt; the retry correctly declined, because a 529
mid-investigation is not a failed start.

Triage recall **1.0** on all four. Precision 0.43 on three, 0.25 on repeat 4. **Unchanged by T7.3's rescore** — `product-catalog-flag-failure`'s recording at the time had no service alerting both during the fault and in recovery.

Coverage **0 / 4**. With the prior byte-identical row, the abstention is **5 / 5**.

## The read

### Is the abstention stable?

**Yes — completely.** Five observations under one byte-identical configuration, five
abstentions, all at `low` confidence, all reaching `unknown` / `none`. Not one repeat
answered.

The user's hypothetical — *if any repeat answers, that trajectory becomes the most
valuable object in the experiment* — **has no referent. No repeat answered, so there is
no such trajectory, and none is manufactured here.**

But reading the four trajectories closely produced something better than a lucky repeat:
a mechanical explanation for why the abstention is stable, which is not the explanation
the experiment was designed to test.

### The abstention is not calibrated judgement. It is an evidence-reachability gap.

The scenario was assumed to be hard because its cause sits on a service the alerts never
name — the flag service — so the planner cannot dispatch at the target. That is true, and
it is not what is stopping the agent.

**Every plan in every repeat dispatched `logs:productcatalogservice`, and that stream is
empty by construction.** ADR-0005 measured it and published the number: `product-catalog-service`
emits **0 lines/hour**. The scenario file says so too, in a comment written at authoring
time — *"product-catalog-service logs only a startup banner at its default level, so the
deliberate-failure signal exists solely on the span."* The container's entire log file is
**525 bytes**, last written three days before the first repeat. Loki holds no `service`
label for it at all.

The planners budget their evidence on that stream, in their own words:

> "The dependency graph is small and already enumerated, and per-dependency metrics on
> frontend plus **productcatalogservice logs** should localize the fault; traces would be
> worth the cost only if metrics show frontend errors that do not attribute to any named
> downstream."

Both log calls in all four repeats went to that stream. Both came back empty. And the
agent's diagnosis of the emptiness was wrong in a way that closed the exit:

> "What is the correct Loki label for this service? Both attempts used the hyphenated form
> and matched nothing; the unhyphenated service value or a different key (app/job/container)
> should be tried before any conclusion is drawn about log content."

It read an empty stream as a **query-syntax defect** rather than as a fact about the world,
so it re-issued the same query — several round-2 plans describe "corrected logs pending" —
instead of converting to a different evidence class.

**No repeat ever called `trace_query`.** Tool mix across all four: `change_history` 2–3,
`promql_query` 2–4, `logql_query` 2. Zero traces — and the scenario puts **four of its eight
`expected_evidence` items on traces**, including both discriminators (the span event naming
a deliberate flag-driven path; the successful `GetFlag` preceding each failing `GetProduct`).
Every plan skipped traces on an explicit cost argument. The planner prompt supplies the prior
that invites it: *"change history and metrics were consulted in all ten, logs in seven,
**traces in two**."*

So the chain is: plan on a stream that cannot answer → misread its silence as a syntax
error → spend the retry on it → never reach the evidence class that holds the answer →
honestly report the mechanism as unmeasured → abstain. The abstention is correct behaviour
given what the agent held. It just never held what it needed.

**Corroboration from the one run that ever solved this scenario.** `20260826T075423Z` (S1,
stamp `59bf438b2a96` — a different stamp and a different budget, so **not** a repeat and not
counted as one) queried **`frontend`** logs instead, and got the answer verbatim:

```
Error: 13 INTERNAL: Error: ProductCatalogService Fail Feature Flag Enabled
```

One tool call, different service, and the flag names itself. That route is not in the
scenario's `expected_evidence` at all — frontend logs 0 lines/hour when healthy and only
speak when something downstream fails. The difference between the solve and the five
abstentions is not reasoning quality. It is which service's logs got queried.

### Breadth variance, beside T4.10's

| | T4.11 (abstains) | T4.10 (answers) |
|---|---|---|
| round-1 breadth | 4, 4, 5, 5 | 5, 7, 8, 8, 13 |
| spread | **1** | **8 (2.6×)** |
| rounds | 2, 2, 2, 2 | 1, 2, 2, 2, 2 |
| tool calls | 7–9 | 8–11 |
| tokens | 28,846–39,055 (**1.35×**) | 36,430–68,493 (**1.9×**) |
| distinct verdicts | 1 (`unknown`/`none`) | 1 (`bad_config`/`config_revert`) |
| exhausted bounds | 0 | 1 (`metrics` 4/4) |
| confidence | low ×4 | high ×4, medium ×1 |
| judge | `different` ×4 | `same_mechanism` ×5 |
| dead ends closed / missed | 3/2, 4/4, 2/3, 7/4 | 3/3, 5/2, 4/4, 7/2, 5/6 |
| cost per run | $0.378–$0.470 | $0.479–$0.702 |

The abstention path is **tighter than the answering path on every dispersion measure**.
That is the opposite of the intuition that an agent which cannot find the answer flails.
It does not flail — it converges, quickly and cheaply, on the same wrong plan, and stops.
Low dispersion here is a symptom of a *systematic* blocker, not of confident calibration:
the same reachability gap bites identically every time, so there is nothing left to vary.

Both experiments produced exactly **one distinct verdict** across five observations. Neither
is evidence of general determinism; both are single-scenario measurements.

### What this means for S2's dev coverage figure of 4 / 7

`4/7` should **not** be read as "the agent answers 4 and correctly declines on 3." At least
one of the three non-answers — this one — is a non-answer the agent could not have avoided
from where it was standing, because it planned around an evidence source that is empty by
construction and never opened the one that holds the answer.

Concretely:

- **The abstention is stable, not flickering.** `4/7` will not drift to `5/7` on a re-run.
  Five observations, zero answers. The figure is reproducible.
- **Stability is not the same as correctness of the decision.** The denominator is doing
  work here that it should not. Reporting `4/7` alongside "the agent abstains rather than
  guessing" implies the abstentions are calibrated. For this scenario that reading is
  **not supported** — the abstention is forced by tool selection, and a single different
  log target flips it, as the S1 row shows.
- **Nothing here changes 4/7.** No prompt, budget or tool change was made; the stamp did
  not move. What changes is what the number is allowed to claim.

The other two dev non-answers have **not** been analysed this way. Whether they share this
mechanism is unmeasured, and the honest statement is that one of three is explained.

## The judge

Same configuration as T4.10: `claude-haiku-4-5` against `claude-opus-5`. **Shared lineage
— both are Anthropic models**, so the run required `FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE=1`
and every row above carries that label. The agreement column is not an independent check.

All four scored `different`, for the same structural reason rather than a disagreement about
mechanism — the reference narrative names the flag, and the agent narrative reaches no
conclusion at all. `different` is the correct code for "no conclusion" and should not be
read as "wrong conclusion."

Judge cost: in 21,959 / out 1,515 tokens, **$0.1477**.

## What this experiment does not show

- Nothing about `email-wrong-image` or the holdout abstentions. Untouched, by design.
- Nothing about whether traces *would* have solved it. That is the obvious next experiment
  and it was not run here — dispatching traces is a stamp-moving change, out of T4.11's scope.
- Nothing about the other two dev non-answers.
- n = 4 repeats + 1 prior observation, one scenario, one stamp. No interval is claimed on a
  5/5 unanimous outcome; the honest statement is the count and the mechanism, not a rate.
