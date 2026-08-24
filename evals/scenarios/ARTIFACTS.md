# Rehearsal artifact bundle (T1.5 / ADR-0009)

Every rehearsed scenario leaves exactly one bundle:

```
evals/scenarios/artifacts/<split>/<scenario-id>/
├── manifest.json          machine-readable facts and provenance
├── incident.md            the narrative — hand-written, the only file that matters most
├── queries.md             the exact PromQL behind every metrics/ file
├── metrics/
│   ├── error-ratio.json   query_range over the incident window
│   ├── call-rate.json
│   ├── latency-p95.json
│   ├── alerts-firing.json ALERTS series — when each alert fired and cleared
│   └── runtime.json       the target's own runtime series — capture set 2 only
└── logs/
    └── <target>.txt       best-effort Loki pull for the injected service
```

`manifest.json`'s `capture_set` says which of those files to expect; absent means the four
above `runtime.json`. The ten bundles recorded before the fifth capture carry no
`capture_set` and are staying that way — see below.

The path is the quarantine (T1.6): `<split>` is the scenario's own split, and the guard
tests in `tests/test_contamination.py` fail the build if a bundle lands on the wrong side.

## The capture set changed, and the existing ten are not being re-recorded

The original four `query_range` results — error ratio, call rate, p95, and the firing-alert
series — describe an incident's *shape*: what broke, how hard, for how long, and what
alerted. They do not contain the series that discriminates the three `resource_exhaustion`
scenarios.

Measured on `ad-memory-squeeze` and `recommendation-memory-squeeze`: a service's own
runtime metrics (`process_runtime_jvm_*`, `runtime_cpython_*`, and their Go and .NET
equivalents) do reach Prometheus, and their **disappearance** under fault separates "no
traffic because the process is gone" from "no traffic because nobody called it" — a
distinction no captured query can make, and one `ServiceNoTraffic` cannot make either. See
`CATALOG.md`, "Runtime metrics reach Prometheus, and their absence is the signal", for the
measurements and the boundary conditions.

### The decision

**The recorder takes a fifth capture, from the next rehearsal onward.**
`metrics/runtime.json` holds the target service's runtime series, selected on
`exported_job` — not `service_name`, which every other query uses and which does not exist
on these series. `evalharness.prom.runtime_query` is the query; `queries.md` records it in
each bundle like the other four.

**Every bundle names its capture set.** The manifest gains `capture_set`, and its absence
means the original four. A catalog recorded across this change is then legible rather than
silently inconsistent: a bundle says what it holds, and `tests/test_artifact_bundle.py`
checks it in both directions — a set-2 bundle without `runtime.json` fails, and so does a
set-1 bundle that has one.

**The existing ten stay as they are.** Two reasons, and the second is the load-bearing one:

- Their narratives' runtime-series claims were verified against the live world, not against
  the bundles, and those measurements are recorded in `CATALOG.md`. The evidence exists; it
  is one directory over.
- **Backfilling is impossible, not merely unattractive.** Prometheus retention is 6h and
  the server started `2026-08-24T08:53Z`. Every recorded window is from 2026-08-23, so the
  data is gone — verified by querying at `cart-dependency-latency`'s `t_inject` and getting
  no data back. The only way to give the ten a `runtime.json` is to re-record all ten, which
  orphans ten hand-written narratives for evidence whose absence is already documented.

  The 6h horizon is itself locked: retention lives in `compose/telemetry.yml`, one of the
  three `compose_digest` inputs, so raising it invalidates every bundle. It is queued for
  T7.1's re-record — see `CATALOG.md`, "Prometheus keeps 6 hours, and raising it invalidates
  the catalog", which is also the general argument for why a bundle's captures are the only
  durable record of a run.

**This is not the schema-v2 precedent, and the difference is the point.** ADR-0014 bumped
`bundle_schema_version` and obsoleted every bundle before it, so it is fair to ask why this
does not.

| | v1 → v2 (ADR-0014) | capture set 1 → 2 |
|---|---|---|
| what changed | `world.compose_digest`, `ffs_stub_source_digest` | one more metric file |
| effect on existing bundles | **made them false** — they claimed a world they could not identify, and one guard compared a field that produced false positives | none: they hold exactly what they say they hold |
| comparability | the field *is* comparability — without it, two bundles claiming the same world described different ones | additive evidence, with a boundary the manifest states |
| cost of the alternative | three bundles, ~1h | ten bundles and ten narratives, for data that cannot be recovered anyway |

v2 was load-bearing for comparability itself. This is additive evidence with a documented
boundary, which is why it is an optional manifest field rather than a version bump — see
`evalharness.provenance.CAPTURE_SET`.

**T7.1 is the natural uniform re-record.** It grows the catalog past 30, every scenario is
rehearsed against one world for that, and the mixed set closes itself there without a
re-record whose only purpose is uniformity.

### What this leaves open for T4.2

The ten set-1 bundles seed the corpus (T2.4b) without a `runtime.json`, so an agent
learning from past incidents sees the runtime-series argument in `incident.md` prose and
never in captured evidence. Whether that costs anything is T4.2's to measure — it is the
first task that scores against this evidence — and it is now a question about a documented
difference between bundles rather than about a gap nobody wrote down.

## `superseded/` — manifests from earlier recordings

A re-record replaces `manifest.json`, and the previous one is gone. Every number ever cited
from it then becomes unverifiable, which has happened three times: ADR-0012 quotes a 567ms
reading from a replaced bundle, the stub image ids that split the catalog's provenance came
from manifests no longer in the tree, and CATALOG.md's 197s onset for `cart-bad-image-tag`
survived for a while only as a sentence in that document.

`--force` archives the outgoing recording before writing the new one:

```
superseded/20260823T160717Z/
├── manifest.json
└── metrics/
    ├── error-ratio.json.gz
    ├── call-rate.json.gz
    ├── latency-p95.json.gz
    └── alerts-firing.json.gz
```

**Manifest plus compressed metrics. Logs are excluded.** The archive kept manifests alone
at first, on the reasoning that metrics are megabytes and disposable. That cost a real
argument within a day: settling whether `cartservice` was bimodal needed the metric window
of a recording that had been replaced, and only the manifest had survived. Numeric JSON
gzips to roughly a tenth, so a whole capture is on the order of a hundred kilobytes.

Logs stay out because they are the largest capture and the one nothing has ever cited. If
that changes, revisit it then.

`clear_bundle` preserves `superseded/` alongside `incident.md`, so re-recording does not
wipe the archive it just added to.

**Two layouts exist.** Predecessors recovered from git history are flat
`superseded/<t_inject>.json` files — a manifest and nothing else, because a manifest is all
git had. Anything the recorder archives itself is a directory with metrics beside it. The
guard accepts both; a flat entry means no metric window survives for that run.

### The archive is not complete, and cannot be

It begins today. Everything recorded before it exists only if a copy happened to be
committed, so the archive was backfilled from git history — which recovers a predecessor
only where one was committed before being replaced.

| Bundle | Archived predecessors |
|---|---|
| `cart-redis-misconfig` | **4** — 06:03:51, 06:38:03, 07:40:38, 08:16:35 |
| `ad-memory-squeeze` | 1 — 08:45:41 |
| `cart-bad-image-tag` | 1 — 16:07:17 (the 197s onset CATALOG.md cites) |
| `cart-dependency-latency` | 1 — 08:30:22 |
| `currency-cpu-throttle`, `flag-service-crashloop`, `product-catalog-flag-failure`, `productcatalog-dependency-latency`, `recommendation-memory-squeeze`, `shipping-wrong-image` | **none** |

The six with none have either never been re-recorded or were re-recorded before the
predecessor was ever committed. **Absence of an entry is not evidence that a bundle was
never re-recorded** — several were, and their earlier manifests are simply lost. Read the
table as "what survives", not as a history.

A guard checks that whatever is in `superseded/` parses, is named for the `t_inject` it
contains, and does not duplicate the live manifest. It does not require the directory to
exist.

## Everything under `artifacts/` is a capture, not source

**No tool in this repo may rewrite a file under `evals/scenarios/artifacts/.`** These are
logs and metric series pulled straight from the running world; their value is that they are
exactly what the system produced. A formatter that strips a trailing space from a container
log, or reflows a metric JSON, makes the committed bundle a rendering of the capture rather
than the capture — and nothing afterwards can tell the difference.

**`evals/baselines/` and `docs/evidence/` are under the same rule.** Quiet-world baselines
are captures of exactly the same kind — raw metric JSON and the summaries generated from it
— and `docs/evidence/` holds webhook payloads, service logs and `psql` dumps taken from live
runs. All three are cited in ADRs the same way bundle metrics are. The rule is about
captured evidence, not about one directory.

`.pre-commit-config.yaml` therefore excludes all three trees from `trailing-whitespace` and
`end-of-file-fixer`, under a single `captured_evidence` pattern shared by the two hooks.
The read-only hooks still apply and should stay: `check-yaml`, `check-json`,
`check-added-large-files` and `detect-private-key` guard a capture without touching it.

A regex cannot tell a capture from source, so the pattern lists directories — and the two
kinds sit side by side, since `evals/scenarios/*.yaml` is authored and must stay formatted
while `evals/scenarios/artifacts/` beneath it must not be touched. **Any new directory that
holds recordings has to be added there.** That has now been learned three times: once for
bundles, again when `evals/baselines/` was rewritten by a hook after the same defect had
already been fixed, and a third time when `docs/evidence/t2.2-live-smoke/final-state.txt`
was rewritten at commit time.

**That third one is committed in its rewritten form.** The hooks stripped the trailing
padding from `psql`'s column headers before the exclusion existed. No value changed — only
whitespace — but the file will not byte-match a fresh `psql` run, and re-recording it would
mean re-running an injection to reproduce a cosmetic difference. It stays as it is, and
`docs/evidence/t2.2-live-smoke/README.md` says so at the point where a reader would go
looking. It is the last file this can happen to.

Authored files that live inside these trees are excluded too — `incident.md`, and each
evidence directory's `README.md`. That costs a little tidiness and is the right side of the
trade: an unformatted README is untidy, a rewritten capture is a record of something the
world did not produce.

If a capture needs to change, re-record it. Editing one in place produces an artifact that
claims to be evidence and is not, which is the failure ADR-0009 is built around.

## Recording one

```
uv run python -m evalharness.rehearse <scenario-id>
```

The recorder injects the fault, waits for an alert, holds steady state for five minutes,
reverts, waits for the alert to clear, then captures the metric window and writes
everything above. It drives the injector through its CLI only — never its internals — so
that T4.1 can later reuse the same boundary.

It cannot write `incident.md`. That one is yours.

## incident.md is the corpus

This is the file T2.4b seeds the past-incident store from, and it is the file a retrieval
agent will surface months later when it sees a similar incident. Everything else in the
bundle is supporting evidence; this is the thing that gets read.

Three rules. The first two are the difference between a corpus that teaches and one that
cheats; the third is what stops the writing being thrown away.

**Write it from the responder's chair, not the author's.** You know the root cause because
you injected it. The person the corpus is simulating did not. If the narrative opens with
"the flag service was deployed with a broken image", you have written an answer key, and
retrieval will hand it to the agent verbatim. Open with what was actually visible: which
alert fired, what the dashboard looked like, which service was loudest.

**Keep the dead ends.** A real investigation checks three things that turn out to be
irrelevant before finding the one that matters. Those wrong turns are the most useful
thing in the document — they are what makes a retrieved incident a piece of experience
rather than a lookup table. Delete them and you have written a spoiler.

**No absolute timestamps in the prose.** Write `T+3m`, "about four minutes after the page",
"once cart stopped serving" — never `08:02:41`. Two reasons, and both are load-bearing:

- *A re-record orphans them.* Wall-clock times belong to one recording. Two bundles needed
  re-recording in a single evening, and every timestamp written into a narrative would
  have silently become a reference to an incident that no longer exists — text that still
  reads as fact. The manifest holds the wall clock and is regenerated with the recording;
  `incident.md` is preserved across re-records precisely because it is the one file a
  person wrote, so it must not contain anything a re-record invalidates.
- *They carry no information anyway.* A retrieved incident is read months later by an agent
  matching it against a live problem. That it happened at 08:02 on a Saturday tells the
  reader nothing. That the cascade reached seven services three minutes after the page
  tells them everything.

The generated template already renders its tables this way — offsets from onset for the
page, offsets from the page for everything after. Match it in the prose.

### The front matter does the opposite, on purpose

`recorded_from` in the front matter is an **absolute** timestamp, copied verbatim from the
manifest's `t_inject`. This looks like a contradiction of the rule above. It is the point.

| | written to | so that |
|---|---|---|
| prose | **survive** a re-record | a narrative is not silently orphaned by one |
| `recorded_from` | **fail** on a re-record | a narrative cannot silently outlive one |

A re-record changes `t_inject`. `test_every_narrative_names_the_recording_it_describes`
compares the two and fails the build the moment they diverge, which is exactly when the
prose has stopped describing the bundle beside it. Without it a stale narrative sits green
over facts that no longer hold — that happened, and it was caught by eye rather than by a
test.

`onset_to_page` is guarded the same way against `seconds_to_alert`. Both the template and
the guard format durations through `evalharness.rehearse.duration`, one function, so the
check cannot start failing on narratives that are perfectly correct.

**Do not "fix" the inconsistency.** Removing the absolute timestamp from the front matter
would remove the only thing tying a narrative to its recording.

### Known limitation: prose outside `incident.md` is unguarded

This closes the gap for narratives only. **ADR prose citing bundle contents is still
unchecked**, and it has already gone wrong: ADR-0012 quotes a `cartservice` figure of 567ms
from a `cart-redis-misconfig` recording that has since been replaced, and nothing in the
repository noticed. The committed bundle now peaks at 2ms in the same window.

There is no `recorded_from` equivalent for a paragraph in `docs/adr/`. A checksum would
need every citation to name the bundle and the field it came from, which is a bigger change
than the problem currently justifies. Until then: **an ADR quoting bundle numbers is
quoting a snapshot, and a re-record can invalidate it silently.** Date such claims and say
which recording they came from, so a reader can at least tell that the recording has moved
on.

Never mention the injector, the scenario id, or the fault class inside the prose.

## manifest.json

Written by the recorder. Required keys:

| Key | Meaning |
|---|---|
| `origin` | `scenario:<id>` — the provenance stamp T4.1b's exclusion filter reads |
| `scenario_id`, `split`, `fault_class` | copied from the scenario, so a bundle is self-describing |
| `injection` | target, method, params — exactly what was run |
| `t_inject`, `t_alert_firing`, `t_revert`, `t_clear` | UTC timestamps |
| `seconds_to_alert` | detection latency; `null` if no alert fired |
| `bundle_schema_version` | **2** — see ADR-0014. A v1 bundle fails the guards and must be re-recorded |
| `world.compose_digest` | sha256 over the three layered compose files, in load order |
| `world.ffs_stub_source_digest` | sha256 over `compose/ffs-stub/`, sorted by filename |
| `world.ffs_stub_image_id` | informational only — a build artifact, never compared between bundles |
| `alerts_at_fire` | what was firing at that moment — the page a responder would have got |
| `alerts_over_window` | every firing episode across the incident, with first/last seen |
| `window` | the span the metric captures cover |

A bundle whose `seconds_to_alert` is `null` is not necessarily wrong — some faults are
meant to be quiet — but it needs a note in `incident.md` saying so deliberately.

### What identifies a world (schema v2)

Two fields answer "was this recorded against the same world as that", and they are the only
two compared between bundles:

- **`compose_digest`** — sha256 over `world/docker-compose.yml`,
  `compose/world-arm64.override.yml` and `compose/telemetry.yml`, concatenated in the order
  compose layers them. Every container's limits, image and environment are in those files,
  so an edit to any of them is a different world. Raising kafka's memory limit changed the
  world and no v1 manifest could show it.
- **`ffs_stub_source_digest`** — sha256 over everything in `compose/ffs-stub/`, sorted by
  filename. The stub's source, not its image.

**`ffs_stub_image_id` is kept but is informational.** It is a build artifact: it changed
overnight from unchanged source when `make world-up` rebuilt the image and re-resolved a
pip layer. Comparing it reported a difference that was not one. `make ffs-stub` now stamps
the source digest and rebuilds only when it changes, so the image is stable — but the guard
still does not compare it, because the guard should not depend on that discipline holding.

### The three existing valid bundles are stale by design

`ad-memory-squeeze`, `cart-dependency-latency` and `cart-redis-misconfig` are v1 and now
fail two guards each. **This is the intended state, not a break to work around.** They are
queued for re-record.

Do not backfill the new digests into them. Beyond ARTIFACTS.md's rule that captures are
never rewritten, a backfilled digest would be *false*: those three were recorded under the
old container memory limits (kafka 1200M, paymentservice 200M, quoteservice 120M), so they
genuinely describe a different world from the one a digest computed today would name.

### The two alert fields have different shapes

This is a wart. `alerts_at_fire` is a flat list of **strings**; `alerts_over_window` is a
list of **objects**. Reading one as though it were the other raises
`AttributeError: 'str' object has no attribute 'get'`, which has already caught one
ad-hoc query.

```python
paged = {a.split("/")[0] for a in m["alerts_at_fire"]}            # "ServiceHighErrorRate/frontend"
grew  = {(e["alert"], e["service"]) for e in m["alerts_over_window"]}   # {"alert": ..., "service": ...}
```

**It is not being fixed, deliberately.** Nothing downstream loses information to it: both
fields carry the alert name and the service, and every consumer reads one or the other
rather than merging them. The shapes differ because they were added at different times for
different questions — `alerts_at_fire` is a snapshot the recorder already had in hand,
`alerts_over_window` is derived from the captured series and needs per-episode timestamps
a string cannot hold.

Normalising them would change the manifest shape, which means bumping
`bundle_schema_version` from 1 to 2, which obsoletes every bundle recorded before the bump.
At ~20 minutes per scenario, serial because they share one world, that is roughly three
hours of re-recording to make two field shapes match. ADR-0009 sets the bar for a bump at
*a field a downstream phase cannot work without and cannot derive from what is captured* —
cosmetic consistency is explicitly below it. An awkward field shape that works is cheaper
than three hours.

## Marking a scenario rehearsed

Set `rehearsed: true` in the scenario YAML **only** once `incident.md` is finished. The
guard tests read that flag: a rehearsed scenario must have a bundle, and a finished
`incident.md` must have no template comments left in it.

### First, check every expected_evidence item against the bundle

Before flipping the flag, walk the scenario's `expected_evidence` list and confirm the
bundle actually contains each item. Correct — or move — any item the world does not
produce.

This is not a formality, and rehearsal is the only point where it is discoverable. The
scenarios were authored from how the system *should* behave; the bundle is what it
*does*. An eval that scores an agent against evidence which does not exist measures
nothing: the agent cannot find it, loses the point, and the score reads as a reasoning
failure when it is a labelling error.

Three failure shapes to look for, all of them seen at least once:

- **The signal exists, but on a different telemetry type.** Most common by far. Check the
  traces before deleting an item — a service that records something on a span very often
  logs nothing at all.
- **The service is too quiet to produce it.** Several demo services log only a startup
  banner at their default level. Silence in `logs/` is not evidence of health.
- **The signal exists but not in the captured window.** Widen `--dwell`, or note the
  timing in the item so it is reproducible.

### Also check for signal the world produced on its own

**Superseded.** This section used to say `cartservice` is bimodal, reaching 353ms unprompted
about once every 29 minutes, and told you to expect roughly six such excursions across the
catalog and to discount them as background. That was wrong: every reading behind it was
taken while the container was still warming up from a recreate. A clean 45-minute baseline
measures `cartservice` at a flat 1.9ms with zero excursions (ADR-0012, third correction).

What to check instead:

- **Warm-up transients.** A recreated container takes about four minutes to settle;
  `cartservice` decays from ~100ms to 1.9ms over that span. A p95 sampled inside that
  window is not a baseline reading. The recorder now refuses to start when any container
  has been up under five minutes, so new bundles should be free of this — but bundles
  recorded before that gate exists are not, and
  `productcatalog-dependency-latency`'s pre-injection window contains one.
- **Alerts on services the fault never touched.** Still worth looking for, and still not
  blast radius. Check `began_after_revert` first, since that already separates
  recovery-phase alerts from incident ones.
- Note either in the narrative only if a responder would have been misled by it, which is
  itself worth recording: a spurious signal during a real incident is a realistic thing for
  an investigation to have to dismiss.

Corrections already made this way:

| Scenario | Item | What happened |
|---|---|---|
| `product-catalog-flag-failure` | `logs:` the failure is reported as a deliberate flag-driven path | Moved to `traces:`. `product-catalog-service` emitted one line in 4.75 hours — its startup banner. The demo records this failure with `span.SetStatus` and `span.AddEvent` and never logs it, so the item was unobtainable as written. |

Nothing else in the ten scenarios claimed log evidence from a service measured silent.
`flag-service-crashloop` is the one to re-check at its own rehearsal: it expects a repeated
startup line, which the stub does emit on every restart, but the restart cadence has never
been observed.
