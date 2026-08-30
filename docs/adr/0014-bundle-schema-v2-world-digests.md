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

## Addendum (T7.15): the observability config is a sibling digest, not an extension

**This is the revisit condition above, arriving.** *"Revisit if … the world gains configuration
outside those four paths."* It had it all along: T7.14 found that `compose/prometheus/alert-rules.yml`
is covered by nothing. The three compose files *name* it as a mount and say nothing about what is
inside it, so editing a threshold changes every future bundle's alert set — which alerts fire, how
fast, how wide the blast radius — and no manifest field moves. That is precisely the defect this
ADR was written to fix, on a file outside its cover.

### The decision, and why not the obvious one

**Extending `compose_digest` to include these paths was rejected.** Adding a file to a digest's
input set changes the value it computes. The twelve recorded bundles would keep asserting the old
value while a recomputation produced a new one, and the guard on them
(`test_bundles_agree_about_the_world_they_were_recorded_against`) rests on a property stated in its
own comment: the digests *"are reproducible from the repository and move only when the world's
definition moves."* Extending the input set breaks both halves at once — the recorded values stop
being reproducible, and the digest moves for a reason that is not a world change.

Worse, it is silent. Two bundles recorded either side of the redefinition would compare unequal on
an unchanged world, and the guard would report a world change that never happened. **By this ADR's
own bar — does the change make existing bundles false — extending fails.** The bundles would not be
lying about what they recorded; they would stop meaning what a reader computes, which is the same
damage arriving by a quieter route.

**The decision is an additive sibling: `world.observability_digest`, with
`world.observability_files` beside it.** Existing bundles honestly lack both. `compose_digest`
keeps its definition and its value, and every recorded bundle stays reproducible.

### Which kind of field is this — T7.5's test

T7.5 separated a field that *reads what the capture contains* from one that *asserts something
outside it*. `reachability` was the first kind: derivable from committed captures, so backfilling
it was honest, because it only stated what the bundle already held. `answers_idle_or_absent` was
the second: an author's claim that no capture could settle, so it was declared going forward and
left absent on everything older.

**An observability digest is the second kind, decisively.** A bundle does not contain the alert
rules, the scrape config, or the collector pipeline. Nothing in a 2026-08-28 capture can tell you
what `alert-rules.yml` said at the moment it was recorded. Computing today's digest and writing it
into an older bundle would assert something unverifiable and probably untrue — the identical
argument this ADR already made when it refused to backfill `compose_digest` into the three
pre-change bundles.

So: **absence means unknown, not unchanged.** No bundle is rewritten. The guard skips bundles
without the field, and that is a scoping decision, not a loophole — the same one `valid_bundles()`
already makes.

### The whole hole, not the one that was tripped over

T7.14 found `alert-rules.yml`. A survey of what is mounted found five more of the same kind, and
all six are now under cover — the set and the reason each one matters live in
`evalharness.provenance.OBSERVABILITY_FILES`. In short: the alert rules, the Prometheus scrape and
evaluation config, the Alertmanager routing that decides whether an alert reaches the orchestrator
at all, the Promtail config that decides which containers ship logs and under what label, and the
two OpenTelemetry collector configs that decide whether `calls_total` and `latency_bucket` exist
and what their bucket boundaries are.

They belong in **one** digest rather than six, for the reason `compose_digest` covers three files
rather than three fields: they are one pipeline, and a bundle is comparable to another only if the
whole of it matched. The per-file map is what makes a mismatch legible — one value to compare, and
enough detail to say which file moved.

Three files were considered and excluded, named here so the exclusions are decisions:
Grafana provisioning (a human reads it; no capture, tool or score does),
`world/src/prometheus/prometheus-config.yaml` (**dead** — `telemetry.yml` points Prometheus at
`--config.file=/etc/prometheus/faultline-prometheus.yaml`, so the demo's own config is mounted and
never read), and the world's service source (already identified by `otel_demo_image` and the
upstream tag).

### What the guard does, and what it does not do yet

It compares the recorded digest against the repository as it stands, not bundle against bundle,
because the drift worth catching happens when somebody edits a rule — not months later when the
next bundle is finally recorded. The failure names the file that moved, says what each file
decides, and says what it means for bundles recorded before the change: not wrong about what
happened, but no longer comparable with anything recorded after it. It also says explicitly not to
edit the recorded digest to match, because that makes the bundle lie.

**It is vacuous today and that is correct.** No existing bundle carries the field, so there is
nothing yet to disagree with the tree; the guard goes live with the first bundle recorded after
this addendum. What is live now is the shape test, which edits `alert-rules.yml` for real,
asserts the digest moves, asserts that only that file's digest moves, and asserts the message
names it — so the cover cannot silently stop covering the file that prompted all this.

Revisit if: a bundle needs to record *which* rule fired it rather than which rule set existed, or
the observability pipeline gains a component configured outside these six paths.

## Addendum (T7.28): the queue cashed, and what a digest bump actually costs

The first bump this ADR's machinery has been used for deliberately, rather than to record a change
already made. Three world changes landed together and both digests moved:

| digest | before | after |
|---|---|---|
| `compose_digest` | `299d791c5e0da43e…` | **`f5bd108f4f70f460…`** |
| `observability_digest` | `3d061a2793b1cd57…` | **`857d95b4d174ec43…`** |
| `ffs_stub_source_digest` | `8defed3104c42adf…` | unchanged |

**Eleven of fifteen scenarios re-recorded, four blocked, none discarded.** Every bundle carries an
`archive_recording` copy of what it replaced under `superseded/`, so the superseded numbers stay
checkable — which is the whole reason that directory exists and the reason a bump is affordable
rather than destructive.

### What the bump cost, stated because the next one will cost the same

**The narratives were the expensive part, not the recordings.** Eleven recordings ran unattended in
about three hours. Reconciling eleven narratives against new captures took a careful pass each, and
**seven of them carried at least one claim the new captures contradict** — see PLAN.md for the list.
The contradictions were not stylistic: three narratives described a page composition that no longer
matched what fired, and one asserted a recovery alert the new recording does not contain.

**A guard cannot do this.** CATALOG.md already records that no guard reads a sentence. What the
guards caught was the front matter, `recorded_from`, and the rendered pages; every prose
contradiction was found by reading `logs/` first and then the manifest, and would have survived a
green `make check` otherwise.

**One test moved from a live recording to an archived one.** `test_a_service_that_alerts_during_and
_after_stays_in_the_blast_radius` pinned T7.3's fix against `product-catalog-flag-failure`, whose
new recording has no after-revert alert at all. Its fixture now reads
`superseded/20260828T035307Z/`. **A scorer test about an alert shape belongs against a recording
that has the shape**, not against whichever recording is current — the test's own docstring had
already predicted this, having made the same move once before.

### Every published figure now names its world

README, `docs/RESULTS.md` and eleven files under `evals/runs/` each carry a banner saying the
figures describe `299d791c5e0d…` and **that nothing has been re-run against the new world, so there
are no current-world figures**. The distinction matters and is stated rather than implied: those
numbers are not wrong, they are correct about a world that no longer exists, and they do not carry
over. What is worth re-measuring is a separate pre-registered decision, deliberately not taken here.

Revisit if: a future bump changes the *shape* of a bundle rather than the world it describes, in
which case `bundle_schema_version` is the mechanism and this addendum does not apply.
