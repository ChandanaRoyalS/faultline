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
