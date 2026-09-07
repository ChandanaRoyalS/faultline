# Pre-registration — dev sweep 11, the other five at `b6837dd449ca`

**Written and committed before the run.** Same discipline as sweep 10 and the same reason: a scope
chosen after the numbers exist is a scope chosen to suit them.

---

## Why this sweep exists, stated plainly

**Not to discover anything. To finish the table README now carries up top.**

T5.6's audit put a per-scenario table at the top of README, generated from `evals/runs/` at the
stamp this repository ships. Five of its ten dev rows are zero: `payment-telemetry-blackout`,
`product-catalog-flag-failure`, `redis-cart-dependency-latency`, `shipping-quote-misconfig` and
`shipping-wrong-image` have every one been scored on the current world — at `1b0e7cbb4c47`, five
stamps ago — and none since. The execution plan's T5.3 column says *"the 10-scenario eval table"*;
the table has five measured rows.

**This is a first observation at this stamp, not a re-run.** ADR-0022 §3.3 forbids re-running a
scored run to improve a number; none of these five has ever run at `b6837dd449ca`.

**The three holdout rows are not in this sweep and will stay at zero.** Holdout entry 4 is blocked
indefinitely by ADR-0029, not pending, and `HOLDOUT-2026-09-01-entry4-NOT-OPENED.md` is the ledger
entry saying so. This document does not reopen that.

---

## Scope, fixed here

**Five scenarios, R=1, both arms, in this order:**

```
payment-telemetry-blackout
product-catalog-flag-failure
redis-cart-dependency-latency
shipping-quote-misconfig
shipping-wrong-image
```

Pipeline arm first, then B0.2, each as one `faultline-sweep --only` invocation at the bounds every
published figure was measured under (`--max-tool-calls 4 --max-tool-calls-changes 8 --max-tokens
120000`), settle 300 s, the default six retries on a gate refusal, no retry on a discard. **`--only`
is the commitment**: a registration that names five is a commitment to five.

**B0.2 runs alongside at \$0.0000 and is not optional** (CLAUDE.md rule 6).

**Cost, named before spending it (rule 8):** about **\$3.50** in model calls for the pipeline arm and
about **\$0.15** for the judge; the B0.2 arm makes no model call. Wall clock about 2 h 15 m on the
reference platform with both arms and the settle windows.

**What this sweep cannot establish, registered so nobody reads it as more:** R=1, so no variance
component — sweep 10 measured a fixed-stamp disagreement at n=2 and nothing here bounds it; five
scenarios across three classes, so no per-class rate is worth a decimal place; and the ten dev rows
this completes are ten runs at R=1, which is a table, not a benchmark.

---

## The record this is measured against

Every scored run of these five on the current world, all at `1b0e7cbb4c47`, read from the manifests.
None carries a service score — that axis dates from T4.2 — so this sweep is the first measurement
of culprit service on all five.

| scenario | truth | at `1b0e7cbb4c47` on `f5bd108f4f70` | cost range |
|---|---|---|---|
| `payment-telemetry-blackout` | `bad_config` / `config_revert` / `paymentservice` | **4 ✓, 1 abstained** (n=5) | \$0.48–0.70 |
| `product-catalog-flag-failure` | `bad_config` / `config_revert` / `featureflagservice` | **1 ✓** (n=1); on earlier worlds 5 ✓ and 6 abstentions, all six at `53fafe9c12bc` | \$0.53 |
| `redis-cart-dependency-latency` | `dependency_latency` / `restart` / `redis-cart` | **3 ✓ on class**; fix `restart` ✓ once, `config_revert` ✗ twice (n=3) | \$0.46–0.52 |
| `shipping-quote-misconfig` | `bad_config` / `config_revert` / `shippingservice` | **1 ✗** — returned `bad_deploy` (n=1); ✓ once on `299d791c5e0d` | \$0.56 |
| `shipping-wrong-image` | `bad_deploy` / `rollback` / `shippingservice` | **1 ✓** (n=1); across all worlds 5 ✓, 4 abstained, 0 wrong | \$0.59 |

Four earlier attempts at `product-catalog-flag-failure` on 2026-09-02 are discards that never
reached triage — the API account had run out of credit. That is the reason `faultline-eval` now
pre-flights the key with a minimal billed call before injecting anything; it is not evidence about the
scenario.

---

## Predictions

Registered before the run, with the consequence of each failure named.

### 1. Pipeline cost lands between \$2.60 and \$4.20

Sweep 10's five runs at this stamp cost \$0.51–0.87 each (mean \$0.72); these five cost \$0.46–0.70
at the previous stamp. **Above \$4.20 is a finding about the proposer or the `remediation_class`
key, not noise**, and joins Q25b's cost note.

### 2. Every scenario produces a verdict — 5 of 5 answered or abstained, no "no verdict"

The only recent no-verdicts on these scenarios were the credit-exhaustion discards, and the
pre-flight now refuses before injecting. **A no-verdict here is a contract or budget failure and
outranks every other result in this document.**

### 3. Culprit service: 4 or 5 of the runs that answer

Sweep 10 scored 5 of 5, and nothing between the two sweeps touches triage. The reason this is not
registered as 5 of 5: two of these targets are unlike anything the service axis has been scored on.
`featureflagservice` is the stub that stands in for the retired flag service, and `redis-cart` is
a datastore rather than a service — both are the kind of name a blast-radius traversal can reach
and a synthesizer can decline to blame. **A miss on either is a finding about the service axis's
name space, and belongs beside T4.2's design note. A miss on the other three is the first plain
miss on this axis and immediately qualifies README's strongest claim.**

### 4. Fault class: 3 to 5 correct of those that answer, and the interesting part is *which*

- **`payment-telemetry-blackout` correct.** 4 of 5 at the previous stamp.
- **`redis-cart-dependency-latency` correct.** 3 of 3.
- **`product-catalog-flag-failure` correct or abstains — not wrong.** Never wrong at any stamp
  after `53fafe9c12bc`; six abstentions there and none since.
- **`shipping-wrong-image` correct or abstains — not wrong.** 0 wrong in 9 scored runs across
  three worlds (5 correct, 4 abstained).
- **`shipping-quote-misconfig`: no prediction, and the clause that matters.** Its one current-world
  run returned `bad_deploy` for a `bad_config` truth. **A second `bad_deploy` makes that a property
  of the scenario rather than an instance** — the same clause sweep 10 registered for
  `cart-redis-misconfig` — and the right response is to ask whether the telemetry distinguishes a
  configuration change from a deployment on `shippingservice` at all, not to edit a prompt.

### 5. Abstention is 0, 1 or 2 — not 3

Sweep 10 had one abstention in five at this stamp, and the eleven current-world runs of these five
scenarios hold one between them. **Three or more here would mean abstention at this stamp is behavioural, not mechanical**
— the same consequence sweep 10 registered — and it would need its own investigation before the
README headline is re-read.

### 6. Fix class: `redis-cart-dependency-latency` is the one to watch

Its labelled fix is `restart` and it has no `also_correct_remediation`; the two `config_revert`
verdicts at the previous stamp were scored wrong. **If this sweep returns `config_revert` again, the
question is T7.17's — whether clearing the netem qdisc fixes this one durably too — and the answer
is a measurement, not a scorer edit.** Every other scenario's fix follows its class and no separate
prediction is made.

### 7. Latency: median above 180 s

Sweep 10's median was 248 s and G4's clause failed on all five. Nothing here is faster. **A median
under 180 s would be the first on this world and would need an explanation before it is believed.**

### 8. B0.2: at most 2 of 5 on fault class, no service named

B0.2 scored 1 of 5 in both sweep 9 and sweep 10. Two of these five are `bad_config` faults whose
symptom is silence rather than error rate, which is the shape the alert-label heuristic handles
worst. **3 or more would be a finding about the baseline, and welcome.**

### 9. Nothing else moves

`f5bd108f4f70` on all ten runs, `cap:c4d52d00`, `prompts:b6837dd449ca` on the pipeline arm and
`baseline:B0.2` on the other, `demo: false` throughout, `leave_one_out.enforced` true. **Anything
else is a harness defect and stops the sweep from being written up as a sweep.**

---

## What happens to the numbers afterwards

`uv run python -m evalharness.scenario_table --write` regenerates README's table from the ten new
manifests; `tests/test_scenario_table.py` refuses a README that disagrees. `docs/MVP-CUT.md`'s
*"measured on 5 of them"* sentence is corrected to whatever the table then says. Nothing in
`docs/RESULTS.md` is edited: sweep 10's section describes sweep 10, and this sweep gets its own,
`SWEEP-2026-09-07-sweep11.md`, written after the run against this document.
