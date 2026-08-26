# T4.9 — planner allocation, read from the archive

No model calls, no injections, no world. This reads every stored investigation and asks the
question T4.8 surfaced: **the same scenario, the same stamp, and 12 planned round-1 dispatches
against 3 — how variable is planner allocation, and does breadth predict outcome?**

## What is in scope

39 trajectories are stored. **36 carry a plan** and appear below; three are excluded and named
here rather than dropped:

- `08242d2b` (`t3.2-smoke`) and `701e810f` (`t3.3-stage1`) — boundary smokes, not investigations.
- `f7261a74` — T3.5's failed start, **zero steps**, no plan.

Of the 36, **33 produced a verdict**; three failed before the synthesizer and are shown with
`_no verdict_`. Summary statistics below use the 33 unless stated.

**Thirteen rows predate the run manifest.** Their scenario is inferred from the injector's
`change_records` — the change closest before the trajectory started names the target service, and
where one service hosts several scenarios the record's own summary (`environment`,
`traffic-shaping`, `image`) disambiguates. Their budget, blast radius and stamp show `—` where the
manifest is the only source. The seven rows stamped `t3.3` carry the literal string the field held
before T4.1 derived it, which is why that stamp cannot be compared with the others.

## Every stored investigation

`c/m/l/t` = changes / metrics / logs / traces dispatches in round 1. "Target" is the service the
injector actually broke, canonicalised.

| # | scenario | stamp | `changes` bound | round-1 dispatches | per tool (c/m/l/t) | services in r1 plan | rounds | services queried | blast radius | target in r1 | target ever | exhausted | outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ad-memory-squeeze | `53fafe9c12bc` | 4 | **13** | 6/6/0/1 | 6 | 1 | 4 | 7 | **yes** | **yes** | changes tool calls: 4 of 4 | _abstained_ |
| 2 | ad-memory-squeeze | `53fafe9c12bc` | 8 | **13** | 6/5/1/1 | 6 | 1 | 6 | 7 | **yes** | **yes** | metrics tool calls: 4 of 4 | **correct** |
| 3 | ad-memory-squeeze | `59bf438b2a96` | 4 | **9** | 6/2/0/1 | 6 | 1 | 4 | 7 | **yes** | **yes** | changes tool calls: 4 of 4 | wrong |
| 4 | cart-bad-image-tag | `53fafe9c12bc` | 8 | **3** | 1/1/0/1 | 1 | 2 | 2 | 13 | no | **yes** | - | **correct** |
| 5 | cart-bad-image-tag | `53fafe9c12bc` | 4 | **5** | 1/2/1/1 | 2 | 2 | 3 | 14 | no | **yes** | - | **correct** |
| 6 | cart-bad-image-tag | `59bf438b2a96` | 4 | **5** | 1/2/1/1 | 2 | 2 | 2 | 12 | **yes** | **yes** | - | **correct** |
| 7 | cart-bad-image-tag | `69aa6c670318` | — | **3** | 1/1/0/1 | 3 | 2 | 4 | — | no | **yes** | - | wrong |
| 8 | cart-bad-image-tag | `_t3.3 (literal)_` | — | **3** | 1/1/0/1 | 1 | 2 | 2 | — | no | **yes** | - | _no verdict_ |
| 9 | cart-dependency-latency | `53fafe9c12bc` | 4 | **4** | 1/2/1/0 | 2 | 2 | 4 | 12 | **yes** | **yes** | - | **correct** |
| 10 | cart-dependency-latency | `53fafe9c12bc` | 8 | **9** | 2/6/1/0 | 6 | 1 | 4 | 12 | **yes** | **yes** | metrics tool calls: 4 of 4 | **correct** |
| 11 | cart-dependency-latency | `59bf438b2a96` | 4 | **3** | 1/1/1/0 | 1 | 2 | 2 | 12 | **yes** | **yes** | - | wrong |
| 12 | cart-dependency-latency | `_t3.3 (literal)_` | — | **3** | 1/1/1/0 | 1 | 2 | 2 | — | **yes** | **yes** | - | wrong |
| 13 | cart-redis-misconfig | `53fafe9c12bc` | 4 | **9** | 4/4/0/1 | 4 | 2 | 4 | 12 | **yes** | **yes** | changes tool calls: 4 of 4 | **correct** |
| 14 | cart-redis-misconfig | `53fafe9c12bc` | 8 | **9** | 3/3/2/1 | 4 | 2 | 4 | 12 | **yes** | **yes** | - | **correct** |
| 15 | cart-redis-misconfig | `59bf438b2a96` | 4 | **4** | 1/1/1/1 | 1 | 2 | 2 | 12 | no | **yes** | - | **correct** |
| 16 | cart-redis-misconfig | `59bf438b2a96` | 4 | **4** | 1/2/0/1 | 2 | 2 | 3 | 12 | no | **yes** | - | **correct** |
| 17 | cart-redis-misconfig | `69aa6c670318` | 4 | **4** | 1/1/1/1 | 1 | 2 | 4 | 12 | no | **no** | - | _abstained_ |
| 18 | email-wrong-image | `53fafe9c12bc` | — | **3** | 1/1/0/1 | 1 | 2 | 1 | — | no | **no** | - | _abstained_ |
| 19 | email-wrong-image | `53fafe9c12bc` | 4 | **12** | 5/5/1/1 | 5 | 1 | 4 | 9 | **yes** | **yes** | changes tool calls: 4 of 4 | _abstained_ |
| 20 | frauddetection-memory-squeeze | `53fafe9c12bc` | 4 | **3** | 1/1/1/0 | 1 | 2 | 1 | 1 | **yes** | **yes** | - | **correct** |
| 21 | frauddetection-memory-squeeze | `53fafe9c12bc` | 8 | **3** | 1/1/1/0 | 1 | 2 | 1 | 1 | **yes** | **yes** | - | **correct** |
| 22 | frauddetection-memory-squeeze | `59bf438b2a96` | 4 | **3** | 1/1/1/0 | 1 | 2 | 1 | 1 | **yes** | **yes** | - | wrong |
| 23 | product-catalog-flag-failure | `53fafe9c12bc` | 4 | **4** | 1/2/1/0 | 2 | 2 | 3 | 7 | no | **no** | - | _abstained_ |
| 24 | product-catalog-flag-failure | `53fafe9c12bc` | — | **5** | 2/2/1/0 | 2 | 1 | 2 | — | no | **no** | - | _no verdict_ |
| 25 | product-catalog-flag-failure | `53fafe9c12bc` | 8 | **5** | 2/2/1/0 | 2 | 2 | 3 | 7 | no | **no** | - | _abstained_ |
| 26 | product-catalog-flag-failure | `59bf438b2a96` | 4 | **3** | 1/1/1/0 | 2 | 2 | 2 | 7 | no | **no** | - | **correct** |
| 27 | productcatalog-dependency-latency | `53fafe9c12bc` | 4 | **6** | 3/2/1/0 | 3 | 2 | 3 | 12 | **yes** | **yes** | - | **correct** |
| 28 | recommendation-memory-squeeze | `53fafe9c12bc` | 4 | **12** | 6/5/0/1 | 6 | 1 | 4 | 7 | **yes** | **yes** | changes tool calls: 4 of 4 | _abstained_ |
| 29 | shipping-wrong-image | `53fafe9c12bc` | — | **4** | 1/1/1/1 | 1 | 1 | 1 | — | no | **no** | - | _no verdict_ |
| 30 | shipping-wrong-image | `53fafe9c12bc` | 4 | **4** | 1/2/1/0 | 2 | 2 | 4 | 11 | no | **no** | - | _abstained_ |
| 31 | shipping-wrong-image | `53fafe9c12bc` | 8 | **8** | 4/3/0/1 | 4 | 2 | 5 | 12 | no | **yes** | - | **correct** |
| 32 | shipping-wrong-image | `59bf438b2a96` | 4 | **3** | 1/1/0/1 | 1 | 2 | 2 | 12 | no | **yes** | - | **correct** |
| 33 | shipping-wrong-image | `_t3.3 (literal)_` | — | **3** | 1/2/0/0 | 2 | 2 | 3 | — | no | **no** | - | _abstained_ |
| 34 | shipping-wrong-image | `_t3.3 (literal)_` | — | **3** | 1/1/0/1 | 1 | 2 | 3 | — | no | **yes** | - | **correct** |
| 35 | shipping-wrong-image | `_t3.3 (literal)_` | — | **3** | 1/1/1/0 | 1 | 2 | 3 | — | no | **no** | - | _abstained_ |
| 36 | shipping-wrong-image | `_t3.3 (literal)_` | — | **4** | 1/2/0/1 | 2 | 2 | 3 | — | no | **yes** | - | **correct** |

## How variable is breadth?

Round-1 dispatch counts across all 36 rows: **minimum 3, maximum 13**.

Per scenario where n ≥ 2 — the only comparisons where the scenario is held constant:

| scenario | n | round-1 breadths | spread |
|---|---|---|---|
| shipping-wrong-image | 8 | 3, 3, 3, 3, 4, 4, 4, **8** | 5 |
| cart-bad-image-tag | 5 | 3, 3, 3, 5, 5 | 2 |
| cart-redis-misconfig | 5 | 4, 4, 4, 9, 9 | 5 |
| cart-dependency-latency | 4 | 3, 3, 4, **9** | 6 |
| product-catalog-flag-failure | 4 | 3, 4, 5, 5 | 2 |
| ad-memory-squeeze | 3 | 9, 13, 13 | 4 |
| frauddetection-memory-squeeze | 3 | 3, 3, 3 | **0** |
| email-wrong-image | 2 | 3, **12** | **9** |

Two scenarios have n = 1 and no spread to report: `productcatalog-dependency-latency`,
`recommendation-memory-squeeze`.

**Breadth is variable, and unevenly so.** `frauddetection-memory-squeeze` planned exactly three
dispatches on all three runs. `email-wrong-image` planned three and twelve — the observation that
prompted this analysis, and the largest spread in the archive at n = 2. `shipping-wrong-image`
sat at 3–4 on seven of eight runs and once planned eight.

**These rows are not repeats.** They differ in stamp, in `changes` bound, and in the incident the
world produced that day. Spread here is an upper bound on run-to-run variance, not a measurement
of it — no two rows in this table hold everything else constant. A clean variance figure needs
repeats under one configuration, which the archive does not contain.

## Does breadth predict outcome?

n = 33.

| round-1 breadth | n | correct | wrong | abstained | answered |
|---|---|---|---|---|---|
| 3–4 | 20 | 10 | 4 | 6 | 14 / 20 |
| 5–8 | 5 | 4 | 0 | 1 | 4 / 5 |
| 9–13 | 8 | 4 | 1 | 3 | 5 / 8 |

**No.** The narrowest band answers 14 of 20 and the widest 5 of 8; correct-rate is 10/20 against
4/8. If anything the widest plans do slightly worse, and they are also where every budget
exhaustion lives — all seven exhausted runs planned 4 or more, and the four widest plans (9–13)
account for four of them.

**This is a correlation across rows that differ in several ways at once**, and the cell counts are
4–20. It does not support "wider plans are worse". It does support "wider plans are not
obviously better", which is the claim the next section makes precise.

## Does asking about the right service predict answering?

This is the relationship the data actually carries.

| target service planned, any round | n | correct | wrong | abstained | **answered** |
|---|---|---|---|---|---|
| **yes** | 25 | 17 | 5 | 3 | **22 / 25** |
| **no** | 8 | 1 | 0 | 7 | **1 / 8** |

Restricting to round 1 only weakens it sharply — target in the round-1 plan answers 13/16, target
absent from round 1 answers 10/17 — because the follow-up round frequently supplies the service
the first round missed. **It is being asked at all that matters, not being asked first.**

### One confound, removed

Three of the eight "never planned" rows are `product-catalog-flag-failure`, whose target is
`featureflagservice` — a service that **emits no span metrics at all** and therefore never enters
a blast radius (`evals/scenarios/artifacts/dev/flag-service-crashloop/INVALID.md`). The planner
cannot name it, so those rows are structurally unable to score "yes" and belong in their own line.

Excluding them, n = 30:

| target planned, any round | n | outcome |
|---|---|---|
| yes | 25 | 22 answered, 17 correct |
| **no** | **5** | **5 abstained, 0 answered** |

**Every investigation that never planned a dispatch against the broken service abstained.** Five
for five. The three `featureflagservice` rows, where the service could not be planned, split
1 correct / 2 abstained — the correct one reached the flag through frontend logs instead, which
T4.4's judge flagged as arriving by a route the recorded narrative names as a way to be
confidently wrong.

**This is a correlation and the mechanism is not mysterious**: a verdict cannot classify evidence
nobody gathered, and since T4.5 the synthesizer is instructed to name an observed mechanism or
decline. The direction is not established by this table — a planner that reaches the right service
may be one that already understood the incident. What the table establishes is that the two travel
together in 30 of 33 rows.

## Two smaller readings

**The follow-up round is where narrow plans recover.** Rows using both rounds: 27, of which 16
correct. Rows using one round: 6, of which 3 abstained. The single-round rows are mostly the very
wide plans that exhausted a bound in round 1 and never got a second — the plan was broad and the
investigation was still short.

**Planned breadth overstates what was queried.** The widest plans did not produce proportionally
more evidence: 13 planned dispatches yielded 4 distinct services queried in one run and 6 in
another; 12 planned yielded 4 in both cases. The bound truncates the plan, so a wide plan under a
tight bound is a plan that will not be executed.

## What this poses for the next stamp

**None of it is acted on here.** The candidate experiment is recorded in `docs/PLAN.md`.

The archive contains no two rows that hold scenario, stamp and budget constant, so **run-to-run
variance has never been measured** — every spread above is confounded. And the one relationship
the data does carry, that never asking about the broken service coincides with never answering, is
about *which* dispatches a plan contains rather than how many.

Both point at the same next measurement, and it needs no new machinery: **repeat one scenario
several times under one fixed configuration.** That would give the first clean variance figure for
planner breadth, and would say whether "did the plan include the target" is itself stable across
repeats or is the thing that varies.
