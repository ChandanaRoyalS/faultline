# Pre-registration — the baseline suite, B0.3 / B1 / B2

**Written and committed before any of these runs.** Merged first, run second; a pre-registration
applied after its runs is not one.

**Why now, and why this is not a sweep.** Gate 4's condition names *"the T4.7 baseline suite"*, and
the 2026-09-20 assessment found the suite **built and never run**: across the whole tree, 42 `b0`
manifests and **zero `b1`, zero `b2`**, with the 42 at B0 version 2, which
[Q34](../docs/QUEUE.md) superseded on 2026-09-14 after finding B0's third signal had never
executed. `BaselinePanel` already refuses to exist without an entry for all three — *"an unrun
baseline is a row that says so, never an absent row"* — so the headline table cannot carry the
panel the brief calls mandatory until these run. **This is G4's last run-shaped blocker and it is
the only one.** The agent arm is not re-run: `prompt_digest` has not moved since dev sweep 12, and
re-running ten scenarios with no registered question would be a re-run to improve a number.

**A second thing these runs buy, stated so it is not claimed as a finding later.** They will be the
first runs recorded after 2026-09-21's instrument fix, so they are the first whose
`metrics.latency` splits model, tool and retrieval time honestly
([`LATENCY-2026-09-21-the-shared-clause.md`](LATENCY-2026-09-21-the-shared-clause.md)). That is a
**by-product**, not a purpose: B1 and B2 are different pipelines from the agent's, so their
decomposition says nothing directly about the agent's 232.8 s median. What it does establish is
that the instrument works.

---

## 1. The runs

Ten dev scenarios — `sweep.runnable()`, the catalog's ten — at **R = 1** for each of three
baselines, thirty runs total.

| arm | what investigates | model calls |
|---|---|---|
| **B0.3** | no LLM: alert attribution, most-recent change in window, largest error delta | none — **\$0.00, and that zero is a measurement** |
| **B1** | one agent, all four tools, no fan-out | yes |
| **B2** | the alert text and the service catalog, **no tools at all** | yes |

**R = 1 is deliberate and is not the agent arm's standard.** A baseline is a floor, and a floor
does not need an interval: the question *"how much of this needed looking?"* is answered by where
the arm lands, not by how tightly it lands there. Any comparison drawn against the agent arm
inherits the agent's R = 3 and the catalog's **16.2 pp MDE**, and no per-arm delta below that floor
will be read as an effect.

**Order**: B0.3 first — it is free and it exercises the loop — then B2, then B1. If the ceiling or
the clock runs out, the batch stops at an arm boundary and the note says which arms ran, rather
than reporting a partial arm.

**Before the loop starts** (T6.8's batch-3 lesson, as a numbered step, not a sentence in a
paragraph): `curl -s localhost:8000/healthz` answers `{"status":"ok"}`, the orchestrator's consumer
is polling, and Prometheus reports 0 alerts firing. The loop does not start until all three are
true.

## 2. Ceiling

**\$8.00 for the batch, not raised.** The estimate beneath it: B0.3 is \$0.00 by construction; B2
makes one call with no tool results in its context, estimated under \$0.10 a run; B1 makes a
handful with four tools' envelopes, estimated \$0.25–\$0.45 a run against the four-specialist
pipeline's \$0.713 median. That is roughly **\$1 + \$4 = \$5**, and the ceiling carries the margin.
Every run is additionally bounded by `Budget.max_usd` at Gate 4's \$2.

**A run the gate refuses is recorded and is not re-run** — refusals cost nothing, injected nothing,
and counting them as runs would flatter the pipeline's discard rate
(`sweep.DISCARD_RATE`'s own note).

## 3. Predictions

| # | prediction | falsified by |
|---|---|---|
| P1 | **B2 scores lowest of the three on fault class.** No tools means no evidence; anything it gets right is prior knowledge of the catalog's shape | B2 at or above either of the others |
| P2 | **B1 scores above B0.3 on fault class.** One agent with four tools should beat three hand-written signals, or the tools are not carrying their weight | B1 at or below B0.3 |
| P3 | **B1 scores below the agent arm's 26 / 27** (dev sweep 12, arm A, abstentions excluded). Fan-out is the only structural difference, so a B1-versus-agent gap is about structure and not capability | B1 at or above 26 / 27, which would say the fan-out buys nothing on this catalog |
| P4 | **B0.3 differs from B0.2's 2 / 10** on fault class. Q34 found B0's third signal had never executed; a version that fixes a dead signal and changes no answer says the signal was not load-bearing | B0.3 at exactly 2 / 10 — **reported either way, and a null here is a finding about Q34** |
| P5 | **Every B1 and B2 run finishes inside Gate 4's 180 s.** Both are structurally shorter than the agent's pipeline — no fan-out for B1, no tool calls at all for B2 — and the agent's median is 232.8 s over 139 runs | any B1 or B2 run over 180 s, which would move the latency problem out of fan-out and into the serial spine |
| P6 | **`metrics.latency` on these runs carries a non-zero `retrieval_ms` and a `model_ms` that includes the proposal and narrative steps.** The instrument fix, checked on live runs rather than by test alone | a zero where a model call happened |
| P7 | **Batch ≤ \$8.00; B0.3 exactly \$0.00; no run exceeds \$2.00** | more |

**P5 is the one worth watching.** If B1 — one agent, four tools, no parallelism — comes in under
180 s while the four-specialist pipeline sits at 232.8 s, the fan-out is not what costs the time,
and the next place to look is the serial tail the instrument has only just started timing.

## 4. What this does not claim

**Not a re-benchmark of the agent.** No agent-arm run is made and no published figure moves.

**Not a like-for-like comparison.** The agent arm is R = 3 on the same scenarios and these are
R = 1; a difference at or under the 16.2 pp MDE is not an effect, and a difference above it is one
observation of a difference, not a rate.

**Not a claim about the holdout**, which has no run on this world at all.

**And not a latency finding about the agent.** P5 and P6 are about these pipelines and this
instrument. The agent's own decomposition needs an agent run, which nothing here registers.
