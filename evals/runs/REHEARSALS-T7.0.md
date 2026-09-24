# T7.0 #5 — the five classes rehearsed end to end, through the injector and the agent's tools

**Written before any rehearsal is run.** The plan's bar for T7.0 is *"same reversibility and
idempotence bar as T1.4; each new class rehearsed end-to-end before any scenario is authored
against it"*, and its deliverable is *"inject/restore verified"*. The attempts (A1–A8b) established
what each mechanism does to the world by hand. A rehearsal establishes that **the injector's code
does the same thing, that the injector's restore undoes it, and that what the attempt measured is
reachable by the agent's own tools** — not by `docker logs` or `curl`, which the agent does not have.

Nothing here is scored, nothing moves a stamp, and no scenario is authored. Cost \$0: no model call.

## The five, and what each must show

| id | class | pages as (from the attempt) | evidence the tools must return |
|---|---|---|---|
| `v2-product-catalog-flag-failure` | `feature_flag` | `ServiceHighErrorRate/frontend` ~6 min (A1) | (d) a `product-catalog` error span carrying the flag's message via `trace_query`; (b) `change_history` empty or unavailable, never a record |
| `v2-product-catalog-freeze` | `process_freeze` | `ServiceHighLatency/frontend` ~6:30, `ServiceNoTraffic/product-catalog` ~7:30, thirteen alerts (A2) | (c) `logql_query product-catalog` returns **nothing new** in the window; (d) no `product-catalog` spans; (a) the cascade |
| `v2-product-catalog-partition` | `network_partition` | as the freeze (A3) | (c) `logql_query product-catalog` returns the once-a-minute `failed to upload metrics` line — the one thing that separates it from the freeze |
| `v2-cart-store-corruption` | `datastore_corruption` | `ServiceHighErrorRate/checkout` ~4:45, `/frontend` ~6:15 (A4b) | (c) `logql_query cart` returns `Can't access cart storage … InvalidProtocolBufferException`; (d) error spans on `checkout` |
| `v2-kafka-disk-fill` | `disk_fill` | `ServiceHighLatency/checkout` ~6:30, `ServiceHighErrorRate/checkout` ~7:00, `ServiceNoTraffic` on both consumers (A8b) | (c) `logql_query kafka` returns `No space left on device` / `KafkaStorageException`; (a) the consumers silent |

## The protocol, identical for all five

Every command on the **Mac**, in `~/dev/faultline`, with `FAULTLINE_TOOLS_WORLD=v2` in front of
every `uv run` — that one variable is what points the injector, the capture and the tools at v2
(T7.0 #6). Terminal 1 runs the steps; the clocks are UTC.

1. **Pre-state.** `python3 evals/attempts/shape.py` — nothing firing; `uv run faultline-inject status`
   — `no active injections`. If anything is firing, wait for it to clear plus five minutes.
2. **Inject through the injector.** `date -u +%H:%M:%S; FAULTLINE_TOOLS_WORLD=v2 uv run faultline-inject start <id>`.
   The injector prints what it changed; that text is part of the record. **Then
   `uv run faultline-inject status`** must show the fault active with its revert described.
3. **Observe.** `python3 evals/attempts/watch.py 12`, then `python3 evals/attempts/shape.py <target>`.
4. **Read back through the tools**, for the culprit and for the service that paged:
   `FAULTLINE_TOOLS_WORLD=v2 uv run python -m evalharness.readback <service> <inject HH:MM> <now HH:MM> --errors`.
   What it prints is what the agent would be handed. A refusal or a backend error is recorded as
   such — it is a fact about the world, not a reason to reach for `curl`.
5. **Restore through the injector.** `date -u +%H:%M:%S; FAULTLINE_TOOLS_WORLD=v2 uv run faultline-inject stop <id>`,
   then `status` must say `no active injections`. **Then `stop` once more**: it must succeed
   and say `not active` — that is the idempotence half of T1.4's bar.
6. **Recover.** `python3 evals/attempts/watch.py 10`; every alert clear and the world quiet for the
   last five minutes, allowing the recovery each attempt measured (~6 min for the two hang
   classes, ~4 for the others).
7. **Record** the transcript verbatim under `evals/attempts/R<n>-<class>/transcript.txt` with a
   `RESULT.md` answering the four questions below and nothing else.

## What a rehearsal answers

- **INJECTS** — the injector's `start` produced the attempt's page shape (rule, services, timing
  within a couple of minutes). If it paged differently, that is recorded, not tuned.
- **VISIBLE** — the evidence in the table's last column came back through `evalharness.readback`, i.e.
  through `faultline.tools`. If the attempt's evidence is *not* reachable this way, the class's
  distinctness claim is weaker than its RESULT says and the RESULT gets an addendum.
- **RESTORES** — `stop` undid it, `status` is empty, a second `stop` is a no-op, and the world
  went quiet within the attempt's recovery time.
- **A SCENARIO MAY BE AUTHORED** — all three, or the reason not.

## What is fixed in advance about the two known gaps

**`change_history` will report unavailable, not empty.** The platform Postgres is not running on
the development Mac (its container has been exited for two days), so the tool returns an error
rather than a record. That is the honest answer ADR-0019 wants; the (b) claim for these classes
rests on the injector's `records_change = False`, which is tested, and on the attempts' observation
that nothing in the world records them. When the platform is up, (b) is re-read and this note
gets an addendum.

**Tempo starts empty.** It was recreated after Q91's bound landed, so `trace_query` sees only what
was emitted since. That is enough: every rehearsal's window is after it.

## Order

Least disruptive first, as the attempts ran: flag, freeze, partition, corruption, disk fill. The
disk fill is last because its restore may recreate kafka and restarts three consumers.

---

## Addendum 2026-09-24, after R2 — the pre-state has a fourth line, and a rehearsal on a split world gets a second run

R2 ran on a world whose rules could not see four services (Q95: since the 03:31 recreate their
traces had been reaching Tempo's receiver instead of the collector's, so they had no spanmetrics
series and nothing could page on them). The pre-state check above — nothing firing, no active
injection — was satisfied and was not enough. From R3 on, step 1 also requires `shape.py`'s
**silent** list to be empty: every running instrumented service has a spanmetrics series in the
last five minutes. A silent service is a world that is not clean, and the rehearsal waits.

R2 is recorded as measured (`R2-process-freeze/`), with the hole named. The freeze is run again
as **R2b** under the fixed world, with its own record — the convention A4b and A8b set: a second
run because the first could not observe what it was registered to observe, never a re-run to
improve a number. The order becomes flag → freeze → freeze again → partition → corruption →
disk fill.

---

## Addendum 2026-09-24, after R5 — all five rehearsed

| class | run(s) | injects | visible through the tools | restores | scenario may be authored |
|---|---|---|---|---|---|
| `feature_flag` | R1 (+ live-flag read) | yes | (a)(c); (d) read on a live flag, the message not carried (Q94) | yes | yes |
| `process_freeze` | R2 (split world, Q95), **R2b** | yes, A2 to the second | (a)(c)(d) | yes; restarts Postgres (Q96) | yes |
| `network_partition` | R3 | yes, A3's shape | (c) the once-a-minute line, (a)(d) | yes; restarts Postgres 8 s later (Q96) | yes |
| `datastore_corruption` | R4 (loop never swept), **R4b** | yes, A4b's shape | (a)(c)(d), culprit in the hop line | yes, ends its own loop | yes |
| `disk_fill` | R5 | yes, A8b's shape | (a)(c)(d); (c) on a 30 s window, (d) after a tool fix (Q97) | yes, by the registered fallback | yes |

Seven runs for five classes. Two second runs (R2b, R4b) followed the convention A4b and A8b set: a
first run that could not observe what it was registered to observe gets its own record and a second
run, never a replacement. What the rehearsals found beyond their verdicts: Q95 (Tempo on the
collector's old address, fixed), Q96 (the catalog's restore restarts Postgres, open), Q97 (the
trace tool crashed on a cycle, fixed), Q98 (`quote` stamps time a day behind, open), two injector
defects fixed the same hour (the corruption loop's variables; its heartbeat deadline), one
`readback` defect (a bare ISO timestamp read as local time), and two tool properties added to Q94
(the culprit's span below the depth limit; the onset lines below the head/tail keep). **T7.0 #5 is
complete**; T7.0's deliverable - *inject/restore verified* for every class - is met.

## Addendum 2026-09-24, Q98 — the pre-state has a fifth line: `quote`'s clock

**Carried to every T7.1 recording on v2, as the silent list was.** `quote` runs the PHP
OpenTelemetry SDK, and the SDK stamps its telemetry from a clock anchored when the process
started. That clock does not advance while the Docker VM is suspended, so each time the Mac sleeps
`quote` falls further behind: **26.6 h** at 08:45 (R5), **29.8 h** at 18:21 and **34.6 h** at
23:30. The two readings in between bracket a ~3 h hole in Prometheus's history (13:26 → 16:26).
The container's own clock is right throughout.

**What it costs.**

- Past Prometheus's 30-minute out-of-order window, every push of `quote`'s own metrics is refused
  as `too old sample`. That is the once-a-minute push of 7 metrics and 52 points that Q95's notes
  recorded since the world came up. A collector debug pipeline filtered to `quote`, run for 150 s
  and then reverted, read 14 metrics and 104 points in two pushes, stamped `2026-09-23 12:32:01`
  at `18:21:42` on 09-24.
- Its spans sit a day and more out of place in every checkout trace.
- Its traffic series, derived from its traces by the collector, and so every alert rule on it,
  are unaffected.

**The fix, measured.** `docker restart quote` re-anchors the clock. Before the restart: 0 of
`quote`'s own series in Prometheus, and its spans −34.57 h from their traces' roots. 150 s after
it: 7 series, and 0.00 h.

**So `shape.py` prints `quote's clock (Q98)`.**

- `current` when `quote`'s own series are landing. That is the pre-state a recording needs.
- `lagging` when none are. The pre-state is then not clean: `docker restart quote`, wait five
  minutes for the recorder's settle gate, and read again.

The world config is unchanged: no digest moves, and neither existing v2 bundle is re-recorded.
Both were recorded with `quote` lagging. Neither narrative cites `quote`'s own metrics or its spans
(the freeze's `ServiceNoTraffic/quote` is its derived traffic series, which was never affected).
