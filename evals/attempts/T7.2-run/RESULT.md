# RESULT - T7.2, the SREGym scored run

Read against [`PREREGISTRATION-T7.2-run.md`](../../runs/PREREGISTRATION-T7.2-run.md), its analysis
as amended by Addendum 1, and its operation as Addendum 2 set it. Run 2026-10-03, 07:54-23:36 UTC,
in three sessions on the deployment, at `d46755e`. Evidence is in
[`docs/evidence/t7.2-run/scored/`](../../../docs/evidence/t7.2-run/scored/). Every figure below is
printed by [`analysis.py.txt`](../../../docs/evidence/t7.2-run/analysis.py.txt) from the committed
files, in `scored/analysis-output.txt`.

**What may be claimed, as registered, and every sentence below carries it:**

1. **Diagnosis only.** Faultline proposes and never executes, so mitigation was not run.
2. **Per application.** Astronomy Shop is Faultline's own demo, at v2.2.0. The two DeathStarBench
   applications are foreign.
3. **A pass rate under SREGym's LLM judge at 0.70**, with Claude Sonnet 4.6 as the judge. It is not
   diagnosis accuracy.
4. **The modalities, as run.**
   - Faultline had SREGym's Prometheus and Loki, and traces on Astronomy Shop only.
   - Its change history is Kubernetes' own record, by name and time.
   - **It had no general Kubernetes describe.** The baseline had kubectl.
5. **Not comparable to SREGym's leaderboard or paper**: a different commit, 33 of 108 problems, R = 1,
   and kind.

## Scores

**66 of 66 attempts completed**: 33 problems, R = 1, both arms. No problem was removed.

- Slot 58 (Claude Code, `cfs_cpu_throttling_hotel_reservation`) timed out at 1,806 s with no
  submission on its first try. **It was re-run once**, under Addendum 2's rule for any run that did
  not complete, and is scored on the second try (67, a fail).
- The registered analysis counts a timeout as a category 4 failure, not a harness loss. **Read that
  way, the result is the same**: a fail on either try, and Claude Code's count stays 30 of 33.

**The pass rate, per application.** The 95 % intervals are a percentile bootstrap over problems, with
10,000 resamples and seed 20261005. A Wilson interval is given beside each as a supplement, because
a bootstrap of 0 of 11 or 11 of 11 has no width by construction.

| application | Faultline | 95 % (Wilson) | Claude Code (Sonnet 4.6) | 95 % (Wilson) |
|---|---|---|---|---|
| Astronomy Shop | **1 / 11, 9 %** | 0-27 % (2-38 %) | **9 / 11, 82 %** | 55-100 % (52-95 %) |
| Hotel Reservation | **1 / 11, 9 %** | 0-27 % (2-38 %) | **10 / 11, 91 %** | 73-100 % (62-98 %) |
| Social Network | **0 / 11, 0 %** | 0-0 % (0-26 %) | **11 / 11, 100 %** | 100-100 % (74-100 %) |

**The paired difference, F − C.** Over all 33 problems this is Addendum 1's primary comparison.

| comparison | n | difference | 95 % | MDE | reading |
|---|---|---|---|---|---|
| **all 33 (primary)** | 33 | **−84.8 points** | −97.0 to −69.7 | 24 | beyond the MDE |
| Astronomy Shop | 11 | −72.7 | −100.0 to −36.4 | 42 | beyond the MDE |
| Hotel Reservation | 11 | −81.8 | −100.0 to −54.5 | 42 | beyond the MDE |
| Social Network | 11 | −100.0 | −100.0 to −100.0 | 42 | beyond the MDE |

- **The pairs**: both arms passed 1 problem, Faultline alone 1, Claude Code alone 29, and neither 2.
- **Faultline's two passes**:
  - `wrong_dns_policy_astronomy_shop` (100). The change log showed `dnsPolicy ClusterFirst -> None`
    and `nameservers 8.8.8.8` on `frontend`. **Claude Code missed this one** (0, it named
    `accounting`).
  - `network_policy_block` (89). The change log showed a NetworkPolicy `deny-all-recommendation`
    created six minutes before the alarm.

  Both are what the change mapping was built to show.
- **The MDE assumes a per-problem difference SD of 0.5.** The observed SD was 0.43 overall, and
  0.62, 0.39 and 0 per application.

## The predictions

| # | registered | observed | held? |
|---|---|---|---|
| 1 | Faultline's rate: shop 25-55 %, hotel 10-40 %, social 10-40 % | 9 % (0-27), 9 % (0-27), 0 % (Wilson 0-26) | **wrong, lower, on all three.** <br>- On the shop and Social Network the estimate is below the range. <br>- On Hotel Reservation it is one point below, inside its interval, so that miss is within the noise. <br>- Each interval (27 points) is narrower than its range (30), so the prediction was testable at this n |
| 2 | the baseline passes more often on every application, beyond the MDE on the two DeathStarBench applications | −73, −82 and −100 points against an MDE of 42 | **held**, and beyond the MDE on the shop as well |
| 3 | on the shop, Faultline's rate on *Regular Virtualization* problems is below its rate on the *OpenTelemetry injector* problems | virtualization 1 / 5, OpenTelemetry 0 / 5 | **not testable at this n**: one problem's difference, in the opposite direction |
| 4 | Faultline's D1 (localisation) mean is its highest of the three | over all 33: D1 0.28, D2 0.20, **D3 0.31** | **wrong as registered.** Over the 13 attempts triage did not gate, D1 is the highest (0.41, 0.21, 0.28). The difference is the judge: an empty submission earns D3-Q1, *"no uninvolved component blamed"* (below) |
| 5 | every trace call on the two DeathStarBench applications returns no trace | 6 of 6 returned none: 5 empty, and 1 failed on DNS (`stale_coredns_config_social_network`) | **held** |
| 6 | no verdict or timeout in at most 10 % of Faultline's attempts | **24 of 33, 73 %**: triage's gate 20, a verdict that establishes no cause 4, timeouts 0 | **wrong**, by the largest margin in the run |
| 7 | cost per attempt: Faultline $0.30-1.50, the baseline $0.50-3.00, the judge $0.02-0.10; time 10-40 minutes | Faultline mean $0.31 (investigated $0.54-1.08); Claude Code mean $0.86, range $0.23-5.23; judge not measured; median slot 7.6 and 7.7 minutes | **cost held on the means**: <br>- Claude Code's range runs outside on both ends, and its top is slot 58 with its timed-out try; <br>- Faultline's mean sits at the floor only because 20 attempts stopped at triage. <br>**Time wrong, faster** |

## Cost and time

| | amount | how |
|---|---|---|
| Faultline (Opus 5) | **$10.26** | trajectory tokens; each of the 20 gated attempts at $0.05, since its single triage call is not persisted |
| Claude Code (Sonnet 4.6) | **$28.37** | session tokens, each message once, including slot 58's first try |
| the judge (Sonnet 4.6) | **$6.60** | 66 judged slots at the registered $0.10 ceiling. **Not measured** |
| the re-check | **$1.80** | Addendum 1's cap includes it |
| **tally** | **$47.04** | it passed $47 only after slot 66, so nothing was cut |

- **The owner's console reading is the authority, and is below** (*The console's reading*). It
  replaces this tally.
- **Time**:
  - three sessions of 3.4, 3.4 and 4.1 hours, 10.8 hours of slots in all;
  - Faultline's gated attempts took a median 6.1 minutes, and its investigated ones 11.9;
  - the longest agent stage was Faultline's 686 s and Claude Code's 1,043 s on a completed try,
    with the one timeout at 1,806 s.

### The console's reading

**Recorded by the owner on 2026-10-04** from the console's Cost page, filtered to the key
`sregym-pilot`, Oct 2-4 (UTC), grouped by model
([`t72-run-console-cost.png`](../../../docs/evidence/t7.2-run/scored/t72-run-console-cost.png)):

| model | billed, Oct 3 (UTC) | what used it |
|---|---|---|
| Claude Opus 5 | **$17.30** | Faultline |
| Claude Sonnet 4.6 | **$33.23** | Claude Code and the judge |
| **billed total** | **$50.53** | nothing on Oct 2 or Oct 4 |

**That day holds the whole key's use**, not only this run: the pilot (01:46-05:33), the re-check
(06:31-07:20) and the scored run (07:54-23:36). The console gives no hourly split, so the cap's
scope is bounded and estimated against the token counts:

| | token count | billed | difference |
|---|---|---|---|
| Faultline, pilot + re-check + run | $1.94 + $1.49 + $10.26 = **$13.69** | **$17.30** | the count is **21 % low** |
| Claude Code, pilot + run | $1.95 + $28.37 = **$30.32** | | |
| the judge, 76 calls at the $0.10 ceiling | **$7.60** | $33.23 − $30.32 = **$2.91**, about $0.04 a call | the ceiling is **2.6 times** the cost |
| **all** | **$51.61** | **$50.53** | about 2 % high, from two errors that cancel |

- **The $50 cap held.**
  - The pilot billed at least its two agents' counted $3.89, so the re-check and the scored run
    together billed **at most $46.64**.
  - Corrected by the two ratios above, they billed **about $45.9**.
  - The $47 stop line was not passed in billed terms either.
- **Why Faultline's count is low** ([`analysis-output.txt`](../../../docs/evidence/t7.2-run/scored/analysis-output.txt),
  section 12):
  - its HTTP client logged **216** model calls over the 33 attempts, and its trajectory recorded
    tokens for **156**;
  - the 60 missing include the 33 triage calls, which are not persisted, as recorded before;
  - the other 27 are in the investigated attempts. **Which roles made them is not established.**
- **Claude Code's console page for the key showed $24.13**, marked there as an analytics estimate.
  The billed Sonnet total above is the figure of record, and it agrees with the session-token count
  if the judge cost about $0.04 a call.
- **For Phase 7's later budgets**: a tally from Faultline's trajectory tokens needs about 1.26 times
  its value, and a Sonnet 4.6 judge call costs about $0.04, not $0.10. Each task's registration
  states the rule it uses.

## The error taxonomy

**Every failed attempt, in the registered five categories.** The rule was fixed in the script
before it was applied:

- **category 4**: no diagnosis was submitted. That is `Faultline reached no verdict.`, a verdict
  whose root cause says it is not established, or no submission at all;
- **category 5**: the run did not complete;
- **otherwise, by the judge's dimensions**: D1 below 0.67 is a localisation miss, then D2 below 0.67
  a characterisation miss, else a scope miss.

| category | Faultline (31 failures) | Claude Code (3 failures) |
|---|---|---|
| 1. localisation miss | 4 | **3** |
| 2. characterisation miss | 2 | 0 |
| 3. scope miss | 1 | 0 |
| 4. no verdict or timeout | **24** (gate 20, *not established* 4) | 0 (the timed-out try was re-run) |
| 5. adapter or harness failure | 0 | 0 |

- **Read by the dimensions instead**, the four *not established* verdicts are all localisation
  misses (D1 0 each). Nothing else changes.
- **No attempt failed for the adapter's defects.** Every tool call returned data, a true absence or
  a named error. The pilot's failures did not recur.

### Category 4a: triage's gate, 20 attempts

**Triage judged 20 of 33 incidents noise and gated them before fan-out.** No specialist ran and no
tool was called. The submission was `Faultline reached no verdict.`

| what the opening found | attempts | Faultline passed | baseline passed |
|---|---|---|---|
| alarms, triage gated | **20** | 0 | **19** |
| alarms, triage investigated | 7 | 1 | 6 |
| no alarm in six evaluations, the front-door fallback | 6 | 1 | 5 |

- **17 of the 20 were warning-severity Kubernetes alarms on one workload**:
  `KubeDeploymentReplicasMismatch` with `KubePodNotReady` or `KubePodCrashLooping`, kube-prometheus'
  own severities as registered.
  - **On 14 of the 20, an alarm named the ground-truth component**: `media-service`,
    `user-service` five times, `frontend` three times, `aux-service` twice, `media-processor`,
    `profile` and `jaeger`. Truth is read from the judge's own records (the D1-Q1 evidence), printed
    beside each in the output.
  - **The baseline passed all 14.**
- **3 of the 20 were `ServiceHighErrorRate` on `load-generator` alone**: the two ad-service flag
  problems and `kafka_poison_pill_hol_block`. **Triage's prompt names that case as noise**, so these
  three followed its written rule.
- **The other 17 do not match any noise example the prompt gives.**
  - The prompt's examples are: *"a single warning-severity latency alert on one service with no
    error-rate alert anywhere, an alert on the synthetic load generator alone, or an incident whose
    services all recovered"*.
  - A crash loop is not a latency alert. The model extended *"a world that is working"* to a
    workload that is not running, at medium confidence in 16 of the 17.
  - The prompt's own instruction, *"declining a real incident costs more than investigating a
    quiet one"*, did not prevent it.
- **The snapshot graph could not show propagation for 10 of the 17.** The alarming service is not
  in the snapshot of record, so the radius was that one service:
  - `user-service`, `media-service`, `aux-service` and `jaeger` are absent from Social Network's
    six-service graph;
  - `media-processor` and `aux-service` are absent from Hotel Reservation's eight.

  The other 7 started from a service the graph holds, and were gated anyway.
- **What Faultline would have scored on these 20 without the gate is not measured here**, and is not
  claimed. Its rate on the 13 it investigated was 2 of 13.

### Category 4b: a verdict that establishes no cause, 4 attempts

- **Both `stale_coredns_config` problems (s40, s60): the fault broke Faultline's tools.**
  - The CoreDNS fault left SREGym's MCP servers unable to resolve `loki`, `prometheus-server` and
    `jaeger-out` in the `observe` namespace. 9 of 17 calls failed on `NameResolutionError`.
  - Faultline reported the failures, and called the cause not established. On the shop it
    attributed them to *"the observability path"*.
  - **Claude Code passed both** (100, 89). Its kubectl reaches the API server without cluster DNS.
- **`missing_service_social_network` (s32)**:
  - nearly every call returned an empty answer: no logs, no traces, and no span-metric samples, as
    SREGym ships Social Network;
  - the deleted Service is `user-service`, which the opening never alarmed on and the graph does not
    hold.
- **`finalizer_deadlock_controller_hotel_reservation` (s41)**:
  - the fallback seeded `frontend`;
  - the fault is a read-only ClusterRole on a cleanup controller, which no telemetry tool and no
    change command reads.

### Categories 1-3: a verdict, wrong, 7 attempts

| slot | problem | category | what Faultline said | the truth, from the judge's record |
|---|---|---|---|---|
| s13 | `kafka_queue_problems` (Q126) | localisation | `accounting`, duplicate-key inserts (SQLSTATE 23505) | `kafka`, the `kafkaQueueProblems` flag. The only alarm was on `accounting`, Q126's neighbour |
| s16 | `pvc_claim_mismatch` | localisation (D1 0.33) | six MongoDBs stopped by external SIGTERMs | a PVC `claimName` that does not exist, so the pods never bind |
| s36 | `wrong_dns_policy_social_network` | localisation | `nginx-web-server` frozen (the fallback's seed) | `user-service`'s `dnsPolicy: None`. That service is not in the graph |
| s57 | `cfs_cpu_throttling_hotel_reservation` | localisation | `frontend`'s CPU limit halved, a real change in the change log (the fallback's seed) | `geo`'s CPU limit |
| s24 | `resource_request_too_large` | characterisation | `mongodb-rate` right; *"terminated by SIGTERM"* | memory requests too large, so the pod stays Pending |
| s56 | `service_port_conflict_astronomy_shop` | characterisation | `ad` right; *"JVM-driven gRPC shutdown"* | a hostPort 9100 collision, so the pod cannot schedule |
| s25 | `astronomy_shop_payment_service_failure` | scope | `payment` and a flag, right; *"a subset … gold loyalty level"* | `paymentFailure` at 100 %: every charge fails |

- **Three of the seven are one fault shape: a pod that never ran or never bound** (s16, s24, s56).
  - Faultline read the logs of pods that started and stopped, and named that as the mechanism.
  - The scheduler's reason (`FailedScheduling`, the PVC's binding error) lives in object state and
    in events' reason and message.
  - Faultline reads neither: the change mapping returns events by kind, name and time only, as
    registered.
- **Two of the seven followed the fallback's seed** (s36, s57). The fallback opens the incident on
  the front door, and Faultline's investigation stayed there.

### The baseline's three failures

All three are localisation misses:

- **s7, `wrong_dns_policy_astronomy_shop`**: it named `accounting`.
- **s43, `kafka_poison_pill_hol_block`**: it named `product-catalog`.
- **s58, `cfs_cpu_throttling_hotel_reservation`**: it named `user`, with `geo` as secondary (D1
  0.33).

**Two of these, and Faultline's s13, named a service with an as-shipped problem.** `accounting`
has its OOM loop (Q126), and `product-catalog` has the shop's startup crash loop (the pilot's
finding 6).

### By family

Families under five problems are given attempt by attempt, as Addendum 1 requires.

| family | n | Faultline | Claude Code |
|---|---|---|---|
| Regular Virtualization (Kubernetes object misconfigurations) | 23 | **1** (shop 1 / 5, hotel 0 / 7, social 0 / 11) | **21** |
| OpenTelemetry injector (the shop's flags) | 5 | **0** | **4** |

- **The three Direct K8S API problems, all Hotel Reservation**:
  - Faultline passed `network_policy_block`;
  - it was gated on `dev_shm_exhaustion_hotel_reservation` and on
    `admission_webhook_tls_mismatch_hotel_reservation`;
  - Claude Code passed all three.
- **The two Application problems**:
  - `missing_env_variable_astronomy_shop`: Faultline gated, the alarm on `product-catalog`'s
    startup crash loop rather than on `frontend`;
  - `storage_user_unregistered-2`: Faultline gated, the alarm on `rate` and not on `mongodb-rate`;
  - Claude Code passed both.
- **Q126's two flagged problems**:
  - `kafka_queue_problems`: Faultline named `accounting` and failed. Claude Code passed (89);
  - `kafka_poison_pill_hol_block`: Faultline was gated on a `load-generator` alarm. Claude Code
    named `product-catalog` and failed (0).

### By the judge's dimensions

| | n | D1 | D2 | D3 |
|---|---|---|---|---|
| Faultline, all | 33 | 0.28 | 0.20 | 0.31 |
| Faultline, investigated | 13 | 0.41 | 0.21 | 0.28 |
| Faultline, gated | 20 | 0.20 | 0.20 | 0.33 |
| Claude Code, all | 33 | 0.92 | 0.94 | 0.89 |

**About the judge.** It scored the identical text `Faultline reached no verdict.` **11 eight times
and 33 twelve times**, on its D1-Q3 and D2-Q3 answers: whether naming nothing counts as blaming
nothing. Both scores fail at 0.70, so no pass depends on it. But a dimension mean over gated
attempts measures that variation, not Faultline.

## Architecture implications

Read from the categories above, in the order of how many failures each explains. **Nothing here is
changed by this report.** Faultline was frozen for the run as T7.2 requires, and any change is its
own task, registered before it is built.

1. **Triage's gate is the largest single cause: 20 of 31 failures.**
   - The gate decides before any evidence exists. Its prompt describes noise as latency warnings,
     the synthetic client and recovered services, and the model applied it to workloads that were
     not running.
   - Under SREGym every incident is real by construction. Faultline's design assumes an alert
     stream with noise in it, and this run is the first measurement of what the gate costs when
     there is none.
   - **The architectural point is that a decline is unrecoverable and unreviewed.** Nothing
     downstream sees a gated incident.
   - Candidates for a later task:
     - Kubernetes availability alarms named as never noise;
     - a declared-incident mode in which the gate cannot decline;
     - measuring the gate's false-decline rate on Faultline's own world in T7.1.

     Each moves the prompt stamp.
2. **No object state: three of the seven wrong verdicts, and the shape of the run's problems.**
   - 23 of the 33 problems are Kubernetes object misconfigurations.
   - Where a pod never ran, Faultline's telemetry shows only silence or a shutdown, and it named
     those. The baseline read the reason directly with kubectl.
   - Clause 4 predicted this. **It is the modality the benchmark's faults live in.** A read-only
     object-state reader (describe, events with reason and message) is a new tool, so it moves the
     capability stamp.
3. **The topology covers only what sends traces.**
   - The snapshot graphs hold 16, 8 and 6 services. None holds a datastore, CoreDNS or a Kubernetes
     object, and Social Network's lacks `user-service`, the truth in seven of its eleven problems.
   - So the blast radius cannot reach the components the benchmark faults. The fallback's
     front-door seed then held two investigations at the front door.
   - An inventory from the cluster itself (workloads, Services) would give the graph nodes that
     traces never will.
4. **A failing tool is treated as missing evidence, not as evidence.**
   - In both CoreDNS problems, the name-resolution failures were the fault's own symptom.
   - Faultline reported them and established nothing.
   - A transport error with a cause is an observation about the platform, and the verdict layer has
     no way to weigh it as one.
5. **Thin metrics on the foreign applications.**
   - 12 error-ratio calls returned *unavailable*. Ten were on the DeathStarBench applications,
     which send no span metrics as shipped. The shop's two were services sending no spans during
     their faults (`frontend` in s8, `ad` in s56).
   - The pilot's finding 3 stands: there are about three minutes of history before each fault.
   - No `latency-p95` call was made on Hotel Reservation, so its reading stays unestablished.

**What the comparison does and does not show.**

- It shows Faultline as built for an alerting stack with a trace-derived topology, measured
  through a thin adapter on a benchmark whose faults are mostly Kubernetes object state, against
  an agent with kubectl.
- **It does not separate the gate's effect from the missing modality's**, because 20 attempts never
  reached a tool.

## The world and the key

- **No incident opened** on the live system, in the three sessions or at the close.
- **No world container restarted.** The counts at the close were the pre-run counts: checkout 6,
  frauddetection 1, accounting 6, email 2.
- **MemAvailable's lowest sample was 3.64 GiB**, at 21:01 in session 3, above the 2 GiB pause line.
  The session 2 check had read 3.81 before that.
- **`kind-worker2`, a node of the benchmark's cluster and not of the world, carried Docker's OOM
  flag from session 1 on.**
  - A process inside it was OOM-killed at some point between the session's first and last
    snapshots.
  - Which process is not recorded. The pause rules do not cover the benchmark's own nodes.
- **The key**: 0 occurrences in `collect`'s archive and in the records, shredded on the VM, and the
  directory removed. The rules are gone and the kill switch is off.

## Next

- Phase 7 continues at the owner's scale. **T7.1's headline** registers its own scale before it
  runs.
