# Pre-registration — dev sweep 10, the five at `b6837dd449ca`

**Written and committed before the run.** Same discipline and the same reason: a scope chosen after
the numbers exist is a scope chosen to suit them.

---

## Why this sweep exists, stated plainly

**Not to discover anything. To make the published figures citable at the stamp that is shipping.**

T5.3 owes a README whose results block describes the pipeline the repository actually contains, and
T5.4 owes a tag whose release notes name the stamp its figures came from. Right now:

| | |
|---|---|
| README §Results headlines | **dev sweep 7**, stamp `1b0e7cbb4c47` |
| HEAD's stamp | **`b6837dd449ca`** |
| scored runs at HEAD's stamp | **one** — `cart-bad-image-tag`, from Q25b |

Three stamp moves and two sweeps separate the front door from the code. **A release that tagged
this would publish a table describing a superseded pipeline**, which is the exact failure this
project exists to make visible in other people's benchmarks.

**This is a first observation at this stamp, not a re-run.** ADR-0022 §3.3 forbids re-running a
scored run to improve a number; four of these five have never been run at `b6837dd449ca` at all,
and the fifth is the reason the stamp exists.

---

## Scope, fixed here

**Five scenarios, R=1, both arms.** `ad-memory-squeeze`, `cart-bad-image-tag`,
`cart-dependency-latency`, `cart-redis-misconfig`, `frauddetection-memory-squeeze` — the five dev
sweep 9 ran, so every figure has a predecessor at the previous stamp on the same world.

**B0.2 runs alongside at \$0.0000 and is not optional.** CLAUDE.md rule 6 wants a baseline beside
every number, and the arm costs nothing. A README table with no baseline column would be a table
this project would criticise elsewhere.

**What this sweep cannot establish, registered so nobody reads it as more:** R=1, so **no variance
component and no A/A check**; n=5 against an MDE of roughly 28pp at n=10, so **no comparison
between arms on fault class can resolve**; and 0–2 scenarios per fault class, so **no per-class
rate is worth a decimal place.**

---

## The record this is measured against

Dev sweep 9, stamp `ba8684b01201`, pipeline arm, read from the manifests:

| scenario | fault class | culprit service | depth | cost |
|---|---|---|---|---|
| `ad-memory-squeeze` | **abstained** (`unknown`) | `adservice` ✓ | 1 | \$0.6755 |
| `cart-bad-image-tag` | **no verdict** | — | — | \$0.3890 |
| `cart-dependency-latency` | `dependency_latency` ✓ | `cartservice` ✓ | 2 | \$0.6334 |
| `cart-redis-misconfig` | `resource_exhaustion` ✗ (truth `bad_config`) | `cartservice` ✓ | 1 | \$0.8015 |
| `frauddetection-memory-squeeze` | `resource_exhaustion` ✓ | `frauddetectionservice` ✓ | 1 | \$0.4955 |

**2 correct, 1 wrong, 2 that did not answer. Culprit service 4 of 4. \$2.9949.**

And the one run at HEAD's stamp, `cart-bad-image-tag` at Q25b: fault class **correct**, service
`cartservice` **correct**, depth 1, \$0.7349.

---

## Predictions

Registered before the run, with the consequence of each failure named — which is the only reason to
write them first.

### 1. Cost lands between \$2.60 and \$3.90

Sweep 9 spent \$2.9949 on these five, but one of them died before synthesis; the Q25b run of that
same scenario cost \$0.7349 completing. Five completing runs should therefore cost **more** than
sweep 9 did.

**Materially above \$3.90 is a finding about the added `remediation_class` key**, not noise, and
belongs beside Q25b's cost note.

### 2. Every scenario produces a verdict — 5 of 5 answered

`cart-bad-image-tag` was the only failure to answer in sweep 9, and Q25b's contract fix is exactly
what unblocked it. It has since answered once at this stamp.

**If any scenario returns no verdict, that is a contract or budget failure and outranks every other
result in this document.** If it is `cart-bad-image-tag` again, the Q25b fix did not hold and the
`REPORTED`/`REQUESTED` split needs reopening rather than patching.

### 3. Culprit service: 5 of 5

Sweep 9 scored 4 of 4 that answered. Nothing between the stamps touches triage or blast-radius
traversal, and prediction 2 says all five answer.

**4 of 5 would be the first miss on this axis and would immediately qualify README's
strongest claim.** Below 4 means something moved that this document does not know about.

### 4. Fault class: between 2 and 4 correct, and the interesting part is *which*

Registered as a range because n=5 with 0–2 per class supports nothing tighter. **The scenario-level
predictions carry the information:**

- **`frauddetection-memory-squeeze` correct.** Right in sweep 9, the easiest in the catalog.
- **`cart-dependency-latency` correct.** Right in sweep 9.
- **`cart-redis-misconfig` wrong again, most likely `resource_exhaustion`.** This is the one
  genuine mistake in sweep 9 — `bad_config` truth, `resource_exhaustion` returned. **A repeat makes
  it a property of the scenario rather than an instance**, and the right response is an
  investigation of whether the telemetry distinguishes the two at all, not a prompt edit.
- **`ad-memory-squeeze`: no prediction.** It abstained in sweep 9 rather than answering wrongly,
  and this project has one abstention on this scenario and no theory of it.

### 5. Abstention is 0 or 1, not 2

Sweep 9 had two non-answers, one of them a contract failure that is fixed. **Two or more
abstentions at this stamp would mean the abstention is behavioural rather than mechanical**, which
would be new and would need its own investigation before any coverage figure is published.

### 6. `cart-dependency-latency` carries depth ≥ 2, the rest depth 1

The only ranked verdict in sweep 9 was this scenario's, at depth 2. Q25b's `remediation_class`
addition made ranking cheaper to express, not more likely.

**If several scenarios come back ranked, top-3 becomes publishable for the first time** — and
sweep 9's registered rule applies: top-3 must not be published as a column while most verdicts
carry no alternative, because it equals top-1 by construction.

### 7. Nothing else moves

**Registered: `cap:c4d52d00` and world generation `f5bd108f4f70` unchanged**, and B0.2's cost
\$0.0000.

A difference in triage recall or precision on a scenario would mean **the world moved, not the
pipeline**, and would invalidate the comparison against sweep 9 that half this document rests on.

---

## What would surprise me

1. **Any scenario without a verdict** — prediction 2, and the largest problem available here.
2. **`cart-redis-misconfig` correct.** It would mean the mistake was an instance after all, and
   n=1-correct-of-2 is a weaker and more honest place than it looks.
3. **Culprit service below 4 of 5** — prediction 3, and it would qualify the headline.
4. **Cost above \$3.90** — prediction 1.

---

## Cost

**Registered: \$2.60–\$3.90 for the pipeline arm, \$0.0000 for B0.2.** Plus roughly 40 minutes of
wall clock: five injections, five settles at 300s, and the runs themselves.

---

## Order of operations

1. **Confirm the stamp reads `b6837dd449ca`** before anything is injected.
2. **Confirm the key is exported.** `faultline-eval` does not read
   `~/.faultline-anthropic-key`; only `demo.py` does. Thirty pre-flight refusals in one sweep came
   from exactly this, and two more from a fresh terminal after it.
3. **Confirm the world is up and the orchestrator is polling.** The baseline gate does both.
4. **Run B0.2 first**, then the pipeline arm on the same five. Free arm first, so a failure in it
   costs nothing to discover.
5. **Judge the narratives**, same `claude-haiku-4-5`, same lineage opt-in as all judged runs.
   `faultline-judge` skips anything already judged unless `--rejudge`.
6. **Write the result against all seven predictions, including the ones that fail.**
7. **Only then** does README's results block get rewritten, and it cites this document.
