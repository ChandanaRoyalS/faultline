# Pre-registration — Q57, what the benchmark's own change log costs the agent

**Written and committed before any figure is produced.** $0.00: no model calls, no injections, no
world. Every number comes from manifests already on disk and two tables already in Postgres.

Q53's pilot found an agent building a confident, fully-cited and **false** root cause out of four
earlier runs' inject/revert cycles. This registers the measurement of how much that costs, and
fixes the decision rule before the answer exists.

---

## 1. What is already known, and therefore not predicted

**Observed before this registration was written, and listed so nothing below can be mistaken for a
prediction about it:**

- `change_records` holds **734 rows, 2026-08-25 → 2026-09-14**. It has never been cleared.
- **`cartservice` carried 14 change records in one 24-hour window** on 2026-09-14; seven services
  carried 28 between them. Sweep days are denser: 96 records across 10 services on 2026-09-09, 85
  on 09-10.
- **`change_history` is the most-called tool in the archive** — 590 calls against `logql_query` 356,
  `metric_baseline` 324, `promql_query` 308, `trace_query` 163 — across **270 trajectories**.
- The recorded `request` carries `service`, the exact `window`, `window_rule` and
  `lookback_seconds`, so no window has to be reconstructed.
- `injector.changelog` is the **only** writer. Every record in the log is a fault injection; there
  is no benign change traffic at all.

**The mechanism is not that the records are wrong.** They are real events and the agent reads them
correctly: it reported *"eight image-reference events ... after ~22 quiet hours"* and the table
says exactly that. The artifact is the **rate** — the harness injects every ~20 minutes, so a 24h
lookback that is right in production returns a whole session here — compounded by the fact that
**100% of the entries are faults**, which no production change log resembles.

## 2. The instrument

Built from pieces that already exist, because a second implementation of the harness is the
recurring defect this repository writes down:

- `evaldb.row_of` flattens each manifest to `scenario_id`, `trajectory_id`, `fault_class_correct`,
  `outcome` and `world_generation`. Only runs `outcome_of` calls scored are used.
- `trajectory_tool_calls` where `tool = 'change_history'` gives **the window the specialist actually
  asked for**, per call.
- For each investigation, over the union of its change queries:
  - **own** = records for that service inside `[injected_at, reverted_at]` — this run's fault.
  - **stale** = records for that service inside the queried window and **before `injected_at`**.
  - Counted as **distinct record ids**, so two queries covering one service do not double-count.

**Stale is defined by time, not by content.** A record is stale if it predates this run's own
injection, full stop. No parsing of summaries, no matching against a scenario catalog: those would
be judgement calls made by the instrument, and the point of the measurement is that the agent
cannot make them either.

## 3. The comparison

**Within-scenario, paired.** Scenario difficulty is the dominant term in this catalog — `variance.py`
is built on that and assumes `rho = 0.8` because of it — so a raw correlation between stale count
and accuracy would mostly measure which scenarios ran late in sweeps.

For each scenario with at least four scored investigations: split its runs at that scenario's own
median stale count, take `accuracy(low half) − accuracy(high half)`, and report the **mean paired
difference with a bootstrapped 95% CI**, seed fixed, using `variance.bootstrap_ci` rather than a
new one.

**Abstentions are excluded from accuracy and counted separately**, per ADR-0022 §1.2. An agent that
abstains under a noisy change log has not got it wrong, and folding that into an accuracy number
would hide the more interesting response.

## 4. The decision

**This instruments; it does not gate.** Q32's precedent, and the reason is the same: a refusal
threshold on a quantity nothing has measured is a number invented to look like a rule.

- **The CI excludes zero** → the penalty is real and is reported as a standing term beside every
  sweep figure in `RESULTS.md`, with its size.
- **The CI includes zero** → the density is still reported, as a measured property of the benchmark
  with an accuracy effect this catalog could not resolve. **That is a result, not a null.** A reader
  comparing a sweep's first scenario against its last is entitled to know the log differed by an
  order of magnitude between them, whether or not the accuracy moved.

**Nothing is cleared, nothing is filtered, no window is narrowed.** Those were the three alternatives
and all were declined: clearing makes *"nothing changed"* free, which five of nine rehearsed
investigations rest on as an observed-and-empty finding; filtering would have to exclude the live
fault's own record along with the stale ones; narrowing the lookback would exclude genuine pre-onset
causes, which is what the 24h window exists for.

## 5. Predictions

Registered against quantities **not yet looked at**. §1 lists what was.

1. **The median scored investigation sees more stale records than own records.** The run's own fault
   writes one record (two if the revert lands inside the window); a session puts many more in front
   of it.
2. **Fewer than one investigation in five sees zero stale records.** Those that do are the first
   run of a session or the first after a quiet day.
3. **Stale count rises with position within a sweep.** Mechanical, and registered as a check on the
   instrument rather than as a finding: if it does not hold, the instrument is wrong, not the world.
4. **Accuracy is lower in the high-stale half than the low-stale half**, mean paired difference
   above zero.
5. **The 95% CI includes zero.** Predicted *against* prediction 4 deliberately: 270 trajectories
   sounds like plenty, but they split across 18 scenarios, three arms and three world generations,
   and this catalog's MDE table puts 30 paired scenarios at 7.2pp. I expect a visible direction and
   an unresolvable size.
6. **Abstention rate is higher in the high-stale half.** If the noisy log does anything, declining to
   name a class is the response I expect before a wrong class.
7. **At least one scored investigation saw more than twenty stale records.** The pilot's own
   `cartservice` window held fourteen, and sweep days were three times denser.

## 6. What this cannot settle

- **Whether the residue caused any particular wrong answer.** Q53's pair 1 is an anecdote with a
  mechanism, not evidence of a rate, and it stays one.
- **Whether a production agent would do better.** No production change log was ever measured here;
  the claim is only that this one is unlike them in rate and in composition.
- **Whether benign change traffic would help.** That is the option this registration declined and it
  remains open behind this row.
- **Anything about holdout scenarios.** The archive is what it is; nothing is run for this.
