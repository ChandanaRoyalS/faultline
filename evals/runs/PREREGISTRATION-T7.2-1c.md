# Pre-registration - T7.2 step 1c, astronomy-shop deployed by SREGym beside the world

**Written before any of 1c's changes are made. Nothing here is a result.** Step 1b
([`PREREGISTRATION-T7.2-1b.md`](PREREGISTRATION-T7.2-1b.md),
[RESULT](../attempts/T7.2-1b-kind-host/RESULT.md)) found **FITS**: SREGym's four-node kind
cluster ran on the deployment beside the world. The nodes held 1.55 GiB, 10.63 GiB stayed
available, and nothing on the world restarted or paged. Its registration made 1c the next step on
FITS, because an idle cluster says nothing about the application, which is most of the cost.

**The question.** With the world and the platform running, can the deployment carry SREGym's
stack and one astronomy-shop problem, deployed by SREGym's own code the way a benchmark run
deploys it, and still leave room for the agent that would investigate it?

## Read before registration (2026-09-30, read-only)

**How SREGym deploys, at `46c853db`** (the pin 1b used):

- **`main.py --use-external-harness --problem <id>`** runs the conductor's `start_problem` and then
  **exits once the fault is injected**, leaving everything deployed. That makes it the benchmark's
  own path with nothing after the deploy. Its `deploy_app` installs, in order:
  - metrics-server (manifest from GitHub);
  - OpenEBS with its node-disk-manager (the `full` profile);
  - Prometheus in `observe`;
  - Jaeger and an OTel Collector;
  - SREGym's MCP server;
  - the application's Helm chart, then the problem's workload and its fault.

  Loki is skipped in this mode (`deploy_loki=not use_external_harness`), so **1c understates a
  real run by Loki's footprint**.
- **No model is called.**
  - **The agent:** `--agent demo` is the one registered agent with no container isolation and
    no pre-flight entry, so no agent image is built and no pre-flight call is made.
  - **The judge:** external-harness mode skips the judge's pre-flight check, and the judge
    backend `api` is a no-op context. The diagnosis judge builds its model client lazily, only
    when it grades, and nothing grades here.
  - **No keys:** no API key is put in the environment of the run.
- **The application.** `AstronomyShop.deploy` installs the vendored OTel Demo chart
  (`SREGym-applications/astronomy-shop`, chart `opentelemetry-demo`). It turns the chart's own
  Prometheus and the browser traffic off. In the `full` profile it keeps the chart's OpenSearch,
  Grafana and Jaeger. The chart's own memory limits sum to **4,500 MiB** over 21 components (the
  load generator's 1,500 MiB the largest), plus OpenSearch 1,100 MiB and Grafana 175 MiB.
- **The problem**: **`wrong_dns_policy_astronomy_shop`**. It is one of SREGym-Lite's astronomy-shop problems
  and needs no Khaos (which kind cannot host). Its fault sets the
  frontend's `dnsPolicy: None` with an external resolver.
- **What it opens on the host.** Both are found in the source, and both are handled below:
  - The conductor's API binds `API_BIND_HOST`, which defaults to **0.0.0.0**, on port 8000.
  - The MCP server is reached through `kubectl port-forward ... --address 0.0.0.0` on port 9954,
    hard-coded. That process is started with `Popen` and **outlives `main.py`**. The MCP server
    exposes cluster tools, and kind's nodes are privileged containers, so an open 9954 on a public
    VM is a route to the host.
- **Where it writes.** SREGym writes to `~/cache_dir` (its cluster baseline). Helm writes to
  `~/.config/helm`, `~/.cache/helm` and `~/.local/share/helm`, and kind to `~/.kube`, unless told
  otherwise. uv writes to its cache.
- **Versions.** SREGym asks for Helm ≥ 4.0, and its CI installs the latest. At the pin's date
  (2026-09-18) that was **v4.3.0** (tagged 2026-09-09), so 1c pins it. kind stays at v0.27.0 and
  kubectl at v1.32.1, as in 1b.

**The deployment** (`c1_preread.sh`, 11:36 UTC, kept in `docs/evidence/t7.2-kind-host/`):

- **Tools.** uv 0.12.10 is on the login PATH; helm, kind and kubectl are absent. Python is
  3.12.3.
- **Home paths.** `~/cache_dir`, `~/.kube`, the three Helm directories and `~/t7.2-1c` are all
  **absent**. Ports 8000, 9954 and 16443 are **free**.
- **Headroom.** 12.28 GiB available, load 0.35, 425 G free, 35 containers running.
- **Docker Hub.** The anonymous pull allowance for this address is **100 per hour, 100
  remaining**. The deploy pulls from Docker Hub, among others, and each worker pulls for itself.
- **The kill switch** is off and answering.
- **`git status` was not read.** The script's `docker compose exec` consumed the rest of the
  script from stdin, so that last check never ran. It was last read empty at 1b's T4 (11:01).

## What 1c changes, and how each change is undone

| change | made by | undone by |
|---|---|---|
| the executor's kill switch **on** | step 1, §3.11 | T4 |
| two host firewall rules: `INPUT` tcp 9954 and 8000 dropped unless from `lo` | step 1, `sudo iptables -I` | T2, `sudo iptables -D` for each |
| `kind` v0.27.0, `kubectl` v1.32.1, `helm` v4.3.0 in `~/t7.2-1c/bin`, each checksum verified | step 3 | T3, `rm -rf ~/t7.2-1c` |
| inotify 1024 / 1,048,576, runtime only | step 4 | T2, back to 128 / 124,032 |
| SREGym at `46c853db` in `~/t7.2-1c/SREGym`, with only the `SREGym-applications` and its `astronomy-shop` submodules; its venv from `uv sync --frozen` with `UV_CACHE_DIR=~/t7.2-1c/uv-cache` | step 5 | T3 |
| the cluster, its `kind` network, the node image; kubeconfig at `~/t7.2-1c/kubeconfig` (`KUBECONFIG`); Helm's homes under `~/t7.2-1c/helm` (`HELM_CONFIG_HOME`, `HELM_CACHE_HOME`, `HELM_DATA_HOME`) | steps 6-7 | T1, T3 |
| the orphaned `kubectl port-forward` to 9954 | step 7 | T1, `pkill -f "kubectl port-forward svc/"` |
| `~/cache_dir` | step 7 | T3 |

**Nothing is written to `~/.kube`, the Helm defaults or uv's shared cache.** T3 checks that each
is still absent, or unchanged for uv's cache.

**Step 1's firewall rules close the two ports whatever SREGym binds.** Step 7 also sets
`API_BIND_HOST=127.0.0.1`. While 9954 is served, the Mac checks that both ports time out from
outside. If either answers, that is the stop rule.

## The procedure

`VM=deploy@<address>` on the Mac, one-line `ssh` commands, each output saved to
`~/Downloads/1c-*.txt` and read before the next step. There is no reboot: none is pending, and the
VM has been up since 1b's.

1. **The kill switch on**, confirmed `"kill_switch":true` with retries. Then the two
   `iptables` rules, listed back, and `/var/run/reboot-required` read (it must be absent).
2. **P0**: `kind_measure_1c.py P0 600`.
3. **Install** kind and kubectl as in 1b, and Helm from `get.helm.sh` against its own `.sha256sum`.
   A mismatch stops 1c.
4. **inotify** raised; the old values printed first.
5. **SREGym**: clone and check out `46c853db`, then
   `git submodule update --init SREGym-applications` and, inside it,
   `git submodule update --init astronomy-shop`, then `uv sync --frozen`.
6. **The cluster**: `kind/setup_kind_cluster.sh`, as in 1b, with `KUBECONFIG` set.
7. **The deploy**:
   `uv run python main.py --use-external-harness --problem wrong_dns_policy_astronomy_shop --agent demo`,
   timed and logged, with `KUBECONFIG`, the Helm homes and `API_BIND_HOST=127.0.0.1` set and no
   model key. **Wall limit 45 minutes**, after which the process is stopped and the outcome is read
   from the log.
8. **The firewall from outside**: once the log shows the MCP server's port-forward started, the Mac
   runs `curl -m 8` against the VM's `:9954` and `:8000`. Both must fail.
9. **P2**: five minutes after the deploy command exits, `kind_measure_1c.py P2 600`. Then, read-only,
   `kubectl top nodes` and the thirty largest pods by memory from `kubectl top pods -A`.

Teardown, whatever the outcome:

- **T1**: kill the port-forward, `kind delete cluster`, `docker network rm kind`, and the node image
  removed by digest.
- **T2**: both `iptables` rules deleted and listed, and inotify set back.
- **T3**: `rm -rf ~/t7.2-1c ~/cache_dir`, and the Helm defaults and `~/.kube` shown absent.
- **T4**: the kill switch off, `healthz` confirming, and `git status` empty.
- **T5**: `kind_measure_1c.py P3 300`, then both helper scripts deleted from `/tmp`.
- **T6**: the deployment's `incidents` table read for the whole of 1c.

**The stop rule.** Teardown runs at once if:

- MemAvailable falls under **1.0 GiB** in any sample;
- any of the 35 containers restarts, is OOM-killed or stops;
- a world alert that was not firing at P0's end starts;
- or step 8 finds either port answering from outside.

## The outcomes, stated now

The threshold for FITS leaves room for the agent a benchmark run would add. That is Faultline's
runtime packaged as SREGym's agent container, not built yet and so not measured. It is allowed
**1 GiB, plus 2 GiB of margin: 3.0 GiB**.

| outcome | when (P2 against P0, the deploy log, and the pod listings) | what follows |
|---|---|---|
| **FITS** | the deploy exits 0 with the log's `Fault injected` line; at P2's start and end every pod in the application's and SREGym's namespaces is `Running` or `Completed`, and no container restarts during P2 (the frontend's fault may fail requests but not restart it); P2's MemAvailable minimum **≥ 3.0 GiB**; none of the 35 restarted, OOM-killed or stopped; no alert that was not firing at P0's end; memory PSI `some` avg60 max **< 5**; load1 max **< 8** | the host question is settled for Astronomy Shop: T7.2 runs on the deployment. Next is scoping step 5 (topology), then the run's pre-registration (step 6) |
| **FITS, TIGHT** | as FITS, but the minimum between **1.5 and 3.0 GiB** | reported; whether T7.2 runs here, and how the agent is sized, is the owner's decision |
| **DOES NOT FIT** | the minimum **< 1.5 GiB**; or memory PSI `some` avg60 ≥ 5; or any pod OOM-killed; or any of the 35 affected; or the stop rule | the second-host question (scoping §3, shape 1 or 3) is answered by the measurement |
| **INCONCLUSIVE** | the deploy fails for a cause that is not the host's size: an image pull refused for the rate limit, a download failing, SREGym's own error, the wall limit | the cause is named and the fit question stays open; any retry is registered as an addendum first |

**One measurement, not a sample.** Astronomy-shop is the application the registration of the
eventual run will lead with (a third of the problems, and the one this repository knows). The
two DeathStarBench applications, which ADR-0042 says should lead the external claim, are **not
measured here**. Whether each needs its own fit check is scoping step 6's question.

**The prediction, stated now: FITS.**

- **The deploy** completes in **8 to 25 minutes**, most of it image pulls.
- **The application** runs inside its chart's limits and **uses 3.0 to 4.5 GiB**. SREGym's stack
  around it (Prometheus, Jaeger and the collector, OpenEBS, metrics-server, the MCP server) uses
  **0.8 to 1.5 GiB**. The cluster's own 1.55 GiB is on top of both.
- **Memory.** MemAvailable's P2 minimum lands **5.5 to 8.5 GiB under P0's mean**, which is 3.7 to
  6.7 GiB if P0 reads near 12.2.
- **Load and pressure.** Load1 stays between 1.5 and 5. CPU PSI rises above 1b's 1.5 %. Memory
  PSI stays under 1.
- **Pods.** Some start with restarts (the Kafka consumers before Kafka is up, as on the world),
  and none restarts during P2.
- **The world and the network.** None of the 35 is touched and no alert fires. Docker Hub pulls
  stay under the allowance. Both ports time out from outside.

## What is recorded

`evals/attempts/T7.2-1c-astronomy-shop/RESULT.md` holds:

- the outcome by the table above;
- every prediction held or not;
- the deploy's duration;
- the application's and SREGym's pods with their memory;
- every departure from this registration.

The captures go to `docs/evidence/t7.2-kind-host/1c-*.txt` verbatim, except the VM's address,
which is withheld as in 1b. Scoping step 5 follows only on FITS.
