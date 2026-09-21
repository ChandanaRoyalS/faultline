# The baseline suite — B0.3, B2 and B1, 2026-09-21

**Thirty runs started, twenty-nine scored, one discarded. $3.4552 of an $8.00 ceiling.** Against
[`PREREGISTRATION-BASELINES.md`](PREREGISTRATION-BASELINES.md), merged before the first run. World
`90e9f29e…`, stamp `prompts:06f24e827915`, ten dev scenarios at R = 1 per arm.

**This is Gate 4's last run-shaped blocker, and it is closed.** Before today the tree held 42 `b0`
manifests at a superseded version and **zero `b1`, zero `b2`**; `BaselinePanel` refuses to exist
without an entry for all three, so no headline table could carry the panel the brief makes
mandatory. All three now have runs at the shipping stamp.

## The panel

| axis | **B0.3** heuristic, no LLM | **B2** prior, no tools | **B1** one agent, four tools, no fan-out | agent, four specialists *(sweep 12 arm A, R = 3)* |
|---|---|---|---|---|
| fault class, of answered | 4 / 10 | 6 / 10 | **9 / 9** | 26 / 27 |
| fix class | 5 / 10 | 8 / 10 | 8 / 9 | 23 / 27 |
| **culprit service** | **not produced** | **not produced** | **not produced** | 23 / 30 |
| abstentions | 0 | 0 | 0 | 3 of 30 |
| median latency | 0.0 s | 30.5 s | **60.5 s** | 251.6 s |
| inside Gate 4's 180 s | 10 / 10 | 10 / 10 | 9 / 9 | 2.9 % *(over 139 runs)* |
| median cost | **$0.0000** | $0.0364 | $0.3406 | $0.7130 |
| arm spend | $0.0000 | $0.3771 | $3.0781 | — |

**B0.3's $0.00 is a measurement, not a missing value** — it makes no model call by construction.

## The predictions, scored

| # | prediction | result |
|---|---|---|
| P1 | **B2 scores lowest of the three on fault class** | **FALSIFIED.** B2 6 / 10 against B0.3's 4 / 10. See below — and see the caution, because +20 pp on n = 10 barely clears the 16.2 pp MDE |
| P2 | **B1 scores above B0.3** | **HELD**, 9 / 9 against 4 / 10 |
| P3 | **B1 scores below the agent arm's 26 / 27** | **FALSIFIED.** 9 / 9. Its registered falsifier says what that means: *"B1 at or above 26 / 27 … would say the fan-out buys nothing on this catalog"* |
| P4 | **B0.3 differs from B0.2's 2 / 10** | **HELD**: 4 / 10. Q34's dead third signal was load-bearing — fixing a signal that had never executed doubled the heuristic. Reported either way, as registered |
| P5 | **Every B1 and B2 run inside 180 s** | **HELD, 19 / 19.** B2 median 30.5 s, B1 median 60.5 s, against a pipeline that clears the bar in 4 of 139 runs |
| P6 | **`metrics.latency` carries non-zero `retrieval_ms` and a `model_ms` including the tail** | **FALSIFIED, 19 / 19.** Every B1 and B2 run printed `models 0.0s` beside a real dollar figure. Two more untimed sites, below |
| P7 | **Batch ≤ $8.00; B0.3 exactly $0.00; no run over $2.00** | **HELD**: $3.4552 total, B0.3 $0.0000, dearest single run $0.6483 |

## What the arms say, and what they cannot

**The fan-out is not what earns the fault-class figure.** One agent with the same four tools and no
parallel specialists answered every scenario it ran and got every one right, at **a quarter of the
latency and under half the cost**. That is P3's registered reading and it is the batch's main
result.

**Three things keep it from being *the fan-out is useless*, and they are not softeners.**

1. **n = 9 at R = 1 against the agent's R = 3.** 9/9 against 26/27 is far inside the 16.2 pp MDE.
   The defensible sentence is **no measurable difference on fault class**, not *B1 is better*.
2. **Dev only** — the ten scenarios the prompts and retrieval were fitted against. Nothing here
   touches the holdout, which has no run on this world at all.
3. **B1 names no culprit service.** Neither does B2, and B0 cannot by design. So the comparison is
   fault class and fix class; the pipeline's 23 / 30 on **service — the benchmark's headline axis —
   is untouched by any of this.**

**Which is the suite's own most uncomfortable finding: the headline axis has no floor.** Not one of
the three baselines produces a culprit service, so *culprit service 23 / 30* has never been read
against a control and this panel cannot give it one. A reader is entitled to ask what 23/30 beats,
and the honest answer today is *nothing measured*. **That is a gap in the baseline suite, not in
the pipeline**, and it is recorded here rather than left for someone to notice.

**P1's falsification, with its caution attached.** B2 — alert text, service catalog, no tools —
beat the heuristic that actually queries Prometheus, Loki and the change log. The mechanism is
visible in the answers: B2 said `bad_config` six times, and `bad_config` is the modal class of the
dev catalog at 4 of 10. It took three of those six, plus both `dependency_latency` scenarios, plus
one `bad_deploy`. So a good part of 6/10 is **the modal class plus what the alert shape gives
away**, which is exactly what this arm exists to expose. But +20 pp on n = 10 clears the 16.2 pp
MDE by less than one scenario, so the reportable statement is **no clear separation between the two
baselines**, with the mechanism noted.

**The number that is robust** is the distance from *no looking at all* to the pipeline: **6 / 10
against 26 / 27**. The pipeline's margin over a model with no evidence is roughly four scenarios in
ten — not ten in ten — and that is the sentence the headline table has been missing.

## P6, and two model calls nobody had timed

The 2026-09-21 instrument fix ([`LATENCY-2026-09-21`](LATENCY-2026-09-21-the-shared-clause.md))
timed four model calls in `investigation.py` and added a guard that parses that file. **It missed
two more**, in `faultline/agents/cli.py`: B1's completion step and B2's, both `StepKind.COMPLETION`
with `tokens_in` / `tokens_out` and no `latency_ms`. So every one of the nineteen paid baseline
runs printed `models 0.0s` next to a real cost.

**P6 caught what the test did not**, which is the argument for having written it. The fix was
deliberately **not applied mid-batch**: three B2 runs were already recorded with `model_ms = 0`, and
letting the remaining seven carry real latency would have left one arm disagreeing with itself
about what it measured. It lands after this note, with the guard extended to every file that
constructs a `TrajectoryStep`.

## The discard, exactly

`20260921T101608Z-cart-redis-misconfig`, B1 arm:

> `REFUSED: incident 654ae9ee-be1b-43f7-8e4d-bba54661ccda is in state resolved; the machine
> investigates from rejected, triaging only. A failed or resolved incident is terminal in
> ADR-0016's table.`

The run passed the gate, injected, and the orchestrator opened an incident — **which resolved
before `faultline-investigate` reached it.** `inject.txt` and `revert.txt` are both in the
directory; `investigate_exit_code` is 3.

**Classified as a discard, and that is right.** ADR-0022 §3.3 keeps refusals out of the discard
count because *nothing was injected*; here something was. The fault was in the world, world time
was spent, and no result came out, which is what a discard is. One in thirty started runs.

**Not diagnosed here.** Why the incident resolved inside the settle window is unestablished — the
same scenario ran clean for B0.3 and B2 earlier the same day — and one occurrence is an
observation, not a rate. Recorded so a second one is recognised rather than re-derived.

## Amendment — what §2 did not cover, written now rather than explained later

The pre-registration's §2 said *"a run the gate refuses is recorded and is not re-run"* and that the
batch *"stops at an arm boundary"*. Two things happened that neither sentence covers, and both are
recorded as they occurred:

**A partial arm, resumed.** B2's first sweep scored 3 of 10 and **paused** the other seven on the
kafka headroom gate — 76.5% of 2048 MB projecting to ~102% over the remaining runs, past the 90%
guard, with the recycle command and the reason a higher limit is not the remedy in the refusal
text. A pause is neither a refusal nor a discard: nothing was injected and the scenario *has not
been attempted*. The seven were resumed with `--only` after recycling kafka and its consumers, and
the three that had scored were **not** re-run. **So B2's ten runs are 3 + 7 and are still R = 1** —
one run per scenario, which is what the design asked for. Seven pauses cost 20 pre-flight tokens
each and nothing else.

**A discard inside an arm.** B1 is nine scored of ten started. The arm is reported at n = 9 and the
discarded run is named above. It is **not** re-run: *no re-runs to improve a number* covers a
number that came out short as much as one that came out wrong.

## What this does not say

**Not a re-benchmark of the agent.** No agent-arm run was made; `prompt_digest` has not moved since
dev sweep 12 and no published figure changes.

**Not a like-for-like comparison.** R = 1 here against R = 3 there, and the axes differ — no
baseline names a service.

**Not a claim about the holdout**, which has no run on this world.

**And not a latency finding about the agent.** B1 and B2 are different pipelines; their being fast
says the fan-out costs time, not where the agent's own 232.8 s goes. That decomposition needs an
agent run recorded after the instrument fix, and nothing here registers one.
