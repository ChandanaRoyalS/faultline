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

## Addendum 3 — 2026-09-18: one datasource joins the path, and why it is the same class of thing

**The occasion.** T6.6 gave the API a `/metrics` surface and a dashboard with panels over it, and
nothing scraped it (Q73). The obvious four lines - a scrape job in
`compose/prometheus/prometheus-config.yaml` - are inside `observability_digest`, which
`generations.CURRENT_OBSERVABILITY` pins for the headline table. Landing them would have cost either
every recorded figure its stamp or every future run its admission, for a change no bundle can
observe. The `up`-count argument (`evalharness.run` counts scrapes across that Prometheus' targets,
so the target set *is* a measurement input) says the digest was right to include the file; it does
not say the platform's counters belong in it. They do not, for a third reason the first two hide:
the agent's `promql_query` reads that Prometheus, and an agent that can read its own spend and
outcome counters has been handed something no specialist should see.

**The decision.** The platform watches itself with its own Prometheus - `prometheus-self`, on the
platform's compose project in development and in `deploy/compose.yml` on the VM, scraping the
platform's `/metrics` and nothing else. The world's telemetry stack is untouched. Grafana reads it
through a datasource that `scripts/provision_dashboards.py` pushes over the API beside the
dashboards, under the uid the dashboard's panels name.

**Why the datasource belongs on this path and not in `telemetry.yml`.** This ADR's argument was
classification: what belongs inside the digest is what can move a recorded measurement, and a
human-facing viewing surface cannot. A datasource pointing at a Prometheus the agent never
queries is that surface's other half. Mounting it through `telemetry.yml` would move
`compose_digest` mechanically while nothing measurable moved - the exact case the original text
declined. The inconsistency the original text named - the Loki datasource file *is* inside the
envelope - stands and now has a third instance on the other side of it, which is the honest
description of where the line was drawn when each file arrived.

**The guard, extended rather than relaxed.** `tests/test_dashboard_provisioning.py`'s allowed API
surface widens by exactly one resource - `/api/datasources` and `/api/datasources/uid/` - and the
test's own docstring says the next addition is the moment this path is being routed around rather
than extended. The datasource's address is a value posted to Grafana, never a host the script
contacts, and a test distinguishes the two. The script still may not import `os` or `subprocess`,
write a file, or name a digest-covered file in code. `isDefault` stays false: the demo's own
Prometheus is what a person expects Explore to open.

**What a reader of this addendum should check.** That `compose/prometheus/self.yaml` is not in
`OBSERVABILITY_FILES` (a test holds it); that the dashboard's Prometheus panels all read
`faultline-self-metrics` (a test holds it); and that the world's `prometheus-config.yaml` carries
no `faultline` job, which is the one thing this addendum promises will stay true.

## Addendum 4 — 2026-09-19: the platform's spans leave the world's collector (Q77)

**What was found.** T6.6 exported the platform's traces to the world's collector, which forwarded
them to Tempo beside the shop's - and ran them through its `spanmetrics` processor first, so the
platform became a service in the world's metrics: `calls_total{service_name="faultline"}`, a
`ServiceNoTraffic faultline` alert the world fired at 12:24 UTC on 2026-09-18 when the platform
went quiet between investigations, and call rates the agent's `promql_query` could read. Addendum 3
closed exactly that exposure for `/metrics` by giving the platform its own Prometheus; the trace
path had reopened it from the other side, and nothing in the sixty T6.5 runs or the thirty
headline runs could have seen it, because the platform emitted no spans before T6.6. The platform
changed the world's metric namespace for every run after it and no digest moved - which is the
failure ADR-0014 exists to name.

**The decision.** The platform exports to Tempo's OTLP receiver directly. Same store, so the demo
beat - the agent's trace beside the outage's, one query away - is unchanged; no `spanmetrics`, so
the platform leaves the world's metrics and the world's alerting; no Jaeger copy, which Q76 shows
was the more available of the two on the day, and which is the price. The `filter` processor route
(drop `service.name=faultline` before `spanmetrics` in `otelcol-extras.yml`) was not taken: that
file is in `OBSERVABILITY_FILES`, and moving the digest for a change that removes the platform's
own artefact from the world would be moving it for something the world never had in it.

**What this costs the boundary.** On the VM it costs nothing: `deploy/compose.yml` names
`tempo:4317` instead of `otelcol:4317`, Tempo is already on the shared network for the traces
specialist, and the collector leaves that network. On a development host the daemons run outside
Docker and Tempo's receiver is not published, so a fourth compose file
(`compose/dev-tempo-otlp.override.yml`) publishes it as 4327 - layered by the Makefile outside
`compose_digest` on the argument the Linux gateway shim made and this ADR drew: a published port
changes nothing a bundle records. **Unlike the two shims before it, it is unconditional**, so the
reference platform's compose command is no longer byte-for-byte what it was before T5.4c; it
gains one file that publishes one port. `host_overrides` records it in every freeze, and
`tests/test_dev_tempo_override.py` holds the file to one service, one key, one entry. A reader
who finds a second key in that file has found this path being used as a way round the digest.

**What a reader of this addendum should check.** That no service in `deploy/compose.yml` names
`otelcol` as an endpoint and `compose.world.yml` no longer puts it on the platform's network (a
test holds both); that `otelcol-extras.yml` and `tempo.yaml` are unchanged since #380 (the digest
says so); and, on the running world, that `calls_total{service_name="faultline"}` stops
increasing after the change - the one observable this addendum promises.
