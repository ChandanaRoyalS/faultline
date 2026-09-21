# The reboot drill — 2026-09-21, and what §3.10 got wrong

**The deployment, `deploy@ubuntu`, 13:24–13:31 UTC. \$0.** A pending
`*** System restart required ***` was cleared by following `deploy/README.md` §3.10 **cold** — the
kill-switch drill's method, one week on: *a drill is following the documentation and recording what
happens, including what the documentation gets wrong.*

**It went right where it was designed to and wrong where nobody had checked.** The restart-policy
fix from the first reboot held perfectly. The procedure around it had **three defects**, one of
them live on the deployment for a day before this drill found it.

**Why a reboot at all**: [the T7.2 scoping note](../../design/t7.2-scoping.md) puts a kind cluster
on this box as step 1b, and a machine about to gain a Kubernetes cluster should not also be
carrying a deferred kernel. The twenty pending package updates were **deliberately not applied** —
a reboot and twenty packages in one window means a container that fails to return cannot be
attributed to either.

## What was run, and what happened

| # | step | result |
|---|---|---|
| 1 | `free -g` / `nproc` / `df -h`, before anything | **4 GB used of 15, 11 available; 8 cores at load 0.65; 40 G of 464 G** |
| 2 | `docker stats` | top twenty containers total **3.75 GiB**; kafka largest at 712 MiB |
| 3 | `sudo reboot` | back in **1 minute**, `no reboot pending` |
| 4 | `docker ps` | **35 containers, every one `Up`** — §3.10 says 32 |
| 5 | `make world-up` | recreated 7 telemetry containers, pushed dashboards at **version 1**, datasource **created** at `host.docker.internal:9091` |
| 6 | the deploy-overlay compose line | recreated Grafana **again** — `[+] up 27/27` |
| 7 | §3.4's third command, **absent from §3.10** | datasource **created** at `prometheus-self:9090`, dashboards **version 1** |
| 8 | `docker inspect grafana` | **four mounts, all configuration.** Nothing on `/var/lib/grafana` |
| 9 | the same command again, no recreate between | datasource **updated**, dashboards **version 2** — then **3** |

**Steps 7 and 9 are the drill's proof and were designed as a pair**, the way the kill-switch
drill's were. The script says `created` only when a GET by uid misses, so *created twice in a row*
is two absences and not a quirk of the script — and step 9 is what establishes that, by showing it
reports `updated` when the container has not been recreated in between. The dashboards corroborate
independently: **version 1 at step 7, version 2 and 3 at step 9.** A surviving dashboard increments.

## Defect 1 — §3.10 omits the command that repairs what the step above it destroys

**Grafana persists nothing on this deployment.** Its four mounts are `grafana.ini`, the
provisioning directory, and the file-provisioned Loki and Tempo datasources. **There is no mount
for `/var/lib/grafana`**, so Grafana's database lives in the container's writable layer.

The two dashboards and the `faultline-self-metrics` datasource are pushed **over the API**, and
that is deliberate: `scripts/provision_dashboards.py` says *"provisioning-file datasources are
`editable: false` and Grafana refuses API writes to them; this one is API-owned from the start,
which is the trade for not touching `telemetry.yml`"* — because editing `telemetry.yml` would move
`compose_digest` and re-found the world generation for a change no bundle can observe (ADR-0030).
**The trade is right. Its cost was never written down: API-owned means ephemeral here**, and
`deploy/compose.world.yml` recreates Grafana *by design*, since it is the file that adds the
`faultline` network and the restart policy.

**§3.4 survives only by ordering.** Its third command runs after the recreate, and its prose gives
a different reason for that command — `make world-up` pushes the *development* self-metrics address,
which resolves to nothing on the VM. **Both reasons are true and only one was recorded**, so a
procedure that copied §3.4's first two commands and not its third looked complete. §3.10 was that
procedure for ten days.

**Fixed**, and now guarded: `test_every_block_that_recreates_grafana_reprovisions_it` fails on any
fenced block in `deploy/README.md` that brings the world up with `compose.world.yml` without
re-pushing afterwards. It was run against the old text first and fails on it.

## Defect 2 — the guard immediately found a third block, and that one had run

**§3.12, the T6.8 egress window, executed 2026-09-20.** It recreates the platform network, brings
the world up with the same overlay, and never re-provisions. **So the platform's own dashboard and
its self-metrics datasource were destroyed yesterday and nothing re-created them** — which is why
step 5's push, the first since, reported `created`.

**The drill did not find this; the guard written for defect 1 did**, on its first run, before the
commit that added it. That is the argument for writing the guard rather than fixing the section:
the same defect existed in a section nobody was looking at, in a procedure that had already run.

**What it cost**: about twenty-four hours with no `faultline-self` dashboard. Nothing measured
depends on it — it is the platform watching itself, not a source of any published figure — and the
deployment's own investigations are unaffected. **But the one instrument pointed at the platform
was dark, and no alert exists for that**, which is the part worth keeping in view.

## Defect 3 — the container count was three low, in the direction that hides absences

§3.10: *"`docker ps …` — 32 containers; anything missing is a finding."* **There are 35**:
`injector.world.SERVICE_CONTAINERS` names 27 and `deploy/compose.yml` defines 8.

**The number is the whole check.** An operator comparing a freshly rebooted world against 32 reads
a deployment with **three containers missing** as correct — and a reboot is exactly the event that
makes containers go missing, which is why this section exists at all. The figure was written on
2026-09-11 and the deployment grew past it.

**Fixed to a derived number and guarded**:
`test_the_readme_container_count_is_what_the_compose_files_define` computes it from the compose
files and fails when the page disagrees. **This is the second hand-maintained count to rot in a
week** — `tests/test_results_run_counts.py` caught RESULTS.md's on 2026-09-21 — and the response
is the same both times: derive it, or do not state it.

## What went right, and it had never been tested

**The 2026-09-11 fix held, 7 of 7.** That reboot found `prometheus`, `alertmanager`, `grafana`,
`loki`, `tempo`, `promtail` and `frontend-proxy` did not come back, *"because the demo declares no
policy on three of them and `compose/telemetry.yml` declared none on the other four"* — the public
page answered and the world could not alert, the silent kind of outage. `compose.world.yml` gained
`restart: always` for all seven in response.

**This is the first reboot since, and all seven were `Up` at step 4**, before anything was run by
hand. A fix written from one incident and held by a test for ten days has now also been observed to
work. Those are different kinds of evidence and this drill supplies the second.

## What this does not establish

**Not that the host can run a kind cluster.** Step 1's numbers say the box is far freer than
[the scoping note](../../design/t7.2-scoping.md) claimed before it was measured — 11 GB available
against a stack that consumes 4 — but *not ruled out* is not *tested*, and the cluster experiment
is still owed.

**Not that the twenty pending updates are safe**, because they were not applied. They are still
pending and are their own decision.

**And not that Grafana's state is now durable.** Everything above repairs the *procedures*; the
underlying fact — that any recreate wipes the platform's dashboard — is unchanged, and it is
[Q85](../../QUEUE.md).
