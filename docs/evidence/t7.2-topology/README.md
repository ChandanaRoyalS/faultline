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
| `g3-recover.txt`, `g3-recover-recheck.txt` | step 9: SREGym's recovery, its first check (the faulted pod still listed), and the read-only re-read that passed |
| `g3-hold.txt` | step 10: 1c's sampler for 70 minutes, then the capture |
| `g3-fault-deps.json`, `g3-deps-30m.json`, `g3-deps-60m.json` | SREGym's `/api/dependencies` replies, unmodified: with the fault in, then the clean 30 and 60 minutes. **`g3-deps-60m.json` is astronomy-shop's snapshot of record** (the owner's decision, 2026-10-02) |
| `g3-accounting.txt` | `accounting`'s last termination and events before teardown: OOM-killed against 120 Mi |
| `g3-teardown.txt`, `g3-host-off.txt`, `g3-cleanup.txt`, `g3-killswitch-off.txt`, `g3-incidents.txt`, `g3-P3.txt` | the teardown and the after-teardown reading. The VM's address is withheld in `g3-host-off.txt` |

**Topology item 4: the DeathStarBench applications under SREGym** ([`PREREGISTRATION-T7.2-graph4.md`](../../../evals/runs/PREREGISTRATION-T7.2-graph4.md)):

| file | what it is |
|---|---|
| `g4_vm.sh.txt` | item 3's stage script with the application as a parameter and the changes the registration lists, plus Addendum 1's `restart-app` stage and, after Hotel Reservation's run, the `incidents` stage's argument fixed (`${3:-6}`); one run per application |
| `g4_ports.sh.txt` | item 3's port watcher, its output named by application; the VM's address is withheld in it |
| `g4-hotel-preread.txt` to `g4-hotel-postrecover.txt` | Hotel Reservation's steps 1 to 5, 2026-10-02 02:06-02:49 UTC, and the read-only diagnosis (`g4-hotel-diag.txt`) and the read after the recovery (`g4-hotel-postrecover.txt`), all read in the registration's Addendum 1. `g4-hotel-deploy.txt` is the second deploy's log; the first's was overwritten. The VM's address is withheld in `g4-hotel-host-on.txt` |
| `g4-hotel-restart-app.txt`, `g4-hotel-hold.txt` | Addendum 1's restart and the gate it passed; the hold and the capture |
| `g4-hotel-fault-deps.json`, `g4-hotel-deps-{5,15,30,60}m.json` | SREGym's `/api/dependencies` replies, unmodified: with the fault in (empty, the tracing gap), then the four lookbacks, which all hold the same five minutes. **`g4-hotel-deps-5m.json` is Hotel Reservation's snapshot of record** (the owner's decision, 2026-10-02) |
| `g4-hotel-teardown.txt`, `g4-hotel-host-off.txt`, `g4-hotel-cleanup.txt`, `g4-hotel-killswitch-off.txt`, `g4-hotel-incidents.txt`, `g4-hotel-P3.txt` | the teardown, the incidents read (run again directly after the stage's bug; it replaced the failed output) and the after-teardown reading. The VM's address is withheld in `g4-hotel-host-off.txt` |
| `g4-social-preread.txt` to `g4-social-mediafrontend.txt` | Social Network's run to the hold: setup, the deploy (one run), the empty fault read, the recovery, `restart-app` under Addendum 1, and the read of `media-frontend`, the one deployment Jaeger did not list |
| `g4-social-hold.txt`, `g4-social-fault-deps.json`, `g4-social-deps-{5,15,30,60}m.json` | the hold and the capture; SREGym's replies, unmodified. **`g4-social-deps-30m.json` is Social Network's snapshot of record**, the longest held lookback |
| `g4-social-teardown.txt`, `g4-social-host-off.txt`, `g4-social-cleanup.txt`, `g4-social-killswitch-off.txt` | the **second** teardown chain (15:54), which found nothing left; the first (12:52) was overwritten by it. Its timing is in `g4-social-sudo-times.txt` and `g4-social-timeline.txt` |
| `g4-social-firewall-diag.txt`, `g4-social-firewall-outside.txt`, `g4-world-ports-outside.txt` | the read-only firewall diagnosis that followed the second `host-off`: ufw's state and log, and three ports tried from outside. The VM's address is withheld in the ufw log lines |
| `g4-social-incidents.txt`, `g4-social-P3.txt` | incidents since 08:00 (none), and P3 of record (16:01) |

