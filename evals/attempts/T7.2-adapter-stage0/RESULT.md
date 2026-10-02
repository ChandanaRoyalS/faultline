# RESULT - T7.2 adapter build, stage 0: Faultline runs in SREGym's agent container

Read against [`PREREGISTRATION-T7.2-adapter.md`](../../runs/PREREGISTRATION-T7.2-adapter.md) and its
Addendum 1.

- **When and how.** Run on 2026-10-02, 23:37-23:52 UTC, by the owner from the Mac, one
  `spike_vm.sh` stage at a time on the deployment.
- **Captures.** Verbatim in [`docs/evidence/t7.2-adapter/`](../../../docs/evidence/t7.2-adapter/)
  (`t72-spike-*`), with the VM's address withheld.
- **$0.** No model was called, no key reached the container, and no cluster was started.

## The answer

**PASS, on the second `box`, under Addendum 1. Faultline can run as an SREGym agent under the
run's frozen settings, with its database outside the container**, reached through SREGym's own
egress proxy. The build proceeds as registered.

| check | predicted | first `box` (23:40) | second `box` (23:49), Addendum 1 |
|---|---|---|---|
| A: `apt-get` in the box | fails | rc 100 | rc 100 |
| B: Faultline's wheel with `[agents,embeddings]`, CPU torch | succeeds in 2 to 8 min | **60 s**, 1.8 GB of site-packages | 64 s |
| C: the embedding model | 384 dims, under 2 min | 12 s, 384 | 13 s, 384 |
| D: `api.anthropic.com` with no key | 401 | 401 | 401 |
| E: Postgres with pgvector through the proxy | succeeds, 50 round trips under 2 s | **failed**: timed out after the proxy's `200` | **succeeded**: PostgreSQL 16.15, a vector distance of 1.0, **50 round trips in 61 ms** |
| F: HTTP to a host port through the proxy | 200 | 200 | 200 |

**The container, as SREGym starts it**, the same both times:

- root, with `CapEff` `0x2` (`DAC_OVERRIDE` alone) and `NoNewPrivs` 1;
- the proxy set, and its CA bundle mounted;
- no key-like variable;
- the proxy blocked no request;
- nothing left behind, and the proxy and its network removed.

## The predictions

| prediction | held? |
|---|---|
| A fails | **held** |
| B in 2 to 8 minutes | **wrong, in the good direction**: 60 and 64 s |
| C, 384 dimensions, under 2 minutes | **held** |
| D 401 | **held** |
| E succeeds | **wrong on the first `box`, held on the second**. The first failure was the registration's own error (Addendum 1) |
| F 200 | **held** |
| MemAvailable above 6 GiB | **held**: 11.70 GiB before, 11.72 GiB after |
| no world alert; `git status` empty | **held**, before and after |
| the proxy blocks nothing | **held**, both runs |
| Addendum 1's `e-blocks`: about 9 lines inside 23:41:50-23:42:20, `IN=docker0`, from the bridge | **held, but the window was wrong.** 9 lines, `IN=docker0`, from `172.17.0.3` to `172.17.0.1`, all one source port, so one connection retried. They ran 23:42:17-23:42:37: E began once B and C were done, later than predicted, and the last five lines fall after the window |

## Step by step

- **`preread`** (23:37):
  - docker0 at `172.17.0.1/16`, and both ports free;
  - pgvector's image present, and the agent and proxy images absent;
  - uv absent, so installed into the run's directory;
  - 11.7 GB available, 35 containers, no alert, `git status` empty.

  `docker info` has no `HostGatewayIP` field on this version, so it read `unknown`. That
  host-gateway is docker0's address was shown by F and E reaching it.
- **`install`** (23:39): SREGym at `46c853db`, its venv, and the wheel copied (sha256
  `b1551cdc…`).
- **`host-on`** (23:40): one rule, 55480 from docker0.
- **`pg-up`** (23:40): Postgres 16.15, listening on `172.17.0.1:55432` only.
- **The first `box`** (23:40-23:42): E failed. **The read-only diagnosis** (`t72-spike-e-read.txt`)
  found:
  - Docker's DNAT for the port carries `! -i docker0`;
  - ufw had logged 9 blocks on it.

  **Addendum 1** was committed (#629) before anything changed.
- **`e-blocks`, `host-on-e` and the second `box`** (23:49-23:51): the blocks read as predicted, the
  rule for 55432 from docker0 was added, and E passed.
- **Cleanup** (23:51):
  - `pg-down` removed the database;
  - `host-off-e` and `host-off` removed both rules (`no rule for 55432`, `rule gone`);
  - `cleanup` deleted the run's directory and the two images it pulled.
- **`postread`** (23:51): both ports free, 11.72 GB available, 35 containers, no alert, and
  `git status` empty.
- **Left on the VM**: the five files copied into `/tmp` (the four scripts and the wheel). They are
  removed with the next stage that needs the VM.

## Departures

- **Addendum 1**: a second `box` with one more firewall rule, after the registration's claim that
  none was needed proved wrong.

## What this settles for the build and the run

- **Persistence outside the box stands as registered**: a pgvector Postgres on `docker0`, reached
  by CONNECT. 61 ms for 50 round trips is about 1.2 ms each, which is negligible beside a model
  call.
- **The install per attempt costs about a minute**, well inside the 30-minute agent timeout, so
  `install-faultline.sh` installing the wheel each attempt is acceptable.
- **The run's operation needs three docker0-only rules**: 8000 and 9954 for SREGym's API and MCP
  server, and the benchmark database's port. Each is registered with the pilot.
- **Open, for the pilot**: whether 55480's HTTP path behaves the same for SREGym's SSE-based MCP
  server. F tested plain HTTP only.
