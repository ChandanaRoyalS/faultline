# Holdout entry 2 — 2026-08-26, `changes` bound raised

> **World: superseded, and two generations back — `compose_digest 4a7690c6fdda…`.**
>
> **Corrected 2026-09-01 (T7.54).** This page previously carried T7.28's banner attributing it to
> `compose_digest 299d791c5e0d…`. That was wrong: the banner was applied per file rather than per
> run, and **every run on this page predates T7.1's world move.** The last run against
> `4a7690c6fdda…` finished `2026-08-28T01:51Z` and T7.1's re-record began capturing against
> `299d791c5e0d…` at `2026-08-28T02:41Z`; no run on this page falls after that. The repo said so
> itself at the time — `PREREGISTRATION-2026-08-28-refound.md`: *"Every published figure in this
> repository was measured on"* the `4a7690c6fdda…` world.
>
> The world has moved **twice** since: to `299d791c5e0d…` at T7.1, then to `f5bd108f…` /
> `observability_digest 857d95b4…` at T7.28 (kafka's allocator bounded, a `maxmemory`/`allkeys-lru`
> bound on redis-cart, a `memory_limiter` on the collector).
>
> **These numbers describe a world two generations old and nothing has been re-run against the
> current one.** They are not current-world figures; there are no current-world figures for this
> page. What is worth measuring against the new world is a separate pre-registered decision.

**Incomplete: one of three scenarios scored.** Two were discarded to an empty API account before
their first model call. Published as it ran, per the
[pre-registration](HOLDOUT-2026-08-26-entry2-PREREGISTRATION.md)'s "no re-runs, discards recorded
and left".

**[Entry 1](HOLDOUT-2026-08-26.md) stands unedited.** This is a second entry, not a replacement —
see [ADR-0022's T4.8 addendum](../../docs/adr/0022-evaluation-harness.md) for why that is
permitted and what separates it from a re-run.

| | entry 1 | **entry 2** |
|---|---|---|
| entitled by | T4.5's taxonomy-instruction pipeline | **T4.7's raised-bound configuration** |
| stamp | `faultline/0.0.1+prompts:53fafe9c12bc` | **identical** |
| `changes` bound | 4 | **8** |
| other three bounds | 4 / 120k / 600s / 2 rounds | identical |
| agent · judge | `claude-opus-5` · `claude-haiku-4-5` (SHARED LINEAGE) | agent identical; **no judge — see below** |
| corpus | 35 rows, 7 docs, **0 holdout chunks** | identical |
| scenarios scored | 3 of 3 | **1 of 3** |
| cost | $1.0774 + $0.1203 judged | **$0.4175**, no judge |

## The table

| scenario | truth | entry 1 | entry 2 | `changes` used |
|---|---|---|---|---|
| email-wrong-image | `bad_deploy` / `rollback` | `unknown` **ABST**, exhausted `changes` 4/4 | `unknown` **ABST**, **exhausted nothing** | **2 of 8** |
| productcatalog-dependency-latency | `dependency_latency` / `restart` | `dependency_latency` ✔ | **discarded** — empty API account | — |
| recommendation-memory-squeeze | `resource_exhaustion` / `config_revert` | `unknown` **ABST**, exhausted `changes` 4/4 | **discarded** — empty API account | — |

Entry 2's one scored run: fault class **abstained**; class of fix `restart` against `rollback`,
**wrong** (not abstained — it named a fix while declining a class, a combination not previously
seen); triage recall **1.00**, precision 0.11, 4 unmeasured edges; nothing flagged, nothing
failed alone, no contradiction, **no bound exhausted**, narrative rendered.

## The prediction versus what happened

Registered before the run. Scored honestly.

| | prediction | outcome |
|---|---|---|
| **P1** | `changes` exhaustion goes to zero | **HELD** — 2 of 8 used, nothing exhausted |
| **P2** | both starved abstentions produce a class | **FALSIFIED** on the one tested. `email-wrong-image` abstained again |
| **P3** | those classes are correct | **FALSIFIED** — no class was produced |
| **P4** | productcatalog stays correct, fix stays wrong | **UNTESTED** — discarded |
| **P5** | exhaustion moves to another bound | **NOT OBSERVED** — nothing exhausted at all |

The pre-registration also named its own falsifier:

> "An abstention that persists **with `changes` unexhausted** is instruction-owned, not starved …
> If either of the two starved scenarios abstains again while exhausting nothing, the dev
> conclusion does not carry to holdout, and this entry says so."

**That is exactly what happened, and this entry says so.** T4.7's dev finding — that raising the
`changes` bound dissolves starved abstentions — **did not carry to `email-wrong-image`.**

## Why it did not carry, which is not what either hypothesis predicted

The interesting part is not that the prediction failed but *how*. Entry 2's planner had six
unused `changes` calls and **never asked about `emailservice` at all** — the service its own
traces named as having vanished.

| | entry 1 (bound 4) | entry 2 (bound 8) |
|---|---|---|
| round-1 dispatches | **12** | **3** |
| `changes` planned, round 1 | checkoutservice, cartservice, productcatalogservice, shippingservice, **emailservice** | checkoutservice |
| round 2 | — | 2 dispatches, `changes` on checkoutservice **again** |
| `emailservice` change history | planned at #5, **cut off by the bound** | **never planned** |

**Same scenario, same prompts, same stamp — and the planner's round-1 breadth differed fourfold.**
Entry 1 was starved reaching for the right service. Entry 2 never reached.

So this scenario's abstention has a **third** cause, distinct from both hypotheses T4.7
separated on dev: not budget starvation, and not the taxonomy instruction refusing to classify
from a change record, but **planner allocation** — the plan simply did not investigate the
implicated service. The verdict says so in its own words:

> "What removed emailservice from DNS (failed deploy, OOM kill, scale-to-zero, discovery-side
> change) **was never dispatched on**, so the initiating act is unestablished."

It is worth being clear about what the run *did* get right. It identified the failing mechanism
precisely — an outbound POST to `emailservice:6060` failing at DNS resolution against the
container's embedded resolver before any TCP dial, the same host and port having succeeded
earlier in the window, with the email step non-fatal so the error ratio peaked near 7.8% rather
than going total. It declined only the *initiating act*. That is a defensible abstention on the
evidence it gathered, and a poor allocation decision about which evidence to gather.

**n = 1.** One scenario, one run per entry. This does not establish that planner breadth is
unstable; it establishes that it was different on these two runs, by a factor that mattered.

## The two discards

| run | scenario | reason |
|---|---|---|
| `20260826T220307Z` | productcatalog-dependency-latency | `BadRequestError: 400 — Your credit balance is too low` at the first model call |
| `20260826T221635Z` | recommendation-memory-squeeze | same |

Both **passed their baseline gate**, injected, failed to start, reverted from the `finally`, and
**confirmed recovery**. Neither persisted a trajectory, and per T3.5's failed-start rule neither
incident was marked `FAILED` — both stayed investigable and resolved normally. The retry
correctly declined: a 400 is terminal and is deliberately outside `TRANSIENT_SIGNALS`.

**Neither was re-run.** The pre-registration said no re-runs and discards recorded and left, and
re-reading that after seeing a result is the move pre-registration exists to prevent. The two
scenarios are **untested under the raised bound**, and that is the honest state of this entry.

## No judged column

The judge runs on the same account and could not be reached. Entry 2 has **no judge figures at
all** — not a refused narrative, not a failed judgement, simply not run. Entry 1's judged column
stands and is not carried across.

## What this entry costs and what it bought

It is entry **2 of 2** in the ADR's ledger, on a three-scenario set, and it spent one scenario's
worth of that set to return a falsification and a new hypothesis. A third entry would need an
argument the addendum does not supply — and it would now also have to explain why two of these
three scenarios remain untested under the current configuration rather than simply running them.

**What entry 2 establishes:** T4.7's dev conclusion does not generalise to `email-wrong-image`,
and the reason is a cause neither hypothesis named.

**What it does not:** anything about the other two holdout scenarios under the raised bound.
Entry 1 remains the only measurement of those, taken under a bound now known to have starved them.
