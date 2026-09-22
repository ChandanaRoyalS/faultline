# The harness still speaks v1 — 2026-09-22, an inventory rather than a discovery

**\$0, no model call, no live world needed.** The gate was found blind on v2 by accident, while
looking for somewhere to put an unrelated check. **That is not a repeatable way to find this class
of defect**, and the gate was unlikely to be the only one. This is the survey that should have
happened when the world moved: every place in the harness that names a v1 metric, service or
container, what each one does on v2, and which ones have been fixed.

## The failure mode, stated once

**PromQL over a metric that does not exist is an empty result, not an error.** A v1 metric name on
the v2 world therefore produces a successful query returning nothing, which every consumer here
reads as *a quiet world*. Nothing raises, nothing logs, nothing refuses.

The three consumers differ only in **what they do with the silence**, and that is what sorts this
list:

- a **gate** that sees nothing refuses nothing — it certifies a world it never measured;
- a **bundle** that captures nothing records an empty world as evidence — and a run scored against
  it registers a miss the agent did not make;
- an **agent** shown nothing reports that it found nothing — truthfully, about a question it was
  never allowed to ask.

## Fixed here, because they fail silently

| where | what it did on v2 | cost |
|---|---|---|
| `rehearse.py` bundle capture | built four captures from the v1 `METRIC_QUERIES` constant | **four empty series in every recorded bundle** |
| `baselines.py` B0 | `render_query(..., service)` with no world → v1 by default | **B0's only metric signal empty; it reports "no service moved" as a finding** |

**The bundle one is the most expensive defect found today.** A gate's blindness costs the refusal it
failed to make; a bundle's blindness is written into the corpus, scored, and read afterwards as a
fact about the agent. The run completes normally. `rehearse` now builds its captures from
`metric_queries(metrics_for(ToolSettings().world))` and records `world` in the bundle's facts, so a
later reader can tell an empty series that means *quiet* from one that means *asked in the wrong
language*. Both are pinned by source guards in `tests/test_spanmetrics.py`.

**`render_query`'s v1 default is what made B0's version possible**, and the default is still right:
it is what keeps 197 scored runs' expressions frozen byte for byte. The lesson is narrower — a
default that is safe for the thing it protects is a trap for every caller that forgets to override
it, so the guards name the callers rather than removing the default.

## Not fixed, and each one says why

| where | shape | behaviour on v2 |
|---|---|---|
| `gate.HEADROOM_GROWTH_MB_PER_HOUR = 151.0` | a v1 measurement (T7.29) with no world attached | projects v2's kafka with v1's rate; **Q88** |
| gate's kafka remedy text | names `accounting-service`, `frauddetection-service`, `checkout-service` | **fails loudly** — v2 calls them `accounting`, `fraud-detection`, `checkout` |
| gate's kafka remedy text | attributes growth to Rosetta translation cache (ADR-0005) | **cannot be true here** — v2 is native arm64, measured |
| `injector/world.py` `SERVICE_CONTAINERS`, `canonical_service` | v1's two naming schemes (`cartservice` / `cart-service`) | falls through to identity, which is accidentally right for v2 and **untested there** |
| `context/catalog.py` `KNOWN_ABSENT` | cites `count by (service_name) (calls_total)` returning 15 services; entries for `featureflagservice`, `frontendproxy` | **prose handed to the agent**, describing a world it is not in; changing it moves `prompt_digest` |
| `provenance.py` cover set | covers `world/src/otelcollector/otelcol-config.yml` | v2's clone is `world-v2/`; **the v2 collector config is covered by nothing**, so a change to it moves no digest |
| `rehearse.STUB_IMAGE = "ffs-stub:1"` | ADR-0006's flag-service stub | v2 has flagd natively; the stub is deletable rather than portable |

**The loud ones are left deliberately.** A remedy naming a container that does not exist fails at
the shell with `No such container`, which is a bad experience and not a wrong answer. They get fixed
with the injector work, where the v2 service names are being handled anyway.

**The provenance gap is the one that most resembles today's defects** and it is not small: a world
whose observability configuration is outside the cover set can change without moving
`observability_digest`, which is Q31's territory. Recorded here; not opened as a new row, because
Q31 already names the generation-identity problem and this is the same hole seen from the v2 side.

## What this survey does not cover

**The scoring path.** `evalharness.run` and the comparison code were not read for world assumptions
beyond their use of the gate. The scenarios themselves are v1 targets and cannot run on v2 at all,
so that path fails loudly today — but it will stop failing loudly the moment the v2 injector lands,
and it should be surveyed before then rather than after.

**How it should have been found.** Not by a survey after the fact. The general shape is a check that
every PromQL this repository sends resolves to at least one series on the world it is pointed at —
which is what `gate`'s new "no service reports a call rate" refusal does for two queries, and what
nothing does for the rest.
