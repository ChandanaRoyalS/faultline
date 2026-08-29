# ADR-0026: The world clone is recorded by nothing; the image tag is not enough

- **Status:** accepted
- **Date:** 2026-08-29
- **Task:** T7.16 (the world is somebody else's repository)
- **Relates to:** ADR-0014 and its T7.15 addendum (what a digest covers)

## Context

T7.15 closed the observability holes and set one aside: `world/` is gitignored, is its own clone
pinned at tag `v1.2.1`, and nothing verifies it is at that tag, is clean, or has not gained files.
It carries an untracked file. `compose_digest` already reaches into it. Is that a provenance gap
or merely untidy?

## The facts

**The clone is at its tag and no tracked file is modified.** `HEAD` is
`9d9056d372825f8f59ba0246f7056e63e6143551`, which is exactly what `v1.2.1` resolves to. `git
status` is clean apart from two untracked files.

**The untracked file is a Docker mount point, and it is empty.**
`world/src/grafana/provisioning/datasources/loki.yml` is 0 bytes. Nobody wrote it. The demo's
Grafana bind-mounts `./src/grafana/provisioning/` as a *directory*, and `compose/telemetry.yml`
mounts a single file at `datasources/loki.yml` *inside* that directory. Docker has to materialise
the target of the second mount, and because its parent is a host bind mount, the empty file
appears in the clone. Verified from the container's mount table, and the container reads the real
content — `compose/grafana-loki-datasource.yml` overlays it read-only. **Nothing reads the empty
file.** The other untracked file is `.cloned`, our own Makefile marker.

**What `compose_digest` covers, by residence.** Of its three inputs, one lives in the clone
(`world/docker-compose.yml`) and two in this repository (`world-arm64.override.yml`,
`telemetry.yml`). T7.15's `observability_digest` adds four here and two more in the clone (both
collector configs). So **three clone-resident files reach a bundle, and all three are already
covered by content digests.**

**The clone is not the source of what runs.** `make world-up` passes `--no-build`. All sixteen
demo images are pulled from `ghcr.io/open-telemetry/demo`. The clone's service source,
Dockerfiles and build context produce nothing that executes; they are inert.

## Decision 1: record nothing about the clone

Each option, and what it would catch that the others miss:

| option | what it would catch | verdict |
|---|---|---|
| resolved commit SHA | the clone being at a different commit than the tag names, including a tag moved upstream | **Nothing a bundle can see.** The three files that reach a bundle are content-digested: a commit that changed any of them moves `compose_digest` or `observability_digest` already. A commit that changed only the other files changed only inert build context. |
| dirty / clean flag | a locally edited clone file | **Redundant where it matters, noisy where it does not.** An edit to one of the three digested files is caught by its digest. An edit anywhere else is invisible to a bundle, and the flag would report it as though it mattered. |
| count or digest of untracked files | files appearing in the clone | **Actively harmful.** It would flip on a Docker mount artifact that reappears on every `world-up`. That is the `ffs_stub_image_id` failure ADR-0014 already names — a field that moves for reasons unrelated to what it claims to identify, so disagreement means nothing and readers learn to ignore it. |
| nothing | — | **Chosen.** |

**Being honest about realistic versus theoretical:** the only failure a commit SHA catches and the
digests do not is upstream re-pointing the `v1.2.1` tag such that the change touches only
clone files outside both digests. Those files do not run. So the failure is not merely unlikely —
it has no path to a bundle. Recording a SHA would buy a field that cannot change the answer to any
question a bundle is asked.

So this was untidy, not a provenance gap. **The tidiness is left alone too** — see Decision 3.

## Decision 2: `otel_demo_image` records a tag, and that *is* a gap

Following the same reasoning to where it actually leads. What runs is the pulled image, and the
bundle identifies it as `ghcr.io/open-telemetry/demo:v1.2.1-cartservice` — a **mutable reference**.
If upstream republished that tag, every bundle would go on claiming the same world while running
different code, and *nothing recorded would move*: `compose_digest`, `ffs_stub_source_digest` and
`observability_digest` would all agree, because none of them describes image contents.

**Added: `world.otel_demo_image_digest`**, the registry content digest
(`ghcr.io/open-telemetry/demo@sha256:…`). Additive per T7.15's precedent; existing bundles lack it;
absence means unknown, because a digest is not derivable from a capture and could not be
backfilled honestly.

This looks like it contradicts ADR-0014's refusal to compare `ffs_stub_image_id`, and does not.
That field churns because the stub is **built here** and a rebuild re-resolves layers from
unchanged source. The demo images are **pulled, never built**, so their digest is stable and is a
genuine content identifier. Same principle — prefer content over build artifact — reaching the
opposite conclusion because the situation is opposite.

**Two limits, stated rather than glossed.** It records one image, matching `otel_demo_image`'s
existing choice of a single reference container: the demo publishes its sixteen service images
from one release, so this is a proxy for that release, not proof of the other fifteen. And the
realistic likelihood of a released tag being republished is low. It is recorded because it costs
nothing, is stable, and closes the last mutable link in the chain — not because the failure is
expected.

## Decision 3: the untracked file is documented as expected

Not removed: the next `make world-up` recreates it, so removal is a no-op that would be
rediscovered as a mystery later. Not adopted: it is empty, nothing reads it, and it is not ours —
Docker made it. **Documented**, in the Makefile next to the clone target where somebody checking
the clone's state will actually be standing, along with why it exists and why the container does
not read it.

## Consequences

- A guard compares the image digest across bundles that carry one, and its failure says the thing
  a reader would otherwise get wrong: that the other digests agreeing proves nothing. Vacuous
  today, live from the first bundle recorded after this.
- A test pins Decision 1 by name. If a later task adds a clone SHA or dirty flag, it fails and
  sends the reader here rather than letting the field in by habit.
- A test pins the premise: `--no-build` must stay in the Makefile, and the clone-resident inputs
  to both digests must stay the three named. If the world is ever built from the clone rather
  than pulled, **this ADR is invalid** — the clone's source would become the source of what runs,
  and the SHA argument reverses.

Revisit if: the world is built from source rather than pulled, or a bundle needs per-service image
identity rather than one reference container.
