# Pre-registration - T7.2 step 1b, a kind cluster started on the deployment and measured

**Written before any of 1b's changes are made. Nothing here is a result.** `docs/design/t7.2-scoping.md`
§5 orders T7.2's work, and steps 2, 3 and 4 are done. Step 1b reads:

> **Start a kind cluster on the deployment and measure it**, with the world running, before
> anything is built against it. No model spend. Two outcomes and both are useful: it fits, and
> option 2's *stop the world* disappears; or it does not, and the second-host question is answered
> by a measurement rather than by a capacity table [...]. **Do the pending kernel update and reboot
> first**, so a deferred restart is not carrying a cluster.

The host was chosen by the owner on 2026-09-30: **the deployment VM** (the scoping note's
*deployment*, serving `faultline.chandanasorakundla.com`), not the Mac and not a second host.

**The question.** Can the deployment carry the cluster SREGym creates, with its world and platform
running, and leave room for an application? It can answer *does not fit* outright. It can answer
*fits* only for an idle cluster. Whether an application fits is 1c's question, and 1c is registered
on 1b's result.

## Read before registration (2026-09-30, read-only)

**The deployment** (`vm_baseline.py`, 08:51 UTC; kept in
`docs/evidence/t7.2-kind-host/`):

- **The machine.** 8 AMD EPYC-Milan cores, 15.6 GiB, no swap, 424 G of 464 G disk free. Ubuntu
  24.04.4, kernel 6.8.0-139, up 8 days 19 hours. **A reboot is pending again**: the new kernel is
  `linux-image-6.8.0-142-generic`.
- **Headroom.** MemAvailable was 11.01 to 11.06 GiB over a minute (used 4.6 GiB, page cache 8.3
  GiB). Load 0.31 to 0.44.
- **Docker.** 29.8.0 on cgroup v2 with the systemd driver. 35 containers running of 38: the world's
  27 and the platform's 8, as `deploy/README.md` §3.10 derives.
- **One figure to explain.** The platform container `faultline-deploy-faultline-1` holds **4.14
  GiB**. On 2026-09-21 the scoping note measured it at 698 MiB. Step 0 below reads its anonymous and
  file-backed split before the reboot resets it.
- **What kind needs from the host.** inotify is at **128 instances / 124,032 watches**, against
  SREGym's kind README asking for 1024 / 1,048,576. `vm.max_map_count` is 1,048,576, above
  OpenSearch's 262,144. `/run/udev` exists (the node image mounts it). IP forwarding is on.
- **Tools.** kind, kubectl and helm are absent; python3 is 3.12.3 and git 2.43.0. The check ran in a
  non-login shell, so a tool installed on a login PATH (uv, which §3.10 uses) may have been missed.
  P0 re-checks on a login shell.
- **Egress** from the host reaches ghcr.io, Docker Hub, quay.io, raw.githubusercontent.com,
  github.com, pypi.org, dl.k8s.io and kind.sigs.k8s.io.

**What SREGym asks for** (at `46c853db`, the pin the harness read used):

- `kind/kind-config.yaml` is **one control plane and three workers**. All four use
  `ghcr.io/sregym/kind-node` pinned by digest (`sha256:ccab5d6c...85b93`, built on
  `kindest/node:v1.32.1`), and all four mount `/run/udev`. The default CNI is off.
- `kind/setup_kind_cluster.sh` creates the cluster, applies Calico `v3.27.0` from
  raw.githubusercontent.com, waits up to 300 s for Calico and 120 s for every node to be `Ready`,
  and removes `~/cache_dir/cluster_baseline_state.json`. It needs kind and kubectl, and nothing else.
- SREGym's own CI installs **kind `v0.27.0`**, which pins the kind version below. Helm, uv and
  SREGym's Python environment are 1c's, not 1b's, so none is installed here.
- The README says the 21-problem SREGym-Lite set *"can run easily on a Kind setup with 8 vCPU and
  16 GB of memory"*. That is this whole machine, before Faultline's 4.6 GiB.

## What 1b changes, and how each change is undone

| change | made by | undone by |
|---|---|---|
| kernel 6.8.0-139 → 142, one reboot | step 0, `deploy/README.md` §3.10 as written | not undone; it is the pending update |
| the executor's kill switch **on** | step 1, §3.11 as written | step T4, the same `sed` in reverse |
| `kind` v0.27.0 and `kubectl` v1.32.1 in `~/t7.2-1b/bin`, checksums verified | step 3 | step T3, `rm -rf ~/t7.2-1b` |
| inotify raised to 1024 / 1,048,576 at runtime, not persisted | step 4 | step T2, set back to the values P0 reads (a reboot also resets them) |
| SREGym cloned at `46c853db` into `~/t7.2-1b/SREGym` | step 5 | step T3 |
| a four-node kind cluster, its `kind` Docker network, the node image, `~/.kube/config` | step 6 | step T1; `~/.kube` is removed only if P0 found it absent |

The kill switch is on for the duration because §3.11 says to *"turn it on when the world is being
worked on by hand [...] or after anything unexpected: it costs nothing and it interrupts nothing"*.
Investigation continues. If the world pages during 1b, the deployment investigates as it always
does. That spends model money and writes an incident, and the RESULT records any such incident as
caused by 1b.

## The procedure

`VM=deploy@<address>` on the Mac. Every step after the reboot is one line run from the Mac, so none
leaves a terminal on the VM; the reboot itself follows §3.10's own ssh session, as that section says. Sudo steps use `ssh -t`. Each step's output is saved to `~/Downloads/1b-*.txt` and read
before the next step.

0. **The reboot, first.** Read the platform container's memory split while it still holds the 4.14
   GiB (read-only), then follow `deploy/README.md` §3.10 exactly as written, including the
   provisioning command it says to run last and §3.6's checks from another machine. Wait **15
   minutes** after the reboot, well past the baseline gate's 300 s.
1. **The kill switch on** (§3.11). `healthz` must answer `"kill_switch":true`.
2. **P0**: `kind_measure.py P0 600`, ten minutes, no cluster.
3. **Install** kind and kubectl into `~/t7.2-1b/bin`, each checked against the `sha256` its own
   release publishes. A mismatch stops 1b.
4. **inotify** raised to SREGym's values. The values it replaces are printed first.
5. **SREGym** cloned at `46c853db`. `git log --oneline -1` must print `46c853d`.
6. **The cluster**: `bash kind/setup_kind_cluster.sh` with `~/t7.2-1b/bin` first on the PATH,
   timed. If it fails, `kind delete cluster` and one more attempt. A second failure is an outcome
   (below), not a reason to retry.
7. **P2**: five minutes after the script reports success, `kind_measure.py P2 600`, ten minutes.

Teardown, whatever the outcome:

- **T1**: `kind delete cluster`, `docker network rm kind`, and the node image removed by its digest.
- **T2**: inotify set back.
- **T3**: `~/t7.2-1b` removed, and `~/.kube` too if P0 found it absent.
- **T4**: the kill switch off, and `healthz` answering `"kill_switch":false`.
- **T5**: `kind_measure.py P3 300`, then both helper scripts deleted from `/tmp`.

**The stop rule.** If step 6 or P2 shows any of the 35 containers restarted, OOM-killed or stopped,
the teardown runs at once and the outcome is **does not fit**. So does MemAvailable under 2 GiB in
any sample, or a world alert that was not firing at P0's end.

`kind_measure.py` is committed with this registration (`docs/evidence/t7.2-kind-host/kind_measure.py.txt`)
and runs unchanged in all three phases. At the start and end of each phase it records:

- every container's state, restart count, OOM flag and memory;
- the platform container's anonymous and file-backed memory;
- the world's firing alerts, from Alertmanager on `:9093`;
- the kind nodes and every pod with its restarts;
- the tools, inotify, and whether `~/.kube` exists.

Every 30 s it samples MemAvailable, load, memory and CPU pressure stall (PSI `avg10` and `avg60`),
and the firing alerts. Its SUMMARY line is what the criteria are read from.

## The outcomes, stated now

The application estimate these thresholds rest on is for astronomy-shop, the SREGym application
Faultline knows best:

- **Faultline's own v2 world** measured **3,327 MiB** for its 28 containers on 2026-09-22.
- **SREGym's `full` profile adds its measured peaks**: OpenSearch 1,096 MiB, Grafana 475 MiB and
  OpenEBS NDM about 190 MiB.
- **Allowed for the in-cluster Prometheus and Jaeger**: about 500 MiB.

That is **about 5.5 GiB**, which 1c measures rather than trusts.

| outcome | when (read from P2's snapshots and SUMMARY against P0's) | what follows |
|---|---|---|
| **FITS** | the cluster `Ready` on the first or second attempt; MemAvailable's P2 minimum **≥ 7.0 GiB** (the estimate plus 1.5 GiB); none of the 35 restarted, OOM-killed or stopped; no alert firing at P2's start or in its window that was not firing at P0's end; memory PSI `some` avg60 max **< 5**; load1 max **< 8** | 1c, astronomy-shop deployed through SREGym's own path with no agent and no model, registered next |
| **FITS, TIGHT** | as FITS, but the minimum between **5.5 and 7.0 GiB** | reported as is; whether 1c runs on this box is the owner's decision |
| **DOES NOT FIT** | a second cluster failure; or the minimum **< 5.5 GiB**; or any of the 35 restarted, OOM-killed or stopped; or the stop rule fired | the second-host question is answered by this measurement: scoping §3's shape 1 or 3, the owner's choice |

**The prediction, stated now: FITS.** Four idle nodes with Calico take **1.5 to 2.5 GiB**
together. MemAvailable's P2 minimum lands **1.5 to 3.0 GiB under P0's mean**, which puts it near
8 to 9.5 GiB. Load1 stays under 3 and memory PSI `some` avg60 under 1. No container of the 35
restarts, and no alert fires. **The cluster comes up on the first attempt**, inside the script's
own timeouts.

**What would falsify the reading and not only the prediction**: a P0 MemAvailable far from the
baseline's 11.0 GiB. After a reboot, page cache and the platform container both start small, so P0
may read higher than the baseline. The criteria compare P2 with P0 of the same boot, so that shift
is not read as the cluster's cost.

## What is recorded

`evals/attempts/T7.2-1b-kind-host/RESULT.md` holds:

- step 0's memory split and the reboot's checks;
- P0, P2 and P3 verbatim, with the setup script's own output;
- the outcome by the table above;
- every prediction held or not;
- any incident the deployment opened during 1b.

`docs/design/t7.2-scoping.md` step 1b is struck with a pointer to it.
