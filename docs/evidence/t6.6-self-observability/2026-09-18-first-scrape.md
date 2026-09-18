# The first scrape — 2026-09-18

**`/metrics` mounted on the development read surface** — `faultline-ingest --port 8001`, restarted
onto #360 — and scraped once by hand. **$0.00.** Nothing ran; the surface reads what the
trajectory tables already held.

```
metrics: /metrics mounted
```

## What one scrape said

| series | value |
|---|---|
| `faultline_incidents_queued` | 0 |
| `faultline_investigations_active` | 0 |
| `faultline_investigations_total{outcome="dispatched"}` | 284 |
| `…{outcome="baseline"}` | 32 |
| `…{outcome="budget_exhausted"}` | 16 |
| `…{outcome="failed"}` | 9 |
| `…{outcome="running"}` | **4** |
| `…{outcome="smoke"}` / `…{outcome="stage1"}` | 1 / 1 |
| `faultline_investigation_seconds_count` | 343 |
| `faultline_investigation_seconds_sum` | 78,027 s |
| `faultline_investigation_seconds_bucket{le="900"}` / `{le="+Inf"}` | 342 / **343** |
| `faultline_model_tokens_total{direction="in"}` | 16,836,290 |
| `faultline_model_tokens_total{direction="out"}` | 4,341,157 |
| `faultline_model_usd_total` | **$192.71** |

These are lifetime figures for the development database — every trajectory since the table
existed, not a T6.5 number. T6.5 alone was $44.79 over sixty scored runs.

## Three things the first scrape found

**Four investigations that read as running, in a process where nothing is running.** The gauge
comes from the incident store in memory and says 0, which is true. The `running` label is
`COALESCE(outcome, 'running')` over `trajectories` and says 4: rows that started and never wrote
an outcome. Those are the killed-sweep orphans Q71 (b) describes from the other side — kill a
sweep mid-investigation and the fault stays injected *and* the trajectory row stays open. Nothing
reconciles them. The metric is right to disagree with the gauge; the disagreement is the finding.
**Q72.**

**One investigation ever ran longer than fifteen minutes.** `+Inf` holds 343 and the 900 s bucket
342. The mean is 227 s, and 270 of 343 fall in the 180–300 s buckets — the histogram's edges
were chosen for a minutes-long instrument and the distribution sits where they resolve it.

**`outcome` is doing double duty.** `baseline`, `smoke` and `stage1` appear as outcomes because
`agents/cli.py` writes `trajectory.outcome = "baseline"` for baseline runs; the column names the
*kind* of run for anything that was not an agent investigation. The metric reports the column
faithfully. Noted, not fixed: a dashboard panel over `outcome` should know that three of its
labels are not outcomes.

## One thing learned getting here

**The read surface refused to start.** The process being replaced had `FAULTLINE_API_PASSWORD` in
its environment; the shell relaunching it did not, and `read_surface` refused rather than serve
the incident log unauthenticated — as designed. The relaunch reads the password out of its file
into that one process's environment. Worth carrying into piece 5: the scraper never needs that
credential, because `/metrics` sits outside it on purpose.
