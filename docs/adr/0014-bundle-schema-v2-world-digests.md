# ADR-0014: Bundle schema v2 — content digests identify the world

- **Status:** accepted
- **Date:** 2026-08-23
- **Task:** T1.5 (scenario rehearsal)
- **Breaks:** the schema freeze in ADR-0009

## Context

ADR-0009 froze the manifest at v1 and set an explicit bar for breaking the freeze:

> Worth paying for: a field a downstream phase cannot work without and cannot derive from
> what is already captured.

It also set the cost: a bump obsoletes every bundle recorded before it, at ~20 minutes per
scenario, serial, because they share one world.

**The freeze is being broken.** ADR-0009 is not edited — the reasoning there was right, and
a freeze that is quietly amended when it becomes inconvenient is not a freeze. This ADR
records that the bar was met and the bump taken.

## Why the bar is met

Two fields qualify, and neither is derivable from anything captured.

**A bundle could not tell you what world it was recorded against.** Raising kafka's memory
limit from 1200M to 2g altered a container's environment for every subsequent rehearsal.
No manifest field moved: the demo image tag was identical, the platform identical, and the
only field that did change was one that changes on its own. Bundles recorded either side of
that edit claimed the same world and described different ones. Nothing in the captured JSON
— not metrics, not logs, not alerts — can reconstruct the compose files as they stood.

**The one world field that did vary was noise.** `ffs_stub_image_id` differed between
bundle four and bundle five with **no source change at all**: `make world-up` rebuilt the
image unconditionally and re-resolved a pip layer. The guard comparing it fired correctly
by its own logic and reported a difference that did not exist. A field that produces false
positives and cannot produce true ones is worse than absent.

## Why now rather than later

**Three valid bundles exist, not nine.** The re-record cost is about an hour, against three
hours at a full catalog and rising. ADR-0009's cost argument was always time-dependent, and
this is the cheapest moment the decision will ever be available at. Deferring it does not
avoid the cost; it raises it and adds every bundle recorded in between to the pile.

## Decision

`BUNDLE_SCHEMA_VERSION` becomes **2**, adding under `world`:

| Field | Content |
|---|---|
| `compose_digest` | sha256 over `world/docker-compose.yml`, `compose/world-arm64.override.yml`, `compose/telemetry.yml`, concatenated in load order |
| `ffs_stub_source_digest` | sha256 over every file in `compose/ffs-stub/`, sorted by filename |

Both are taken from `InjectorSettings.compose_files` and the stub directory rather than
hardcoded lists, so they cover exactly what the injector and Makefile layer.

`ffs_stub_image_id` is **kept and demoted to informational**. It is still worth recording —
it identifies the exact artifact that ran — but it is never compared between bundles.

**The guard compares the two digests only.** INVALID.md scoping from the previous change is
retained, and the guard was verified in both directions: three valid bundles carrying the
same digests pass; two carrying different ones fail.

**`make ffs-stub` is pinned.** It writes the source digest to `.faultline/ffs-stub.digest`
and rebuilds only when the digest differs or the image is absent. The digest comes from
`evalharness.provenance.ffs_stub_source_digest`, the same function the manifest uses, so
the stamp and the field cannot drift. The guard still ignores the image id regardless,
because a guard should not depend on build discipline holding.

## Consequences

**The three existing valid bundles are stale and fail two guards each.** That is the
correct state. `ad-memory-squeeze`, `cart-dependency-latency` and `cart-redis-misconfig`
are queued for re-record.

**They must not be backfilled.** Beyond the rule that captures are never rewritten, a
backfilled digest would be a false claim: all three were recorded under the old memory
limits (kafka 1200M, paymentservice 200M, quoteservice 120M) and genuinely describe a
different world from the one a digest computed today would name. Writing today's digest
into them would assert exactly the thing that turned out not to be true — which is the
defect this ADR exists to fix.

**The two invalidated bundles are unaffected**, being out of the guard's scope already.

**ADR-0009's freeze rule survives intact and is now tested.** It permitted this bump on its
own terms; it did not need weakening to allow it. What this episode shows is that the rule
needs a companion: a field can qualify not because a phase demands it, but because its
absence let a wrong claim go unnoticed. Both of these fields are of that kind — nothing
downstream had asked for them, and the catalog was quietly accumulating an untrue statement
without them.

Revisit if: a third consumer needs world identity at a different granularity, or the world
gains configuration outside those four paths.
