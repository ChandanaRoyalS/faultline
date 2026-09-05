# Judge calibration, at the n T4.2 asked for — and what it cannot test

**Thirty blind human grades against the judge's own verdicts.** T4.2 asks for about thirty; this is
thirty, graded one at a time, each recorded before the judge's answer was revealed.

| | |
|---|---|
| grades | **30**, over **13** distinct scenarios |
| raw agreement | **80%** — 24 of 30 |
| Cohen's κ | **0.35** |
| the tool's own reading | *"fair — below what a published figure should rest on"* |
| abstentions excluded from the pool | **18** |

**The headline is not the 80%.** It is that κ is 0.35 on a pool where 25 of the judge's 30 verdicts
are `same_mechanism`, so **69% agreement is expected from chance alone** and the measured 80% is
eleven points above it. `faultline-calibrate --report` says so in its own words, and this document
does not soften it: **this exercise does not establish the judge as a substitute for a reader.** It
establishes that the judge agrees with a reader often, on a pool where agreeing often is cheap.

Every judged figure in [`SWEEP-2026-09-04-top3.md`](SWEEP-2026-09-04-top3.md) keeps its caveat. It
is a weaker caveat than "no human has checked this at all", and it is not nothing, and it is not
removed.

---

## 1. The one thing this pool cannot test

Measured over the whole judged record — **82 judged runs**:

| judge verdict | all | of which abstentions | **gradable** |
|---|---|---|---|
| `same_mechanism` | 59 | 0 | **59** |
| `adjacent` | 4 | 0 | **4** |
| `different` | 19 | **18** | **1** |

**Eighteen of the nineteen `different` verdicts in the entire record are abstentions**, and
abstentions are excluded from the pool for a reason that is correct and not negotiable: a run that
returned `fault_class: unknown` made no claim, the judge grades every abstention `different` **by
construction**, and matching that convention is a free agreement point while differing from it is a
free miss. Including them would put eighteen mechanical rows into a figure whose entire purpose is
checking a judgement.

**The consequence is that this calibration cannot test the `same_mechanism` / `different`
distinction at all.** There is exactly one non-abstention `different` in the record to test it on.
Whatever the figure says, it says it about the boundary between `same_mechanism` and `adjacent` and
about nothing else — the three-level scale is being exercised as a two-level one.

That is not a defect in the grading. It is a property of the corpus: **this pipeline is either
roughly right or it declines**, and it almost never confidently names the wrong mechanism. A
benchmark whose judge disagreement is concentrated in one boundary has a different calibration
problem from one whose judge is wrong in scattered ways, and the two should not be reported with
the same sentence.

---

## 2. Every disagreement is on the `adjacent` boundary. All six.

| judge | grader | n | |
|---|---|---|---|
| `same_mechanism` | `same_mechanism` | **22** | ✓ |
| `same_mechanism` | `adjacent` | **3** | grader stricter |
| `adjacent` | `same_mechanism` | **2** | judge stricter |
| `adjacent` | `adjacent` | **2** | ✓ |
| `different` | `adjacent` | **1** | |

**Not one disagreement is a `same_mechanism` ↔ `different` flip.** Judge and grader never once
disagreed about whether the agent was roughly right. They disagreed only about where the middle
category starts.

**And the direction alternates**, which is what makes this a finding rather than a bias:

| scenario | grader | judge |
|---|---|---|
| `redis-cart-dependency-latency` (`0831T053815`) | same_mechanism | adjacent |
| `redis-cart-dependency-latency` (`0901T062150`) | same_mechanism | adjacent |
| `frauddetection-memory-squeeze` (`0830T043100`) | **adjacent** | **same_mechanism** |
| `shipping-quote-misconfig` (`0829T202910`) | **adjacent** | **same_mechanism** |

Three each way, on the same question: **how much of the causal chain must a narrative name before
it counts as naming the mechanism?** On the `redis-cart` rows the agent identified a fixed ~300ms
per-operation stall on the cart datastore and declined to say where the delay lived; the grader
read that as the mechanism, the judge read it as adjacent. On `frauddetection-memory-squeeze` the
agent identified a memory-limit reduction and a restart loop without establishing that 200 MiB sat
below the JVM's footprint; the grader withheld, the judge granted.

A one-sided disagreement would be a bias and a bias is correctable. **Alternating direction on one
question means the category is underspecified**, and that is a fact about the rubric rather than
about either reader.

**ADR-0022 §1.3 defines `adjacent` as *"right subsystem, wrong mechanism"* and is silent on *right
mechanism, unlocated cause*.** That is the gap, and it is now evidenced six times.

### The definition is not being sharpened here, deliberately

Redefining `adjacent` after seeing which rows produced disagreements would be tuning the instrument
to the data — the same move T7.44 refused when it declined to adopt the warrant check on the
strength of one pair of runs. The gap is recorded as a stated limit on what this figure measures. A
sharper definition, if one is warranted, is written before the next round of grading and applies to
that round, not retroactively to these thirty.

---

## 3. An observation, with its check named and not yet done

Across repeats of a single scenario:

| scenario | grader | judge |
|---|---|---|
| `redis-cart-dependency-latency` ×3 | same_mechanism, same_mechanism, same_mechanism | **adjacent, adjacent, same_mechanism** |
| `shipping-quote-misconfig` ×2 | adjacent, adjacent | **adjacent, same_mechanism** |

**The grader was self-consistent within a scenario; the judge was not.** That is a sharper claim
than the agreement rate, because it is about the judge's stability rather than about whether it
matches anyone.

**It is not established, and the reason is stated rather than buried.** Those are different runs
with different agent narratives, so some of the judge's movement may be correct — the three
`redis-cart` narratives really might differ in how far each located the cause. Settling it means
reading the three side by side and asking whether the judge's movement tracks a real difference in
what the agent wrote. **That reading has not been done**, it costs about half an hour and no money,
and until it is done this table is an observation and not a result.

It is recorded now rather than after the check, because an observation noticed and left unwritten
until it is convenient is the shape of a finding that quietly disappears.

---

## 4. What is wrong with these thirty rows

Four things, none of them fatal and all of them the reader's business.

**One row is not an independent blind grade.** `20260831T053815Z-redis-cart-dependency-latency` was
discussed with an assistant before the level was chosen. Its reason says so on the row. It measures
a joint reading, not the grader's own, and it is one of the six disagreements — so it is load-
bearing for §2's finding and its status has to travel with it.

**Two rows carry placeholder justifications.** Two of the first five grades were recorded with
reason text supplied as a template and pasted unchanged. **The grades themselves are legitimate** —
blind, the grader's own call — but their stated justifications are junk. They were not regraded,
because `--regrade` marks a row not-blind and excludes it from the figure, so correcting the prose
would cost the grade. Recorded here instead.

**The grader never once used `different`.** Zero of thirty. Given §1 that is expected rather than
suspicious — the pool has one `different` in it to find — but it means the scale's lower boundary
was never exercised by either party.

**Thirty grades over thirteen scenarios means repeats are not independent.** A grader who has read
a scenario's recorded narrative already holds a verdict on it; the second and third runs of
`redis-cart-dependency-latency` are not thirty-first-time judgements. `n` overstates how much was
actually rated, and the panel says so on every printing.

---

## 5. The limits that do not go away with more grades

**The grader wrote the reference narratives.** Every `incident.md` in this catalog was authored by
the same person doing the grading, so judge and grader are being compared against a document one of
them wrote. That is a shared prior by construction and no amount of blinding removes it.

**The judge shares a tuning lineage with the agent under test.** `claude-haiku-4-5` grading
`claude-opus-5` is ADR-0008's fifth contamination axis, opted into explicitly on all 82 judged runs
and stamped on every figure. This document is not exempt from it.

**Neither figure says the judge is right.** Raw agreement and κ both say a human reading the same
two documents reached the same verdict at some rate. Agreement with a reader is not correctness,
and on a benchmark where the reader wrote the reference, it is not even independence.

---

## 6. Follow-ups

1. **Read the three `redis-cart-dependency-latency` narratives side by side** and settle whether
   the judge's within-scenario movement tracks a real difference. Free; half an hour. Until then §3
   stays an observation.
2. **Write the `adjacent` boundary question into ADR-0022 §1.3 before the next grading round** —
   specifically whether naming the mechanism requires naming the component it lives in. Written
   first, applied forward, never backfitted to these thirty.
3. **Grade more, and expect κ to stay low.** With 59 of 63 gradable runs judged `same_mechanism`,
   κ's chance term is dominated by that skew and will remain so until the corpus contains runs the
   judge confidently calls wrong. **More grades will not fix this; more variety in the corpus
   would.** That is a fact about the catalog, not about the grading effort.
4. **A second-model grader arm is a different experiment** and would need its own pre-registration,
   its own `grader` value, and a change to `agreement()` so it cannot pool with the human rows.
   Named here so it is not later done by relabelling.
