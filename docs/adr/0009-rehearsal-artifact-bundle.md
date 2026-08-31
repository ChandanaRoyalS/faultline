# ADR-0009: One recorded bundle per rehearsal, with the narrative written blind

- **Status:** accepted
- **Date:** 2026-08-23

## Context

T1.5 rehearses ten scenarios by hand. Each rehearsal produces evidence, and that evidence
has two consumers that pull in opposite directions.

T2.4b seeds the past-incident store from these rehearsals, so part of the output must be
prose an agent can retrieve and reason over. T4.2 scores runs against them, and T5.3
records a demo from them, so another part must be raw, timestamped, re-queryable data.

Left unspecified, ten hand-run rehearsals produce ten differently-shaped piles — some with
screenshots, some with pasted terminal output, some with nothing but memory. Building a
retrieval corpus out of that later means redoing the rehearsals, and rehearsals are the
most expensive manual step in the whole plan.

There is also a subtler failure available. Because we inject the faults, every narrative is
written by someone who already knows the answer. A write-up that opens with the root cause
is not an incident report; it is an answer key. Seeded into retrieval, it teaches the agent
to look up rather than diagnose — and the leak is invisible in the scores, because the
scores go up.

## Decision

One bundle per rehearsal, at `evals/scenarios/artifacts/<split>/<id>/`, with a fixed
shape: `manifest.json`, `incident.md`, `queries.md`, `metrics/*.json`, `logs/*.txt`. The
format is specified in `evals/scenarios/ARTIFACTS.md`.

Everything mechanical is recorded by `evalharness.rehearse`, which drives the injector
through its CLI, polls Prometheus for the alert transition, holds a steady-state window,
reverts, and captures the metric range. Using the CLI rather than the injector's internals
is deliberate: T4.1's harness is specified to work through public interfaces only, and this
recorder is its ancestor.

`incident.md` is hand-written, under two rules that the format enforces socially and the
tests enforce mechanically where they can:

1. **Written from the responder's chair.** Observed symptoms first; root cause only in its
   own section, at the end. No mention of the injector, the scenario id, or the fault class
   anywhere in the prose.
2. **Dead ends preserved.** The checks that led nowhere stay in the document. They are what
   makes a retrieved incident read as experience rather than as a solution manual.

`rehearsed: true` in a scenario YAML is a claim that a complete bundle exists. The guard
tests treat it as one: a rehearsed scenario must have a bundle, and its `incident.md` must
have no template comments left unfilled.

## Consequences

Easier: the corpus at T2.4b is assembled rather than authored, every accuracy claim traces
back to a re-runnable query, and the demo at T5.3 has real captured incidents to draw on.
The recorder also removes the two mistakes hand-running invites — forgetting to note the
inject timestamp, and reverting before the metric window is long enough to be readable.

Harder: rehearsal is now a fifteen-minute commitment per scenario rather than a five-minute
one, and the narrative discipline is genuinely difficult — writing blind about a fault you
designed takes real effort, and there is no test that can prove you did it honestly.

Accepted risk: rule 1 is unenforceable by machine. A narrative that leaks the answer in its
opening paragraph passes every test. The mitigation is that the leak is visible on reading,
and the bundles are in the repo where a reviewer — or an interviewer — can check.

## Measured on the first live rehearsals (2026-08-23, T1.5)

Three runs of `cart-redis-misconfig` against the live world, which produced four changes to
the recorder and the numbers below. All of it came from rehearsing one scenario; the other
nine are unrehearsed and may move these figures.

### Settle time: 2.5–6.5 minutes from revert to all-clear

| Run | Reverted | All clear | Settle |
|---|---|---|---|
| 1 | 05:27:30 | 05:30:00 | 2.5 min |
| 2 | 05:57:00 | 06:03:30 | 6.5 min |
| 3 | 06:11:37 | 06:15:30 | 3.9 min |

**The floor is the rate window, not the `for` clause.** `ServiceHighErrorRate` reads
`rate(calls_total[2m])`, so errors from before the revert stay in scope for two more
minutes; add the 15s evaluation interval and ~2.5 minutes is the best case. Run 1 hit
almost exactly that. The `for: 2m` guard delays firing, not resolution, and contributes
nothing here.

**The variable part is a second error wave from the revert itself.** Reverting recreates
the container, and cartservice crash-loops on `EnsureRedisConnected` while it comes back —
the captured logs show restarts 42 and 47 seconds apart. Callers keep erroring through
that, refilling the rate window. That is the difference between run 1's 2.5 minutes and
run 2's 6.5.

**Series staleness is not a factor**, which is worth stating because it was the obvious
suspect. `ServiceNoTraffic` cleared within 0–14 seconds of the revert in all three runs.

An earlier reading of "15+ minutes" was wrong: it came from reading Prometheus's `activeAt`
as the start of the post-revert tail, when it is the moment the alert *condition* first
became true — during the fault. Recorded because the mistake is easy to repeat.

### Practical cycle time: ~20 minutes per scenario

Inject to first alert ~3 min, dwell 5 min after the alert, settle 3–7 min, plus capture.
Nine remaining scenarios is roughly three hours of wall clock, and they cannot be
parallelised: they share one world. `--baseline-timeout` defaults to 300s, comfortably
above the worst settle observed.

### Alert sets grow, so the manifest records both shapes

Run 3 paged on 2 services and reached 10 over the following six minutes, the second wave
being seven `ServiceNoTraffic` alerts that fired once cart stopped serving entirely. A
manifest holding only the page-time snapshot understates that incident fivefold.

`alerts_at_fire` is kept as-is — it is what the responder actually had, and a narrative
written from anything more is written from hindsight. `alerts_over_window` is added
alongside it, derived from the captured `alerts-firing.json` rather than from extra
polling, each entry carrying first-seen and last-seen. The `incident.md` template renders
the two together and marks which alerts were on the page, because blast radius is what
T3.1 scores triage on and it is invisible in the snapshot.

### The window extends past the revert, so every bundle contains recovery signal

The capture window runs from five minutes before injection to two minutes after the alerts
clear. The tail is deliberate: a bundle has to show the world returning to baseline, or
there is no evidence the fault was actually reverted and no way to tell a fixed incident
from one that merely stopped alerting.

The cost is that **every bundle contains alerts that have nothing to do with the fault.**
Reverting recreates a container, and a recreate has its own failure modes. Measured in the
`cart-redis-misconfig` bundle: emailservice held a 0% error ratio through the entire
incident, then went to 100% for about 75 seconds starting 28 seconds after `t_revert`,
decaying back over the following two minutes as the rate window emptied. Nothing about that
is the misconfigured Redis address. It is what happened when cartservice was recreated and
its callers retried into a service that was still starting.

That signal is worth keeping — it is real, it is reproducible, and an operator reverting
this fault in production would see it. But it is **signal about the recreate, not about the
fault**, and the two must not be summed. A narrative that reports emailservice as part of
the blast radius blames the fault for damage the fix did, and T3.1 scores triage on blast
radius.

Each `alerts_over_window` entry therefore carries `began_after_revert`, set from its
`first_seen` against `t_revert`, and the `incident.md` template lists recovery-phase alerts
under their own heading rather than mixed into the incident table. The flag is *omitted*
rather than set false when there is no revert to compare against — a baseline capture has
none, and false would assert something the data cannot support.

An alert that began during the fault and continued past the revert is incident signal and
is not flagged. Only episodes that started after the fault was already gone are.

### A stale or empty artifact is worse than a missing one

Four defects reached a recorded bundle during the first rehearsals. Every one of them was
present, well-formed, and wrong:

| Artifact | What it said | What was true |
|---|---|---|
| `logs/cartservice.txt` | "no lines matched - widen the selector" | the label did not exist; the selector was built wrong |
| `manifest.alerts_at_fire` | 2 services alerting | 11 alerted over the incident |
| `logs/cartservice.txt` again | sat beside the correct capture after a re-record | `--force` merged instead of replacing |
| `manifest.seconds_to_alert` | 165s | its own timestamps said 166s |

The pattern is that **a wrong artifact reads as a finding about the world rather than as a
defect in the tool.** "No lines matched" looks like a quiet service. Two alerts looks like
a small incident. Neither invites suspicion, and both were believed - the empty log capture
was reported as evidence that a promtail filter was suppressing logs, which cost an
investigation and a wrong conclusion before measurement corrected it.

Missing artifacts do not have this property. A bundle with no `logs/` directory is
obviously incomplete and nobody reasons from it.

**Presence guards cannot catch this class; consistency guards can.** The bundle tests
therefore check the pieces against *each other*, not against a schema:

- `alerts_over_window` must equal what re-deriving it from `metrics/alerts-firing.json`
  produces. A manifest that disagrees with its own evidence fails.
- `seconds_to_alert` must equal `t_alert_firing - t_inject`. This one caught a real
  one-second disagreement caused by stamping whole seconds while computing durations from
  full-precision datetimes; `now()` was changed to truncate at the source rather than
  tolerating slack in the check.
- The declared window must contain every sample in every metric capture.
- Exactly one log file, named for the container `SERVICE_CONTAINERS` maps the target to.
  Two files means a re-record left something behind; a differently-named one means the
  selector was built from the compose service name.
- No metric capture may be silently empty.

**Where a guard cannot tell a quiet world from a failed capture, it says so.** An empty
`alerts-firing.json` is legitimate when a fault fired nothing, so that check consults the
manifest to disambiguate and only fails when the manifest claims alerts fired. The other
metric files have no such disambiguator, so their failure message states plainly that the
result is ambiguous and names what to compare against. An ambiguous guard phrased as a
certainty is the same defect one level up: a tool output that reads as a finding.

## The manifest schema is frozen at version 1 (2026-08-23, before the batch)

Three schema changes during the first scenario's rehearsal cost one re-record each, which
was cheap. The same change after ten bundles costs three hours of held world, because the
consistency guards compare bundles against each other and will correctly refuse a catalog
recorded by two different recorders. So the schema was settled deliberately before the
batch rather than discovered during it, by asking each downstream consumer what it needs.

| Consumer | Needs | Field |
|---|---|---|
| T2.4b corpus seeding | dev-only quarantine, provenance stamp | `split`, `origin` |
| T4.1 harness runner | what to inject; how long to wait; how long between runs | `injection`, `seconds_to_alert`, `seconds_of_steady_state`, `seconds_to_settle` |
| T4.1b self-exclusion | the origin to exclude, asserted to have fired | `origin` |
| T4.2 RCA + remediation scoring | the label this recording is evidence for | `scenario_fingerprint`, `expected_remediation_class`, `fault_class` |
| T5.3 demo | something human before reading the scenario file | `title`, `alerts_at_fire`, `alerts_over_window` |
| all of them | is this one measurement or several? | `bundle_schema_version`, `recorder`, `world` |

Added for this freeze: `bundle_schema_version`, `title`, `scenario_fingerprint`,
`seconds_to_settle`, `recorder` (tool, git SHA, dirty flag) and `world` (demo image, stub
image id, docker arch, host platform).

`recorder.git_dirty` is recorded rather than ignored. A bundle produced from uncommitted
work is reproducible only by whoever had that work, and the manifest should say so instead
of implying a SHA describes the code that ran.

`world` is read from the running containers, not from config files, so it records what
actually ran. A guard fails if two bundles disagree about it: the catalog's central claim
is ten scenarios measured under the same conditions, and without this there is nothing
behind that claim.

`scenario_fingerprint` hashes only the fields a bundle is evidence *for* - injection,
fault class, split, ground truth, remediation class. Titles, evidence lists and comments
are excluded deliberately: three evidence items were corrected the night the catalog was
authored, and rewording one does not make an existing recording wrong. Changing an
injection parameter does.

Deliberately **not** added: a checksum of `incident.md`. It is written by hand after the
recording, so the recorder cannot know it. T4.1 computes it at seed time, which is where
ADR-0008 puts that enforcement anyway. Nothing speculative is in the schema.

### What a bump costs, and what would justify one

Bumping `BUNDLE_SCHEMA_VERSION` obsoletes every bundle recorded before it. At ten scenarios
and ~20 minutes each that is roughly three hours of serial, un-parallelisable world time -
they share one world - plus re-reading every narrative for facts that moved.

**Worth paying for:** a field a downstream phase cannot work without and cannot derive from
what is already captured. If T4.1 needs a signal nobody thought of, the catalog is worth
less without it than the re-record costs.

**Not worth paying for:** anything derivable from the captured JSON. `alerts_over_window`
is derived from `alerts-firing.json` and could be recomputed for old bundles by a migration
rather than a re-record; so could any future summary of a captured series. Reach for a
migration first, and bump only when the *raw capture* is missing something.

**Also not worth paying for:** renames, reorderings, or anything cosmetic. A field with an
awkward name that works is cheaper than three hours.

If a bump does happen mid-batch, re-record everything rather than mixing versions. A
partially migrated catalog is the failure the guards exist to prevent, and a bundle that
looks current and is not is worse than one that announces itself as old.

Revisit if: T4.1's harness needs fields the manifest does not carry, or the corpus turns
out to want a different granularity than one document per incident (for example, one per
hypothesis rather than one per incident).

## Addendum (2026-08-31, T7.42): the recreate in a bundle is the config change, not the harness

**A reader of a `bad_config` or `bad_deploy` bundle will see the target container replaced once, near
onset. It is not an unexplained event and it does not need a second cause.**

`BadConfigFault` and `BadDeployFault` both apply through a generated compose override and a
recreate, because **an environment variable and an image cannot be changed on a running container** —
`docker update` carries resource limits only, and no service in this world re-reads its configuration
at runtime. So the replacement is the change taking effect.

**It is explicable from the evidence, by construction.** The injector writes a change record for
every injection, and `change_history` returns it with a timestamp and the old and new values:

```
2026-08-31T04:34:08  platform-automation  environment updated:
  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
  None  ->  http://127.0.0.1:4317
```

**Read it as one inference step, and a realistic one**: *config changed at T* → *container replaced
at T*. A real incident looks the same, because a real config change replaces the container too.

**Scope, measured (T7.42).** Seven of thirteen valid scenarios recreate; the three memory squeezes
(`docker update`, a live property) and the three latency scenarios (pumba sidecar) do not.

**And the apparatus signature is the quiet one.** Startup lines in captured target logs:
`frauddetection-memory-squeeze` **38** and `ad-memory-squeeze` **37** — both *non*-recreating, where
the fault restarts the container repeatedly — against **2–6** for the scenarios whose recreate is the
injector's. **The loudest restart evidence in this catalog belongs to faults, not to the harness.**

**Not changed, and why.** Switching to a mechanism that avoids the recreate would change what the
fault *is* (blackholing a collector address models a network fault, not a config one), and
`scenario_fingerprint` covers `injection`, so it would invalidate four recorded bundles. See
`docs/design/t7.42-injector-restart.md`.
