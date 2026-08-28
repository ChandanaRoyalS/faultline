# T7.3 — the blast radius counts alerts, not services

The defect T7.1 recorded rather than fixed, diagnosed, fixed, and every stored run re-scored.

## The diagnosis

`score_triage` partitioned alert entries correctly and then threw the partition away:

```python
alerted: set[str] = set()
after: set[str] = set()
for entry in alerts_over_window:
    service = entry.get("service")
    if not isinstance(service, str):
        continue
    (after if entry.get("began_after_revert") else alerted).add(service)
return TriageScore(
    predicted=frozenset(predicted),
    alerted=frozenset(alerted - after),
    excluded_after_revert=frozenset(after),
    ...
```

The loop reads the flag **per entry** — correctly, since `began_after_revert` is a property of one
alert episode. But it stores **service names**, so a service with two episodes lands in both sets,
and `alerted - after` then removes it from the blast radius **entirely**, including the alert the
fault itself caused.

**Why per-service was the natural mistake.** `TriageScore` compares a predicted blast radius to an
observed one, and both are sets of *service names* — `matched` is `predicted & alerted`. Once both
sides of the comparison are service sets, the exclusion looks like it must be a service set too.
The category error is that the projection from episodes to services has to happen **after** the
filter, not before. The fix is one line of ordering:

```python
(recovery if entry.get("began_after_revert") else during).add(service)
...
alerted=frozenset(during),
excluded_after_revert=frozenset(recovery - during),
```

`excluded_after_revert` now means what its name says: services whose alerts were **entirely**
post-revert. A service with one of each is not excluded and is not listed.

**Nothing else in the scorer makes this error.** `began_after_revert` appears in four places and
the other three are correct: `prom.py:225` sets it per entry; `bundle_render.py:148` reads it per
alert when rendering a timeline; `rehearse.py:653,701` filters entries with list comprehensions and
never projects to services. `TriageScore` is also the only consumer — it is constructed at
`run.py:346`, serialised under the `"triage"` key, and printed in the report, and nothing reads it
back.

## T7.1's account of this defect was wrong

T7.1 recorded that the bug was unreachable until its own re-record: *"every after-revert alert in
the catalog belonged to a service that alerted only after the revert… so the sets were disjoint and
the subtraction was harmless."*

**That is false, and the rescore is what falsified it.** `cart-redis-misconfig`'s *original*
recording has `emailservice` raising two episodes:

| | alert | began_after_revert |
|---|---|---|
| 04:50:27 | `ServiceNoTraffic` | **false** — the fault's own damage |
| 04:54:42 | `ServiceHighErrorRate` | **true** — recovery |

The same shape appears in `cart-bad-image-tag` and, with `frontend`, in `shipping-wrong-image`. The
overlap has existed since the earliest recordings; **24 of 55 stored runs are affected**, the
earliest from 2026-08-26. T7.1 generalised from a single test fixture losing its recovery alert to
a claim about the whole catalog and did not check it. The scorer's docstring now carries the
correction.

## What moved

24 of 55 scored runs. Every one moved in the same direction — a service was **restored** to the
blast radius, so `n_alerted` rose by one, recall rose or held, and precision rose.

| restored service | scenarios | runs |
|---|---|---|
| `emailservice` | `cart-redis-misconfig`, `cart-bad-image-tag` | 18 |
| `frontend` | `shipping-wrong-image` | 6 |

**No run moved in the other direction**, and none lost a service. That follows from the fix: the
old code could only ever remove a service the new code keeps.

## Per-table effect

Each run was re-scored against **the bundle recording current when it ran**, not the current one —
T7.1 re-recorded all twelve, and scoring an August 26th run against an August 28th capture would
mix this fix with that re-record and measure neither.

| table | n | runs moved | recall | precision |
|---|---:|---:|---|---|
| S1 (dev sweep 1) | 7 | 3 | 0.94 (unchanged) | 0.56 → **0.60** |
| S2 (dev sweep 2) | 7 | 3 | 0.95 (unchanged) | 0.57 → **0.60** |
| S3 (dev sweep 3) | 7 | 3 | 0.91 → **0.92** | 0.54 → **0.58** |
| S4 (dev sweep 4) | 7 | 3 | 0.92 (unchanged) | 0.56 → **0.59** |
| S5 (dev sweep 5) | 7 | 3 | 0.90 → **0.91** | 0.54 → **0.57** |
| T4.10 variance | 5 | **5** | 0.78 → **0.80** | 0.58 → **0.67** |
| T4.11 abstention variance | 4 | 0 | 1.00 (unchanged) | 0.38 (unchanged) |
| Holdout entry 1 | 3 | 0 | 1.00 (unchanged) | 0.32 (unchanged) |
| Holdout entry 2 | 1 | 0 | 1.00 (unchanged) | 0.11 (unchanged) |
| Holdout entry 3 | 3 | 0 | 1.00 (unchanged) | 0.32 (unchanged) |

**No holdout figure moves.** None of the three entries' scenarios has an overlapping service, so
every published holdout number stands exactly as measured. That is worth stating plainly, because
holdout is the only part of this repository that claims to be a benchmark.

**T4.10 is the table most affected** — all five repeats are `cart-redis-misconfig`, so every one
moved, and its precision rises most. Its finding is untouched: the experiment measured *variance*
across repeats, and all five moved by the same amount in the same direction, so the spread is
identical.

## Nothing about verdicts, coverage or fault classes changes

Stated from the code rather than from expectation. `TriageScore` is one field of `ScoredRun` and
nothing derives from it: `reached_a_class` — the coverage figure — reads `fault_class` only;
`fault_class`, `fix_class` and `categories` are computed by `score_label` and the budget/refusal
paths and never reference triage. The fix cannot move a coverage, accuracy, abstention, judge or
cost number, and the rescore confirms none moved.

## Reproducing

```
uv run python docs/evidence/t7.3-rescore/rescore.py
```

Read-only recomputation: no model calls, no live world, no injections. Per-run output is in
`rescore.json`; the aggregates above are in `tables.json`. **The stored manifests were not
rewritten** — a run manifest records what was computed at the time, and the corrected figures live
in the reports beside the originals rather than replacing them in the record.
