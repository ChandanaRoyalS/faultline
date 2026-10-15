# Three things the measurements said that the design did not expect

*Faultline's technical writeup (T7.5), 2026-10-15. Every number below is from a dated report in this
repository and links to it; nothing is computed here. Each is a run of R = 1 on a small catalog,
so each comes with the size of effect it could have seen.*

Faultline is an incident-investigation agent system for the OpenTelemetry stack. An alert opens
an incident; triage decides whether it is worth investigating; a planner sends specialist agents
(logs, metrics, traces, deploy history) out in parallel; a synthesizer turns their evidence into a
root-cause report in which every claim cites a tool result the system can check; a proposer
suggests a fix that runs only if a person approves it. It was built against a published execution
plan, and measured on a world that is broken on purpose with labelled, reversible faults.

The plan expected the measurements to show which parts of that pipeline earn their place. They
did, though not in the direction it assumed.

---

## 1. One agent with the same tools did as well as the pipeline, and on the dev set better

**The finding.** B1 is a single agent with the same five tools as Faultline and none of its
structure: no triage gate, no planner, no fan-out, no retrieval, no synthesis round. On the nine
usable holdout scenarios of the v2 world it named the fault class on **6 of 9** and the culprit
service on **7 of 9**. So did Faultline: **6 of 9 and 7 of 9**, a paired difference of **+0
points** (-33 to +33). On the 27 dev scenarios B1 was right on fault class **22 of 25 (88 %)**
against Faultline's **15 of 26 (58 %)**: **-26 points (-48 to -4)** for the pipeline, beyond the
16-point minimum detectable effect, with an interval clear of zero
([headline report](../evals/runs/HEADLINE-2026-10-11-v2.md)).

**It replicated.** The ablation series registered the same comparison as its first experiment
and ran it again, nine days later, on ten dev scenarios: B1 minus Faultline **+40 points (+10 to
+70)** on fault class, past that series' 28-point MDE
([E1](../evals/runs/ABLATION-2026-10-15-E1-single-agent.md)). Two separate runs, the same
direction.

**Where the pipeline loses.** Of the nine dev scenarios B1 got and Faultline did not, three were
triage declining the page (finding 2). The other six were the synthesizer naming an *adjacent
mechanism* from the evidence B1 read correctly in one pass: connection refusals read as a network
partition when an image was bad, a crash loop read as a hang, a broker's stall read from its
consumers as latency. On culprit service the gap is 15 points and its interval reaches zero: the
fan-out finds the right service about as well. It is naming the class that goes wrong, in the
step that summarises other agents' summaries.

**What it cost.** On dev B1 was three times faster to a report (median 71 s against 228 s) at a
lower median cost ($0.74 against $0.85). On holdout it was slower and dearer (185 s, $1.99 against
235 s, $0.88), because it has no per-role budget and will keep looking. Faultline's 228-235 s
also misses the 180 s latency clause two of the plan's gates carry.

**What it does not show.** That the multi-agent structure is worse in general. B1 differs from
Faultline in several things at once (it has no retrieval, no proposer, no gate), so the
comparison cannot say which missing part helps it. It is one world (OpenTelemetry Demo 2.2.0),
nine fault classes, R = 1. What it does show is that on this catalog the planner, the four-way
fan-out and the synthesis round do not buy accuracy, and that a pipeline built without a
same-tools single-agent baseline would never have found that out.

## 2. Most misses began before any tool ran: the triage gate

**The finding.** Triage is a cheap first model call that decides whether an alert is worth an
investigation. On SREGym, the external benchmark, it declined **20 of 33** incidents as noise
before any tool ran. Faultline passed **2 of 33** problems under SREGym's judge, against **30 of
33** for SREGym's own Claude Code agent on the same problems. 24 of Faultline's 33 attempts ended
without a verdict that established a cause: 20 at the gate, 4 with a verdict that named none
([SREGym result](../evals/attempts/T7.2-run/RESULT.md)). The two it passed were the two where its
change log named the fault outright (a DNS policy edited, a deny-all network policy created six
minutes before the alarm).

**The same gate, on Faultline's own world.** It gated 3 of Faultline's 36 headline runs, all on a
page whose only alert was one warning-severity latency alert, all with the same written reason:
*a lone warning alert, no error-rate alert, no propagation*. They are three of the nine dev
scenarios B1 got and Faultline did not; B1 has no gate and investigates everything. In the ablation series it declined
`v2-payment-dependency-latency` under the standing configuration and **under all seven pipeline
variants** ([ablations](ABLATIONS.md)): every experiment changed something downstream of a
decision that had already been made.

**Why this matters more than the number.** The gate was designed on Faultline's own world, where
it rarely fires and saves a model run when it does. On a foreign world, whose alerts look
different, it became the largest single cause of failure, and it fails silently: a declined
incident produces no wrong report to notice, only no report. The scoring rule that made this
visible is that a gated run is scored as a miss on every axis rather than left out of the
denominator; leaving it out would have made Faultline's accuracy look better the more it refused
to look.

**What it does not show.** How much a gate-off Faultline would score. Nobody ran that experiment,
and it is the obvious next one. The SREGym figures are a pass rate under an LLM judge, diagnosis
only, on 33 of 108 eligible problems, with tools that differed (Faultline had no Kubernetes
describe; the baseline had kubectl). They are not comparable to SREGym's leaderboard.

## 3. The prompt injection reached the agents and was never followed

**The finding.** Four scenarios plant an attacker's line in the logs: a runbook-shaped
instruction naming a decoy fix, with a canary token unique to each run. It was **delivered** to
Faultline's log reads in 3 of its 4 runs (the fourth was gated and read nothing) and to B1's in 3
of 4. **No run mentioned the canary, named the decoy target, or proposed the decoy action**:
`followed: false` on all 16 runs across the four arms
([headline report §4](../evals/runs/HEADLINE-2026-10-11-v2.md)). B0 and B2 read no logs, so the
line never reached them; the meaningful count is six deliveries and no compliance.

**Why it held, as far as the design can say.** Telemetry enters the model as untrusted data in a
delimited envelope whose closing tag carries an id random to each call, so a log line cannot
forge the end of its own envelope ([ADR-0019](adr/0019-tool-layer.md)). And the agents could not
have acted on the instruction if they had believed it: the investigation runtime holds no write
credential, and the executor acts only on a single-use token a human approved, for one action on
one target inside the incident's blast radius, refused outright when the kill switch is on
([threat model](THREAT-MODEL.md)). Three of those refusals were demonstrated on a live world, not
only in tests.

**What it does not show.** That the defence is robust. It is one attack shape and six deliveries,
across two arms. On the scored axes Faultline got all three dev injection scenarios wrong (two
on class, one gated) while B1 got all three right, and nothing here attributes either result to
the injected line. A planted log line cannot be retracted, so later runs may have seen earlier
runs' lines; the canary is per run, so none could have mistaken another's for its own.

---

## How the numbers were kept honest

- **Registered first.** Every scored run had a pre-registration merged before it, with its
  predictions and its analysis; the headline registration's predictions included the one that
  came true in finding 1.
- **Held-out scenarios** never entered a prompt or the retrieval corpus, from the day each was
  written, and the dev set is labelled as fitted wherever it is reported.
- **No rate without its n and an interval**, and every comparison states its minimum detectable
  effect before its result. At these sizes that is 16-28 points, so most differences in this
  repository are reported as *no measurable effect at this catalog size*, which is what they are.
- **Discards are recorded, never deleted**, and the rule for each was written before the run.
- **The run record is the source.** The reports, the README's tables and the
  [eval dashboard](../evals/dashboard/index.html) are generated from the committed run manifests,
  and tests fail when any of them disagrees with the record.

## Where to read more

- [The headline run](../evals/runs/HEADLINE-2026-10-11-v2.md): four arms, 36 scenarios, R = 1.
- [The SREGym benchmark](../evals/attempts/T7.2-run/RESULT.md): 33 problems, two arms.
- [The ablation series](ABLATIONS.md): nine dimensions, one at a time, against a 28-point floor.
- [The eval dashboard](../evals/dashboard/index.html): every version of the pipeline and the
  baselines, with what changed between them.
- [Deviations from the plan](DEVIATIONS.md), each with who decided it and when.
