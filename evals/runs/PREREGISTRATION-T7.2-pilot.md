# Pre-registration - T7.2, the dev read and the dev pilot

**Written before either part is run. Nothing here is a result.** This is step 3 of
[the run's registration](PREREGISTRATION-T7.2-run.md) (*The order*), with the dev read that
[the adapter's](PREREGISTRATION-T7.2-adapter.md) Addendum 2, item 9, requires before it. It also
registers **how the run is operated** on the deployment, which step 4 left for this registration.

**The owner's decisions, 2026-10-03:**

| decision | chosen |
|---|---|
| the API key | **a new key, for the benchmark alone**. Its spend is measured on its own, and it can be revoked after |
| the plan's shape | **one registration with a gate**: the pilot starts only after the dev read's names are recorded and merged |
| the spend cap | **$30 for the pilot**. Above it, the pilot stops and is reported before anything else |

## Found while registering it: the box would have had no graph

**Adapter Addendum 3, below and in the adapter's registration.** `install-faultline.sh` installed a
**wheel**. A wheel carries `src/` and nothing else, and Faultline walks up from its own `__file__`
to find the dependency snapshots, `knowledge/`, `alembic.ini` and `migrations/`.

- **Measured** (`docs/evidence/t7.2-adapter/bundle-check.txt`): installed from the wheel, loading
  Hotel Reservation's catalog fails with `FileNotFoundError` on its snapshot. **Every
  investigation would have failed before triage.**
- **Stage 0 could not see it.** It imported Faultline and loaded the embedding model, and never
  loaded a graph.
- **The fix**: the box gets a source bundle instead, `git archive` of exactly
  `faultline.sregym.bundle.BUNDLE_PATHS`, installed editable at `/opt/faultline`.
  - Measured: all three applications' graphs load, as do `alembic.ini` and the allowlist.
  - `tests/test_sregym.py` holds the bundle to `tests/test_packaging.py::REPO_DATA`, so a sixth
    runtime path added for the image cannot be forgotten for the box.

## Part A - the dev read ($0, no key on the VM)

**What it settles**: adapter Addendum 2, item 9. `PROFILE_READ` stays `False` until all four are
recorded:

1. whether Astronomy Shop's span metrics exist under v2's names in SREGym's Prometheus;
2. every workload whose name differs from its span service;
3. the Loki labels the selector uses;
4. the server's time zone.

**How**: [`pilot_vm.sh.txt`](../../docs/evidence/t7.2-pilot/pilot_vm.sh.txt), part A.

- Each dev problem is deployed by SREGym's external harness, as 1c and the topology runs did:
  no agent, no model, no key.
- **The dev problems only**: `edge_request_filter_cpu_saturation` (Astronomy Shop),
  `update_incompatible_correlated` (Hotel Reservation) and `k8s_target_port-misconfig`
  (Social Network).
- **A fresh cluster per problem** (`cluster-reset`), so each application deploys as it would
  first.
- **Read-only reads, two minutes after each deploy**:
  - the workloads and their containers;
  - Jaeger's services;
  - Prometheus' span-metric families and services;
  - `kube_pod_owner`, `kube_replicaset_owner` and cAdvisor's working set;
  - **the registered alarms, evaluated once**;
  - Loki's labels and pod values;
  - the time zone.

**Predictions:**

| read | predicted |
|---|---|
| Astronomy Shop's span metrics | **uncertain**. SREGym's collector may or may not turn traces into metrics. If none, `span_metrics` becomes `None` and Faultline's three rules drop out for it |
| workloads named differently from their spans | `nginx-thrift` → `nginx-web-server` only. Hotel Reservation's deployments carry their span names (item 4's restart list). Astronomy Shop's carry v2's |
| `kube_pod_owner`, `kube_replicaset_owner` and cAdvisor | present for all three |
| Loki labels | include `namespace` and `pod` |
| time zone | UTC |
| alarms firing two minutes after the deploy | Hotel Reservation (an incompatible update) yes; Social Network (a target-port misconfiguration, whose pods stay ready) no; Astronomy Shop (CPU saturation) no kube alarm, and only a latency rule if span metrics exist |

**The gate.** The reads are committed with a profile patch:

- `profiles.py` corrected to what was read;
- `PROFILE_READ = True`;
- tests updated.

Part B starts only from a commit that has it. **A read that contradicts a frozen design**, rather
than filling a name in, is an addendum and the owner's decision, not a profile edit.

## Part B - the dev pilot

**The adapter's registration names it**: the three dev problems, R = 1, both arms. Its purposes:

- to measure cost and time per attempt;
- to show every piece works;
- to set nothing in the frozen setup.

**It is reported and never scored.**

**The run's operation, registered here** (`pilot_vm.sh.txt`, part B). The scored run uses it
unchanged, unless an addendum says otherwise.

- **The firewall** (`host-on`):
  - SREGym's API (8000), MCP forward (9954) and Kubernetes proxy (16443) are dropped from every
    interface but the loopback, as in every T7.2 run;
  - then **docker0 is admitted** for those three, the benchmark database (55432) and the bundle
    (55480);
  - the boxed agents reach the host through the egress proxy on the default bridge (stage 0,
    Addendum 1);
  - **16443 is new**: the baseline's kubectl reaches SREGym's Kubernetes proxy through it.
  - ufw's INPUT DROP stays the first layer.
- **SREGym's API binds every interface** (`API_BIND_HOST=0.0.0.0`) for the attempts only, under
  those rules, so the boxes can reach it.
- **The benchmark database** (`bench-db`):
  - pgvector Postgres 16, bound to `172.17.0.1` only, with a random password kept in the run's
    directory;
  - **migrated and seeded into `faultline_seeded`** by a throwaway `python:3.12-slim` container,
    from the seed bundle (`BUNDLE_PATHS` plus `evals/scenarios/artifacts/dev`) at the run's
    commit;
  - its chunk count and `corpus_state` are recorded;
  - the password reaches the box through the `faultline` row's `kickoff_env`, written into the
    run's SREGym checkout only;
  - each attempt recreates its database from the template.
- **The bundle**: served on `172.17.0.1:55480` (`serve-on`) for `install-faultline.sh`.
- **`claudecode` pinned**: `install` sets its `agent_version` to npm's `latest` at that moment,
  recorded. **The same version is used for the scored run.**
- **One image for both arms**: every attempt passes `--force-build`. That builds SREGym's agent
  image from the pinned tree plus `faultline-agent.patch`, cached after the first build.
- **The key**:
  - created by the owner for the benchmark;
  - copied from the Mac by `ssh "$VM" 'umask 077; cat > ~/t7.2-1c/key' < <file>`, never typed
    or printed;
  - read by the attempts and `judge-check` from that file;
  - checked absent from the collected results (`collect`);
  - **shredded by `cleanup`**.
- **The judge's string**: `judge-check` makes one 1-token call with SREGym README's
  `anthropic/claude-sonnet-4-6-20250627`, and if that is refused, with the alias
  `anthropic/claude-sonnet-4-6`.
  - The one that answers is the judge for both arms, and the baseline's model. **It is recorded,
    and the scored run uses it.**
  - Faultline's arm passes `--model anthropic/claude-opus-5`. Faultline's own client reads
    `AgentSettings.model`, the same model, so the record says what ran.
- **The world** is watched as in every T7.2 run:
  - the kill switch on;
  - 1c's sampler over the whole pilot (`hold`);
  - `incidents` at the end;
  - nothing on the world touched.

**The attempts**, six, in this order, so neither arm always goes first:

| # | problem | first | second |
|---|---|---|---|
| 1-2 | `edge_request_filter_cpu_saturation` | Faultline | Claude Code |
| 3-4 | `update_incompatible_correlated` | Claude Code | Faultline |
| 5-6 | `k8s_target_port-misconfig` | Faultline | Claude Code |

**Every attempt's settings**: `--stages diagnosis --n-attempts 1 --profile full --internet-access
filtered --container-hardening on --agent-timeout 1800`, the run's frozen settings at R = 1.

**The spend cap.** After each attempt the owner reads the key's spend in the Anthropic console.
**The pilot stops when the cumulative figure passes $30**, and is reported with what was spent on
what.

**Predictions:**

| prediction | predicted |
|---|---|
| every attempt ends with a submission | 6 of 6. Faultline's says `Faultline reached no verdict.` at most once |
| Faultline's install in the box | 60 to 120 s (stage 0: 60-64 s for the same dependencies, plus the editable build) |
| Faultline's opening | alarms on Hotel Reservation; the front-door fallback on Social Network; Astronomy Shop as the dev read finds |
| Faultline's cost per attempt | $0.30 to $1.50 |
| the baseline's cost per attempt | $0.50 to $3.00 |
| time per attempt, deploy to submission | 10 to 40 minutes |
| total spend | **$5 to $15**, under the cap |
| the world | no alert, none of the 35 restarted, MemAvailable above 5 GiB throughout (1c's lowest was 5.83 with Astronomy Shop) |
| the key | 0 occurrences in the collected results |

**No pass-rate prediction at n = 3**: it would mean nothing, and it is not what the pilot is for.

**What follows the pilot** (the run's step 4):

- the owner's go, on the pilot's measured cost and time projected to 108 × 3 × 2 attempts;
- with it, an addendum for anything the pilot forced. **A change to a frozen setting** (the
  rendering, the alarms, the change commands, the rules of the run) **is the owner's decision
  before the scored run**, never made silently.
