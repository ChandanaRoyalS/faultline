# T4.12 evidence — the re-issue analyser and the S3/S4 comparison

Two read-only scripts. Neither calls a model, injects anything, or writes to the store; both read
the run manifests in `evals/runs/` and the stored trajectories in Postgres.

They are kept because the instruction they measured was **rejected** — the finding survives the
stamp, and the next formulation (PLAN.md) needs the same instruments to be comparable to this one.

## `reissue.py` — the registered primary endpoint

T4.12's pre-registration made the primary endpoint behavioural rather than coverage: *no run
re-issues a question to a stream that returned empty in a prior round.* Coverage is one draw from
a spread T4.10 measured at 2.6×; the re-issue count reads the behaviour an instruction about
silence actually names.

A **re-issue** is a tool call to the same `(tool, service)` pair as an earlier call in the same
trajectory whose envelope carried `empty="true"`. The window of each call is reported alongside,
so a materially-changed re-ask can be told from a bare repeat — all four re-issues found in S3 and
both survivors in S4 were same-window.

```
uv run python docs/evidence/t4.12-evidence/reissue.py 'evals/runs/2026*/manifest.json'
```

Measured: **S3 four re-issues across three runs; S4 two across two.** On the targeted scenario,
`product-catalog-flag-failure`, 2 → 0.

## `s4compare.py` — S3 against S4 on every registered endpoint

Emits the per-scenario table in `evals/runs/SWEEP-2026-08-27-evidence.md`, plus the column that
turned out to explain the result: **dispatches at the service whose failure is the fault.** That
mapping is hard-coded in `TARGET` because it is ground truth about each scenario, not something to
infer from a trajectory that may have localized wrongly.

```
uv run python docs/evidence/t4.12-evidence/s4compare.py /tmp/s4.json
```

Measured: every regression was a target-dispatch collapse (3→0, 4→1, 3→0) and no scenario whose
target dispatches held regressed.

## What these scripts do not do

They read one run per scenario per sweep. Nothing here produces an interval, and n = 1 per
scenario is the honest denominator for every number they emit — except where a prior byte-identical
observation exists, which is a fact about the archive rather than about these scripts.
