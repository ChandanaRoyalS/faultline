# ADR-0012: Alert thresholds, and the headroom left on ServiceHighLatency

- **Status:** accepted
- **Date:** 2026-08-23
- **Task:** T1.3 (alert rules), revisited during T1.5 rehearsal

## Context
T1.3 set three alert rules against a measured baseline and recorded the numbers in a
comment at the top of `compose/prometheus/alert-rules.yml`. Nothing recorded *why* the
thresholds are where they are, or what would justify moving them — which matters now,
because rehearsing the scenario catalog puts continuous pressure on exactly that question.

Every scenario is scored partly on which alerts fired. That makes the rules part of the
measuring instrument, not part of the environment, and an instrument adjusted to make its
own readings tidier is not measuring anything.

## The thresholds, and what they are grounded in

| Rule | Threshold | `for` | Grounded in |
|---|---|---|---|
| `ServiceHighErrorRate` | ratio > 0.05 | 2m | baseline error ratio is 0.000 on every service |
| `ServiceHighLatency` | p95 > 250ms | 3m | most services 1.9–9.6ms; checkout 37ms, frontend 42ms |
| `ServiceNoTraffic` | rate == 0, given prior traffic | 3m | two false-positive guards, learned on a healthy world |

Re-measured 2026-08-23 over 29 quiet minutes (a partial baseline; see
`evals/baselines/20260823T061632Z-INVALID-contaminated/summary-partial.md` for why it is
partial):

**Error ratio: the "baseline 0%" claim is accurate.** Every service at or near 0.00%, zero
samples above the 5% threshold. An earlier reading of emailservice at 4.77% was an
averaging artifact of a contaminated window — its only non-zero samples were an injected
incident's recovery phase. No change warranted.

## Decision: ServiceHighLatency has ~75s of headroom on cartservice, and stays as it is

`cartservice` p95 is **bimodal**: mean 22ms, but with excursions to 353ms and nothing
injected. One such excursion in 29 minutes, lasting **105 seconds** — against a 180-second
`for` clause. The rule does not fire, with about 75 seconds to spare.

The rule is **not** being tuned around this. Three reasons:

**The excursion is a real property of this world.** Something in cartservice genuinely
takes a third of a second at p95, periodically, under emulation. An alert that hides it is
an alert that lies about the environment the agents are being evaluated in.

**An alert tuned for rehearsal convenience is not the alert being evaluated.** The scenario
catalog is scored against these rules. Widening the threshold or lengthening `for` to make
recording smoother would change the instrument to suit the experiment, and every number
downstream would be measured against a rule chosen for the wrong reason.

**75 seconds is headroom, not a margin of error.** The measured excursion would have to run
71% longer to fire. That is not close.

### What would change this decision

- The excursion lengthening past ~180s, at which point `ServiceHighLatency/cartservice`
  starts firing on a healthy world and the rule is producing false positives rather than
  narrowly avoiding them.
- Finding a *cause* worth fixing in the world itself — the honest fix is to make cart stop
  doing this, not to stop the alert noticing.

### This is one observation

n=1, over 29 minutes, from a window recovered out of a contaminated 45-minute run. It wants
confirming with a clean 45-minute baseline before anything is built on it. Recorded now
because the batch of nine rehearsals starts before that confirmation exists, and a reader
finding `ServiceHighLatency/cartservice` in a bundle needs to know this is a known
possibility rather than a discovery.

## Consequences

**Roughly six healthy excursions are expected across nine rehearsals.** At one per 29
minutes and ~20 minutes of world time per scenario, most rehearsals will contain at least
one. They are short enough not to fire, so most will be invisible — but one that runs long
enough would appear in `alerts_over_window` looking exactly like blast radius.
`evals/scenarios/ARTIFACTS.md` therefore makes checking for it part of marking a scenario
rehearsed.

**`cart-dependency-latency` is separated from this by duration, not magnitude.** The fault
produces ~650ms; healthy excursions reach 353ms. Those are the same order, and an
investigator — or an agent — reading a single latency sample cannot tell them apart. What
distinguishes them is that the fault holds for the length of the dwell while the healthy
excursion lasts under two minutes. The `for: 3m` clause is doing the discriminating work,
not the 250ms threshold. Worth knowing before concluding that a 300ms delay is comfortably
above a 250ms threshold: on magnitude alone, it is not.

Revisit if: a clean 45-minute baseline shows the excursion is longer or more frequent than
this single observation suggests, or if any healthy-world alert starts firing during a
rehearsal.
