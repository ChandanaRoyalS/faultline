"""Which world a recorded run executed against, and whether two runs may share a table (T7.55).

**A comparability generation is a world, not a counter.** Two runs belong to the same generation
when the world they ran in is the same one; the identifier is derived from the world digests
themselves, so nobody maintains it and nobody can forget to bump it.

## Two provenances, never conflated

`observed` — the run built a freeze manifest against the live world before it injected anything.
That is the only way a world digest can be *known*, and from T7.55 onward every run has one.

`reconstructed` — the run predates T7.55 and recorded no world at all. T7.54 established which
world it must have run in by placing its timestamp against the re-record windows below. **The
value is right and the provenance is weaker, and the two are never allowed to look alike.** A
manifest that claimed to have observed a world it reconstructed afterwards would be a lie in the
record even with the correct value in it - the same failure T7.22 had with reachability - so no
freeze manifest was ever backfilled. This module is where the reconstruction lives instead:
outside the run manifests, labelled, and derived rather than stored.

## What the windows are, and where they come from

A world move is not instantaneous. It begins when the compose edit is applied and becomes
observable at the first capture taken against the result, so each window runs from the first to
the last `t_inject` of the bundles that re-record wrote. **No run falls inside either window** -
`tests/test_world_generations.py` pins that - so every recorded run has an unambiguous world.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

T7_1_FIRST_CAPTURE = "20260828T024126Z"
T7_1_LAST_CAPTURE = "20260828T052049Z"
T7_28_FIRST_CAPTURE = "20260829T225404Z"
T7_28_LAST_CAPTURE = "20260830T013651Z"

RECORD_WINDOWS = (
    (T7_1_FIRST_CAPTURE, T7_1_LAST_CAPTURE, "T7.1"),
    (T7_28_FIRST_CAPTURE, T7_28_LAST_CAPTURE, "T7.28"),
)

WORLD_4A = "4a7690c6fdda"
WORLD_299 = "299d791c5e0d"
WORLD_F5B = "f5bd108f4f70"

WORLD_ERAS = (
    (T7_1_FIRST_CAPTURE, WORLD_4A),
    (T7_28_FIRST_CAPTURE, WORLD_299),
)
"""`(exclusive upper bound, world)`, oldest first. Anything later is the current world."""


@dataclass(frozen=True, slots=True)
class Generation:
    """A world, and how confidently this run's membership in it is known."""

    world: str
    provenance: str
    """`observed` or `reconstructed`."""

    @property
    def label(self) -> str:
        mark = "" if self.provenance == "observed" else " (reconstructed)"
        return f"{self.world}{mark}"

    @property
    def is_reconstructed(self) -> bool:
        return self.provenance == "reconstructed"


def world_from_stamp(stamp: str) -> str:
    """The world a run started at `stamp` must have executed against (T7.54's reconstruction)."""
    return next((world for bound, world in WORLD_ERAS if stamp < bound), WORLD_F5B)


def straddles_a_world_move(stamp: str) -> str | None:
    """The re-record this run started inside, if any. **A straddling run has no world at all** -
    it ran against a half-changed one, and no digest describes that."""
    return next((who for lo, hi, who in RECORD_WINDOWS if lo <= stamp <= hi), None)


def generation_of(manifest: dict[str, Any]) -> Generation:
    """This run's generation: observed from its freeze manifest, else reconstructed from its id."""
    world = (manifest.get("freeze") or {}).get("world") or {}
    digest = world.get("compose_digest")
    if digest:
        return Generation(world=digest[:12], provenance="observed")
    run_id = str(manifest.get("run_id") or "")
    return Generation(world=world_from_stamp(run_id.split("-")[0]), provenance="reconstructed")


def group_by_generation(manifests: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """**The grouping that keeps two worlds out of one table.**

    ADR-0022 §3.3 says the harness refuses to print incomparable results side by side. Separation
    is the form that refusal takes here rather than an error: the data exists and is worth reading,
    and what must not happen is a reader taking two worlds for one set of columns. An error would
    withhold correct rows to prevent a misreading that grouping already prevents.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for manifest in manifests:
        grouped.setdefault(generation_of(manifest).world, []).append(manifest)
    return grouped
