# RESULT - T7.2 topology item 4, Social Network's graph under SREGym

Read against [`PREREGISTRATION-T7.2-graph4.md`](../../runs/PREREGISTRATION-T7.2-graph4.md) and its
Addendum 1.

- **When and how.** Run on 2026-10-02 08:18-16:06 UTC, by the owner from the Mac. Every stage was a
  `g4_vm.sh social` stage on the deployment, with the script fixed after Hotel Reservation's run
  (the `incidents` argument, its only change).
- **Captures.** Verbatim in [`docs/evidence/t7.2-topology/`](../../../docs/evidence/t7.2-topology/)
  (`g4-social-*`), with the VM's address withheld.
- **$0.** No model was called.

## The answers

**Question 1: CAPTURED.** The 30-minute reply, `g4-social-deps-30m.json`, is **Social Network's
snapshot of record**, by the registered rule.

- **The store's reach.**
  - At the capture (12:33:14), 12 services had a trace at the start of the 5-, 15- and
    30-minute lookbacks, and none between 62 and 58 minutes back.
  - So the longest held lookback is 30 minutes, and the next shorter held one, 15 minutes, has the
    same cross-service edges.
  - **All four replies hold the same 8 edges.**
- **The graph: 6 services, 8 cross-service edges.** Counts are over 30 minutes:

  | edge | calls |
  |---|---|
  | `nginx-web-server → home-timeline-service` | 1,007 |
  | `home-timeline-service → post-storage-service` | 1,008 |
  | `nginx-web-server → user-timeline-service` | 473 |
  | `user-timeline-service → post-storage-service` | 474 |
  | `nginx-web-server → compose-post-service` | 166 |
  | `compose-post-service → home-timeline-service` | 167 |
  | `compose-post-service → user-timeline-service` | 167 |
  | `home-timeline-service → social-graph-service` | 167 |

- **Six more services trace and join no edge**: `text-service`, `unique-id-service`,
  `user-service`, `media-service`, `url-shorten-service` and `user-mention-service`. They are the
  rest of `compose-post-service`'s write path.
  - Jaeger lists each, so their spans arrive.
  - None of their spans has a parent or child in another service in the graph.
  - **The compose path is in the graph only as far as the two timelines.** Why the calls to the six
    do not join their caller's trace was not read.
- **`media-frontend`** served no request in the hour (below), so it has no span and no edge.
- **The datastores** (MongoDB, Redis and memcached) are not services, as predicted.
- **The store reached back only about 40 minutes**, not the hour the 1 % sampling predicted.
  - The 60-minute reply's counts are 1.35 times the 30-minute reply's, against the 2 times a full
    hour would give.
  - At 25,000 traces that is about 10 a second, against the 0.4 a second that
    `nginx-web-server`'s sampled requests account for. So most stored traces are not rooted at
    `nginx-web-server`.
  - The six edgeless services' own traces would account for it, but **that was not read**.
- **Not SREGym as shipped.** As for Hotel Reservation, the graph is the application with **its
  tracing wired as SREGym intends**: every non-datastore deployment was restarted once, under
  Addendum 1.

**Question 2: INCONCLUSIVE.** The fault read (10:34:40) held no trace: Jaeger's services were
`null`, the same tracing gap as Hotel Reservation's.

## The predictions

| prediction | held? |
|---|---|
| 11 or 12 traced services | **held**: 12 |
| 12 to 18 cross-service edges, centred on compose-post, the timelines and post-storage | **wrong**: 8. The centre held, but the six write-path services join no edge |
| every lookback held; the 30- and 60-minute replies agree | **wrong**: the store reached back about 40 minutes, so 60 was not held. The edges agree in every reply |
| CAPTURED | **held** |
| the deploy takes 5 to 10 minutes, or 15 to 20 if `user-service` stalls | **just under**: 4m45s. No stall |
| question 2: NO, or YES if the faulted pod starts | **neither**: INCONCLUSIVE, for the tracing gap |
| MemAvailable at or above 6 GiB | **held**: minimum 7.98, mean 8.30 |
| none of the 35 touched, no world alert, both ports `000` from outside | **held**. See the note on the firewall below for what `000` tested |
| $0 | **held** |

## Step by step

- **The gate and the setup** (08:18-08:21). All passed, as in the earlier runs.
- **The port watcher** saw 9954 at 10:28:18, and both ports answered `000` from outside.
- **The deploy** (10:24:55-10:29:40, 4m45s). One run, a fresh namespace, exit 0 with
  `Fault injected`.
- **The fault read** (10:34:40). Jaeger had no services. **Addendum 1's condition was met, so
  `restart-app` applies**, as registered for Social Network.
- **The recovery** (11:16:45-11:17:23) passed: one `user-service` pod, `ClusterFirst`, every pod
  ready. **The fault stayed in for 47 minutes**, because the recovery ran after the fault read was
  reported.
- **`restart-app`** (11:17:24-11:18:51). All 13 deployments rolled out, and every pod was ready.
  Jaeger listed 12 services: every one but `media-frontend`.
  - **The gate as written did not pass**, so the run stopped and read
    (`g4-social-mediafrontend.txt`). `media-frontend` was Running and ready, and had written no
    log line since its restart. Nothing called it: every request of the workload goes to
    `nginx-thrift`.
  - **By the owner's decision**, the gate was read as *"every restarted service that served
    traffic"*, which the 12 met.
- **The hold** (11:23:08-12:33:23). 141 samples:
  - MemAvailable 7.98-8.52 GiB, load1 at most 7.07, CPU PSI at most 3.02;
  - no world alert, and none of the 35 restarted or stopped.

  At the capture, no application or SREGym pod had restarted.
- **The teardown ran twice** (below). The VM is as it was: no cluster, no tools, no run
  directories, the kill switch off and `git status` empty.
- **P3 of record** (16:01-16:06): MemAvailable 11.48-11.57 GiB, 35 of 38 running, no restart, no
  alert.
- **No incident opened** from 08:00 to 16:08.

## Departures

- **`restart-app`**, applied under Addendum 1, and **the gate read as "served traffic"** (the
  owner's decision, above).
- **The teardown chain ran twice, at 12:52 and at 15:54.**
  - The second run's outputs overwrote the first's, so **the 12:52 chain's outputs are lost**.
  - **Its timing is established** from the VM's sudo log (`g4-social-sudo-times.txt`): `host-off`
    at 12:52:27 and again at 15:54:14. The executor was last started at 12:52:34, which is the
    first `killswitch-off`.
  - **So the first chain ran 19 minutes after the capture.** Its `teardown` stage kills SREGym's
    port-forward before `host-off` removes the rules, so 9954 was never open without them.
  - The second chain found nothing left to undo, which is why its `host-off` reported
    `iptables: Bad rule` twice.
- **The P3 attempted at 15:58 failed.** The sampler had already been deleted, by a step not
  recorded. P3 of record was taken at 16:01 with the sampler copied back, then deleted again.
- **My false alarm.** Reading the second `host-off`, I reported the rules as removed by something
  unknown, before ruling out the simplest cause. The sudo log ruled it out. The read-only
  diagnosis that followed is kept (`g4-social-firewall-diag.txt`, `g4-social-timeline.txt`).

## Found on the way

- **Social Network, as SREGym ships it, also sends its traces nowhere**, exactly as Hotel
  Reservation does: no service in Jaeger until the restart. **Q127 now covers both
  applications.**
- **The firewall, read in full.** ufw is active on the deployment with `INPUT` policy DROP,
  allowing only 22, 80 and 443, plus 8000 from the Docker subnet. Its log shows it blocking
  internet scans on port 8443 every 10 to 30 minutes throughout the run.
  - So the two rules that 1c, item 3 and item 4 added for 9954 and 8000 were **a second layer**.
  - Every `000` from outside in those runs tested ufw and the rules together, not the rules
    alone. 1c's RESULT says *"The firewall rules held"*, which overstates what was tested, and it
    carries a note to that effect.
  - **The world's Docker-published ports** (3000 and 32768 tried, `g4-world-ports-outside.txt`)
    also answered `000` from outside.
- **The six edgeless services** and the 40-minute store reach are recorded for the loading build.
  Its absent-service table for Social Network has to say what these services are: they trace,
  but nothing links them to their callers.
