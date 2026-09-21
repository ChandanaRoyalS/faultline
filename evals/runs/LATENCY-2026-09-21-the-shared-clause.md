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
