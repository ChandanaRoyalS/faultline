# Dev sweep 2 — 2026-08-26, with the taxonomy instruction

The same seven runnable dev scenarios, through the **unchanged harness**, after one addition to
the synthesizer's instructions. Set beside sweep 1 throughout. Sweep 1 is untouched.

| | sweep 1 | sweep 2 |
|---|---|---|
| file | `SWEEP-2026-08-26.md` | this |
| stamp | `faultline/0.0.1+prompts:`**`59bf438b2a96`** | `faultline/0.0.1+prompts:`**`53fafe9c12bc`** |
| change | — | 28 lines added to `SYNTHESIZER_SYSTEM`; nothing else in any prompt |
| model / budget / harness protocol | identical | identical |
| cost | $2.9217 · 259,299 tokens | **$3.2676 · 305,145 tokens** |

The stamp moving is the experiment. Everything the digest covers — every role system prompt,
every contract schema — is otherwise identical, and everything it does not cover (the harness,
the gate, the scorer, the judge) was changed only in ways recorded under "Two defects" below,
none of which touch a prompt or a contract.

## Per-scenario, side by side

| scenario | truth | **S1** fault | fix | **S2** fault | fix | moved |
|---|---|---|---|---|---|---|
| ad-memory-squeeze | `resource_exhaustion` / `config_revert` | `bad_config` **WRONG** | ok | `unknown` **ABST** | ABST | wrong → abstained |
| cart-bad-image-tag | `bad_deploy` / `rollback` | `bad_deploy` ok | ok | `bad_deploy` ok | ok | — |
| cart-dependency-latency | `dependency_latency` / `restart` | `bad_config` **WRONG** | **WRONG** | **`dependency_latency` ok** | **WRONG** | **wrong → correct** |
| cart-redis-misconfig | `bad_config` / `config_revert` | `bad_config` ok | ok | `bad_config` ok | ok | — |
| frauddetection-memory-squeeze | `resource_exhaustion` / `config_revert` | `bad_config` **WRONG** | ok | **`resource_exhaustion` ok** | ok | **wrong → correct** |
| product-catalog-flag-failure | `bad_config` / `config_revert` | `bad_config` ok | ok | `unknown` **ABST** | ABST | correct → abstained |
| shipping-wrong-image | `bad_deploy` / `rollback` | `bad_deploy` ok | ok | `unknown` **ABST** | ABST | correct → abstained |

## Per fault class, both sweeps

Accuracy is over **answered** runs; abstentions leave the ratio and appear as coverage
(ADR-0022 §1.2).

| fault class | n | S1 fault | S2 fault | S1 fix | S2 fix | S2 abstained |
|---|---|---|---|---|---|---|
| `bad_config` | 2 | 2/2 | **1/1** | 2/2 | 1/1 | 1 |
| `bad_deploy` | 2 | 2/2 | **1/1** | 2/2 | 1/1 | 1 |
| `dependency_latency` | 1 | **0/1** | **1/1** | ~~0/1~~ **1/1** | ~~**0/1**~~ **1/1** | 0 |
| `resource_exhaustion` | 2 | **0/2** | **1/1** | 2/2 | 1/1 | 1 |
| ~~`scale`~~ | 0 | — | — | — | — | — |

**`bad_config` gained a third dev scenario at T7.22 — `shipping-quote-misconfig` — and it has
now been run once (T7.24).** The n above still does not move, because this table reports the S1/S2
sweeps and that run is neither: it is a single scored run at stamp `1b0e7cbb4c47`, reported on its
own in [`RUN-2026-08-29-shipping-quote-misconfig.md`](RUN-2026-08-29-shipping-quote-misconfig.md).

**Its result, stated where the class lives and not folded into any sweep figure:** fault class
`bad_config` ✔, fix class `config_revert` ✔, faulty service `shippingservice` ✔, judge
`same_mechanism`. **n=1 — an observation, not a rate**, and it is not averaged with anything.
The scenario's ground truth is unchanged by T7.28 - `fault_class: bad_config`,
`expected_remediation_class: config_revert` - so these axes still read against the labels they were
scored on. **The bundle the agent saw was re-recorded**, though, so the run is superseded in its
evidence; the run report carries the banner.

**The `scale` row is a mislabel, corrected at T7.13.** `scale` is a `RemediationClass`, not
a `FaultClass` - it is not in the scenario schema's enum, not in the agent's answer space, and
has no slot in SPLIT.md. It never belonged in a fault-class table. The remediation class is
genuinely empty, and ADR-0024 records why this world cannot fill it: 50x offered load for
twenty minutes saturates throughput at 102 req/s and trips no alert rule, so a scale fault
opens no incident and can never be scored.

| | sweep 1 | sweep 2 |
|---|---|---|
| fault class, of answered | **4/7** | **4/4** |
| coverage (reached a class) | **7/7** | **4/7** |
| class of fix, of answered | ~~6/7~~ **7/7** | ~~3/4~~ **4/4** |
| distinct classes returned | `bad_config`, `bad_deploy` | **all four, plus `unknown`** |

## The three questions

### 1. Does fault class move on `resource_exhaustion` and `dependency_latency`?

**Yes, on every one that produced an answer.**

- `dependency_latency`: **0/1 → 1/1.** `cart-dependency-latency` returned
  `dependency_latency`, the pair the dispute register was opened for.
- `resource_exhaustion`: **0/2 → 1/1 answered**, the second abstaining.
  `frauddetection-memory-squeeze` returned `resource_exhaustion`.

Both classes were returned for the first time in this project's history. **No run in either
sweep answered one of these classes and got it wrong.**

### 2. Does anything previously correct regress?

**Yes — two scenarios, and both regress to abstention rather than to a wrong answer.**

`product-catalog-flag-failure` and `shipping-wrong-image` were correct in sweep 1 and returned
`unknown` in sweep 2. Neither returned a *wrong* class.

**It is not budget exhaustion.** One abstention was budget-exhausted (`ad-memory-squeeze`) and
two were not; one budget-exhausted run did not abstain (`cart-redis-misconfig`). The two do not
line up.

The abstaining verdicts say why in their own words — `ad-memory-squeeze`:

> "With no observation of the failing mechanism — no evidence of saturation, of waiting on a
> slow dependency, of a wrong artifact, or of a wrong configuration value — assigning a fault
> class here would be invention, not inference."

That is the added instruction being followed: it asks what mechanism was *observed*, and a run
whose dispatches did not observe one now declines instead of naming the class its change record
suggests. Sweep 1 answered those runs from the change record and was sometimes right by
coincidence of the artifact matching the symptom.

### 3. Does the two-value classifier become a real one?

**Yes.** Sweep 1 returned exactly two values across seven scenarios and never a symptom class.
Sweep 2 returned **`bad_config`, `bad_deploy`, `dependency_latency`, `resource_exhaustion` and
`unknown`** — the whole taxonomy that has a scenario, plus abstention.

## What this does and does not say

**It says**: the classifier stopped being wrong. Every fault class it asserted in sweep 2 is
correct, against 4 of 7 in sweep 1.

**It also says**: it asserts less often. Coverage fell from 7/7 to 4/7.

Whether that trade is an improvement depends on what the system is for, and **this data does not
settle it**. Two of the three abstentions replaced correct answers. A reader who wants a class on
every incident is worse off; a reader who wants to trust the classes they get is better off.

**n is 1 per scenario and 1–2 per class.** No confidence interval on any cell here excludes the
opposite conclusion. What the tables support is direction, not magnitude.

## Triage — the control

| | sweep 1 | sweep 2 |
|---|---|---|
| recall (mean) | 0.94 | 0.95 |
| precision (mean) | 0.56 | 0.57 |
| unmeasured edges | 19 | 20 |

The change is confined to the synthesizer, which runs after triage, and triage did not move.
That is the closest thing this experiment has to a control, and it behaved.

## Reported separately, never averaged in

| category | sweep 1 | sweep 2 |
|---|---|---|
| flagged (other) | 1 | **0** |
| specialists failed alone | 0 | 0 |
| contradiction firings | 2 | **0** — the check was retired at T4.3 |
| budget exhausted | 1 | **2** |
| narrative refused | 0 | 0 |

## Judged columns

Same configuration both times: judge **`claude-haiku-4-5`** vs agent **`claude-opus-5`**,
**SHARED LINEAGE**, opted into by name. Sweep 2 judge cost: 39,997 tokens, **$0.2575**.

| | sweep 1 | sweep 2 |
|---|---|---|
| `same_mechanism` | **7** | 4 |
| `adjacent` | 0 | 0 |
| `different` | 0 | **3** |
| dead ends closed / missed | 42 / 35 | 31 / 29 |
| traps taken | 1 | 3 |

**The three `different` verdicts are exactly the three abstentions.** A narrative that declines
to name a mechanism does not name the recorded one, so the judge is measuring the same event the
deterministic scorer is — from the prose, with a different model, and agreeing.

This also removes T4.4's largest caveat: the judge had never used a level other than
`same_mechanism`, so it had not been shown to discriminate. **It has now**, and it did so on
exactly the runs a separate measurement says are different.

## Two defects the sweep found, both fixed, neither touching the stamp

**A lost update, which blocked the sweep.** The investigation runner held an `Incident` loaded
before the run and wrote it back at each phase boundary; `save` upserts episodes from that
in-memory copy, so it silently overwrote `resolved_at` on episodes the orchestrator had resolved
during the investigation. The incident could then never reach `resolved`, and the baseline gate
correctly refused **two scenarios** because a non-terminal incident was sitting in the store.
`applied_events` recorded the resolves as applied, so replaying the delivery was a correct no-op
— the record said done and the row said otherwise. The runner now uses a narrow write
(`save_investigation_state`) that touches the two fields it owns and no episode row.

**Retry meeting terminal states, which cost two more scenarios.** T4.3's bounded retry fired on
a 529 that landed *after* the run had done work. A run that got somewhere and then failed leaves
the incident `FAILED`, which ADR-0016 makes terminal — so the retry could only ever be told the
incident is not investigable, and it was, twice. Retry is now limited to a **failed start**,
which is the one case that leaves the incident in `triaging` untouched. Both scenarios were
re-run and appear in the table above.

Neither fix is in `faultline.agents`' prompts or contracts, so `53fafe9c12bc` covers every sweep-2
row regardless of which side of the fix it ran on.

## Discards

| run | scenario | reason | outcome |
|---|---|---|---|
| `20260826T103141Z` | cart-bad-image-tag | gate refused — stranded incident (lost update) | re-run `20260826T105651Z` |
| `20260826T103722Z` | cart-dependency-latency | gate refused — same | re-run `20260826T111958Z` |
| `20260826T115857Z` | product-catalog-flag-failure | 529 mid-run → incident `FAILED` → retry refused | re-run `20260826T123016Z` |
| `20260826T121554Z` | shipping-wrong-image | same | re-run `20260826T125005Z` |

All four directories keep their `DISCARDED.md`. Cost figures above are the seven scored runs
only; the discards are additional and are not in any table.
