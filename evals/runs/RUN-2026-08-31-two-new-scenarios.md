# T7.41 — scoring `payment-telemetry-blackout` and `redis-cart-dependency-latency`

Pre-registered in
[`PREREGISTRATION-2026-08-31-two-new-scenarios.md`](PREREGISTRATION-2026-08-31-two-new-scenarios.md),
committed before any run. **Nothing was re-run.**

| | |
|---|---|
| stamp | `faultline/0.0.1+prompts:1b0e7cbb4c47` |
| budget | `changes` 8, others 4, 120k tokens, 600s, 2 rounds (T4.7) |
| world | `compose_digest f5bd108f…` |
| registered | 3 runs per scenario, 6 total |
| **completed** | **4 scored, 2 discarded** |
| cost | **$2.1082 agent.** No judge — judging needs the same API |

## The sweep was cut short by billing, not by design

**Both discards are the same environmental failure**, and neither is a result about a scenario or
the agent:

```
FAILED MID-INVESTIGATION: did not start - BadRequestError: 400
'Your credit balance is too low to access the Anthropic API.'
```

Runs 5 and 6 — the third attempt at each scenario — never made a model call. **`discard_reason:
run failed`**, recorded and not deleted, per ADR-0022 §3.3.

**They were not re-run.** The pre-registration fixed three attempts per scenario and forbade re-runs
to improve a number, and that rule does not have an exception for a discard that is inconvenient.
**So both scenarios are reported at n = 2, and the registered n = 3 was not reached.**

**No judged figures.** The judge is a model call and the account has none, so `same_mechanism`
agreement is absent from this writeup rather than estimated.

## Results

| run | scenario | fault class | fix class | triage R / P | cost |
|---|---|---|---|---|---|
| 1 | D5 `payment-telemetry-blackout` | **`unknown` — ABSTAINED** | — | 1.00 / 0.33 | $0.6023 |
| 3 | D5 | **`bad_config` ✔** | `config_revert` ✔ | 1.00 / 0.33 | $0.5473 |
| 5 | D5 | **DISCARD** — credit | — | — | $0 |
| 2 | D1 `redis-cart-dependency-latency` | **`dependency_latency` ✔** | `restart` ✔ | 1.00 / 0.33 | $0.5000 |
| 4 | D1 | **`dependency_latency` ✔** | `config_revert` ✘ | 1.00 / 0.33 | $0.4586 |
| 6 | D1 | **DISCARD** — credit | — | — | $0 |

**Accuracy and coverage, separately, each with its n:**

| | D5 (n = 2 scored) | D1 (n = 2 scored) |
|---|---|---|
| **coverage** | **1 / 2** — one abstention | **2 / 2** |
| **fault class, of answered** | **1 / 1** | **2 / 2** |
| **fix class, of answered** | **1 / 1** | **1 / 2** |
| triage recall / precision | 1.00 / 0.33 both runs | 1.00 / 0.33 both runs |

**n = 2 is below the registered n = 3 and below SPLIT.md's own floor.** *"Two cannot show a
spread."* Every figure above is two observations, and none of them is a rate.

## D5: the prediction is falsified

**Registered: correct in ≥ 2 of 3. Falsified — at most 1 of 3 was correct.**

**And the failure mode was not the one registered either.** The prediction named the plausible wrong
answer — *"the service is down"*, `bad_deploy` or `resource_exhaustion` with remediation `restart`.
**The agent did not fall for it. It abstained.**

Run 1 dispatched to `paymentservice` and **exonerated it correctly**:

> *"error ratio flat zero across 57 and 61 sample points with a defined (non-zero) denominator
> throughout, Charge server spans steady at ~0.2ms with caller-side checkout client spans at
> ~1.4–1.7ms, and post-gap logs showing continuous successful charge/completion pairs"*

It reached the correct **intermediate** conclusion — the service is healthy — and declined to take
the final step to *"therefore the telemetry is misdirected"*. Under ADR-0022 an abstention is
neither right nor wrong; it leaves the ratio and shows as coverage.

Run 3 took that final step and **named the mechanism exactly**:

> *"platform-automation set paymentservice's OTLP traces exporter endpoint to a loopback address on
> port 4317 where no in-pod collector listens"*

**Both answering runs held low confidence.** One converted the exoneration into a diagnosis and one
did not, and n = 2 cannot say which is typical.

### A finding about D5's design, not about the agent

Run 1's first open question was:

> *"Why was the paymentservice container replaced between ~04:31 and ~04:42? An OOM kill, a
> liveness-probe failure, an eviction and a routine reschedule…"*

**That container replacement is the injection mechanism, not the fault.** `BadConfigFault` recreates
the container to change an environment variable, so every run of this scenario contains an
unexplained restart that the responder can see and cannot account for — because the exit reason is
not captured, which T7.40 decided one task ago to keep that way.

**So the scenario hands the responder a second, unanswerable question alongside its real one.** At
n = 2 this cannot be shown to have caused the abstention, and it is recorded as a design observation
rather than a cause. It belongs in D5's CATALOG entry.

## D1: the prediction is confirmed, including its mechanism

**Registered: class ≥ 2 of 3, faulty service ≤ 1 of 3.** Class **2 / 2**. Service **0 / 2**.

**The registered failure mechanism was exact.** The pre-registration said the failure would be *"not
that it skips the tool but that it queries the wrong subject"*. Every `change_history` call across
both runs:

| run | subjects |
|---|---|
| 2 | `cartservice`, `productcatalogservice` |
| 4 | `cartservice`, `cartservice` |

**`redis-cart` was never asked about, in either run, by any tool.**

**Under the decision table registered in advance, this is an agent finding, not a scenario finding.**
`canonical_service('redis-cart')` resolves, `redis-cart` is in `SERVICE_CONTAINERS`, and the change
log holds **4 records** for it — all verified before the runs. The culprit was reachable and the
agent did not ask.

**It got remarkably close.** Run 2's root cause:

> *"each cache round trip to its Redis-style backend takes a near-constant ~300ms, and cartservice
> handlers do essentially nothing but wait on those calls (handler spans exceed their child cache
> spans by only 1-3ms)"*

It found the client/server span split that T7.38 identified as the discriminator, described the
backend as *"Redis-style"* — and never turned that into the container's name.

### Run 4's fix-class miss is a consequence of a discipline call, and stays one

Run 4 answered `config_revert` against a labelled truth of `restart`. **`also_correct_remediation` is
empty on this scenario because T7.38 removed it**: the first draft carried `config_revert` by analogy
with `cart-dependency-latency`, and T7.17's rule is that an entry there means *measured on this
scenario*. ADR-0027 measured the qdisc delete on `cart-service`; nobody has measured it on
`redis-cart`.

**So the agent gave an answer that plausibly works and scored wrong because it is unmeasured here.**
That is the rule working, not a scoring artifact, and **the field is not being reinstated to improve
the number.** Measuring the qdisc delete on `redis-cart` would settle it, and is a separate task.

## Protocol: T7.32's sweep gate, first real use

**It behaved as designed and never refused.** The threshold relaxed as remaining work shrank,
exactly as remaining-work scoping intends:

| runs remaining | threshold | kafka |
|---:|---:|---:|
| 6 | **74.6%** | 42.6% |
| 2 | **84.9%** | 50.0% |
| 1 | **87.4%** | 50.0% |

kafka drifted **42.6% → 50.0%** across the sweep (~100 MB/h under load, consistent with T7.30's
measured rate) and fit at every point, so **no recycle was performed and none was requested** — the
gate decided that rather than the operator guessing. `runs_remaining` is recorded in every manifest.
The world lock was held through the harness on every run.

## What this establishes, and what it does not

**Establishes:** both scenarios are answerable, and each was answered correctly at least once by an
agent that had never seen them. D1's culprit is reachable and the agent's failure to name it is the
agent's. D5's evidence supports the correct diagnosis and one run made it.

**Does not establish:** any rate. **n = 2 per scenario, below the registered 3 and below the
catalog's own floor**, with no judged agreement. Whether D5's abstention or its correct answer is
typical is unknown, and the sweep that would have said was stopped by billing.

**Holdout was not touched.**


---

# Completed at T7.51 — the registered n = 3, and the judge

**The two runs that died on credit exhaustion have been run.** They are the registered-but-never-
scored runs, not replacements: **no run above was re-run, and no recorded verdict was altered.**
And the judge — which never ran at T7.41, for the same reason — has now been run across **all six**.

> **Judging adds; it does not alter.** `judge_cli` writes `manifest["judge"]` and has **zero
> references to the score block**. Every class-label score above stands exactly as recorded.

## The completed experiment

| run | scenario | fault class | fix | **judge** |
|---|---|---|---|---|
| `20260831T0434` | D5 | **`unknown` — ABSTAINED** | — | **different** |
| `20260831T0515` | D5 | `bad_config` ✔ | ✔ | **same_mechanism** |
| **`20260901T0559`** | **D5** | **`bad_config` ✔** | **✔** | **same_mechanism** |
| `20260831T0456` | D1 | `dependency_latency` ✔ | ✔ | **same_mechanism** |
| `20260831T0538` | D1 | `dependency_latency` ✔ | ✘ | **adjacent** |
| **`20260901T0621`** | **D1** | **`dependency_latency` ✔** | **✘** | **adjacent** |

| | **D5 (n = 3)** | **D1 (n = 3)** |
|---|---|---|
| coverage | **2 / 3** | **3 / 3** |
| fault class, of answered | **2 / 2** | **3 / 3** |
| fix class, of answered | **2 / 2** | **1 / 3** |
| judge `same_mechanism` | **2 / 3** | **1 / 3** |

**Cost.** T7.51's two runs **$1.0562**; the judge across all six **$0.2555**. **Whole experiment:
$3.1644 agent + $0.2555 judge = $3.4199.**

## The predictions, quoted and scored as written

**D5 — registered:** *"predicted **correct in ≥ 2 of 3** on fault class … **Falsified if fault class
is correct in ≤ 1 of 3**."*

> **HOLDS. 2 of 3 correct.**

**This reverses what T7.41 reported**, and the reversal is the point of completing a registration
rather than reporting a truncated one. At T7.41 the honest statement was *"at most 1 of 3 was
correct"* — true of what existed then: two scored runs and a credit discard. **The third registered
run is correct, so the prediction as written is met.** Both statements were honest when made; only
the completed n tests what was actually registered.

**D5's registered failure mode also held.** Registered: *"a run that answers from the page without
opening the logs should return `bad_deploy` or `resource_exhaustion` with remediation `restart`"* —
**no run did that.** The one failure was an abstention, which the registration named as the more
interesting outcome and which T7.43 then reconstructed.

**D1 — registered:** *"class ≥ 2 of 3, faulty service ≤ 1 of 3"*, and *"Does the agent consult
`change_history` unprompted? Predicted **yes, in at least 2 of 3**"*, with the failure predicted as
*"not that it skips the tool but that it queries the wrong subject."*

> **All three hold, and the mechanism held every time.**
> - class **3 / 3** ✔ (predicted ≥ 2)
> - faulty service **0 / 3** ✔ (predicted ≤ 1)
> - `change_history` consulted **3 / 3** ✔ (predicted ≥ 2)
> - subjects across all three runs: `cartservice`, `productcatalogservice`, `cartservice`,
>   `cartservice`, `cartservice`, `productcatalogservice`. **`redis-cart` was never asked about,
>   in any run, by any tool.**

**Under the decision table fixed before the runs, that is an agent finding, not a scenario finding**
— `change_history` resolves `redis-cart` and the log holds records for it.

## The label score overstates D1, and the judge is what shows it

**This is the most interesting thing the completed experiment turned up, and T7.43 predicted it was
possible.**

**D1's fault class is 3 / 3. Its judged mechanism agreement is 1 / 3.** The two runs the judge rates
**`adjacent`** — ADR-0022's *"right subsystem, wrong mechanism"* — **scored fully correct on the
fault-class label.**

The two disagreeing runs are exactly the two that also missed the fix class (`config_revert` against
a truth of `restart`), so the label score was not blind — but **`fault_class` alone would have
reported 3/3 for a scenario where two of three verdicts named a mechanism the judge does not accept
as the recorded one.**

**This is T7.44's argument arriving as data.** The scorer scores conclusions; the judge assesses the
mechanism named; they can disagree, and here they do on **two runs out of three**. A reader given
only *"fault class 3/3"* would have a materially better impression of D1's result than the record
supports. **Coverage and accuracy are reported together by rule; on this evidence the judged
agreement deserves the same treatment.**

**D5's abstention is judged `different`**, which is the correct handling rather than a finding: a
verdict with no root cause cannot name the same mechanism as the narrative.

**One trap was taken**, in D5's third run — *"if payment were really down, checkout would error (and
it doesn't)"* — by a run that nonetheless reached the right answer. Worth recording because it is
the shape T7.43 described from the other side: the reasoning and the conclusion coming apart.

## What this still does not establish

**n = 3 per scenario.** Three observations, not a rate, and the registration said so before any run.
**All figures are judged under SHARED LINEAGE** — judge `claude-haiku-4-5`, agent `claude-opus-5`,
both Anthropic — which every judged figure in this repository carries.
