# RESULT - T7.2 step 1b, a kind cluster on the deployment

**Outcome: FITS.** This follows the registration's own table
([`PREREGISTRATION-T7.2-1b.md`](../../runs/PREREGISTRATION-T7.2-1b.md)). SREGym's four-node
cluster with Calico came up on the first attempt, on the deployment VM, with the world and the
platform running. After it had settled, **10.63 GiB** was still available at its lowest. None of
the 35 containers restarted, stopped or was OOM-killed. No alert fired, and the deployment opened no
incident. So the scoping note's option 2, *stop the world, run the benchmark, restart it*, is not
needed **for the cluster**. Whether an application fits beside it is 1c's question, which is what
the registration makes FITS lead to.

Run on 2026-09-30, 09:06 to 11:07 UTC, by the owner from the Mac. Every output is kept verbatim in
[`docs/evidence/t7.2-kind-host/`](../../../docs/evidence/t7.2-kind-host/) (`1b-*.txt`). They live
beside the registration's evidence because that directory is excluded from the formatting hooks.
$0, no model call.

## The criteria, read

P2's snapshots and SUMMARY, read against the end of P0, as registered:

| criterion | needed for FITS | measured |
|---|---|---|
| the cluster `Ready` | first or second attempt | **first**, in 1m09.7s (10:19:51-10:21:01); 4 nodes `Ready`, v1.32.1 |
| MemAvailable, P2 minimum | ≥ 7.0 GiB | **10.63 GiB** (mean 10.74, max 10.80) |
| any of the 35 restarted, OOM-killed or stopped | none | **none**: every container's restart count, OOM flag and start time at P2's end equals P0's end |
| alerts not firing at P0's end | none at P2's start or in its window | **none**: 0 firing at P0's end, at P2's start, in all 21 samples, and at P2's end |
| memory PSI `some` avg60, max | < 5 | **0.00** |
| load1, max | < 8 | **1.07** |

The stop rule never fired. The lowest sample in any phase was 10.63 GiB, against its 2 GiB floor.

## What the cluster costs

- **Memory.** The four node containers held **1,540 MiB at P2's start and 1,557 MiB at its end**:
  the control plane about 670 MiB (etcd, the API server, the controller manager and the
  scheduler), the three workers 263 to 350 MiB each. MemAvailable fell **1.59 GiB** from P0's
  mean (12.22) to P2's minimum (10.63), and 1.48 GiB mean to mean. The 35 containers held 3,178 MiB
  at P0's end and 3,249 MiB at P2's end, within their own drift.
- **CPU.** PSI CPU `some` avg60 rose from 0.01-0.12 in P0 to **1.36-1.53** in P2, a cost the
  registration did not predict. It is the control plane's steady work: the control-plane node sat
  at about 15.6 % of a core in both snapshots, the workers 3 to 8 %. Load1 stayed at or under 1.07.
- **The pods.** 16 system pods, all `Running` with 0 restarts over their first 15 minutes: Calico
  (4 nodes and the controllers), CoreDNS (2), kube-proxy (4), etcd, the API server, the controller
  manager, the scheduler and the local-path provisioner.

## The predictions

| prediction | held? |
|---|---|
| FITS | **held** |
| the four idle nodes take 1.5 to 2.5 GiB | **held**, at the low edge: 1.54-1.56 GiB |
| MemAvailable's P2 minimum 1.5 to 3.0 GiB under P0's mean | **held**: 1.59 GiB |
| ...*"which puts it near 8 to 9.5 GiB"* | **wrong**: 10.63 GiB. The range was derived from the pre-reboot baseline (11.0 GiB). P0 of the same boot read 12.22, as the registration warned it might, and the criteria compare P2 with P0, so the outcome does not move |
| load1 under 3; memory PSI `some` avg60 under 1 | **held**: 1.07; 0.00 |
| no container of the 35 restarts; no alert fires | **held** |
| the cluster comes up on the first attempt, inside the script's own timeouts | **held**: Calico rolled out and every node went `Ready` inside the script's waits |

## Step by step

- **Step 0, before the reboot** (09:06). The platform container's 4.14 GiB was **not the
  application**. Its cgroup held 72 MB anonymous and 1.8 MB file-backed memory. The rest was
  **kernel memory: 4.38 GB of slab** (`kernel 4377083904`, `slab 4376329048`). The ingest process
  itself had an RSS of 100 MB after 8 days 19 hours up. Kernel slab charged to a container is the
  kernel's own caches (dentries and inodes, typically), so it is not a leak in the process. How
  much of it was reclaimable was **not read**, and the reboot has reset it: the registration's
  query took `slab` whole, not `slab_reclaimable` and `slab_unreclaimable`. After the reboot the
  same container held 119-122 MiB.
- **Step 0, the reboot** (`sudo reboot` 09:06:16; up about 09:07; kernel **6.8.0-142**, no reboot
  pending). All 35 containers came back by themselves, which is the 2026-09-11 restart-policy fix
  holding a second time (09-21 was the first). §3.10's two world commands ran at
  09:18:42-09:19:19 and exited 0. Grafana was recreated and the dashboards and the
  `faultline-self-metrics` datasource were re-provisioned, created rather than updated, as
  §3.10 describes. §3.6 from the Mac:
  `{"status":"ok"}`, then 401, 404, 401, 404, and `:3000` and `:3200` timed out (`000`).
- **Step 1** (09:34:18). The switch was set and the executor recreated. `healthz` answered only
  at 10:17:13 (below).
- **Step 2, P0** (09:51:00-10:01:02). Clean: MemAvailable 12.09-12.27 GiB, load1 at most 0.46,
  no pressure, no alert. `~/.kube` was absent. checkout and accounting each showed 6 restarts and
  fraud-detection 1. **All seven happened at boot**, while they waited for kafka: the containers
  started at 09:07:12, before P0 and unchanged through P3.
- **Steps 3-5** (10:18). kind v0.27.0 and kubectl v1.32.1 were installed, with `kind: OK` and
  `kubectl: OK` against their releases' own `sha256`. inotify went 128 → 1024 and 124,032 →
  1,048,576. SREGym checked out at `46c853db`.
- **Step 6** (10:19:51-10:21:01). SREGym's `kind/setup_kind_cluster.sh` ran unchanged: the node
  image by digest, Calico `v3.27.0`, and all nodes `Ready`. 39 containers were then running.
- **Step 7, P2** (10:26:03-10:36:06). Read above.
- **Teardown** (11:00-11:02).
  - T1: the cluster deleted, the `kind` network removed, the node image deleted by its digest, 35
    containers running.
  - T2: inotify back to 128 / 124,032.
  - T3: `~/t7.2-1b` and `~/.kube` gone.
  - T4: the kill switch off (`"kill_switch":false`), and `git status` on the VM empty.
- **P3** (11:01:52-11:06:52). Back to P0: MemAvailable 12.06-12.12 GiB, 35 of 38 running, no
  restart, no alert, inotify restored, no tools, no `~/.kube`. Both helper scripts were deleted
  from the VM's `/tmp`.
- **Incidents** (11:09, `1b-incidents.txt`). None was opened in the three hours covering the whole
  of 1b, read from the deployment's own `incidents` table. No model money was spent by the
  deployment during 1b.

## Where the run departed from the registration, and what each departure moves

- **The post-reboot steps did not run in an ssh session.** The first reconnection was attempted
  while the VM was still booting, and it timed out. The next five lines were then pasted into the
  Mac's own shell, not the VM's: `uptime`, `uname` and `docker ps` read the Mac (its v2 world
  showed 31), both `cd ~/faultline` failed there, and nothing ran on either machine. §3.10's
  commands were then run unchanged as single-line `ssh "$VM" '...'` commands, in a login shell so
  `uv` was on the PATH. **Nothing moves**: same commands, same host. The trap is §3.10's own
  warning about pasting blocks, met from the other side, and the registration already names
  one-line ssh for every later step.
- **The kill switch was confirmed after P0, not before it.** `healthz` was queried at 09:34 before
  the recreated executor was listening (`curl: (7)`). The switch file read `"1"` from 09:34:18, and
  the executor started then with no restart after. P0 then ran, and `healthz` answered
  `"kill_switch":true` at 10:17:13, before anything was installed. **Nothing moves**: the switch
  guards approvals, none was presented, and P0 measures memory and load, which the switch does not
  touch.
- **P0 ran twice**, back to back. The second run, 09:51-10:01, overwrote the first's file and is
  **P0 of record**. The first run's SUMMARY survives only in the terminal (MemAvailable min 12.01,
  mean 12.26, no restart, no alert) and agrees with it.
- **The fifteen minutes were counted from 09:18:56**, the last telemetry recreate, not from the
  reboot at about 09:07. That is stricter than the registration.
- **Two capture lines are edited.** In `1b-step4.txt` and `1b-T2.txt`, `ssh -t` closes with
  `Connection to <address> closed.`, and the address is replaced with `<the VM>`. The repository
  does not record the VM's address (`deploy/README.md` writes `ssh deploy@...`). No other byte is
  changed, carriage returns included.
- **The captures live in `docs/evidence/t7.2-kind-host/`**, not beside this file as the
  registration's *"holds"* implied. That directory is excluded from the formatting hooks, so a
  capture's trailing whitespace and `\r` survive the commit.

## What follows

**By the registration, FITS leads to 1c.** 1c is astronomy-shop deployed through SREGym's own
path, on this host, with no agent and no model, registered next. 1b cannot answer 1c's question,
because an application is most of the cost. The registration's estimate for astronomy-shop under
SREGym's `full` profile is about 5.5 GiB, and 10.6 GiB was left. That margin makes 1c worth
measuring, but it proves nothing about 1c. 1c needs what 1b deliberately did not install: Helm 4,
uv, SREGym's Python environment, and the application submodule. `docs/design/t7.2-scoping.md` step
1b is struck with a pointer here.
