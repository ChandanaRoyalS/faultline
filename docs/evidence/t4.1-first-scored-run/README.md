# T4.1 live smoke — the first scored run

One dev scenario through the harness end to end, as one command. `cart-redis-misconfig` was
chosen because T3.3 investigated it before the synthesizer existed, so there is prior evidence
to read the run against and the scored report is checkable by eye.

    $ faultline-eval cart-redis-misconfig

Files here: `transcript.txt` is the run as it printed, assembled from the run directory's own
artifacts; `report.txt` is the scored report verbatim; `manifest.json` is the full run record;
`investigate.txt` and `narrative.md` are what the investigation produced. The live run directory
is `evals/runs/20260826T043356Z-cart-redis-misconfig/`.

## The protocol, as it ran

| step | |
|---|---|
| run id | `20260826T043356Z-cart-redis-misconfig` |
| baseline gate | **passed** — 15 services reporting, 0 alerts, `frontend-proxy` silent as expected, no open incidents, no active injections |
| injected | 04:33:57Z |
| incident | `cae7e558-dc95-413f-b7ee-f0ae88173022` |
| investigated | `faultline-investigate` as a subprocess, exit **0** |
| reverted | 04:42:15Z |
| recovery | **confirmed** — the same gate, re-read, passed |
| finished | 04:47:18Z |
| trajectory | `07991318-2c68-4333-bf99-a42e6d839e50` |
| tokens / cost | in 26,502 / out 12,243 — **$0.4386** |

Total wall clock 13m21s, of which the investigation was about 5 minutes and the rest is the
world: correlation, the settle wait, and recovery.

## The scored report

```
TRIAGE (blast radius vs alerts_over_window)
  recall    0.78  (7/9 alerted services predicted)
  precision 0.58  (7/12 predicted services alerted)
  missed (alerted, not predicted): frauddetectionservice, quoteservice
  extra  (predicted, not alerted): adservice, emailservice, paymentservice,
                                   productcatalogservice, recommendationservice
  unmeasured edges crossed: 4
  excluded as recovery-phase (began_after_revert): emailservice

VERDICT
  fault class unknown vs bad_config - ABSTAINED (excluded from accuracy; counted in coverage)
  fix class   none vs config_revert - ABSTAINED
  coverage: abstained

REPORTED SEPARATELY (never averaged into the above)
  flagged verdicts        0
  specialists failed alone 0
  contradiction firings   0
  budget exhausted        no
```

### ADR-0017's number exists now, and it is not zero

> "A directed 2-hop traversal that under-reaches shows up there as a recall miss on services
> that alerted and were not predicted. **That is the number to look at, and it does not exist
> yet.**" — ADR-0017

It exists: **recall 0.78, two misses — `frauddetectionservice` and `quoteservice`.** Both
alerted in the recorded bundle and neither was in the predicted radius.

This is one observation on one scenario and it settles nothing on its own. What it does is turn
a hypothesis ADR-0017 could only state into a measurement the harness now produces on every run.
If the pattern holds across the ten scoreable scenarios, ADR-0017 already names the fix: "a
radius derived from directed coverage rather than inherited from undirected coverage".

Precision 0.58 is reported beside it and **not combined with it**. Five predicted services did
not alert. Whether that is over-reach or a blast radius correctly describing where to look is a
different question from whether the traversal reached far enough, and an F-score would blur them.

`emailservice` was excluded from both sides: its alert `began_after_revert`, and ADR-0009 is
explicit that scoring it in would blame the fault for damage the fix did.

### The verdict abstained, and the scorer handled it as designed

`unknown` / `none` against `bad_config` / `config_revert`. Under ADR-0022 §1.2 that is an
**abstention, not an error**: excluded from accuracy, reported as coverage. The run contributes
`reached_a_class: false` and contributes nothing to a fault-class rate.

The verdict says plainly why, and it is worth reading:

> "Not established. … that pattern — a partial error ratio well below 1.0, with the caller
> silent about the failure in its own logs — is characteristic of a caller propagating a
> downstream failure … **But the three dispatches that would have identified the downstream
> culprit all returned no usable data for non-substantive reasons**: the trace query failed with
> a backend 500 (`tr_d7c5f0e96cd3`), the dependency error-ratio query used a prose string as an
> exact-match `service_name` selector and therefore could not match…"

Two causes, and only one of them is the agent's:

1. **A Jaeger 500.** An infrastructure failure inside the run. The tool layer returned it as an
   error rather than an empty result — which is ADR-0019's empty-vs-error distinction earning
   its keep — and the specialist reported it as a failed query rather than as evidence of
   nothing.
2. **The comma-list dispatch defect, recurring.** A `service` field carrying prose, producing a
   PromQL selector that cannot match. **This is exactly the defect T3.4c fixed, and T3.4c
   (PR #28) is not merged to `main`, which this branch is off.** One-service-per-dispatch
   validation would have refused that dispatch and re-asked. The first scored run in the
   project's history was degraded by a fix sitting in an open PR, and that is worth saying
   plainly rather than filing as bad luck.

The agent declined to name a culprit on evidence that had not arrived. That is the behaviour the
abstention rule exists to score correctly, and this run is the first demonstration that it does.

## `runtime_version`, and what the stamp is derived from

Every trajectory ever written said **`t3.3`**, including T3.5's, three tasks later. It now says:

    faultline/0.0.1+prompts:69aa6c670318

Two components, and each is there for a reason:

- **`faultline/0.0.1`** — the distribution version.
- **`prompts:69aa6c670318`** — a sha256 prefix over *every role system prompt* and *the JSON
  schema of every contract those prompts promise the model*, serialised with sorted keys so a
  reordering of the module does not move it.

Those two are what determines what a run *is*. Change a prompt and it is a different agent;
change a contract and it is answering a different question. A literal string cannot notice
either, which is how the old one went three tasks stale while looking maintained.

**No git and no subprocess.** ADR-0004 keeps benchmark infrastructure out of the product, and a
product that shells out to `git` to describe itself does not work from a wheel. The git sha is
recorded separately by the harness, in the run manifest, where it already belonged:

    "recorder": {"tool": "evalharness.run",
                 "git_sha": "15e5d4ee006dc9ed74fcf348cbe2bbac392d42a6", "git_dirty": true}

A run is identified by both, from the side that can legitimately know each.

## The `DecisionLog` column, and what it immediately showed

ADR-0017 deferred the schema change to "whoever builds that reporting". It landed as `join_rule`
on **`incident_episodes`**, not on `incidents`: a join is a decision about an episode, and an
incident accumulates several. The first episode of an incident carries `no_candidate`, which is
a decision too.

Across the database now:

| rule | rows |
|---|---|
| `time_overlap` | 20 |
| `no_candidate` | 2 |
| `graph` | **0** |
| (null — written before this column) | 28 |

**That is ADR-0017's exposure, made visible on the first day the column existed.** Its words:
"how often did the graph actually decide, and how often did this quietly become time overlap
again". The answer is *never* and *always* — the deployed policy is `TimeOverlapPolicy` and
`DependencyPolicy` is not wired into the running orchestrator. Nothing about that is new; what
is new is that a person reading the database can see it.

## A gap the design has, found by breaking it

The first attempt at this run was killed by the shell's ten-minute tool timeout, ten minutes
into the protocol. It left `evals/runs/20260826T041920Z-cart-redis-misconfig/` holding the
artifacts of every completed step — and **no `manifest.json` and no `DISCARDED.md`**.

The discard rule holds for every failure the process can observe: the run directory is created
before the gate is read, and `RunError`, a gate refusal and a subprocess timeout all write their
reason into it. A `SIGKILL` runs no `except` and no `finally`, so it writes nothing.

**A directory with no `manifest.json` is an incomplete run**, and any later aggregation has to
treat it as one. That directory now holds a `DISCARDED.md` written by hand, which says so and
says it was written by hand.

## Housekeeping

Baseline gate passed before injection and again after revert — the same checks, so recovery
means what quiet meant. World clean at 04:48:07Z: no active injections, incident `cae7e558`
resolved with its investigation id intact. Ingest and orchestrator stopped.

`make check`: 354 passed, 1 skipped.

---

# The second run — attempted, discarded, and what that showed

The first scored run above **stands exactly as recorded**, degradation and all. This section is
added beside it, not over it.

After PR #27 (T3.4b) merged to `main` and T3.4c was cherry-picked onto this branch, the pipeline
finally held both fixes the first run was missing. A second run of the same scenario was started
to measure the difference.

**It did not produce a scored report.** The investigation failed on its first model call:

    FAILED MID-INVESTIGATION: did not start - BadRequestError: Error code: 400 -
    'Your credit balance is too low to access the Anthropic API.'

Run id `20260826T045545Z-cart-redis-misconfig`, kept in `evals/runs/` with its `DISCARDED.md`.
`second-attempt-manifest.json` here is its manifest.

## What the harness did with it, which is the point worth keeping

| step | |
|---|---|
| baseline gate | **passed** — 15 services reporting, 0 alerts |
| injected | 04:55:45Z |
| incident | `82dc019b-ee6f-4138-b8e0-c3ed33dfc669`, 2 episodes |
| investigate | exit **4**, no verdict artifact |
| reverted | 05:00:18Z — from the `finally`, so the revert ran despite the failure |
| recovery | **confirmed** |
| discarded | recorded, with the reason, in `DISCARDED.md` |

Three behaviours built earlier in this task and in T3.5 were exercised by an external failure
nobody arranged:

1. **The failed-start rule held.** The CLI reported `did not start`, no trajectory was
   persisted, and the incident stayed in `triaging` rather than moving to the terminal `FAILED`.
   That distinction was added at T3.5 after a `ModuleNotFoundError` permanently retired a live
   incident; this is the first time it has protected one in the wild. Incident `82dc019b`
   resolved normally when its alerts cleared.
2. **The revert ran anyway**, because it is in a `finally`. The world was clean at 05:06:19Z:
   no active injections, no firing alerts, no open incidents.
3. **The run was recorded, not deleted.** `evals/runs/` now holds three directories for this
   scenario — one scored, two discarded, each saying why. That is the honest count.

It also exercised the exit-code contract end to end: `faultline-investigate` returned **4** (no
verdict, trajectory persisted up to the failure), and `faultline-eval` turned that into its own
**4** (run discarded) rather than a zero that would have entered an aggregate.

## What changed between the two runs, measured without a second run

The one comparison that does not need a model call is the stamp, and it is exactly what the
stamp is for:

| | run 1 (`20260826T043356Z`) | run 2 (`20260826T045545Z`) |
|---|---|---|
| `runtime_version` | `faultline/0.0.1+prompts:69aa6c670318` | `faultline/0.0.1+prompts:59bf438b2a96` |

**The digest moved because the code the model is held to moved.** T3.4c changed the `Dispatch`
contract — `service` is now validated against the service catalog, and the class's own
documentation of that rule becomes the `description` in `model_json_schema()`. A literal version
string would have said the same thing for both runs; this one says they are not the same
experiment, which is the whole reason it was derived rather than typed.

**No scored comparison is available yet, and none is claimed.** What the first run's two causes
of abstention would look like under the complete pipeline is unmeasured:

- the **comma-list dispatch defect** is now refused at plan-parse time with a bounded re-ask
  (T3.4c, pinned by seven tests in `tests/test_roles.py`), so the specific failure the first run
  hit cannot recur in the same form;
- the **Jaeger 500** was infrastructure and nothing in this branch addresses it.

Whether that changes the verdict from `unknown` to a class is the question the re-run exists to
answer, and it stays open until the API account has credit.
