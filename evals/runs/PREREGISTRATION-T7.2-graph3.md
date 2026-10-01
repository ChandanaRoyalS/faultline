# Pre-registration - T7.2 topology item 3: astronomy-shop's graph under SREGym, against v2's

**Written before anything of this run is changed. Nothing here is a result.** This is item 3 of
`docs/design/t7.2-topology.md`, "what the decision costs":

> Astronomy-shop under SREGym uses the same service names. Its graph is captured once from SREGym's
> own Jaeger, on the deployment, with a 1c-style deploy and no agent, and compared to the v2
> world's. If they match, one snapshot serves both. If they differ (a Kubernetes chart can wire
> differently from compose), it is its own snapshot.

**The two questions.**

1. **Does astronomy-shop under SREGym have v2's graph?** That means the same cross-service edges as
   the v2 snapshot of record, `docs/evidence/t7.2-topology/q121-v2-dependencies-1h.json` (22, with
   self-edges aside).
2. **Does SREGym's fault remove the edges triage needs from the live graph?** That is part of the
   case the design note made against option B (querying SREGym's `get_dependency_graph` during a
   run): *"the injected fault can remove the very edges triage needs"*. The case was argued and not
   measured.

## Decided by the owner, 2026-10-01, before this registration

- **A clean graph comes from SREGym's own recovery.** SREGym cannot deploy without a fault: its
  external-harness path deploys, injects and exits (`main.py:494-498`), and no flag skips the
  fault. So the run deploys exactly as 1c did, with the same problem. It then undoes the fault
  with SREGym's own recovery for it, run verbatim, and captures an hour that begins ten minutes
  after the recovery. Driving SREGym's deploy code from a script of our own, with no problem, was
  the alternative. It was rejected as less like a benchmark run.
- **One read-only read of the graph while the fault is in.** It answers question 2 at no cost.

## Read before registration (SREGym at `46c853db`, its submodules as 1c checked them out)

- **The application.**
  - The vendored chart is `opentelemetry-demo` 0.40.4, **`appVersion: 2.2.0`, the v2 world's tag**.
  - SREGym's overrides (`sregym/service/apps/values/astronomy-shop-fixes.yaml`):
    - `accounting` runs a nightly image, one commit after 2.2.0, which changes only its
      `Consumer.cs`;
    - the load generator gets a different exporter sidecar;
    - the collector's metrics are not exported;
    - and, in `AstronomyShop.deploy`, the chart's Prometheus and **the browser traffic are off**.
- **The load.** The chart's Locust runs **10 users**. The v2 world runs 25
  (`compose/world-v2.override.yml`), so the same paths should appear at about 40 % of the rate.
- **Where the traces go.** The conductor deletes the chart's own Jaeger
  (`Jaeger.create_external_name_service`). Every Jaeger name in the application's namespace
  becomes an `ExternalName` to `otel-collector.observe`, which exports to SREGym's central Jaeger.
  - That Jaeger is `jaegertracing/all-in-one:1.57` (Jaeger v1, where the v2 world runs v2), in
    memory, capped at **25,000 traces**, behind the service `observe/jaeger-out:16686`.
  - SREGym's MCP tool `get_dependency_graph` reads exactly this Jaeger, at `/api/dependencies`.
  - **The capture reads the same endpoint, so it is the graph SREGym's own tool would return.**
- **The fault** (`wrong_dns_policy_astronomy_shop`) sets `frontend`'s `dnsPolicy: None` with
  `8.8.8.8` as the only resolver and no search domains. **Its recovery**
  (`VirtualizationFaultInjector.recover_wrong_dns_policy`) is two `kubectl` commands: a JSON patch
  removing `dnsPolicy` and `dnsConfig`, then a `rollout restart`. `g3_vm.sh` runs them verbatim
  and then checks the result.
- **Why the fault should silence `frontend` altogether.** The chart points `frontend`'s exporter
  at `http://$(OTEL_COLLECTOR_NAME):4317`, with `OTEL_COLLECTOR_NAME=otel-collector`, a short name
  only cluster DNS can resolve. So the fault should cut `frontend`'s own spans as well as its
  calls.
- **The host.** 1c's teardown left the deployment with:
  - no cluster, no tools, and no `~/.kube`, `~/cache_dir` or `~/t7.2-1c`;
  - the firewall rules removed and inotify back to 128 / 124,032;
  - the kill switch off.

  **1c measured FITS**, with MemAvailable at least 5.83 GiB with the application up. This run holds
  the application for about 85 minutes, where 1c's P2 held it for 10. The first step re-reads all
  of this before anything changes.

## What the run changes, and how each change is undone

These are 1c's changes, as amended by its Addendum 1, with one addition. All of them are made and
undone by stages of one script, `g3_vm.sh` (committed with this registration as
`docs/evidence/t7.2-topology/g3_vm.sh.txt`).

| change | stage | undone by |
|---|---|---|
| the executor's kill switch **on** | `killswitch-on` | `killswitch-off` |
| `INPUT` tcp 9954 and 8000 dropped unless from `lo`; inotify 1024 / 1,048,576 | `host-on` (sudo) | `host-off` (sudo) |
| kind v0.27.0, kubectl v1.32.1, Helm v4.3.0 in `~/t7.2-1c/bin`, each checked against its published sha256; SREGym at the pin with only its astronomy-shop submodules; its venv | `install` | `cleanup` |
| the cluster, its `kind` network and node image; `~/t7.2-1c/kubeconfig`, copied to `~/.kube/config` | `cluster` | `teardown`, `cleanup` |
| SREGym's stack and astronomy-shop, the fault, SREGym's 9954 port-forward, `~/cache_dir` | `deploy` | `teardown`, `cleanup` |
| **new:** a port-forward to `observe/jaeger-out` on **127.0.0.1:26686**, killed by its PID after each read | `faultread`, `capture` | the same stage; `teardown` checks it |
| the fault recovered on `frontend` | `recover` | nothing to undo: the cluster is deleted |

**1c's sampler runs unchanged** (`kind_measure_1c.py`, copied to `/tmp`), which is why the run keeps
1c's directory, `~/t7.2-1c`. **Teardown's process patterns live inside the script**, not on the
`ssh` command line, and are anchored. 1c's T1 matched its own shell; this cannot.

## The procedure

On the Mac, `VM=deploy@<address>`. Each stage is one line, its output saved to
`~/Downloads/g3-<stage>.txt` and read before the next:

```
ssh "$VM" 'bash /tmp/g3_vm.sh <stage>'
```

`host-on` and `host-off` go through `ssh -t ... sudo bash`.

0. **Copy** `g3_vm.sh`, and 1c's sampler from the repository, to `/tmp` on the VM.
1. **`preread`**, read-only.
   - **The gate, all of it:**
     - 35 containers running and no world alert firing;
     - the tools absent, and `~/.kube`, `~/cache_dir` and `~/t7.2-1c` absent;
     - ports 8000, 9954, 16443 and 26686 free;
     - no reboot pending;
     - the kill switch off and `git status` empty;
     - Docker Hub's anonymous allowance at 100 remaining.
   - **If anything else**, stop and read. A lower allowance waits until it reads 100.
2. **`killswitch-on`**, confirmed `"kill_switch":true`.
3. **`host-on`**, with both rules listed back.
4. **`install`**. A checksum mismatch stops the run.
5. **`cluster`**: SREGym's `kind/setup_kind_cluster.sh`, then the kubeconfig copied to
   `~/.kube/config` and compared.
6. **The port watcher first**: `g3_ports.sh` in a second terminal on the Mac, under
   `caffeinate`. It is 1c's step 8 with its output renamed.
7. **`deploy`**:
   `uv run python main.py --use-external-harness --problem wrong_dns_policy_astronomy_shop --agent demo`.
   It runs with `KUBECONFIG` unset, Helm's homes under `~/t7.2-1c/helm`,
   `API_BIND_HOST=127.0.0.1` and no model key. The wall limit is 45 minutes. The time it exits is
   kept.
8. **`faultread`**, read-only, at five minutes after the deploy exits:
   - `frontend`'s DNS settings and its pod's `resolv.conf`;
   - SREGym's Jaeger services;
   - `/api/dependencies` with a lookback of exactly the time since the deploy exited, so every
     span in it was made with the fault in.
9. **`recover`**: SREGym's two commands, then `rollout status`. **It passes when**:
   - `frontend`'s `dnsPolicy` reads `ClusterFirst`;
   - its pod's `resolv.conf` names no `8.8.8.8`;
   - every pod in `astronomy-shop` is `Running` and ready.

   Otherwise, stop and read.
10. **`hold`**, started with `nohup` so no connection has to last.
    - It runs 1c's sampler for **70 minutes** (`W 4200`), then `capture`:
      - `/api/dependencies` at lookbacks of **30 and 60 minutes**, each checked to be JSON;
      - the services;
      - whether the store still holds traces of `frontend-proxy`, `frontend` and `checkout`
        between 62 and 58 minutes back. That is the check on the 25,000-trace cap.
    - The capture's hour therefore begins ten minutes after the recovery.
    - The replies and the log are copied to the Mac.
11. **Teardown, whatever happened**:
    - `teardown`: the port-forwards killed and checked, the cluster deleted, the network and the
      node image removed;
    - `host-off`;
    - `cleanup`, after the copies;
    - `killswitch-off`, with `git status` empty;
    - then `kind_measure_1c.py P3 300` and `incidents`, and both scripts deleted from `/tmp`.

**The stop rule.** Teardown runs at once, and the run reads as INCONCLUSIVE unless its capture is
already taken, if:

- step 1's gate fails;
- a checksum mismatches;
- the deploy does not exit 0 with `Fault injected`;
- the port watcher finds 9954 or 8000 answering from outside;
- the recovery check fails;
- any sample shows MemAvailable under **1.0 GiB**;
- any of the 35 restarts, is OOM-killed or stops;
- a world alert not firing at step 1 starts.

The sampler records the hold; it cannot act during it. So a breach found when the hold is read
is recorded, and the capture is judged by whether the application ran steadily through its hour.

## The outcomes, stated now

**Question 1**, read from the 60-minute reply's cross-service edges against the snapshot of
record's 22, self-edges aside:

| outcome | when | what follows |
|---|---|---|
| **SAME** | the two sets are equal | **one snapshot serves both**: astronomy-shop under SREGym is scored against `q121-v2-dependencies-1h.json`, and the design note says so |
| **SAME, RARE EDGES UNSEEN** | the reply lacks only some of the four rarest flag reads, nothing else differs, and the hold check found traces at the hour's start. The four are ad, fraud-detection, product-reviews and recommendation → flagd, at 5 calls an hour each on v2, and Q122's census missed all four in 138 traces | as SAME, with the unseen edges named. An hour at 40 % of the load is not evidence that they are absent |
| **DIFFERENT** | any other edge is missing, or any edge is not in the snapshot | each difference is named. The 60-minute reply becomes **astronomy-shop's own snapshot of record**, committed, and loading by application is registered as a build before any scored run |
| **INCONCLUSIVE** | the run did not reach a capture as registered, or the hold check found no trace at the hour's start **and** the sets differ | the cause is named. Any retry is an addendum first |

**Question 2**, read from the fault read against the clean capture:

| outcome | when |
|---|---|
| **YES** | the fault read lacks `frontend-proxy → frontend` and every edge of the order path that the clean capture holds: `frontend → checkout`, `checkout →` its six callees, and `shipping → quote` |
| **PARTLY** | some of those edges are present in the fault read; each is named |
| **NO** | all of them are present |

## Predictions, stated now

- **Question 1: SAME.** The images are 2.2.0's and the instrumentation is the application's own.
  Kubernetes changes the addresses, not who calls whom.
  - The four rare flag reads are periodic, not driven by load, so they appear too.
  - Self-edges may differ (Jaeger v1 against v2), and they are set aside by definition.
  - **The two predictions most at risk are**:
    - an edge Kubernetes adds through a proxy or a sidecar that compose has none of;
    - the rare reads.
- **The 30-minute reply** holds a subset of the 60-minute one.
- **The cap holds the hour**: at 10 users the hour is a few thousand traces, well under 25,000, so
  the check finds traces of all three services.
- **Question 2: YES, and more than the order path.**
  - With `frontend`'s exporter unable to resolve `otel-collector`, the fault read holds no edge into
    or out of `frontend`, and nothing that only `frontend` drives: no order path, no storefront
    edges.
  - What remains is `load-generator → frontend-proxy`, `load-generator → flagd`, and at most a
    rare flag read.
- **The run.**
  - The deploy takes **5 to 10 minutes** (1c: 5m31s), and the recovery under 2.
  - MemAvailable stays **at or above 5 GiB** through the hold. 1c's P2 minimum was 5.83, and an
    hour more of OpenSearch and Kafka costs some of that.
  - None of the 35 is touched, no world alert fires, and both ports time out from outside.
- **$0.** No model is called and no key is in the environment, as in 1c.

## What is recorded

- **The result.** `evals/attempts/T7.2-graph3/RESULT.md` holds:
  - both outcomes by the tables above;
  - every prediction, held or not;
  - every edge difference;
  - every departure from this registration.
- **The evidence** goes verbatim to `docs/evidence/t7.2-topology/`:
  - the outputs, as `g3-*.txt`;
  - the three replies, as `g3-fault-deps.json`, `g3-deps-30m.json` and `g3-deps-60m.json`.

  The VM's address is withheld, as in 1b and 1c.
- **The design note's item 3** records the outcome. On DIFFERENT, a Q-row is opened for loading
  by application.
