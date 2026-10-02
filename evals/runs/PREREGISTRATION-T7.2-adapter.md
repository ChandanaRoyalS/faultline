# Pre-registration - T7.2, the adapter build: Faultline presented to SREGym

**Written before any adapter code exists and before stage 0 is run. Nothing here is a result.**
This is step 2 of [the run's registration](PREREGISTRATION-T7.2-run.md) (*The order*):

- the adapter that lets SREGym run Faultline as an agent;
- the two designs that registration left to this one, the incident's opening and the change
  mapping;
- the stamp check.

It opens with **stage 0**, a free test of whether Faultline can run inside SREGym's agent container
at all. The build itself starts only if stage 0 says it can.

**The question.** Can Faultline, unchanged in what it reasons with, run as an SREGym agent under the
run's frozen settings, and submit its verdict rendered as registered?

## Read before registration

All of it was read at SREGym `46c853db` and Faultline `e16089a`. Nothing was run.

- **Where an agent runs.** `agent_launcher.py` and `container_runner.py`:
  - **in a container**, unless its `agents.yaml` row sets `container_isolation: false`. A row
    without isolation is refused under `--internet-access filtered`, which the run froze. So
    Faultline runs in the container, as the baseline does.
  - **The image**: `ghcr.io/sregym/agent-base` pinned by digest, Ubuntu 22.04 with Python 3.12,
    Node 22 and kubectl (`docker/agents/Dockerfile`). Its entrypoint is `bash -c`.
  - **As root, hardened**: `--cap-drop=ALL --cap-add=DAC_OVERRIDE
    --security-opt=no-new-privileges`, 4 CPUs, 8 GB.
  - **Filtered internet**:
    - the container sits on an `--internal` Docker network whose only other member is a
      mitmproxy egress proxy, which also joins the default bridge;
    - `HTTP(S)_PROXY` point at it, and `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` at its CA;
    - the proxy blocks only SREGym's own GitHub sources;
    - **the host is reached through the proxy too**: `MCP_SERVER_URL` is
      `http://host.docker.internal:9954`.
  - **Install-then-run**: each attempt runs `/opt/sregym/install-scripts/<script>`, then the
    driver. **The install scripts are baked into the image**, so adding an agent means adding its
    script and driver to SREGym's tree and building the image locally (`--force-build`).
  - **The problem's identity is withheld.** `SREGYM_PROBLEM_ID` is popped from every agent's
    environment. Only `SREGYM_ARTIFACT_ID` passes, for artifact names.
  - **`claudecode` installs Claude Code at `latest`** unless its row sets `agent_version`, so the
    baseline is not reproducible as shipped.
- **What Faultline needs that the box does not have.**
  - **Postgres with pgvector**, for:
    - incidents (`PostgresIncidentStore`);
    - trajectories;
    - rejections;
    - the change log;
    - **retrieval** (`PgVectorPastIncidentStore`).

    Every store has an in-memory double, but **the in-memory retrieval is not the real ranking**:
    its text arm is token overlap, not Postgres full text (`context/store.py`). So in-memory
    storage would change what the agent retrieves.
  - **Postgres refuses to run as root**, and the box is root with no `CAP_SETUID` to switch user.
    SREGym's own README says `apt-get` fails under hardening. **So Postgres cannot run inside the
    box under the frozen settings**, which stage 0 confirms (check A) rather than assumes.
  - **The embedding model** `sentence-transformers/all-MiniLM-L6-v2` (ADR-0018), and torch, from
    the `embeddings` extra. `anthropic`, from the `agents` extra, reads `ANTHROPIC_API_KEY`,
    which SREGym forwards.
- **What SREGym's MCP tools return.** These are the tools every agent's observability goes
  through:

  | tool | what it does | what that costs Faultline |
  |---|---|---|
  | Prometheus `get_metrics(query)` | an **instant** query; reply is `str()` of the JSON | no range query. A subquery with `@` (`(q)[d:step] @ end`) returns a range from an instant query, and the adapter uses that |
  | Loki `get_logs(query, last_n_minutes)` | a window ending **now**, **100 lines**, timestamps reformatted to whole seconds in local time | windows are absolute in Faultline. The adapter asks back to the window's start, filters to the window, and marks the 100-line cap as truncation |
  | Jaeger `get_traces(service, last_n_minutes)` | **20 traces**; reply is a Python repr (the harness read) | parsed with `ast.literal_eval`; at most 20 traces per call |
  | kubectl `exec_kubectl_cmd_safely(cmd)` | any kubectl command, **writes included** | the change mapping issues a fixed list of read-only commands and nothing else |

- **An incident is alerts and nothing else.** `Incident` holds alert `Episode`s; it has no
  free-text field.
  - Triage seeds its blast radius from the alerting services.
  - The planner's retrieval query is *"{alerting services} {severity} starting at {start}"*.
  - **With no episode, triage has no seed and the planner has no query.** SREGym hands the agent
    no alert, and its Prometheus has no alert rules.
  - It does deploy `kube-state-metrics`, a dependency of the Prometheus chart SREGym installs, so
    pod and deployment state are queryable.
- **The change vocabulary** (`tools/changes.py`): `Resource` ∈ {image, environment,
  resource_limits, container, config}, and `Action` ∈ {created, updated, removed, reverted}.
- **A consequence for the run's operation, found here.** Earlier runs dropped 8000 and 9954 from
  everything but the loopback. The run used a non-isolated agent, so that was harmless. **A
  containerised agent reaches both through the egress proxy, from the default bridge**, and ufw
  drops that unless it is allowed. Stage 0's check F measures the path on a test port. The run's
  firewall design is registered with the pilot.

## The owner's decisions, 2026-10-02

| decision | chosen |
|---|---|
| how the incident is opened | **standard health alarms**, evaluated by the adapter at the start, falling back to the application's front door if none fires. The list is fixed below and never tuned on a scored problem |
| if Postgres cannot be reached from the box | **stop and ask**: the owner chooses, with the options priced, before anything is amended |

## Stage 0 - can Faultline run in SREGym's box? ($0, on the deployment)

**Scripts**, in [`docs/evidence/t7.2-adapter/`](../../docs/evidence/t7.2-adapter/):

- `spike_vm.sh.txt`, its stages;
- `spike_box.py.txt`, which starts **SREGym's own `ContainerRunner`** with the run's settings:
  filtered, hardened, and no host credential;
- `spike_inside.sh.txt`, the checks run inside;
- `spike_tunnel.py.txt`, a CONNECT tunnel that gives psycopg a local port.

No cluster is started, no model is called, and nothing on the world changes. **The stages, in
order**: `preread`, `install`, `host-on`, `pg-up`, `box`, `pg-down`, `host-off`, `cleanup`,
`postread`. Faultline's wheel is built on the Mac from `main` and copied with the scripts.

**The checks, each one line of `box`'s output:**

| check | what it asks | predicted |
|---|---|---|
| A | `apt-get update` in the box | **fails** (non-zero), as SREGym's README says |
| B | `pip install` of Faultline's wheel with `[agents,embeddings]`, CPU torch | **succeeds, in 2 to 8 minutes** |
| C | the embedding model downloaded and run once | succeeds, **384 dimensions**, in under 2 minutes |
| D | `https://api.anthropic.com/v1/models` with no key | **401**: reachable, nothing spent |
| E | Postgres with pgvector, outside the box on `172.17.0.1:55432`, through the proxy by CONNECT | **succeeds**: a version, a vector distance, 50 round trips in under 2 s. This is the uncertain one: it needs the proxy to pass a non-HTTP stream after CONNECT |
| F | plain HTTP to a host port through the proxy, with `host-on`'s one rule | **200** |

**Also predicted:**

- MemAvailable stays above 6 GiB;
- no world alert fires;
- `git status` on the deployment stays empty;
- the proxy blocks no request.

**The decision rule:**

- **B to F all pass** (A failing is expected): the build below proceeds, with the database
  outside the box.
- **E fails**: stop. The owner chooses, with each option priced:
  - hardening off for both arms, and Postgres in the box;
  - the in-memory stores, stating the retrieval difference;
  - another transport.

  Each is an amendment to the run's registration before the pilot.
- **B, C or D fails**: stop and report. A failure here is not a design question until it is
  understood.

## The build (only after stage 0 passes)

### 1. The SREGym side: an agent row, kept as a patch

- **`agents.yaml`** gains a `faultline` row with `container_isolation` left at its default (true).
  **`claudecode`'s row gains `agent_version`**, pinned to the Claude Code version the pilot
  installs, so the baseline is reproducible.
- **`docker/agents/install-scripts/install-faultline.sh`** installs Faultline's wheel, served from
  the host through the proxy, with the two extras and CPU torch.
- **`clients/faultline/driver.py`** waits for the conductor, then calls `faultline.sregym`'s entry
  point. **It holds no logic of its own.**
- **Both arms run on the one locally built image**: SREGym at the pin plus these three changes.
  The change set is committed here as a patch against `46c853db`, so the image can be rebuilt.

### 2. The Faultline side: `faultline.sregym`, a new package

`faultline.sregym` is a new package. It is the only new code the agent's run touches, and it adds
no tool, prompt or role:

- **`McpToolSet`**: an implementation of `ToolSet` (the five methods and `window_policy`) over the
  MCP servers at `MCP_SERVER_URL`:
  - **`promql_query` / `metric_baseline`**: the range is read as one instant query of
    `(q)[d:step] @ end`, giving the same matrix shape `Tools` parses;
  - **the metric templates for SREGym's applications** name the series SREGym's Prometheus
    actually holds:
    - span metrics, if Astronomy Shop's collector emits them;
    - cAdvisor's `container_memory_working_set_bytes` for runtime memory;
    - nothing for a template that has no series. That returns an error, never an empty answer
      (ADR-0019).

    The names are read on **the three dev problems only** and recorded before the pilot;
  - **`logql_query`**: a selector on the application's namespace and the service's pods, asked
    back to the window's start, filtered to the window. 100 lines means `truncated`;
  - **`trace_query`**: Jaeger's repr parsed with `ast.literal_eval`, then converted into the span
    model T6.1's span tree reads, so the degrading-hop rules run on it. At most 20 traces is
    recorded as the tool's cap;
  - **`change_history`**: §3 below.
- **The incident's opening**: §4 below.
- **Persistence outside the box**, if stage 0 passes:
  - a Postgres 16 with pgvector on the deployment, bound to `docker0` only;
  - migrated, and seeded by `faultline-seed` at the run's commit into a template database, with
    its chunk count and corpus digest recorded;
  - reached through the CONNECT tunnel;
  - **each attempt starts by recreating its database from the template**, so nothing one attempt
    writes is visible to the next (the run's constraint 5);
  - nothing is written to the deployment's own database.
- **The rendering**, exactly as frozen in the run's registration, with the evidence lines read
  from the trajectory's bound `Evidence`, never with samples. An attempt with no verdict submits
  `Faultline reached no verdict.`
- **The submission**: the rendering is POSTed to SREGym's `/submit` as `{"solution": text}`.
  Diagnosis only.

### 3. The change mapping, frozen

`change_history(service, start, end)` issues exactly these read-only commands through the kubectl
tool, for the application's namespace, and nothing else:

1. `kubectl get replicasets -n NS -o json`, then the ReplicaSets whose owner is the service's
   Deployment;
2. `kubectl get statefulsets,controllerrevisions -n NS -o json`, for a StatefulSet's revisions;
3. `kubectl get configmaps,secrets -n NS -o json`, for metadata only. **No value is ever read
   from a Secret**;
4. `kubectl get events -n NS -o json`.

Each yields `ChangeRecord`s in the window:

| source | what becomes a record | `resource` | `action` |
|---|---|---|---|
| consecutive ReplicaSet / controller revisions | the field diff of their pod templates: image | `image` | `updated` |
| | env | `environment` | `updated` |
| | resources | `resource_limits` | `updated` |
| | any other container or pod-spec field (probes, ports, command, DNS policy, volumes, scheduling) | `container` | `updated` |
| ConfigMap / Secret | a `managedFields` time inside the window, naming the object and that it changed, never what to | `config` | `updated` (or `created`) |
| a Service, NetworkPolicy, webhook or other object | an event in the window naming it | `config` | `updated` |

- **Leak guard.** `actor` is always the platform's (`platform-automation`). A summary is built only
  from the field diff's paths and values, and **never from annotations, labels, field-manager
  names or event reasons that a fault injector writes**. No `Resource` or `Action` value is added,
  because they are in the stamp's contracts.

### 4. The incident's opening, frozen

At the driver's start, and again once a minute for up to five minutes until at least one fires, the
adapter evaluates these rules through `get_metrics`, with NS the namespace `/get_app` names:

| rule | expression | severity |
|---|---|---|
| `KubePodCrashLooping` | `max by (pod) (max_over_time(kube_pod_container_status_waiting_reason{namespace="NS",reason="CrashLoopBackOff"}[5m])) >= 1` | warning |
| `KubePodNotReady` | `max by (pod) (kube_pod_status_phase{namespace="NS",phase=~"Pending\|Unknown\|Failed"}) > 0` | warning |
| `KubeContainerWaiting` | `max by (pod) (kube_pod_container_status_waiting_reason{namespace="NS",reason!="CrashLoopBackOff"}) > 0` | warning |
| `KubeDeploymentReplicasMismatch` | `kube_deployment_spec_replicas{namespace="NS"} != kube_deployment_status_replicas_available{namespace="NS"}` | warning |
| `KubeStatefulSetReplicasMismatch` | `kube_statefulset_status_replicas_ready{namespace="NS"} != kube_statefulset_replicas{namespace="NS"}` | warning |
| `ServiceHighErrorRate` | Faultline's v2 rule (`compose/prometheus/alert-rules-v2.yml`), on the span-metric series if they exist | critical |
| `ServiceHighLatency` | Faultline's v2 rule, likewise | warning |
| `ServiceNoTraffic` | Faultline's v2 rule, likewise | critical |

**Where the rules come from:**

- The first five are kube-prometheus' standard rules, scoped to the namespace.
- The last three are Faultline's own, with their thresholds unchanged.

**One departure from both**: a rule's `for:` duration cannot be applied by a single evaluation, so
a rule fires on its condition holding when evaluated.

**How a firing becomes an episode:**

- **Pod to service**: the pod's owner from `kube_pod_owner`, then `kube_replicaset_owner`, to its
  Deployment or StatefulSet. A table of names that differ from the snapshot's is read on the dev
  problems: `nginx-thrift` → `nginx-web-server` is known already.
- **One episode per (rule, service)**, starting when it was evaluated, with `join_rule
  no_candidate`. A service outside the catalog still opens an episode, and the catalog reports its
  presence.
- **None fires in five minutes**: one episode, `SREGymProblemReported`, critical, on the
  application's front door:

  | application | front door |
  |---|---|
  | Astronomy Shop | `frontend` |
  | Hotel Reservation | `frontend` |
  | Social Network | `nginx-web-server` |

  The attempt records that the fallback was used.

The opening is built only from what any agent can query. The rules and the front doors are fixed
here and **are never changed after a scored attempt**.

### 5. The checks before the pilot

- **The stamps.** **Predicted unchanged**: `cap:91279a09` and
  `faultline/0.0.1+prompts:9ce16b66bbcc`.
  - `ToolSet` keeps its five methods.
  - No prompt or contract changes.
  - `faultline.sregym` is outside every digest.

  **If either moves, the run's registration is amended before the pilot.**
- **Tests, offline, in `make check`**:
  - `McpToolSet` against recorded MCP replies, one per tool, including the repr, the `@` subquery,
    the 100-line cap and an error reply;
  - the change mapping against fixture objects, including **the leak guard**: an annotation naming
    a fault never reaches a summary;
  - the alarm evaluator against fixture metric replies, the owner mapping and the fallback;
  - **the rendering against a golden text** built from a fixture verdict;
  - the tunnel against a local fake proxy;
  - `isinstance(McpToolSet(...), ToolSet)`.
- **An ADR** (ADR-0044) records the adapter's design: why MCP and not the backends directly, the
  opening and the change mapping. It cites this registration.

## Predictions for the build

1. Stage 0 as tabled above.
2. **Both stamps unchanged.**
3. `make check` passes with the new tests and nothing else changed.
4. **The adapter's own code**, `faultline.sregym` plus the SREGym patch: under 1,500 lines,
   tests excluded.

## What comes next

The dev pilot's registration, with the build's result: the three dev problems, R = 1, both arms,
measuring cost, time and that every piece works, and the run's operating design, including the
firewall for 8000 and 9954.
