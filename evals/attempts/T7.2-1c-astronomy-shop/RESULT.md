# RESULT - T7.2 step 1c, astronomy-shop deployed by SREGym beside the world

**Outcome: FITS.** This reads the registration's own table
([`PREREGISTRATION-T7.2-1c.md`](../../runs/PREREGISTRATION-T7.2-1c.md), as amended by its
Addendum 1). SREGym's own external-harness path deployed its whole `full`-profile stack and the
SREGym-Lite problem `wrong_dns_policy_astronomy_shop` on the deployment, beside the world and the
platform. The deploy took 5m31s and exited with `Fault injected`. Over the ten minutes that
followed, all 67 pods were running and ready, and none restarted.

MemAvailable stayed at or above **5.83 GiB**, against FITS's 3.0. None of the world's 35
containers was touched, no alert fired, and the deployment opened no incident. SREGym's two
public listeners stayed closed from outside.

**So the host question is settled for Astronomy Shop: T7.2 runs on the deployment.** The second
host (scoping §3, shape 1) is not needed for it. The next step is scoping step 5: where topology
comes from on an application Faultline does not know.

Run on 2026-09-30 (attempt 1, INCONCLUSIVE) and 2026-10-01 (the retry under Addendum 1), by the
owner from the Mac. Captures are verbatim in
[`docs/evidence/t7.2-kind-host/`](../../../docs/evidence/t7.2-kind-host/) (`1c-*.txt`), with the
VM's address withheld. $0: no model was called, and no key was in the run's environment.

## The criteria, read

P2 (06:51:52-07:01:59, 2026-10-01) is read against P1's end (06:24). Under Addendum 1, P1's end is
the reference for the 35 and for the alerts.

| criterion | needed for FITS | measured |
|---|---|---|
| the deploy | exits 0 with `Fault injected` | **exit 0**, `✅ Fault injected for problem` at 06:46:50; 06:41:20-06:46:51, **5m31s** |
| the pods | all `Running` or `Completed` at P2's start and end, none restarting in P2 | **67 of 67** `Running` and ready at both, in six namespaces (`astronomy-shop`, `observe`, `sregym`, `openebs`, `kube-system`, `local-path-storage`); **0 restarts in P2** |
| no pod OOM-killed | none | **none.** The one pod with restarts, `product-catalog` (3), last terminated `Error`, exit 1, at 06:45:26: during the deploy, while its Postgres came up. Its limit of 20 MiB was not what killed it |
| MemAvailable, P2 minimum | ≥ 3.0 GiB | **5.83 GiB** (mean 5.96, max 6.07) |
| the 35 | none restarted, OOM-killed or stopped | **none**: every restart count, OOM flag and start time at P2's end equals P1's end |
| alerts | none not firing at P1's end | **none**: 0 at P1's end, at P2's start, in all 21 samples and at its end |
| memory PSI `some` avg60, max | < 5 | **0.00** |
| load1, max | < 8 | **2.13** |
| the ports, from outside, while 9954 was served | both fail | **`000` and `000`**. At 06:44:30 the VM showed `127.0.0.1:8000`, from `API_BIND_HOST`, and `0.0.0.0:9954`, from the hard-coded port-forward, as read at source. The firewall rules held. **Note, 2026-10-02** ([item 4's Social Network RESULT](../T7.2-graph4-social/RESULT.md)): ufw's default-deny `INPUT` policy also drops both ports, so `000` tested ufw and the rules together, never the rules alone |

The stop rule never fired. The lowest sample was 5.83 GiB, against its 1.0 GiB floor.

## What the application costs

- **The node containers** held 1,852 MiB idle at P1's end. They held **7,690 MiB at P2's start and
  7,839 MiB at its end**, so the stack and the problem added **about 5.9 GiB**. `kubectl top`
  read the four nodes at 1,618 / 2,473 / 1,364 / 2,368 MiB.
- **The thirty largest pods**, by working set (`kubectl top pods`, so a floor for each namespace):
  - `astronomy-shop` at least 3,511 MiB. OpenSearch 841, Kafka 509 and Grafana 400 lead it.
  - `kube-system` at least 961 MiB.
  - `observe` (SREGym's Prometheus, collector and Jaeger agent) at least 316 MiB.
  - `sregym` (the MCP server) 87 MiB.
- **MemAvailable** fell 6.22 GiB from P0's mean (12.05) to P2's minimum, and 4.35 GiB from P1's
  minimum. The 35 containers' reported memory fell from 3,779 to 2,974 MiB over the same span,
  while their restart counts and states were unchanged and memory PSI stayed at 0. That is page
  cache given back under competition, not the containers losing anything they needed.
- **CPU** PSI `some` avg60 rose to 3.29 at most, against 1.50 in P1 and 0.12 in P0, and load1 to
  2.13. Eight cores carried it.

## The predictions

| prediction | held? |
|---|---|
| FITS | **held** |
| the deploy completes in 8 to 25 minutes | **wrong**: 5m31s. The pulls were faster than estimated |
| the application 3.0-4.5 GiB, SREGym's stack 0.8-1.5 GiB, the cluster's 1.55 GiB on top | **held, combined**: about 5.9 GiB over the idle cluster, at the top of 3.8-6.0. `astronomy-shop`'s top-30 floor of 3.5 GiB is inside its range. SREGym's stack is not separable from the top-30 listing (floor 0.4 GiB), so its own range is **not checkable** |
| MemAvailable's P2 minimum 5.5 to 8.5 GiB under P0's mean | **held**: 6.22 GiB under (5.83 against 12.05) |
| load1 1.5-5; CPU PSI above 1b's 1.5 %; memory PSI under 1 | **held**: 2.13; 3.29; 0.00 |
| some pods start with restarts, *"the Kafka consumers before Kafka is up"*, and none in P2 | **half held**: one pod restarted during the deploy, and none in P2. But it was `product-catalog`, not a Kafka consumer |
| none of the 35 touched; no alert; pulls under the allowance; both ports time out | **held**. No pull was refused. The number of pulls was not counted |
| Addendum 1: P1 reads like 1b's P2, minimum 10.4-11.0 GiB | **wrong**: 10.18 GiB. The idle nodes held 1.85 GiB after 17 hours against 1.55 GiB fresh in 1b |

## Step by step

- **Attempt 1, 2026-09-30.** Steps 1 to 6 ran as registered (11:47-12:41). The deploy stopped in
  13 s on SREGym's fixed `~/.kube/config`, and was **INCONCLUSIVE**. That is read in full in
  Addendum 1.
- **R1** (06:14, 10-01). `~/.kube/config` was installed as an exact copy of the cluster's
  kubeconfig (`identical`).
- **P1** (06:14:41-06:24:43). The idle cluster after 17 hours: MemAvailable 10.18-10.37 GiB, load1
  at most 1.07, nothing restarted, no alert.
- **Step 8's watcher** started first, at 06:24:58, and waited.
- **R4, first try** (06:39). It never reached the VM. It ran in a new terminal window where `VM`
  was unset, so `ssh` was given an empty host (`Could not resolve hostname :`, exit 255). That is
  not an attempt: nothing ran on the VM.
- **The deploy** (06:41:20-06:46:51). The environment held no key-like variable (count 0). The
  API was on `127.0.0.1:8000`. The stack went up in this order:
  - metrics-server (two `ServiceUnavailable` while it came up, then ready);
  - OpenEBS;
  - Prometheus in `observe`;
  - Jaeger and the collector;
  - Loki skipped, as this mode does;
  - the MCP server and its port-forward;
  - the five Helm repositories and astronomy-shop.

  Then the workload started, and the fault patched `frontend`'s DNS policy. Helm's default homes
  were never created; `~/cache_dir` was, as registered.
- **Step 8** (06:44:30). The bindings were read on the VM, and both ports failed from outside.
- **P2** (06:51:52-07:01:59) and **step 9** (07:02-07:05): `kubectl top`, and `product-catalog`'s
  termination reason.
- **Teardown** (07:08-07:22), below.
- **Incidents** (07:14). None in the 22 hours to then, which covers both attempts.

## The teardown, and the mistake in it

**T1 as written killed itself.** `pkill -f "kubectl port-forward svc/"` matches every process whose
command line contains that text. The shell `ssh` started for T1 had that text in its own command
line, so `pkill` signalled it with the two port-forward processes, and T1 ended after its first
listing. **`kind delete cluster`, the network and the image were never reached.** T2 (07:08:10:
both firewall rules removed, inotify back to 128 / 124,032), T3 (`~/t7.2-1c`, `~/cache_dir` and
`~/.kube` removed, along with the `kind` binary) and T4 (the kill switch off and confirmed,
`git status` empty) then ran as registered.

**The first P3 (07:09-07:14) was read with the cluster still up.** It held 5.83 GiB, P2's figure.
It is kept as `1c-P3.txt` and is **not** the after-teardown reading. Its own `kind cluster: none`
is wrong for the same reason: its kind binary had been removed in T3.

**Finished at 07:16-07:17**, read first and then acted on, with patterns anchored so they could
not match their own shell:

- **No port-forward process was left.** The VM listened on neither 8000 nor 9954, and 9954 failed
  from outside (`000`). T1's `pkill` had signalled both port-forward processes at 07:08:04, six
  seconds before T2 removed the rules. **The window in which 9954 could have been open without
  the rules is not measured.** It is bounded by how long `kubectl port-forward` took to exit on
  SIGTERM, which is normally immediate. It was gone by 07:16:18.
- The four nodes were removed with `docker rm -f -v`, which is what `kind delete cluster` does,
  since T3 had removed the binary. The `kind` network was removed, and the node image deleted by
  its digest (`no sregym image left`). 35 containers were running.
- **P3 of record** (07:17:16-07:22:16). MemAvailable 11.71-11.72 GiB, 0.34 GiB under P0's mean of
  the day before. 35 of 38 running, no restart, no alert. inotify was 128, there were no tools,
  and `~/.kube`, `~/cache_dir` and `~/t7.2-1c` were all absent. The helper script was deleted
  from `/tmp`.
- **The incidents read** (07:14) came before this finish. The P3 of record covers 07:17-07:22 with
  no alert firing, but **the deployment's `incidents` table was not read again after 07:14**.

**The lesson is the one 1b's teardown did not need.** A process match that can see its own command
line is a self-match. Every later teardown uses anchored patterns or PIDs.

## What follows

**FITS sends T7.2 to scoping step 5**: deciding where topology comes from on a foreign
application, priced before the run (`docs/design/t7.2-scoping.md`). The DeathStarBench
applications, where ADR-0042 says the external claim should lead, were not measured here. Whether
each needs its own fit check is for step 6's registration.
