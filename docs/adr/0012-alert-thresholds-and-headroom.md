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

## Decision: ServiceHighLatency has ~75s of headroom on cartservice, and stays as it is [see corrections below]

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

## Correction (same day): the headroom claim is wrong

The section above rests on one observation over 29 recovered minutes. A rehearsal recorded
hours later contradicts it, from that bundle's own captured series.

`cartservice` p95 in the five minutes **before** any fault was injected:

```
07:48:39   380ms      07:52:24   340ms
07:48:54   320ms      07:52:39   379ms
07:49:09   100ms      07:52:54   396ms
07:49:24 …  2-26ms    07:53:09   525ms
  (quiet ~3 min)      07:53:24   567ms      <- injection at 07:53:39
```

Three claims above do not survive this:

| Claimed | Measured |
|---|---|
| max 353ms | **567ms**, still climbing at injection |
| one excursion per 29 min | **two in five minutes** |
| 105s, ~75s of headroom, does not fire | crossed 180s continuous and **fired** at 07:55:39 |

The behaviour is not an occasional excursion. It is **oscillation across the threshold**,
bursting every few minutes, and it does fire on an unfaulted world. `ServiceHighLatency`
has no headroom on `cartservice`; it has a false-positive rate nobody has measured.

The decision not to tune the rule stands, and for the same reason — an alert adjusted to
make rehearsal tidier is not the alert being evaluated. What changes is that this is now a
known false-positive source rather than a near miss, and two things follow.

**`cart-dependency-latency` loses most of its separation.** The fault produces ~650ms; the
world reaches 567ms on its own. Magnitude no longer distinguishes them at all, and duration
distinguishes them less than assumed, because the healthy excursion here lasted long enough
to fire. That scenario needs re-examining before it is rehearsed - it may not be
separable from background behaviour on this world.

**A baseline gate that checks firing alerts is not enough.** At injection cart was at 567ms
with `ServiceHighLatency` pending, 15 seconds from firing, and the recorder's gate saw a
quiet world because nothing was *firing* yet. The gate should refuse on pending alerts too.
Not implemented here.

The underlying question - what makes cartservice do this under emulation - is unanswered
and now worth answering, because it is contaminating an eval scenario rather than merely
sitting near a threshold.

## Second correction (2026-08-23, later the same day): the first correction was also wrong

The section above is left in place unedited. Both it and the original claim are wrong, in
opposite directions, and the record of that is worth more than a clean document.

### 1. The evidence it rests on is no longer in the repository

The correction cites `cartservice` reaching **567ms unfaulted**, quoted from a
`cart-redis-misconfig` recording. That bundle has since been re-recorded; the committed
one peaks at **2ms** in its pre-injection window. Nothing in the tree supports 567ms.

The observation was real when made. It is now unverifiable, because a re-record replaced
the artifact it came from — an ADR citing a bundle by its contents rather than by a
checksum has no way to notice this. See ADR-0009 on `scenario_fingerprint`: bundles can
now be tied to labels, but prose citing a bundle still cannot.

### 2. It attributed a fired alert to a cause that was not acting alone

The correction states that a healthy excursion "crossed 180s continuous and fired." It did
not. The excursion began at **07:52:24**. The fault was injected at **07:53:39** — 75
seconds in. What crossed the clause was the excursion *plus the injected fault*, and the
conclusion drawn was that unfaulted behaviour alone was sufficient to fire the alert.

**This is a confounding error**, and naming it plainly matters: a signal was attributed to
one cause while a second, larger cause was acting on the same service in the same window.
It is precisely the reasoning failure this benchmark exists to measure — an investigator
seeing elevated latency and concluding "the world does this on its own" while a fault is
active is exactly the wrong answer `cart-dependency-latency` is designed to catch. The
author of the scenario made it while writing the ADR about the scenario.

### 3. Corrected figures, from all committed unfaulted data

Coverage counted by samples (177 × 15s), not by elapsed span:

| | Unfaulted | Under fault |
|---|---|---|
| coverage | 44.2 min | 8.5 min |
| peak p95 | **353ms** | **663ms** |
| longest run above 250ms | **105s** (58% of the clause) | **600s** (3.3× the clause) |

Sources: 29.2 min from the recovered quiet spans of the invalidated baseline, plus 5.0 min
of pre-injection window from each of the three committed bundles.

**Separation: 5.7× on duration, 1.9× on magnitude.** No unfaulted excursion in any
committed data has fired, or come within 75 seconds of firing.

### The decision does not change — and the argument for it is now stronger

The rule is still not tuned. The reason has improved rather than weakened: the first
correction argued against tuning while claiming the hazard was severe (a firing
false positive), which is the case where tuning is most tempting. With the hazard
measured at 58% of the clause and never firing, there is no pressure to tune at all.

That is worth flagging on its own. **This ADR's evidence was wrong in the direction of its
own conclusion** — it overstated the danger while recommending no action, so the error was
invisible from the recommendation. An ADR that reaches the right decision from wrong
evidence is not self-correcting: nothing downstream misbehaves, so nobody looks. It was
caught only because the numbers were re-derived from committed data on request.

`cart-dependency-latency` is **separable** on present evidence, contrary to the first
correction's claim that it "loses most of its separation." It should be treated as sound
unless a longer baseline says otherwise.

### The measurement defect that produced the overstatement

Unfaulted coverage was first reported as 59.2 minutes. It is 44.2. The script computed
coverage as last-sample-minus-first, which for the baseline series spans the **16-minute
contaminated gap that had been explicitly excluded from the analysis** — the exclusion was
applied to the samples and not to the span calculation. Coverage was overstated by 34%
while the surrounding argument was about whether the sample was too thin to trust.

Same shape as every other defect in this project, and ADR-0009 names the class: a number
that looks like evidence and is not. It was not a wrong measurement of the world; it was a
correct measurement of the wrong thing, reported without a unit anyone would question.
Sample counts are now used instead of spans, because a sample count cannot silently
include time that was excluded.

## Third correction (2026-08-24): cartservice is not bimodal, and never was

The original section and both corrections above are left unedited. All three were
reasoning about a service that was still warming up.

### The clean baseline

`evals/baselines/20260824T033742Z` — 45 minutes, `valid: true`, zero injections during the
window, 181 samples:

| Service | min | mean | max | samples over 250ms |
|---|---:|---:|---:|---:|
| `cartservice` | **1.9ms** | **1.9ms** | **1.9ms** | **0** |
| `checkoutservice` | 35.3ms | 37.6ms | 39.5ms | 0 |
| `frontend` | 40.8ms | 41.9ms | 43.0ms | 0 |

Flat. Not "mostly flat with occasional excursions" — 181 consecutive samples at 1.9ms. The
INVALID capture reported `checkoutservice` peaking at 1060ms; the clean one never exceeds
39.5ms.

### Every elevated observation was a post-recreate transient

Each figure this ADR rests on was sampled inside cartservice's recovery from being
recreated by a cart-targeting fault:

| Observation | Sampled | After a cartservice revert at |
|---|---|---|
| INVALID baseline excursion (353ms) | 07:00:02 | 06:45:49 — 14.2 min |
| the first correction's 567ms reading | 07:52:24 | 07:48:24 — 4.0 min |
| a 100ms reading in a later bundle | 16:16:22 | 16:15:34 — 0.8 min |

The third is decisive because its whole decay is committed, in
`productcatalog-dependency-latency`'s pre-injection window:

```
16:16:22  100.0ms      16:17:07   30.0ms
16:16:37   90.0ms      16:17:37    8.5ms
16:16:52   50.0ms      16:19:37    1.9ms   settled, +4.0 min
```

Monotonic decay to baseline over about four minutes. That is a warm-up transient — the same
shape as the rate window emptying that ADR-0009 documents — not a service that oscillates.

**The premise was an artifact of mining figures from a capture this repository marks
INVALID.** The directory is named `-INVALID-contaminated` and carries an `INVALID.md`
saying not to cite it; a partial summary was derived from its "quiet" spans anyway, and one
of those spans contained a recovery.

### The decision does not change, and is now trivially correct

`ServiceHighLatency` stays untuned. There is no longer a headroom question to answer,
because there is no baseline noise to have headroom against: cartservice sits at 1.9ms
against a 250ms threshold. The first correction's claim that the rule "has a false-positive
rate nobody has measured" is withdrawn — the rate is zero over 45 clean minutes.

### The limit of this argument

**Only one pre-world-change bundle survives** (`currency-cpu-throttle`, injected 09:46, and
flat). The container memory limits were raised at ~10:40, so the case that those changes
were *not* responsible for the difference rests on the transient being visible **after** the
change — the 16:16 decay above — rather than on a pre/post comparison, which one sample
cannot support.

The stronger pre-change evidence was lost to a re-record: the 07:52 window showing 567ms
belonged to a `cart-redis-misconfig` recording that has since been replaced, and the
superseded archive kept manifests only. That gap is why the archive now keeps compressed
metric captures too (ARTIFACTS.md).

## Consequences

**Superseded by the correction above — this estimate is too low.** Roughly six healthy
excursions were expected across nine rehearsals. At one per 29
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
