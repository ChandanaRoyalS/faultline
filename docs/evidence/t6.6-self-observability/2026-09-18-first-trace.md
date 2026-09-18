# The first trace — 2026-09-18

**Trace `e420efea2fe46357cc202aaf0a53802e`**, from a `--demo` run of `cart-dependency-latency`
launched with `OTEL_EXPORTER_OTLP_ENDPOINT` pointed at the world's collector on its published
host port. Excluded from every aggregate by `counts_toward_aggregates`, as a demo run is.
**$0.70.**

![The trace in Grafana Explore](2026-09-18-first-trace.png)

## What Tempo holds

| | |
|---|---|
| spans | **33** |
| root spans | **1** — `investigation`, 4m 21s |
| `model.call` | 10 |
| `tool.call` | 5 |
| `backend.get` | 17 |
| depth | 3 |
| services | 1 — `faultline`, `faultline.component = investigator` |

Read back through Tempo's HTTP API and rendered in Grafana against the provisioned `tempo`
datasource. One root means `tracing.propagate` did what it exists for: the specialist workers'
spans are children of the investigation rather than five fragments.

## What Postgres holds, joined

Trajectory `8ca5aa20…`, `trace_id = e420efea…`. **All 18 steps carry a span id.** The 7
completion steps map to 7 distinct spans and the 5 tool-call steps to 5 — the precise joins —
while message, retrieval, proposal and verdict share the root span, which is the coarse join
`Trajectory.add` provides. **7 of 7 completion steps carry non-zero latency, the slowest
33,088 ms** — the first model-call durations ever recorded in a trajectory.

## What the waterfall says that the trajectory could not

**The wall-clock is the model, not the world.** Every `model.call` is 14–19 seconds. Every
`tool.call` is single-digit to low-hundreds of milliseconds, with its `backend.get` children in
single-digit milliseconds beneath it. The four specialist `model.call` bars overlap at the
five-second mark — `_fan_out`'s thread pool, visible for the first time — and the investigation's
four minutes are almost entirely the agent waiting on its own model calls.

That is a statement about where the latency budget goes, and nothing before this could make it:
the trajectory recorded tool-call latency and zero for every model call.

## Two things learned getting here

**`configure()` existed and nothing called it** — piece 2 forgot the entry points, and no test
could see it because a library that is inert until its process opts in is exactly the shape
`make check` cannot exercise. Piece 2b.

**Grafana asks Tempo with the time picker's range attached.** A `curl` to `/api/traces/{id}`
found the trace; Grafana's TraceID query said *404 trace not found* until the range was widened
past the run's start. Worth knowing before the dashboard's trace panel is built.

## Addendum, 2026-09-18 — the sentence about 14–19 seconds is wrong at the tail

Written the same day, after the trace was opened in Grafana's Trace View rather than read back
as a span list. **"Every `model.call` is 14–19 seconds" describes the first six calls and not the
last four.** The waterfall reads, in order: 14.49s, 18.39s, 15.92s, 19.16s, 17.51s, 14.93s — then
**33.09s, 1m 3s, 1m 9s, 39.16s.** The planner and the four specialists are the short calls; the
synthesis end of the run — the synthesizer, the proposer, the verdict — is the long one, and the
two calls over a minute are about half of the investigation's 4m 21s between them.

The conclusion the sentence was supporting stands and is stronger for the correction: the wall
clock is the model, and it is the *last* model calls most of all. What the trajectory's
`latency_ms` column now records for every completion step is exactly this shape, and it was
readable in the span list too — the sentence was written from the overlap at the five-second
mark and generalised. Kept above as written; corrected here.

## Addendum 2, 2026-09-18 — the run made two traces, and search lost one of them for a while

**"One root means `tracing.propagate` did what it exists for"** is true of trace `e420efea…`
and blind to the run around it. Tempo's search for `resource.service.name = "faultline"` over the
last 48 hours returns **two** traces from the one `--demo` run:

| trace | root | start | duration |
|---|---|---|---|
| `e420efea2fe46357cc202aaf0a53802e` | `investigation` | 05:27:03Z | 4m 21s |
| `ea12a29e3ec5983c64a8f5aa6a8452e9` | **`model.call`** | 05:26:59Z | **4.3s** |

The second is the **triage judgement**. `run_investigation` asks the triager whether to
investigate at all *before* `Investigation.run` opens its root, so triage's model call had no
parent and became a trace of its own - four seconds long, four seconds earlier, and absent from
the waterfall the note above describes. Triage is part of the run, and a run triage declines
used to leave no trace but that orphan. **Fixed the same day**: the runner opens an `incident`
span before the judgement and closes it after the state write-back; `investigation` is its
child; a live-SDK test asserts every span of a run shares one trace id and exactly one has no
parent. The trajectory's `trace_id` is unchanged by this - it names the trace, not the root.

**Search also disagreed with itself.** At 07:03Z, with the trace 1h 42m old and `GET
/api/traces/{id}` returning 200, a search over the last two days returned nothing with one job,
while a twenty-minute window around the run found it, and half an hour later every window from
two hours to forty-eight found both traces with a job count that scaled with the window. Not
reproduced since. The likeliest shape is the querier's block list lagging the backend - the
same family as Q31's *"blind to the last five minutes"*, though this lasted longer - and it is
recorded as an observation rather than a queue row, because a search that recovered with no
change is not yet something anyone can act on. The dashboard's Tempo panel says so in its
description; the trace-id link on the incident page does not depend on search.

## Addendum 3, 2026-09-18 — addendum 2's search anomaly, reproduced with its mechanism

*"Not reproduced since"* lasted until the afternoon. The first `action.execute` span on the VM was
absent from Tempo search for twenty minutes and answered 404 by id at 12:37, then 200 at 12:42
with nothing changed, while Jaeger served it throughout. The cause is in `compose/tempo.yaml`:
`max_block_duration: 30s` and `complete_block_timeout: 2m` (T6.1, so the trace tool sees an
incident quickly) push a trace out of the ingester ~2.5 minutes after arrival, after which only
the tenant's block index reaches it - rewritten every ten minutes, and failing whenever the
compactor has just removed a block. This morning's two-day search that found nothing and the
twenty-minute window that did are the same thing: the window covered the ingester, the wider
search depended on an index that had not caught up. Full account and the probes that ruled out
everything else: *the first action on the deployment*. Queue row Q76.
