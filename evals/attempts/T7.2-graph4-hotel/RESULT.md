# RESULT - T7.2 topology item 4, Hotel Reservation's graph under SREGym

Read against [`PREREGISTRATION-T7.2-graph4.md`](../../runs/PREREGISTRATION-T7.2-graph4.md) and its
Addendum 1.

- **When and how.** Run on 2026-10-02 02:06-08:08 UTC, by the owner from the Mac. Every stage was a
  `g4_vm.sh hotel` stage on the deployment.
- **Captures.** Verbatim in [`docs/evidence/t7.2-topology/`](../../../docs/evidence/t7.2-topology/)
  (`g4-hotel-*`), with the VM's address withheld.
- **$0.** No model was called, and no key was in the deploy's environment.

## The answers

**Question 1: CAPTURED, UNSETTLED.** By the owner's decision of 2026-10-02, the 5-minute reply,
`g4-hotel-deps-5m.json`, is **Hotel Reservation's snapshot of record**.

- **The graph: 8 services, 7 cross-service edges.**
  - `frontend →` profile (24,694 calls), reservation (15,258), search (15,139),
    recommendation (9,581) and user (242);
  - `search →` geo (15,139) and rate (15,125).
- **No self-edges** (Jaeger v1).
- **The store reached back about five minutes.** At the capture, all 8 services had a trace
  between 7 and 3 minutes back, and none between 17 and 13, 32 and 28, or 62 and 58.
  - So only the 5-minute lookback was held, and the 15-, 30- and 60-minute replies are that same
    window: all four hold the same 7 edges, with counts within about 1 % of each other.
  - With one held lookback there is nothing shorter to compare against, so the table reads
    UNSETTLED.
- **Why the owner accepted it.**
  - A longer window is impossible with SREGym's Jaeger as configured. It keeps 25,000 traces, and
    this application traces every request at 100 a second.
  - A second run would hold the same five minutes.
  - The window saw every edge at least 242 times.
  - **The limit, stated**: a path rarer than about 1 in 25,000 requests could be missing from any
    five-minute window, and nothing here can rule one out.
- **Not SREGym as shipped.** The graph is the application under SREGym's own workload, with **its
  tracing wired as SREGym intends**: every service was restarted once (Addendum 1) so that its
  spans reached SREGym's Jaeger. As SREGym ships it, the Jaeger receives nothing from this
  application (below).

**Question 2: INCONCLUSIVE.** The fault read (02:43:14) held no trace at all. The cause is the
tracing gap, not the fault, so nothing about the fault's effect on the live graph can be read from
it.

## The predictions

| prediction | held? |
|---|---|
| 8 traced services: frontend, search, geo, rate, profile, recommendation, reservation, user | **held** |
| 7 edges: `frontend →` search, profile, recommendation, user, reservation; `search →` geo, rate | **held**, exactly |
| datastores, Consul and memcached not services | **held**: none appears |
| held at 5 minutes only, so CAPTURED, UNSETTLED | **held** |
| the deploy takes 15 to 20 minutes, with a stalled `profile` rollout | **wrong**. The kept deploy took 1m30s (its images were already pulled by the first, lost run), and the fault injection took 10 s, with no stall. The first run's duration is unknown |
| question 2: NO, the healthy `profile` pod keeps serving | **wrong twice**. The fault did bite: `profile` crash-looped with no healthy pod, and `frontend` logged `GetProfiles failed`. The question is INCONCLUSIVE anyway, for the tracing gap |
| MemAvailable at or above 7 GiB through the hold | **held**: minimum 8.08, mean 8.25 |
| none of the 35 touched, no world alert, both ports `000` from outside | **held** |
| $0 | **held** |

## Step by step

- **Steps 1 to 5** (02:06-02:49) are read in Addendum 1:
  - the gate and the setup;
  - the two deploys, with the first log lost;
  - the empty fault read and the diagnosis;
  - the recovery.
- **`restart-app`** (02:55:05-02:56:09). All eight Go services restarted and rolled out. A minute
  later Jaeger listed all eight, and every pod was Running and ready, so the hold's gate passed.
- **The hold** (02:58:15-04:08:30). 141 samples:
  - MemAvailable 8.08-8.48 GiB, memory PSI 0.00;
  - load1 at most **7.06**, CPU PSI at most 6.60 (the highest of the T7.2 runs, from 100
    requests a second, every one traced);
  - no world alert, and none of the 35 restarted or stopped.

  At the capture (04:08:21), every application pod had run 73 minutes or more with no restart,
  and SREGym's Jaeger and collector 94 minutes, likewise.
- **Teardown** (08:02-08:08) and **P3**:
  - SREGym's port-forward was killed, and 8000 and 9954 were closed;
  - the cluster, network and node image were removed, and the rules and inotify put back;
  - the run's directories and the Helm homes are all absent;
  - the kill switch is off and `git status` empty;
  - P3: MemAvailable 11.38-11.63 GiB, 35 of 38 running, no restart, no alert.

## Departures

- **The deploy ran twice**, and the first log is lost (Addendum 1).
- **`restart-app`** (Addendum 1, the owner's decision).
- **The cluster stayed up about four hours past the capture.** The capture finished at 04:08 and
  the teardown began at 08:02. The sampler covered only the hold, so those hours were not watched.
  What covers them:
  - P3 found nothing changed;
  - **the deployment opened no incident in the eight hours to 08:10**;
  - the teardown found 35 running.
- **`incidents` failed as written: my bug in `g4_vm.sh`.** Making the application its first
  argument moved the hours argument from `$2` to `$3`, and the stage still read `$2`, so the query
  asked for `interval 'incidents hours'` and was refused (`invalid input syntax for type
  interval`).
  - It was run again directly, as the same query over 8 hours (`g4-hotel-incidents.txt`, which
    replaced the failed output).
  - The script is fixed (`${3:-6}`) before Social Network's run. That fix is its only change.

## Found on the way

- **Under SREGym as shipped, Hotel Reservation sends its traces nowhere.** Its services set up
  their Jaeger agent while `jaeger` still names the application's own Jaeger. SREGym replaces that
  service with an `ExternalName` to its collector after the application is up, and restarts
  nothing (`conductor.deploy_app`, for every application but train-ticket).
  - **Measured**: Jaeger listed no service, then `profile` alone after its restart, then all
    eight after theirs.
  - **So in SREGym's own runs of any Hotel Reservation problem, its trace tools
    (`get_traces`, `get_dependency_graph`) return nothing.** Queued as **Q127** for scoping step 6.
  - Whether Social Network does the same is read in its run.
- **The application's own Jaeger pod survived SREGym's cleanup**, as astronomy-shop's did,
  together with its `jaeger-out` NodePort service. Neither receives anything.
