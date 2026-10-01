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
