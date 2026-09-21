# The latency clause, at n = 139 — read from the record, 2026-09-21

**No run was made and nothing was spent.** Every number here is read from the committed manifests
of runs that already exist, on the current world `90e9f29e…` at the current stamp
`prompts:06f24e827915`. It exists because both undeclared gates fail on one clause and both
assessments (2026-09-20) reported it from **thirty** runs when the tree holds **139**.

**The clause.** Gate 4: *"a dev-set median time-to-report ≤ 3 minutes."* Gate 6 inherits it
verbatim and asks for it *"re-asserted with the full pipeline — four specialists, retrieval, rerank,
and self-instrumentation included."* G6's assessment said the measurement it names *"does not
exist"* because no sweep had run since self-instrumentation landed on 2026-09-18. **That was
wrong.** The stamp has not moved since dev sweep 12 — `prompt_digest` still reads
`06f24e827915`, because nothing between the executor, self-instrumentation and the adversarial
harness touched a prompt or a contract — and T6.5's sixty runs on 09-17/18 are at this stamp, this
world and the 60-document corpus, with ten of them after self-instrumentation. The measurement
existed; nobody had read it.

## The distribution

**139 runs that count toward aggregates**, `metrics.latency.investigation_seconds` from each
manifest:

| | |
|---|---|
| minimum | **168.6 s** |
| 25th percentile | 210.2 s |
| **median** | **232.8 s** |
| 75th percentile | 253.0 s |
| maximum | 289.0 s |
| **under the 180 s bar** | **4 of 139 — 2.9 %** |

| date | n | median | range | under 180 s |
|---|---|---|---|---|
| 2026-09-08 | 15 | 233.5 s | 181.3 – 266.8 | 0 |
| 2026-09-09 (sweep 12, arm A) | 35 | 245.2 s | 168.6 – 289.0 | 2 |
| 2026-09-10 (sweep 12, arm B) | 29 | 213.1 s | 172.7 – 272.8 | 1 |
| 2026-09-17 (T6.5) | 50 | 231.8 s | 177.8 – 274.5 | 1 |
| **2026-09-18 (T6.5, after self-instrumentation)** | **10** | **246.9 s** | 197.8 – 256.4 | **0** |

**Every scenario's median is over the bar**, which is the finding that stops this being one slow
outlier dragging an average:

| scenario | n | median |
|---|---|---|
| `cart-redis-misconfig` | 15 | 253.0 s |
| `cart-bad-image-tag` | 13 | 251.5 s |
| `redis-cart-dependency-latency` | 14 | 247.4 s |
| `ad-memory-squeeze` | 13 | 242.9 s |
| `shipping-quote-misconfig` | 15 | 242.8 s |
| `shipping-wrong-image` | 15 | 242.8 s |
| `cart-dependency-latency` | 14 | 238.2 s |
| `payment-telemetry-blackout` | 14 | 219.1 s |
| `product-catalog-flag-failure` | 13 | 217.2 s |
| **`frauddetection-memory-squeeze`** | 13 | **194.9 s** — the fastest, still 15 s over |

**And the four that pass, pass narrowly**: 168.6 s, 172.7 s, 176.6 s, 177.8 s. The fastest
investigation ever recorded on this world is **11.4 seconds** inside a bar it misses by a median of
**52.8 seconds**. There is no fast tail to widen; the distribution's whole lower edge sits just
under the line.

## Where the time goes, as far as the manifests can say

`metrics.latency` carries a model/tool split, and **only ten runs in the tree carry it** — the
T6.8 adversarial runs, which count toward no accuracy figure but are the same pipeline executing
the same way. Over those ten:

| | median | range |
|---|---|---|
| wall clock | 213.0 s | 190.0 – 254.7 |
| **model time** | **166.9 s — 75 % of wall** | 56 % – 88 % |
| **tool time** | **0.23 s** | 0.17 – 0.57 |
| steps | 24 | 20 – 26 |

**Tool calls are free.** Under six tenths of a second per run, against a wall clock of three and a
half to four minutes — every query this agent makes against Loki, Prometheus, Tempo and the change
log, added together, is a rounding error. Any proposal that starts by making the tools faster is
optimising 0.1 % of the problem.

**The quarter that is neither is the interesting number, and it is bigger than the deficit.** At
the median, roughly **58 s** of wall clock is not model time and not tool time. The gap to the bar
is **52.8 s**. So on the panel's own arithmetic, *the non-model overhead alone is larger than the
amount the clause misses by.*

**What that quarter is, is not established here, and it decides which lever is available.** Two
readings fit the same number and they have opposite consequences:

- **Harness time** — retrieval and embedding (the sentence-transformer load is visible in the run
  logs), trajectory writes, the gaps between serial stages. If it is this, the first lever is
  **code, and moves no stamp**.
- **Model time the panel does not attribute.** Specialists run concurrently
  (`investigation.py`, `ThreadPoolExecutor`, one thread per admitted dispatch), so a sum over
  completion steps and a critical path are different quantities, and `model_ms` may be measuring
  the second. If it is this, the levers are prompt- and policy-shaped — fewer dispatch rounds, a
  cheaper triage model, smaller briefings — and **every one of them moves `prompt_digest` and
  re-founds the benchmark.**

`trajectory_steps.latency_ms` per role and kind separates them. That read is the next step and it
costs nothing.

## What this settles

**For Gate 4**: the latency clause fails, at n = 139 rather than n = 30, with 2.9 % of runs inside
the bar and no scenario's median inside it. It is not *unmeasured*, not *marginal*, and not an
artifact of the sweep that was quoted for it.

**For Gate 6**: clause 4's *"re-asserted … with self-instrumentation included"* has its
measurement. Ten runs at 09-18 postdate self-instrumentation and their median is **246.9 s** — the
highest daily median in the table, though n = 10 and the day-to-day spread is 213–247 s, so this
note does **not** claim self-instrumentation slowed anything. What it claims is that the clause has
been measured on the pipeline it names and fails.

**And it removes a reason to spend.** Both gate assessments listed *one sweep at the current stamp*
as the first thing they needed. For the latency half, that sweep would have re-measured a quantity
the record already answers 139 times over. What a sweep is still needed for is **B1 and B2, which
have never run** — zero manifests each — and that is ten cheap runs each, not a full re-record.

## What this does not say

**Not that latency can be fixed.** It locates the deficit and names two candidate causes without
choosing between them.

**Not that self-instrumentation is the cause.** The 09-18 median is the highest and the sample is
ten; 09-09 ran 245.2 s before any of it existed.

**Not a claim about the holdout**, which has no run on this world at all, or about the deployment,
whose only investigations are the four it opened about itself.

**And not a new measurement.** Every figure is a reading of runs made for other registered
questions. That is the reason it cost nothing, and also the reason it carries no pre-registration:
there is nothing here to pre-register, because nothing was run.

---

## Addendum — the residue was the instrument, and four model calls were never timed

**Read the same day, from `trajectory_steps` across all 356 trajectories (2026-08-25 to 09-20).**
The §*Where the time goes* section above offered two readings of the ~58 s that is neither model
nor tool, and said a per-role read would tell them apart. It did, and the answer is neither of
them: **the panel that produced that 58 s cannot locate time, and the 75 % model share is not a
quantity.**

**Only five of the nine roles record a model call's latency at all.**

| role · kind | steps | of them untimed | timed |
|---|---|---|---|
| `synthesizer` · verdict | 308 | **308** | 0.0 s |
| `scribe` · message | 307 | **307** | 0.0 s |
| `proposer` · proposal | 223 | **223** | 0.0 s |
| `planner` · completion | 616 | 594 | 437.0 s |
| `metrics` · completion | 709 | 681 | 423.5 s |
| `changes` · completion | 634 | 609 | 301.3 s |
| `logs` · completion | 479 | 460 | 342.9 s |
| `traces` · completion | 272 | 261 | 265.1 s |

The verdict, the proposal and the narrative are **model calls** — their steps carry `tokens_in`
and `tokens_out` off the completion object — and **not one of the 838 of them has ever been
timed.** `Completion.latency_ms` arrived at T6.6 with a docstring naming the problem it fixed:
*"the trajectory had never measured this … so every COMPLETION step recorded 0."* It was carried
onto the steps of kind `COMPLETION` and no further, and the three roles that record under
`VERDICT`, `PROPOSAL` and `MESSAGE` were left exactly where they had been. **The fix was applied by
kind, and the property it needed was *is this a model call*.**

`metric_panel` then read `model_ms = by_kind["completion"]`, so **the entire serial tail of every
investigation sat outside the panel's model share** — and the tail is where the long calls are
(the first-trace note clocked single completions at 33 s, 39 s, 63 s and 69 s).

**A fourth site, found by the guard rather than by the table.** A specialist whose reply fails its
schema twice records a `COMPLETION` step off `failure.response` with no completion object and no
latency — two real model calls, recorded as taking no time. The table above could not show it
because the step is filed under a role that also has timed completions.

**So the arithmetic in the section above does not hold, and it is withdrawn.** *Model time is 75 %
of wall* was a sum over `COMPLETION` steps only, and those steps also run **concurrently** — the
four specialists are one `ThreadPoolExecutor` per dispatch round — so the figure was simultaneously
missing the serial tail and double-counting the parallel middle. It is neither a critical path nor
a total. **`investigation_ms`, the wall clock, is the only latency number in this system that has
ever meant what it appears to mean**, and the n = 139 finding above rests on it alone and stands.

**Fixed in the same commit as this addendum, and it costs no stamp**: all four steps now carry
`latency_ms` (and the three with a completion object carry its `trace_id` / `span_id`, so they link
to their `model.call` spans); `model_ms` becomes every kind that is not a tool call or a retrieval;
`retrieval_ms` is split out, because embedding and search are neither and folding them into either
is how a real cost — 4.8 s a run at the planner — disappeared. `Latency.model_ms` now says in its
own docstring that it is a sum and not a critical path.
`tests/test_metrics.py::test_every_model_call_is_timed_whatever_kind_it_is_recorded_under` parses
`investigation.py` and fails on any `TrajectoryStep` that records a model's tokens without its
latency; it was run against the old source first and fails on it, and it is what found the fourth
site.

**What this does not fix.** The stored 356 trajectories keep their zeros — nothing is backfilled,
because a latency invented after the fact is not a measurement. **The decomposition is therefore
available from the next run onward and not before**, and until then *where the 233 s goes* has no
answer in this repository. What did not change is the clause: 139 runs, median 232.8 s, four inside
the bar.

**And the parallel structure is worth keeping in view when the numbers do arrive.** Per timed run
the four specialists average 12.1 s (`changes`), 15.1 s (`metrics`), 18.0 s (`logs`) and 24.1 s
(`traces`), but run concurrently — so a dispatch round costs about `traces`, not their sum — while
the planner's completions average **19.9 s** and are serial, twice per investigation. Tool calls
remain free at 0.23 s a run in total, though `traces` queries cost 0.3 s each against `metrics` at
0.015 s: **Tempo is twenty times slower per query than Prometheus**, and still not worth
optimising.
