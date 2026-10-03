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

## Addendum 1 - Loki is not there under the external harness; the dev read's log check moves to part B

**Written 2026-10-03, after `devread shop` and before anything else runs.** Outputs so far are in
[`docs/evidence/t7.2-pilot/`](../../docs/evidence/t7.2-pilot/) (`t72-pilot-*`).

**What the shop's read found** (`t72-pilot-devread-shop.txt`, 00:41-00:48 UTC):

| item | predicted | read |
|---|---|---|
| Astronomy Shop's span metrics | uncertain | **present under v2's names**: `traces_span_metrics_calls_total` and the duration histogram, for 18 services. So `span_metrics = V2` stands, and Faultline's three rules apply |
| workloads named differently | none for the shop | **none**: all 24 Deployments carry their span names |
| `kube_pod_owner`, `kube_replicaset_owner`, cAdvisor | present | **present**: 29, 25 and 39 series |
| time zone | UTC | **UTC** (`Etc/UTC`) |
| the shop's alarms two minutes after the deploy | no kube alarm | **wrong**: `KubePodCrashLooping` fired on `product-catalog`, whose pod had been in `CrashLoopBackOff` within the last five minutes. The fault is in `frontend-proxy`, so this is either a startup crash loop or a standing one, as accounting's was (Q126). `podstate` reads which |
| Loki's labels | `namespace` and `pod` among them | **not read**: `services "loki" not found` |

**Why Loki was absent: SREGym does not install it under the external harness.** `main.py:900`
passes `deploy_loki=not args.use_external_harness`, and `conductor.py:1431` logs *"Skipping Loki
deployment (external harness mode)"*. **Part A cannot read Loki at all.** Loki exists only in agent
runs, which is part B.

**The changes, before anything else runs:**

1. **`podstate shop`** (new, read-only, before `cluster-reset`): the shop's pods and every
   restarted container's last termination, to tell a startup crash loop from a standing one.
   **The dev reads for Hotel Reservation and Social Network print their pods too.**
2. **The Loki check moves to part B.**
   - A read-only `loki-read shop` runs right after attempt 1, Faultline on the shop, which deploys
     Loki. It reads Loki's service, its labels and the pod values for the namespace.
   - **If `namespace` and `pod` are not both labels, the pilot stops before attempt 2.** The
     selector's fix is the owner's decision then.
   - Attempt 1's own log results are read with it, since `get_logs` prints each line's labels.
3. **The gate keeps its meaning** for the three items part A can read:
   - span metrics;
   - workload names;
   - the time zone.

   `PROFILE_READ` is set once Hotel Reservation's and Social Network's reads are in, recording
   that Loki is read in part B.

**Noticed, not changed**: `install` printed `uv 0.12.10`. A `uv` already in `~/.local/bin` sits
ahead of the one installed into `uvbin` on `renv`'s PATH. Both read the same frozen lock.

## Addendum 2 - the dev read done; the gate's profile patch; span metrics decided per service

**Written 2026-10-03, after part A's three reads and before part A's teardown or anything of part
B.** Outputs: `t72-pilot-podstate-shop.txt`, `t72-pilot-devread-hotel.txt` and
`t72-pilot-devread-social.txt`.

**The reads against the predictions:**

| item | predicted | read |
|---|---|---|
| the shop's `product-catalog` loop | startup or standing, to be read | **startup**: 3 restarts, the last at 00:45:34, a minute after its deploy, then running. The shop's catalog stumbles on startup as shipped. In a scored attempt its crash-loop alarm can be a seed that is not the fault. Recorded, not changed |
| workloads named differently | `nginx-thrift` only | **held**: Hotel Reservation's 19 and Social Network's 27 Deployments carry their span names, but `nginx-thrift` |
| owner and cAdvisor series | present for all three | **held**: Hotel Reservation 20, 27 and 16; Social Network 28, 27 and 28 |
| time zone | UTC | **held** |
| Hotel Reservation's alarms | yes | **held**: `KubePodCrashLooping` on five MongoDB pods, and `KubeDeploymentReplicasMismatch` on six MongoDB Deployments and `reservation` |
| Social Network's alarms | none | **held**: none. The fallback to `nginx-web-server` applies |
| DeathStarBench span metrics | none, so `span_metrics = None` | **wrong for Hotel Reservation**: v2's span-metric series for `reservation`, the one service that restarted after SREGym repointed its exporter, and for no other. Social Network has none, as shipped |

**The finding behind the last row.** SREGym's collector does turn DeathStarBench traces into
span metrics under v2's names. It has none only for services that send no trace, which as shipped
is nearly all of them (Q127).

- With `span_metrics = None`, `reservation`'s real series would read as unavailable.
- With v2's spelling and nothing else, an untraced service's templates would read as **empty**,
  which a responder takes for *no traffic*.

**The owner's decision, 2026-10-03: check each service.**

- All three profiles carry v2's spelling.
- `McpToolSet.has_span_series` asks once per service, per tool set, whether the service has any
  span-metric series in the last hour.
  - **If not**, its span templates are an error that says *unavailable, not zero*.
  - **If the check cannot be answered**, the template is read as asked: unknown is not absent.
- Faultline's three rules now apply to all three applications. On the DeathStarBench
  applications they can fire only for traced services.

**The gate's patch**, in this commit:

- `profiles.py`: v2 for all three, and `PROFILE_READ = True`, recording that Loki is read in
  part B;
- `toolset.py`: the per-service check;
- tests: the untraced service is unavailable, the traced one is read, an unanswered check does not
  block, the dev read is recorded.

**Both stamps are unchanged.** Part B starts from the commit that merges this. Its bundle and seed
bundle are built from that commit.

## Addendum 3 - part B's setup ran twice; the stages now refuse a second run; migrate's database fixed

**Written 2026-10-03, before part B goes further.** No key has been on the VM and no model has
been called.

**What happened.** Part B's setup chain was run twice, and the outputs kept are the second's
(`t72-pilot-b-doubled-*.txt`, 01:41 UTC). The record shows the first:

- the preread found the run's directory present, 55432 and 55480 in use, the kill switch on, and
  four kind nodes;
- `host-on` printed every rule twice;
- the cluster was 22 minutes old.

**The first chain's own outputs were overwritten**, and it ran before the two bundles reached the
VM (an `scp` failed for an unset `$VM`). So its `install` pinned nothing, its seeding had no seed
bundle, and its server had no bundle to serve.

**What the second run did, stage by stage:**

- `install` stopped at `git clone` (directory exists), changing nothing.
- `cluster` reported the existing cluster.
- `bench-db`:
  - refused the container's name, which already existed;
  - **wrote a new password to `pg.pass` that the existing container does not have**;
  - failed its `CREATE DATABASE`, which already existed.
- `serve-on` found 55480 already served by the first chain's server, so its own server is not the
  one listening.

**And a defect of its own, which a single clean run would also have hit.** `faultline-migrate`
reads `FAULTLINE_ORCH_POSTGRES_DSN` (`migrations/env.py`), not the
`FAULTLINE_CONTEXT_POSTGRES_DSN` the seeding container set. So it tried `localhost:5432` and
failed, and no table exists in the template.

**The changes to `pilot_vm.sh`, before anything runs again:**

1. **Every stage that creates state refuses to run twice**, saying so:
   - `host-on` if its rules are present;
   - `install` if SREGym's checkout exists;
   - `bench-db` if the database container exists;
   - `serve-on` if 55480 is in use.
2. `host-off` removes **every** copy of each rule, so a doubled `host-on` is undone in full.
3. `teardown` stops every bundle server on 55480 by its command line, not only the one in
   `serve.pid`.
4. **`bench-db` runs `faultline-migrate --dsn` with the template's DSN.**

**Recovery**, then part B from its start:

- `teardown`, `host-off` and `cleanup` return the VM to before part B. The kill switch stays on.
- Then one clean run of the setup chain.

**Nothing frozen changes.** Every setting of the run and of the pilot is as registered.

**Part A's close**, recorded here: `teardown`, `host-off`, `cleanup`, `killswitch-off` and
`incidents` (`t72-pilot-*-a.txt`).

- The cluster and its image are removed, the rules gone, and the directory deleted.
- The kill switch is off.
- **No incident opened in the two hours.**

## Addendum 4 - the clean setup ran; seeding needs the committed acceptances; `bench-reset` added

**Written 2026-10-03, after the clean setup and before anything else.** Outputs:
`t72-pilot-b-reset-*.txt` and `t72-pilot-b-*.txt`.

**The reset and the clean run, 01:46-01:53 UTC:**

- **The reset**: the database removed, all five ports closed, both copies of the rules gone, and
  the directory deleted.
- **The clean preread** found five free ports, no directory, no key and the kill switch on.
- **`install`**: SREGym at the pin, the patch applied, and **`claudecode` pinned to 2.1.288**.
  The bundles' sha256s are `ea773f50…` (box) and `6a214629…` (seed), built at `afe6419`.
- **`cluster`**: four nodes.
- **`serve-on`**: the box's bundle served over docker0, 793,878 bytes.
- **`bench-db`**: the template migrated (`schema at 0010`, so Addendum 3's `--dsn` fix worked),
  then `faultline-seed` **refused**:

  > `ad-memory-squeeze/postmortem.md has no acceptance for its current text … A postmortem joins
  > the corpus when a person accepts it through the approval surface and not before`

  So the template holds 5 chunks, the runbooks that seeded before the refusal, and no narrative.
  **It is not the corpus Faultline runs with.**

**Why: a fresh database has no acceptance rows.** T6.5's guard admits a postmortem only on a
recorded acceptance of its exact text. `faultline-seed --import-acceptances` replicates the
committed ledger (`evals/scenarios/artifacts/dev/ACCEPTANCES.json`, in the seed bundle) into the
new database first. The flag's own help names it for this case: *"so a fresh deployment can admit
the postmortems a person accepted elsewhere without anyone re-deciding"*. The script omitted it.

**And the recording query was wrong.** `corpus_state` is a function of `evalharness.freeze`, not a
table.

**The changes to `pilot_vm.sh`:**

1. `bench-db` seeds with **`faultline-seed --import-acceptances`**.
2. The template is recorded from inside the seeding container: its chunk count, its document count
   and **`body_digest_of`**, the corpus digest `faultline.context.corpus` defines.
3. **`bench-reset`** (new) removes the database, puts the run's checkout's `kickoff_env` password
   back to its placeholder and deletes `pg.pass`, so `bench-db` can run once more from nothing. It
   touches nothing else.

**Recovery**: `bench-reset`, then `bench-db`. The cluster, the install, the rules and the bundle
server stay as they are.

**Nothing frozen changes.** The corpus is still the committed dev split with its committed
acceptances, as the image ships it.

## Addendum 5 - the database, the key and the judge are ready; the Loki read moves into attempt 1

**Written 2026-10-03, after `judge-check` and before the first attempt.** Outputs:
`t72-pilot-b-bench-reset.txt`, `t72-pilot-b-bench-db-2.txt` and `t72-pilot-b-key-judge.txt`.

**Addendum 4's recovery ran:**

- **`bench-reset`** removed the partial database and put the `kickoff_env` password back to its
  placeholder.
- **`bench-db`** seeded the template in full: **334 chunks over 65 documents, body digest
  `a6de378e3b55`**, and set the password in the run's checkout.
  - The same three numbers come from the working tree at `a1f67e0`, off the VM, through
    `evalharness.corpusdrift.working_tree_rows` and `body_digest_of`.
  - Nothing under the corpus's paths changed between `afe6419`, where the seed bundle was built,
    and `a1f67e0`.
  - **So the template is the committed dev corpus with its committed acceptances**, as part B
    registered.

**The key**: present on the VM, mode 600, 106 bytes, the same size as the owner's file. It was
copied by stdin and never printed.

**The judge**: the README's `anthropic/claude-sonnet-4-6-20250627` was refused, and the alias
**`anthropic/claude-sonnet-4-6` answered**. As registered, it is the judge for both arms and the
baseline's model, here and in the scored run.

**What reading SREGym's cleanup found: `loki-read` cannot run after attempt 1.**

- `deploy_app` records the cluster's baseline **before any infrastructure is deployed**
  (`conductor.py:1340`). The baseline is persisted in `~/cache_dir`, which Addendum 3's `cleanup`
  deleted, so attempt 1 records it from the bare part B cluster.
- Every attempt's cleanup runs `reconcile_to_baseline` (`conductor.py:496`). That deletes every
  namespace not in the baseline, except the protected ones (`cluster_state.py:246`, list at `:35`).
- Loki is deployed into **`observe`** (`sregym/service/metadata/loki.json:3`), which is neither in
  the baseline nor protected.
- **So by the time attempt 1 has finished, Loki is gone.** `loki-read` would print `loki service
  namespace: NONE`, and Addendum 1's rule would stop the pilot for a reason that has nothing to do
  with the selector.

**The change, before attempt 1 runs:**

1. **`loki-watch shop <file>`** (new, read-only) starts beside attempt 1.
   - It polls every 30 s, and runs `loki-read shop` once, while Loki exists. It reads when Loki has
     pod values for the namespace, or after ten polls in which Loki answered with labels but no
     such values. **So the label list is read either way.**
   - It reads nothing else and touches nothing.
2. **Addendum 1's rule is unchanged**: if `namespace` and `pod` are not both labels, the pilot stops
   before attempt 2.
   - **If `loki-watch` reports that the attempt ended before a reading, the pilot also stops before
     attempt 2.** The label question is then open, and what to do is the owner's decision.
   - Attempt 1's own log results are read with it, as Addendum 1 says.
3. **Each attempt, `hold` and `loki-watch` run under `nohup` on the VM**, each writing its output
   to a file in `~/t7.2-1c/out/`. A dropped ssh connection then cannot stop an attempt. The Mac
   waits for the attempt's file to say `exit`, and that wait can be repeated safely.

**Nothing frozen changes.** The settings of the run and of the pilot are as registered, and so is
the order of the six attempts.

## Addendum 6 - attempt 1 ran end to end and found two adapter defects; the pilot goes on, with a probe beside attempt 2

**Written 2026-10-03, after attempt 1 and before attempt 2.** Outputs:
`t72-pilot-b-a1-record/` (SREGym's log, Faultline's logs, and the trajectory from the bench
database, the key checked absent) and `t72-pilot-b-a1-hang.txt`.

**Attempt 1, Faultline on `edge_request_filter_cpu_saturation`, 02:16:05-02:35:47 UTC, exit 0:**

| item | predicted | measured |
|---|---|---|
| ends with a submission | yes | **yes**: `Submission received`, stage `diagnosis` |
| Faultline's install in the box | 60 to 120 s | **66 s** (02:25:26-02:26:32), the box's bundle at `ea773f50…` |
| Faultline's opening | Astronomy Shop as the dev read finds | **one evaluation, no fallback**: `KubePodCrashLooping` on `product-catalog` (warning) and `ServiceHighErrorRate` on `load-generator` (critical) |
| time, deploy to submission | 10 to 40 minutes | **17.4 minutes** to the submission (02:33:57), 19.7 to exit; SREGym's deploy took 367 s, the agent's stage 518 s |
| the world | no alert, none restarted, MemAvailable above 5 GiB | **no alert, 9.5 GiB available** at 03:41 |

- **Faultline reached a verdict**: `frontend`, fault type unknown, low confidence, 3 evidence
  items cited, from 7 tool calls.
- **The judge scored it 0.0**: the ground truth is `frontend-proxy`. No pass-rate prediction was
  made, and none is drawn from one attempt.
- The startup crash loop the dev read found on `product-catalog` (Addendum 2) opened the incident,
  and the investigation went there first.

**`loki-watch` read Loki at 02:23:43**: 11 labels, **`namespace` and `pod` among them**, and 9
pod values for the namespace. **Addendum 1's rule is met.**

**The cleanup** deleted `astronomy-shop` and `observe` and left `sregym` and `openebs`, as
Addendum 5 read in SREGym's code.

**The wait that never returned was the script's, not SREGym's.**

- SREGym exited at 02:35:46.
- The Mac's wait checked for `loki-watch` with `pgrep -f "pilot_vm.sh loki-watch"`, and that
  matched the waiting command's own line, so it waited for itself.
- **From attempt 2 on, the Mac waits only for the attempt's `exit` line.**
- One process outlived the attempt: SREGym's `kubectl port-forward svc/mcp-server 9954`. SREGym
  starts it through a shell and stops only the shell. Its next `start_port_forward` kills a stale
  one first (`sregym/service/mcp_server.py:166`), so it is left to SREGym.

**What Faultline's seven tool calls returned** (`db-trajectory_tool_calls.jsonl`):

| tool | calls | result |
|---|---|---|
| `trace_query` | 1 | **worked**: 20 traces found, 5 shown |
| `logql_query` | 2 | **HTTP 400 from Loki, both** |
| `change_history` | 2 | **`Expecting ',' delimiter: … (char 10000)`, both** |
| `metric_baseline` (error ratio) | 2 | **no samples in either window**, for `product-catalog` and `frontend` |

1. **The log selector is malformed: an adapter defect.**
   - `pod_pattern` builds the pod regex with `re.escape`, which writes `product-catalog` as
     `product\-catalog`.
   - `\-` is not an escape a LogQL string accepts, so Loki refuses the query.
   - `memory_query` builds its PromQL the same way, and has the same defect. Attempt 1 did not
     call it.
   - The tests compared the string and never parsed it.
2. **The change commands' answers are cut off: an adapter defect.**
   - SREGym's kubectl server truncates every answer at **10,000 characters**
     (`mcp_server/kubectl_server_helper/utils.py:9`, applied at `kubectl_cmd_runner.py:87`).
   - `kubectl get replicasets -n astronomy-shop -o json` is longer, so the JSON arrives cut and
     cannot be parsed.
   - The server refuses pipes, so the answer cannot be shortened on its way out.
   - The adapter was built without a full-size answer to read.
3. **The empty error ratios: not established.**
   - v2's span metrics create an error-status series only once a span errs. The template divides
     by it, so a service with no errors returns nothing.
   - Faultline's own world behaves the same way, and this fault slows the shop rather than
     failing it.
   - That would make the result correct, but **attempt 1's record cannot show it**.

**The owner's decisions, 2026-10-03**, asked once the findings were explained:

1. **The pilot continues as registered.** Attempts 2 to 6 run unchanged, with the adapter as
   built. **Every finding is fixed together after the pilot and before the scored run**, followed
   by a short re-check of Faultline on the three dev problems, registered before it runs. The
   selector and the change commands are frozen settings, so their fixes are the owner's
   decisions, as part B and Addendum 1 say.
2. **A read-only probe runs beside attempt 2**, so the fixes are built on measured facts.

**The probe** (`probe shop <file>`, new, read-only, beside attempt 2, Claude Code on the shop):

- It waits until Loki has the namespace's pods, then 300 s for the fault, then reads once.
- **What it reads:**
  1. **Loki**: the selector as shipped and as corrected (the name unescaped), for
     `product-catalog` and `frontend-proxy`, the last 30 minutes. It records whether each is
     accepted, and how many streams and lines.
  2. **Prometheus**: the span-call series counted by service and status code, which says which
     services have an error-status series at all.
  3. **The adapter's range reads exactly as it sends them**, `(q)[1800s:15s] @ now`:
     - the error-ratio, call-rate and p95-latency templates for `frontend-proxy`, `frontend` and
       `product-catalog`;
     - the memory query as shipped and as corrected.

     For each it records whether the read is accepted, and its series, points and range.
  4. **The four change commands' answers**, against the 10,000-character cut:
     - each answer's length and item count;
     - the largest and median single item;
     - the largest and median pod template.

     For configmaps and secrets this is the shipped names-and-times command only.
- **It prints statuses, counts and sizes only**: no log line, no object body, and no value from a
  Secret.
- It changes nothing, and Claude Code's attempt is otherwise exactly as registered.

**Nothing frozen changes in this addendum.** The adapter, the run's settings and the order of the
attempts are as registered. The probe's output is recorded with attempt 2's.

## Addendum 7 - attempts 2 and 3 and the probe; each Faultline attempt's record is kept

**Written 2026-10-03, after attempt 3 and while attempt 4 runs, before its record is taken.**
Outputs: `t72-pilot-b-a2-shop-claudecode.txt` (the attempt and the probe) and
`t72-pilot-b-a3-hotel-claudecode.txt`.

**The spend**: after attempt 2 the owner read the key's spend in the console as **well under the
cap**, and went on. The figure is to be recorded in the pilot's result.

**Attempt 2, Claude Code on `edge_request_filter_cpu_saturation`, 04:00:47-04:12:30 UTC, exit
0:**

- Judged **correct, 89/100**: localization 1.0, characterization 0.67, scope 1.0.
- The agent's stage took 316 s, and the whole attempt 11.7 minutes.
- After submitting, the agent went on issuing commands against the removed namespace, and SREGym
  refused its second submission (`This attempt no longer accepts new submissions`). This did not
  change the scored result.

**Attempt 3, Claude Code on `update_incompatible_correlated`, 04:20:48-04:29:18 UTC, exit 0:**

- Judged **correct, 89/100**: localization 1.0, characterization 1.0, scope 0.67.
- The agent's stage took 140 s, and the whole attempt 8.5 minutes.

**What the probe read, 04:08:24 UTC**, about four minutes into attempt 2's fault:

1. **Loki**: the shipped selector was **refused** (HTTP 400) for both services. The corrected one
   was **accepted**: `product-catalog` 1 stream and 2 lines, `frontend-proxy` 1 stream and 100
   lines. **Addendum 6's first defect is confirmed, and so is its fix.**
2. **Prometheus**: only **`frontend`, `frontend-proxy` and `load-generator`** have an
   error-status series. `product-catalog` has none, so **its empty error ratio in attempt 1 was
   the template's arithmetic, not a defect**. Whether `frontend` had one at attempt 1's moment is
   not recoverable.
3. **The adapter's range reads**, each `(q)[1800s:15s] @ now`:
   - every read was accepted, except the memory query as shipped, which was refused, as the log
     selector was;
   - **every series held at most 12 points of the 121 a 30-minute window holds at a 15 s step**.
   - The corrected memory query held 19.
   - `call-rate frontend-proxy` was 0 throughout and its p95 undefined; the probe was taken during
     the fault on that service.
   - `latency-p95` read **0.005** for `frontend` and `product-catalog`.
4. **The change commands' answers**, against SREGym's 10,000-character cut:

| command | characters | items | largest single item | largest pod template |
|---|---|---|---|---|
| `get replicasets -o json` | **213,062** | 25 | 22,060 (3 items over the cut) | 14,077 |
| `get statefulsets,controllerrevisions -o json` | **50,193** | 4 | 12,026 (2 over) | 6,568 |
| `get events -o json` | **328,279** | 257 | 1,190 | - |
| `get configmaps,secrets -o custom-columns=…` | 2,087 | - | - | - |

**What the probe establishes, for the fixes decided after the pilot:**

- **The selector's fix is measured.** Write the name unescaped; a Kubernetes name holds no RE2
  metacharacter but `.`.
- **The change commands cannot be fixed by asking per object.** One ReplicaSet, and one pod
  template, can each exceed the cut. Any fix must ask for named fields only.
- **New: the metric history is minutes long, not hours.**
  - SREGym deploys Prometheus with each attempt (Addendum 5), so a 30-minute read holds about
    three minutes of samples.
  - Faultline's baseline comparison (incident window against the window before it, T3.2b's onset
    − 30 min) **therefore has no baseline in SREGym**. In attempt 1 the baseline window ended
    before Prometheus existed.
  - **This is not an adapter defect but a mismatch between the agent's design and the benchmark's
    world.** The plan's T7.2 requires *"the agent under test is the real one"*, so it is recorded
    for the owner's decision and not tuned.
- **Not established**: whether 0.005 is a real p95, which would need the duration histogram's
  `le` bounds in SREGym's collector, or an artefact of a three-minute history.

**The record of each Faultline attempt is kept** (`record <tag>`, new, read-only, run after
attempts 4 and 5):

- Each Faultline attempt recreates the bench database, which wipes the previous trajectory.
- The stage saves what Addendum 6 saved for attempt 1:
  - Faultline's logs (the newest `attempt.json` under SREGym's results);
  - the attempt's outputs and SREGym's log;
  - the incident and trajectory tables as JSON lines.
- It archives them only if the key is in none of them.
- It changes nothing.

**Nothing frozen changes.** Attempts 4 to 6 run as registered.

## Addendum 8 - attempts 4 to 6, and part B's close

**Written 2026-10-03, after part B's close and before the pilot's result.** Outputs:
`t72-pilot-b-a4-*`, `t72-pilot-b-a5-*`, `t72-pilot-b-a6-*`, `t72-pilot-b-results/`, and the
closing stages' outputs (`collect`, `teardown`, `host-off`, `cleanup`, `cleanup-2`,
`killswitch-off`, `incidents`, `hold`).

**The attempts ran in the registered order**, each with every frozen setting. Their results are
read in [`evals/attempts/T7.2-pilot/RESULT.md`](../attempts/T7.2-pilot/RESULT.md).
`record a4` and `record a5` kept Faultline's records, the key absent from both.

**Part B's close ran in the registered order**: `collect`, `teardown`, `host-off`, `cleanup`,
`killswitch-off`, `incidents`. Four departures:

1. **The sampler was stopped at 05:29:18**, before its six hours were up, so that its output could
   be copied before `cleanup` deleted the directory.
   - It wrote no summary.
   - Its 387 samples, 02:16:03-05:29:04, are the record.
   - The world's restart counts were read instead with `docker inspect`, in `collect`'s output.
2. **The sampler's shell printed a syntax error after it stopped.**
   - `pilot_vm.sh` had been copied over twice while `hold` was running (Addenda 6 and 7), and bash
     reads a script as it runs it.
   - The sampling is Python and was unaffected.
   - No attempt, `probe` or `loki-watch` spanned a copy.
   - **From now on, the script is copied only when no stage is running.**
3. **`cleanup` could not delete three of SREGym's logs.**
   - Claude Code's box writes `/logs` as root, so `rm` was refused.
   - The key had been shredded first, and `collect` had found it in none of the logs.
   - `sudo rm -rf ~/t7.2-1c` finished the cleanup (`t72-pilot-b-cleanup-2.txt`).
4. **The world's prediction was wrong twice.** Both are recorded in the result:
   - **an alert fired** at 04:34:34-04:36:34, and **`email-service` restarted** at 04:34:49;
   - **MemAvailable fell to 4.04 GiB** during attempt 1, and below 5 GiB in 27 samples, all
     during the two shop attempts.

**`incidents`: no incident opened in the eight hours.** The kill switch is off, and every port is
closed.
