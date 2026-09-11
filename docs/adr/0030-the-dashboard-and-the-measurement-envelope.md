# ADR-0030: The shop-health dashboard, and the edge of the measurement envelope

- **Status:** accepted
- **Date:** 2026-09-01
- **Task:** T1.2 (telemetry backends), completed during the Phase 1 audit
- **Relates to:** ADR-0014 (world digests on the bundle), ADR-0026 (the world is somebody
  else's repository), ADR-0012 (the thresholds this dashboard draws)

## Context

T1.2's deliverable column names *"Prometheus + Loki + Grafana wired; health dashboard."*
The wiring was done in week one. The dashboard was never built, and the Phase 1 audit found
its absence: every demo opened on the OpenTelemetry demo's own Grafana, and Gate 1's
evidence screenshot is of a dashboard this project did not author.

Building it turned out to be a provenance question rather than a Grafana question.
Provisioning a dashboard the ordinary way means mounting files into the Grafana service in
`compose/telemetry.yml`. That file is the third entry in `InjectorSettings.compose_files`,
which is what `compose_digest` hashes. Editing it re-founds the world every recorded figure
describes — and the current-world headline is 19 scored runs on `f5bd108f4f70f460`.

## The three options

**Queue it** beside Q1 and Q13, to land with the next world move. Tidiest, and it respects
the digest absolutely. Rejected because both of those items trigger on *"a world move
already forcing a re-record"* and neither is itself a reason to move the world. A dashboard
queued behind them waits on an event nothing schedules, and "deferred to a trigger that
cannot fire" is a worse record than a reasoned exception.

**Land it through `telemetry.yml`** and accept a new comparability generation. T7.55's
freeze path labels rather than refuses, so nothing breaks — existing figures stay valid,
marked previous-generation. Rejected on proportion: it spends the comparability of nineteen
scored runs to gain a panel.

**Provision it outside the compose files**, over Grafana's HTTP API. Chosen.

## Decision

`compose/dashboards/shop-health.json` is committed to this repository and pushed to the
running Grafana by `scripts/provision_dashboards.py`, which `make world-up` calls. No
compose file changes, so no digest moves, and a clean clone still comes up fully wired.

**The argument is classification, not convenience.** What belongs inside `compose_digest`
is what can move a recorded measurement. A Grafana dashboard cannot: the agent reaches
Prometheus and Loki through its own tools and never touches Grafana, so no capture, no
`seconds_to_alert`, no blast radius and no verdict changes because a panel exists. Mounting
it would move the digest **mechanically while nothing measurable moved**. Putting a
human-facing viewing surface outside the measurement envelope is the correct boundary.

No credentials are needed: the demo's Grafana runs anonymous at `org_role = Admin` with the
login form disabled (`world/src/grafana/grafana.ini`), serving under a `/grafana` sub-path.
The script probes both bases rather than assuming one.

## The inconsistency this creates, named rather than hidden

The Loki datasource is **also** purely human-facing — the log analyst queries Loki directly,
not through Grafana — and it **is** inside the digest, mounted through `telemetry.yml`. So
two Grafana provisioning artifacts now sit on opposite sides of the envelope, which looks
arbitrary.

The honest explanation is historical rather than principled. That mount was written at T1.2
in week one; `compose_digest` did not exist until ADR-0014 defined it over whatever the
compose files happened to contain. The datasource was swept in, not placed there by a
judgement that viewing surfaces belong inside. Recording this so the two placements are not
read as a reasoned pair.

## The guard, without which this is an escape hatch

The strongest objection to this decision is that a path which changes the running world
outside the provenance envelope will be used for the next thing too, and the one after.

`tests/test_dashboard_provisioning.py` answers it. The script may talk only to Grafana on
localhost, may use only `/api/health` and `/api/dashboards/db`, may not import `subprocess`
or `os`, may not write or delete a file, and may not name any file `compose_digest` covers.
It also pins every panel to the demo's provisioned Prometheus uid and requires each of the
three alert rules to be named by a panel title, so the dashboard cannot drift away from the
rules it exists to explain. **This decision is only defensible while those tests hold.**

One of them earned its place immediately: it failed on first run against the provisioning
script's own docstring, which names `telemetry.yml` in order to explain why it does not use
it. Prose may name the file the code must not touch, and the test now says so.

## Consequences

**Easier.** T1.2 is delivered without spending a comparability generation. Every demo can
open on a screen that mirrors the three alert rules, so a firing alert is explicable where
it is visible — the rule's own expression, with its threshold drawn as a line.

**Harder.** A bundle cannot record which dashboard version was present, because the
dashboard is in no digest. That is acceptable precisely because it cannot affect a bundle;
but it does mean the dashboard's history lives in git alone.

**Verified rather than assumed.** The first render exposed two defects the code could not:
the error-ratio axis auto-scaled to 10000% because a division by zero plots as `+Inf`, and
the 250ms threshold line sat off the top of an auto-scaled latency axis. Both are fixed —
the ratio axis is pinned to [0,1] since a ratio cannot exceed one, and the latency axis has
a soft maximum of 300ms so the line is visible at rest without clipping a real excursion.
Looking at the thing is part of the deliverable.

## Revisit if

The queue fires for an independent reason and a world move is happening anyway. At that
point moving the mount into `telemetry.yml` costs nothing extra and removes the
inconsistency recorded above. Also revisit if anything other than a Grafana dashboard is
ever proposed for this path — that is the moment the guard is protecting, and the answer
should be no.

## Addendum (T4.5, 2026-09-11): the second thing proposed for this path, and why the answer was not no

*Revisit if* above says that anything other than a Grafana dashboard proposed for the
outside-the-digest path is *"the moment the guard is protecting, and the answer should be no."*
T5.4c crossed it once for `compose/linux-host-gateway.override.yml`, on the argument that the
file describes how a host reaches the world and moves nothing a bundle records. This addendum
records the second crossing, `compose/actions-kafka-jvm.override.yml`, because it is a harder
case than the first and deserves to be argued rather than assumed under T5.4c's precedent.

**The case is harder** because the file changes a world process, not a DNS entry: kafka's JVM
starts with `-XX:-UseContainerSupport` on a GitHub-hosted runner, and without it kafka does not
start there at all (docs/GATES.md, 2026-09-04). The plan's T4.5 table priced four routes on
2026-09-04 and took none; the row for this one read *"worse — runs would claim the recorded
world's digest while running a different world."*

**Two things changed between that table and this addendum, and they are what make the answer
yes.** First, the freeze has recorded `host_platform` since T5.4c (2026-09-07), and
`generations.world_key` names a run's world `<digest>@Linux/x86_64` when the platform is not the
reference. A run from a runner is therefore a different generation *by construction*: README's
table filters on the generation, the eval database's fingerprint carries it, and no reader can
pool a runner's run with a Mac run without a code change that the tests for both would catch. The
row's premise - that the runner's run would claim the recorded world - was true when written and
is not true now. Second, the freeze now records `world.host_overrides`: the manifest of a run made
with this file says so, by name. The digest's job is to make a change to the world *visible from
inside a bundle*; a change that the bundle names is visible.

**What the flag touches, so that "moves nothing measurable" is a checked claim and not a hope.**
The JVM stops sizing itself from the cgroup. Kafka's heap is fixed by `KAFKA_HEAP_OPTS` in the
hashed override; the container carries no CPU limit; the memory limit the gate reads is the
cgroup's, enforced by the kernel with or without the JVM's knowledge. The header of the file
carries this paragraph and `tests/test_actions_kafka_override.py` requires it to keep carrying it.

**The guard, extended rather than relaxed.** The file may contain one service, one variable and
this value; it may not join `compose_files`; the Makefile may layer it only when `GITHUB_ACTIONS`
is `true`; and `provenance.host_overrides` must return exactly what `make -n` layers under every
combination of platform and runner, asserted by running both. A run that carries this file in its
manifest is a runner's run, and a runner's run is never a published figure - `variance.TIERS`
gives the nightly R = 1 and *"not a finding on its own"*.

**What this does not do.** It does not unblock the eval workflows on its own; it removes the
one obstacle that was measured. `.github/workflows/world-boot.yml` is the check that it did, run
on a pull request with no key and no cost before a scheduled workflow spends money finding out.
The third thing proposed for this path, whenever it comes, should read this addendum as the bar:
a recorded, generation-separated, one-line change that turns *no world* into *a world*, argued in
the file's own header. Anything less than that is the moment the original text was written for.
