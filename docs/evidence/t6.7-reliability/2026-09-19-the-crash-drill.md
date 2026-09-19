# The crash drill — 2026-09-19

**A live investigation on the VM, `SIGKILL`ed at step 19; the orchestrator logged `exited -9`,
found the incident still `triaging`, and started attempt 2 fifteen seconds later, which ran to a
verdict.** T6.7 piece 3 (b): failure row 6, *worker crashes mid-investigation*, induced on the
deployment. **$1.85**, against a design-note ceiling of $1.00 for the whole task - see the last
section, which is the part of this note that matters most.

```
22:27:05  trajectory 7d230673 starts (row not visible until 22:29:34 - the finding)
22:29:34  kill -9 inside the orchestrator container; exited -9 logged at 22:29:34.655
22:29:34  incident 01565dbd: triaging          trajectory: 19 steps, outcome NULL, $0.465
22:29:49  "investigating 01565dbd (attempt 2)"
22:33:39  trajectory ce5d223d: dispatched, 24 steps, $0.757; incident: proposing
```

## What was written first

The design note (§2): *"a killed investigation is re-run, not resumed, and this note says so."*
The working session, before the inject: **the incident will be stranded** - `exited -9`, one
attempt counted, the incident left in `planning` or `investigating`, the trajectory row with no
outcome, *"and then nothing happens"*, because the runner's `due()` reads only `triaging` and
`rejected`. That prediction was **wrong**, and the reason it was wrong is the second finding.

## What happened, in order (UTC)

**21:41 - the first attempt killed nothing and cost $0.63.** `cart-redis-misconfig` injected; the
incident (`3e34b4da`) opened at 21:43:55 and its investigation ran 21:45:33-21:48:55 to a normal
`dispatched` verdict, because both kills missed: the image has no `pkill` (no `procps` in a slim
Python image), and the shell loop written to replace it matched its own command line - it was
looking for the string *faultline-investigate* and it contained it - and killed itself. Recorded
because it was paid for.

**22:01 - the second inject reopened the first incident.** Re-injected two seconds after
`3e34b4da` resolved; the same alerts correlated into the `RESOLVED` incident inside the 300 s
settle window and **reopened** it to `proposing`, where an incident with a proposal rests. No new
incident, no new investigation, nothing to kill. Correct behaviour (ADR-0016's reopen rule), and
a constraint on any drill that re-uses a scenario: wait out the window.

**22:22 - the drill.** Six minutes after resolution, injected again; `01565dbd` opened 22:25:25;
`investigating … (attempt 1)` 22:26:57; the kill armed as a two-second poll on the `trajectories`
table, firing the moment a row appeared, then `os.kill(pid, SIGKILL)` from a Python one-liner
inside the container that skips its own pid.

**The row appeared at 22:29:34 - two and a half minutes after the run started**, and the kill
landed at step 19 of what would have been ~20, $0.465 in. Not the few cents the drill was
budgeted at. **Finding 1**: `Investigation.run` first saved the trajectory after synthesis
(T3.4's *"persist before the scribe"*), so a run killed before that left **no row at all** -
nothing for Q72's reconciler to name, nothing for `running` on `/metrics` to count. The drill
could only ever have killed a run near its end, and a kill in the first minute of a real run
would have been invisible to every surface built to see it.

**The incident read `triaging`, and attempt 2 started at 22:29:49.** **Finding 2**, and the one
that overturned the prediction: the runner's state transitions (`triaging → planning → … →
proposing`) are written **after** `engine.run` returns, in sequence, by `advance()` - so during a
run the incident is `triaging` throughout, which is exactly what `due()` reads, and the runner's
two-attempt cap gave the killed incident its second attempt. The retry path exists and it ran.
What the same fact also means: the incident page shows `triaging` for the whole three to four
minutes of a healthy run, and README §3.6's *"`triaging` at four minutes is the defect"* cannot
distinguish a stuck incident from a running investigation. **Q78.**

**Attempt 2 ran to a verdict - about a fault that was reverted under it.** `stop --all` went in
at 22:32 while the second run was mid-flight (the block was written for a run that had finished).
Its verdict blamed the shipping-quote path on traces sampled before onset and said of itself
*"attribution is weak"*; the incident rests in `proposing` with an abstaining proposal. Recorded
as it happened. Whether a run whose fault disappears half-way should notice is not this note's
question.

**The orphan reconciler, by hand, at 22:33:53: closed 0** - correctly, the killed row was six
minutes old against a 1200 s ceiling. It closes after 22:47:05, and until piece 3b nothing on the
deployment would have run it at all (Q72's reconciler lived in the sweep, which the VM never
runs): the row would have read `running` until an operator remembered.

## What changed because of it (piece 3b)

- **The trajectory row is written at the run's first second**, with no outcome, inside the root
  span (`investigation.py`); the later saves are the same row filled in. Every kill now leaves a
  row. A *failed start* (an exception before the first step) closes that row as `failed` with
  zero steps and an `ended_at` - T3.5's *"an empty trajectory is not worth a row"* reversed, with
  the reason in the docstring: an unfilled row would read as a running investigation until the
  orphan ceiling called it a kill.
- **The orchestrator's runner reconciles orphans every poll** (`reconcile_orphans`, before
  `due()`), at the same ceiling as the sweep, and logs what it closed. The process that kills
  investigations is the process that reconciles them.
- `tests/test_roles.py::test_the_trajectory_row_exists_before_the_first_model_call`,
  `tests/test_investigation_runner.py` (two tests), `tests/test_runner.py` updated for the
  failed-start row.
- README §3.6's check is reworded (the `investigating` log line and the trajectory row are the
  signal; `triaging` is not the defect it said it was).

## What this does and does not show

**Shown**: a worker killed mid-investigation on the deployment is retried from scratch by the
runner within one poll, and the incident ends with a verdict; the kill leaves an exit code in the
orchestrator's log and a trajectory with no outcome, which the reconciler names. Row 6's
Mitigation and Recovery, as this repository reads them (a re-run, not a resume).

**Not shown**: a resume from the last completed step (not built, §2 of the design note); the
Redis claim path (that is piece 3a, against real Redis, in `test_integration_worker_kill.py` -
the deployment's subprocess kill never involves the stream); a kill in the first minute, which
before piece 3b was unobservable and after it has not been drilled.

## The ceiling

The design note set **$1.00 for all of T6.7** and called the crash drill *"the one paid piece,
≤ $0.70"*. This drill cost **$1.85**: $0.632 for a run two failed kill attempts never reached,
$0.465 for the run killed at step 19 because the row that would have let it be killed at step 1
did not exist yet, and $0.757 for the retry the drill was testing. Every other piece of T6.7 is
$0 by construction, so the task ends at $1.85 against $1.00. **The ceiling is not raised**; it was
exceeded, here is where, and the design note carries this as an amendment rather than a new
number. Two of the three overruns were tooling mistakes that a rehearsal against the development
platform would have caught for nothing; the third is the finding.

## Addendum, 2026-09-19 23:48 UTC — the deployment closed the row itself

`a07344d6` (piece 3b and after) rolled out at 23:47. The new orchestrator's first poll:

```
23:48:12 WARNING faultline.orchestrator.runner  orphaned 1 trajectory row(s) from killed investigations: 7d230673-515a-47c4-aa4b-c2d157646f15
7d230673  orphaned
ce5d223d  dispatched
```

Nobody ran `faultline-eval-db orphans` after 22:47; the runner did it on its first look, seventy
minutes after the kill and fifty after the ceiling, which is the gap between *reconciled by the
sweep the deployment never runs* and *reconciled by the process that did the killing*.

One more thing the rollout found, on the same read: the orchestrator's `spend ceiling: $5.00 per
rolling 24h` and `investigating what this process admits …` lines were not in the log, and never
had been on any deployment - they are `print`s to stdout, which a container block-buffers without
a tty, while the JSON lines on stderr always arrived. `PYTHONUNBUFFERED=1` on the three daemons
(`deploy/compose.yml`, a guard in `tests/test_deploy.py`). T6.6's *"prints stay on stdout because a
person is reading those"* assumed a person at a terminal; on the deployment the person reads the
log, and the log now gets them.
