# T7.2 step 5 and Q122: the v2 world's dependency graph, captured read-only

Read in [`docs/design/t7.2-topology.md`](../../design/t7.2-topology.md). Captured 2026-10-01 on the
owner's Mac from the v2 world's Jaeger. The path was `GET /jaeger/ui/api/dependencies` through
frontend-proxy on `:8080`, as T2.4 read v1's, with the same check that the reply is JSON. The
script is kept byte for byte as run, with `.txt` appended so the repository's Python linter and
formatter leave it alone. Every output is verbatim; `docs/evidence` is excluded from the
formatting hooks.

| file | what it is |
|---|---|
| `capture_v2_graph.py.txt` | the capture as run the second time; it asks four lookbacks and saves every reply |
| `v2-graph.txt` | its printed tables, run 2026-10-01 07:36:22 UTC |
| `v2-dependencies-{1h,24h,72h,168h}.json` | each reply, unmodified apart from pretty-printing |
| `skew-probe-2.txt` | `skew_probe.py` (`docs/evidence/q120-audit/`) run again at 07:36:29: quote's offset is 1 day 12h06m10s |

**One run is not kept.** The first run, at 07:33:55, saved only its 24 h reply. The second run
overwrote both that reply and the printed tables. Its edge counts are in the design note, as read
at the time.

**This is not the snapshot of record.** The order path's edges appear only once the lookback
clears quote's skew (Q121). Which reply, or which later capture, becomes Q122's snapshot is
decided when Q122 is built.

**Q121's remedy** ([`PREREGISTRATION-Q121-quote-restart.md`](../../../evals/runs/PREREGISTRATION-Q121-quote-restart.md)):

| file | what it is |
|---|---|
| `quote_offset.py.txt` | the read-only measure of quote's offset from shipping's call, fixed by the registration and used before, after and an hour after the restart |
| `q121-worldcheck-1.txt` | the first run's world check, 2026-10-01 07:53:05 UTC: NOT READY, load-generator at 87.9 % of its memory. The run stopped there with nothing changed; Addendum 1 follows |
| `q121_run.sh.txt` | the run as executed (Addendum 1's step 0 included), 2026-10-01 07:59:49-09:05:01 UTC |
| `q121-loadgen-restart.txt`, `q121-worldcheck-2.txt` | step 0 and the world check that passed |
| `q121-before.txt`, `q121-restart.txt`, `q121-after.txt`, `q121-hour.txt` | quote's offset before, the restart, two minutes after (its window reached back before the restart, so 26 of its 40 pairs are pre-restart), an hour after |
| `q121-v2-graph.txt`, `q121-v2-dependencies-{1h,24h,72h,168h}.json` | the capture an hour after the restart; **`q121-v2-dependencies-1h.json` is Q122's v2 snapshot of record** |

**Q122's build** ([`PREREGISTRATION-Q122-v2-graph.md`](../../../evals/runs/PREREGISTRATION-Q122-v2-graph.md)):

| file | what it is |
|---|---|
| `graph_presence.py.txt` | the read-only presence probe fixed by the registration: which of v2's 32 services Tempo holds spans for, the cross-service pairs in up to ten traces per service checked against the snapshot of record, and the datastore, producer and consumer spans |
| `q122-presence.txt` | the probe's output, run by the owner 2026-10-01 22:47:39 UTC, read in [Q122's RESULT](../../../evals/attempts/Q122-v2-graph/RESULT.md) |

**Topology item 3: astronomy-shop under SREGym** ([`PREREGISTRATION-T7.2-graph3.md`](../../../evals/runs/PREREGISTRATION-T7.2-graph3.md)):

| file | what it is |
|---|---|
| `g3_vm.sh.txt` | the run's every stage on the VM, fixed by the registration (as amended by its Addendum 1, in `recover` only): 1c's setup and deploy, the read while the fault is in, SREGym's own recovery, the hour's hold and the capture, and the teardown |
| `g3_ports.sh.txt` | 1c's step 8 watcher with its output renamed, run on the Mac; the VM's address is withheld in it |
| `g3-preread.txt` to `g3-faultread.txt` | steps 1 to 8 as run, 2026-10-01 23:11-23:46 UTC, read in the registration's Addendum 1. The VM's address is withheld in `g3-host-on.txt`, as in 1c |
