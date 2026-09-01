# Holdout entry 4 — assessed, and **not opened**

**Nothing ran. No holdout scenario was injected, no agent saw one, and the set's exposure counts
are unchanged at `email-wrong-image` 3, `productcatalog-dependency-latency` 2,
`recommendation-memory-squeeze` 2.**

This file exists because the ledger's purpose is that *"the number of holdout runs is a fact worth
being unable to hide"* (ADR-0022 §3.3). A reader who finds entries 1, 2 and 3 and no entry 4 should
be able to see whether the fourth was never considered or was considered and declined. It was
declined, and this is the reason.

---

## 1. The protocol governs, and it names this entry specifically

ADR-0022's **T4.15 addendum** — the argument that opened entry 3 — closes with:

> **This should be the last entry before the set is re-authored or extended.** Not a rule this
> addendum can enforce on its successor, but the reason is arithmetic rather than taste: a
> three-scenario set read four times is no longer a holdout in any sense a reader would recognise,
> and T7.0's four further fault classes are the honest way to buy more.

**The set has not been re-authored or extended.** Checked, not assumed:

- `evals/scenarios/artifacts/holdout/` holds **exactly three** bundles — the same three.
- A fourth scenario carries `split: holdout` in its YAML, `flag-service-bad-deploy`, and it is
  **blocked**: it has no slot, no bundle, and `tests/test_contamination.py` records that it
  *"produces no bundle and drops out here too."* It is not a fourth holdout scenario.
- **The extension was allocated but never filled.** SPLIT.md's T7.35 table shows three free holdout
  slots — `bad_config-5`, `bad_config-6`, `bad_deploy-6` — and every scenario authored since
  (T7.36's `payment-telemetry-blackout`, T7.38's `redis-cart-dependency-latency`) went to a **dev**
  slot. Allocating capacity is not extending the set.

Entry 4 would make the exposures **4 / 3 / 3** on a three-scenario set. That is the arithmetic the
addendum described, and the condition it attached has not been met.

## 2. The four conditions, applied honestly — all four pass

This is stated because it is the interesting part: **entry 4 is not blocked by the four-condition
test, and would in fact clear it more cleanly than entries 2 and 3 did.**

**1. Validated on dev before holdout is touched — MET.** T7.28's world change was measured on dev
first: **dev sweep 7 (T7.29)**, 8 of 8 scenarios scored with no discards, coverage 8/8, fault class
7/8, class of fix 7/8, judge `same_mechanism` 7/8.

**2. Justified by mechanism, not by a holdout signal — MET, and cleanly.** Entries 2 and 3 both met
this condition *under strain*, and entry 3's strain was that the failure mode it tested was
chronologically first named on holdout. **Entry 4 has no such leak at all.** What changed is the
world — kafka's allocator bounded, a `maxmemory`/`allkeys-lru` bound on redis-cart, a
`memory_limiter` on the collector — and every one of those came out of T7.27/T7.29's investigation
of kafka memory growth across **dev sweeps**. No holdout run informed any of it. **This would be
the first entry whose condition 2 is met without qualification.**

**3. A prediction registered before the run — would be met.** Drafted in §6 below and deliberately
**not activated**.

**4. Entries 1–3 stand unedited — would be met.** No file was touched.

**So the blocker is not the four-condition test. It is the successor limit the same addendum
attached, and that limit is the whole reason it was written.**

## 3. The entitlement argument, which is real and still loses

There is a genuine argument for opening entry 4, and it is the argument both prior addenda used to
reject a flat *no*:

> a holdout number that can never be refreshed describes a system that no longer exists, and the
> project would be unable to report a holdout figure for its current configuration — which is a
> different way of having no benchmark.

**That condition is now true in its strongest form.** All three entries carry the superseded-world
banner: every holdout figure this project has published was measured against
`compose_digest 299d791c5e0d…`. **There are zero current-world holdout figures.** Dev sweep 7 is a
new reported result under the current world, and §3.3's *"a holdout run happens once per reported
result"* entitles it to an entry.

**It loses anyway**, for the reason T4.15 gave when it declined T7.1's schedule argument: urgency
created elsewhere says nothing about whether the set can bear another read. Both facts are true —
the published holdout figure is stale **and** the set is nearly exhausted — and spending the last
readable margin of a three-scenario set to refresh a number is precisely the trade the addendum
told its successor not to make **without extending the set first**. The remedy it named is
available and cheap relative to what it protects: **three free holdout slots are already allocated
and waiting for scenarios.**

## 4. Two things the check turned up that were not the question

**The stamp is fine; the stamp was never the binding constraint.** Verified live:
`runtime_version = faultline/0.0.1+prompts:1b0e7cbb4c47` — unmoved, and identical to entry 3's.
`compose_digest f5bd108f4f70f460…` and `observability_digest 857d95b4d174ec43…` — both matching
what T7.29 and T7.48 recorded, so the world is where it should be. **But entry 3 ran under this
same stamp against a *different world*.** Comparability with entries 1–3 is broken by the world
move, not by the stamp, and an entry 4 would be a new baseline rather than a continuation.

**§3.3's freeze table does not include the world.** Its six frozen items are prompts, corpus, model
map, budget, tool layer and judge. The world digest is not among them, so the rule that *"a holdout
run whose manifest does not match the dev run it is being compared against is not a comparison"*
would **not** have caught the world move on its own — only the superseded-world banners on the three
entry files record it. Noted here, not fixed; changing the freeze table is a decision of its own.

**Nothing environmental blocks the run.** The gate passes: kafka at **37.14%** against an **82.31%**
threshold for three runs. The stack is up. Had the protocol permitted it, it would have run today.

## 5. Cost, stated before deciding rather than after

**Estimate ≈ \$1.7–1.9, within the \~\$2 ceiling.** Two independent derivations: entry 3's three
scenarios cost **\$1.6758 agent + \$0.1086 judge = \$1.7844** at the same bound and stamp; and
T7.51's two current-world runs cost \$0.5387 and \$0.5175, so three ≈ \$1.60 plus ≈\$0.13 judged.

**Cost is not why this stopped.** It was affordable, the gate passed, and the money was available.
It stopped on the protocol.

## 6. The pre-registration, drafted and NOT ACTIVATED

Recorded so the decision is about the protocol and not about missing preparation. **If this is ever
activated it must be re-committed as its own file, before anything runs, with the date it was
actually registered** — a prediction copied out of a document that already exists is not a
registration.

> **Scenarios.** All three, one run each. n = 3, one observation per scenario. No repeats.
>
> **Configuration.** Stamp `prompts:1b0e7cbb4c47`; bounds `changes` 8, others 4, 120k tokens, 600s,
> 2 rounds; agent `claude-opus-5`, judge `claude-haiku-4-5` (SHARED LINEAGE); world
> `compose_digest f5bd108f…` / `observability_digest 857d95b4…`; freeze manifest committed first,
> `holdout_chunks: 0` asserted.
>
> **Prediction, derived from dev.** Dev sweep 7 on the current world scored **coverage 8/8, fault
> class 7/8, class of fix 7/8, judge `same_mechanism` 7/8**. Holdout entry 3 on the *previous* world
> scored 3/3 on all four. The prediction is therefore **coverage 3/3 and fault class ≥ 2/3**, on the
> ground that the pipeline is unchanged and the world change was a stability fix rather than a
> signal change — dev's one class miss was `shipping-quote-misconfig`, which has no holdout analogue.
> **Falsified by coverage ≤ 1/3, or fault class ≤ 1/3.**
>
> **What a dev/holdout gap would mean, both directions, with the limits.** *Holdout worse* would
> suggest the dev figures are optimistic — but at n = 3, one abstention moves the figure by 33
> points, so a 3/3-versus-2/3 gap is one run and distinguishes nothing. It would be a reason to
> extend the set, not a finding about the pipeline. *Holdout equal or better* would be consistent
> with the dev results generalising, and would establish almost nothing: three scenarios read for
> the fourth time, on a set whose two easiest members answered correctly the last time they were
> asked, cannot demonstrate generalisation. **Neither direction is powered. That is the finding the
> set can support, and it is the same finding whether or not the runs happen.**
>
> **Discipline.** No re-runs. Discards recorded with their reason and never deleted. A run that dies
> environmentally reports at the n it achieved — an entry cut short is a smaller entry, not a retry.
> Judged as part of the entry, since every other holdout run carries a judge block.

## 7. The holdout arm as it actually stands — three entries, and underpowered

| entry | entitled by | stamp | world | scored | cost |
|---|---|---|---|---|---|
| **1** | T4.5's taxonomy-instruction pipeline | `53fafe9c12bc` | `299d791c5e0d` *(superseded)* | 3 / 3 | \$1.0774 + \$0.1203 judged |
| **2** | T4.7's raised `changes` bound | `53fafe9c12bc` | `299d791c5e0d` *(superseded)* | **1 / 3** — two discarded to an empty API account, **not re-run** | \$0.4175, no judge |
| **3** | T4.14's return-to-locus pipeline (dev sweep 5) | `1b0e7cbb4c47` | `299d791c5e0d` *(superseded)* | 3 / 3 | \$1.6758 + \$0.1086 judged |
| **4** | *(would be: T7.29's dev sweep 7 on the current world)* | — | — | **NOT OPENED** | \$0 |

**Seven agent-facing runs, across three entries, on three scenarios. Four answered.** Of those four:
fault class **4 / 4**, judged `same_mechanism` **4 / 4** (T7.52's corpus roster). The other three runs
abstained.

**This arm cannot support a claim, and n is the smaller of the two reasons.**

1. **Every figure describes a world that no longer exists.** All seven runs predate T7.28. There is
   no current-world holdout number, and adding an entry 4 would have produced one that is
   comparable to nothing before it.
2. **Four answered runs over three scenarios**, three of them from a single entry, and two of those
   three scenarios answered correctly the last time they were asked. A 4/4 on that base is not
   evidence of generalisation; it is four observations.
3. **One of the three scenarios is not independent evidence about itself.** T4.15 recorded that
   `email-wrong-image` is *"corroborative, not confirmatory"* — the failure mode entry 3 tested was
   first named on that scenario.

**The honest statement is that this arm remains underpowered, and that spending its last comfortable
read to refresh a stale number would have made it thinner rather than stronger.** The way to a
holdout figure worth quoting is the one T4.15 named: **author scenarios into the three free holdout
slots**, then open entry 4 against a set that can bear it.

## 8. What would unblock entry 4

**Fill at least one free holdout slot** — `bad_config-5`, `bad_config-6` or `bad_deploy-6` — with a
recorded, rehearsed scenario. `bad_config` is the strongest candidate: it has **zero** holdout
representation today and the most unexplored diagnosis paths (SPLIT.md). At that point the set is
extended, T4.15's condition is met on its own terms, the four conditions already pass, and the
entitlement from dev sweep 7 is waiting. **Queued as Q9.**
