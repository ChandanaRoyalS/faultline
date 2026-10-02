# Pre-registration - T7.2 topology item 4: the DeathStarBench applications' graphs under SREGym

**Written before anything of either run is changed. Nothing here is a result.** This is item 4 of
`docs/design/t7.2-topology.md`:

> The DeathStarBench applications (Hotel Reservation and Social Network, where ADR-0042 says the
> external claim should lead) are captured the same way, each before any scored run.

"The same way" is item 3's method: SREGym's own deploy, one read with the fault in, SREGym's own
recovery, a 70-minute hold, then a capture from SREGym's Jaeger
([`PREREGISTRATION-T7.2-graph3.md`](PREREGISTRATION-T7.2-graph3.md), as amended, and
[its RESULT](../attempts/T7.2-graph3/RESULT.md)).

**The two questions, for each application.**

1. **What is its dependency graph** under SREGym's own workload, as SREGym's Jaeger records it?
   There is no graph of these applications to compare against, so the question is a capture,
   plus whether the capture is settled.
2. **Does SREGym's fault remove the faulty service's edges** from the live graph? This is item 3's
   question 2 on two more problems.

## Decided by the owner, 2026-10-02, before this registration

**Two separate runs**, each a whole item-3-shaped run: a fresh cluster, deploy, fault read,
recovery, hold, capture and teardown. **Hotel Reservation first.** No trace of one application can
reach the other's graph, and each result stands alone.

The rejected alternative was one cluster with both applications in turn. SREGym's Jaeger is not
restarted between applications, so separation would have rested on a namespace deletion and the
capture windows.

## Read before registration (SREGym at `46c853db`, its applications as 1c checked them out)

- **The problems.**
  - `wrong_dns_policy_hotel_reservation` faults `profile`; `wrong_dns_policy_social_network` faults
    `user-service`.
  - Both are item 3's fault on another service (`WrongDNSPolicy`), with **the same recovery,
    `recover_wrong_dns_policy`**, the same two `kubectl` commands.
  - Neither is in SREGym-Lite. They are registered problems, used here to deploy and recover, and
    nothing is scored.
- **The applications.**

  | | Hotel Reservation | Social Network |
  |---|---|---|
  | how deployed | Kubernetes manifests (`hotelReservation/kubernetes`) | Helm chart (`socialNetwork/helm-chart`) |
  | namespace | `hotel-reservation` | `social-network` |
  | workload | wrk2 in a cluster job, 100 req/s, in 30 s rounds that loop forever (`mixed-workload_type_1.lua`) | wrk2, 100 req/s in 10 s rounds that loop (`mixed-workload.lua`: 60 % home timeline, 30 % user timeline, 10 % compose) |
  | tracing | Jaeger client, **sample ratio 1 on every service** | Jaeger client, **probabilistic 0.01** |

- **What the sampling means for the cap.**
  - SREGym's Jaeger keeps 25,000 traces. At 100 req/s, every request traced, **Hotel Reservation's
    store reaches back about four minutes**: 25,000 / 100 is 250 s.
  - Social Network at 1 % keeps about one trace a second, so its store holds the whole hour.
  - So the capture reads **5, 15, 30 and 60 minutes**, and for each lookback whether any service
    still has a trace at its start.
- **A risk in the fault itself, read at source.**
  - `profile`'s `main.go` panics if it cannot dial MongoDB, and with the fault's resolver it
    cannot.
  - So the faulted pod may never become ready. The deployments run one replica with the default
    rolling update, so **the old, healthy pod would keep serving**. SREGym's
    `kubectl rollout status` has no timeout, and would return at the deployment's 600 s progress
    deadline.
  - If so, the deploy takes about ten minutes longer and the fault does not bite: the fault read
    would still show `profile`'s edges. That is recorded as what SREGym's problem produces, not
    worked around.
  - The same may hold for `user-service`. Its start-up was not read deeply enough to say.

## What changes, and how it is undone

These are item 3's changes, made and undone by the same stages. They come from **`g4_vm.sh`**,
committed with this registration (`docs/evidence/t7.2-topology/g4_vm.sh.txt`). It is item 3's
script, as amended by its Addendum 1, with these changes and no others:

- **The application is a parameter**: the problem, the namespace and the faulty deployment.
- **The pod `resolv.conf` reads are dropped.** Item 3 found neither `cat` nor `node` in the
  image, and the pod spec is what decides.
- **`recover` waits up to 120 s** for a terminating faulted pod before reading the specs, as
  SREGym's own check does. Item 3's first recovery read caught one.
- **The sampler runs with `python3 -u`**, so its log is written as it goes. Item 3's looked
  stalled for forty minutes.
- **`capture` lists SREGym's `observe` pods** (its Jaeger could restart under Hotel
  Reservation's volume). It reads the four lookbacks, each with the store's reach.

**Item 3's stop rule, gate, wall limit, firewall rules, kill switch and teardown all stand
unchanged.** `g4_ports.sh` is item 3's port watcher with its output named by application.

## The procedure, for each application

`<app>` is `hotel`, then `social` in its own run. Each stage's output goes to
`~/Downloads/g4-<app>-<stage>.txt` and is read before the next:

```
ssh "$VM" 'bash /tmp/g4_vm.sh <app> <stage>'
```

0. **Copy** `g4_vm.sh` and 1c's sampler to `/tmp`.
1. **`preread`**: item 3's gate, in full.
2. **`killswitch-on`**, gated on `"kill_switch":true`, then **`host-on`**.
3. **`install`**, then **`cluster`**, gated on install's exit.
4. **The port watcher first** (`g4_ports.sh <app>`), then **`deploy`**: wall limit 45 minutes.
   **`faultread`** follows if the log has `Fault injected`.
5. **`recover`**. It passes when:
   - the faulty deployment's pods' specs show `ClusterFirst` and no `8.8.8.8`;
   - every pod in the namespace is Running and ready.

   Otherwise stop and read.
6. **`hold`**, under `nohup`: 70 minutes of the sampler, then `capture`. The replies and the log
   are copied to the Mac.
7. **Teardown**, whatever happened:
   - `teardown`, `host-off`, `cleanup` and `killswitch-off`;
   - `incidents`;
   - then the sampler's `P3 300`, and both scripts deleted.

## The outcomes, stated now

**Question 1**, per application. A lookback is **held** when any service has a trace at its start.

| outcome | when | what follows |
|---|---|---|
| **CAPTURED** | the longest held lookback's reply has at least one cross-service edge, and the next shorter held reply has the same cross-service edges, or lacks only edges with 5 calls or fewer in the longer one | the longest held reply is **the application's snapshot of record** |
| **CAPTURED, UNSETTLED** | as CAPTURED, but the shorter reply lacks an edge with more than 5 calls, or only one lookback is held | the same, reported. The owner decides whether a longer or second capture is needed |
| **INCONCLUSIVE** | no capture as registered, or no held reply with a cross-service edge | the cause is named. Any retry is an addendum first |

**Both applications' snapshots of record then wait on one build, registered after both runs.**
Q125's registry needs an entry per application, and today it requires each to be read in a
Faultline world. DeathStarBench's names belong to no world, so the build has to define how they
are read: their artifact edges, if any, and their absent services.

**Question 2**, per application, against its snapshot of record:

| outcome | when |
|---|---|
| **YES** | the fault read has no edge touching the faulty service, which has at least one edge in the snapshot |
| **PARTLY** | some of its edges are present, each named |
| **NO** | all of them are present. If the faulted pod never replaced the healthy one, that is the reason recorded |

## Predictions, stated now

**Hotel Reservation:**

- **Graph.**
  - 8 traced services: frontend, search, geo, rate, profile, recommendation, reservation, user.
  - **7 cross-service edges**: `frontend →` search, profile, recommendation, user and
    reservation; `search →` geo and rate.
  - The datastores, Consul and memcached appear as client spans inside their callers, not as
    services.
- **The store.** Held at 5 minutes only, so **CAPTURED, UNSETTLED** by the table's own rule.
- **Deploy.** About **15 to 20 minutes**, including a stalled `profile` rollout.
- **Question 2: NO.** The healthy `profile` pod keeps serving, so its edge is in the fault read.
- **MemAvailable** stays **at or above 7 GiB** through the hold.

**Social Network:**

- **Graph.**
  - **11 or 12 traced services**: `nginx-web-server` and the Thrift services.
  - **12 to 18 cross-service edges**, centred on `compose-post-service`, the two timeline services
    and `post-storage-service`.
- **The store.** Every lookback is held, and the 30- and 60-minute replies agree: **CAPTURED**.
- **Deploy.** About **5 to 10 minutes**, or 15 to 20 if `user-service`'s rollout stalls as
  `profile`'s should.
- **Question 2: NO**, for the same reason, with low confidence. If the faulted pod does start,
  then **YES**.
- **MemAvailable** stays **at or above 6 GiB**.

**Both runs:**

- none of the 35 is touched, no world alert fires, and both ports time out from outside;
- $0.

## What is recorded

- **Results.** `evals/attempts/T7.2-graph4-hotel/RESULT.md` and
  `evals/attempts/T7.2-graph4-social/RESULT.md` each hold:
  - both outcomes;
  - every prediction, held or not;
  - the services traced against the application's deployments;
  - every departure.
- **Evidence.** The captures go verbatim to `docs/evidence/t7.2-topology/` (`g4-<app>-*`), with
  the VM's address withheld.
- **The design note's item 4** records each outcome.
- **The loading build** (above) is queued after both.

## Addendum 1, 2026-10-02 - Hotel Reservation: no trace reached SREGym's Jaeger; the application's services are restarted once

**Steps 1 to 5 ran** (captures `g4-hotel-preread.txt` to `g4-hotel-postrecover.txt`):

- **The gate and the setup** (02:06-02:09). All passed, matching item 3's.
- **The port watcher** saw 9954 on `0.0.0.0` and 8000 on `127.0.0.1` at 02:35:03. **Both answered
  `000` from outside.**
- **The deploy** (02:36:44-02:38:14) exited 0 with `Fault injected`.
- **The recovery** (02:48:16-02:48:19) passed, with the faulted pod gone and both `profile` pods
  `ClusterFirst`. One was terminating at the check, as in item 3.

**Departure: the deploy ran twice, and the first run's log is lost.** The log kept is a second run
on the same cluster. It reads *"Undeploying app leftovers… Namespace 'hotel-reservation' has been
deleted"* and *"MCP server already running"*, and the watcher saw 9954 at 02:35:03, before this
log's 02:36:44. An earlier deploy, begun about 02:31 by the watcher's timing, had reached at least
SREGym's MCP server. The second redirected output overwrote its log.

**At 02:45 no SREGym process from it was left** (`g4-hotel-diag.txt`). The second run removed the
first's application and deployed its own, so everything below is the second run's.

**The finding: no trace of Hotel Reservation reached SREGym's Jaeger.**

- **The fault read** (02:43:14). Jaeger's services were `null`, and it held 0 edges.
- **The read-only diagnosis** (02:45:55, `g4-hotel-diag.txt`):
  - Every Go service set up its Jaeger agent at **02:37:47**, on `jaeger:6831`. At that moment
    `jaeger` was the application's own Jaeger service.
  - SREGym replaced `jaeger` with an `ExternalName` to its collector at **02:38:02**, and
    restarted nothing.
  - So the services send to the address of a service that no longer exists. Jaeger listed only
    itself.
- **The test** (02:49:20, `g4-hotel-postrecover.txt`). A minute after the recovery restarted
  `profile`, Jaeger listed exactly `jaeger-all-in-one` and **`profile`**, the one service that
  had re-resolved `jaeger`.
- **What follows for SREGym's tools.** This ordering is SREGym's own for every application but
  train-ticket (`conductor.deploy_app`: *"Other apps get it after deploy to avoid Helm ownership
  conflicts"*). **SREGym's trace tools would see nothing of Hotel Reservation in its own runs.**
  It is recorded for scoping step 6.

**A prediction already wrong: the fault did bite.** `profile` crash-looped (6 restarts by 02:45),
with no healthy pod left serving, and `frontend` logged `GetProfiles failed`.

**The change, decided by the owner.** One new stage, **`restart-app`**, added to `g4_vm.sh`:

- **Every deployment of the application except its datastores, Consul and its own Jaeger** is
  restarted once (a `rollout restart`, then `rollout status`), so each re-resolves `jaeger`. For
  Hotel Reservation that is its eight Go services.
- **Consul is left alone**, because restarting it would drop the services' registrations. So are
  the databases, which would reseed.
- **A minute later the stage reads Jaeger's services.** **The hold starts only if they list every
  restarted service** and every pod is Running and ready. Otherwise, stop and read.

Then `hold` and `capture` run as registered. The capture's hour begins ten minutes after the
restart, so every span in it was sent after the services re-resolved.

**What this changes in the outcomes.**

- **Question 1** is now answered about the application's graph under SREGym's workload, **with
  its tracing wired as SREGym intends it to be**, not as SREGym leaves it. The RESULT says so
  beside the graph.
- **Question 2 is INCONCLUSIVE for Hotel Reservation**: the fault read held no trace, for the
  reason above, not because of the fault.
- **For Social Network**, if its fault read shows the same symptom (Jaeger lists none of its
  services), `restart-app` is applied in the same place and on the same condition, and recorded
  as applied under this addendum.

`g4_vm.sh.txt` is replaced by the amended script. Its only change is the new stage and the list
of stages in its header.
