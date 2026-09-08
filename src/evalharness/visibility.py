"""Whether the scenario's culprit is a name the agent could have said (T5.7).

**Reported beside the service axis, never subtracted from it.** The sibling of
`evalharness.reachability`, and it exists for the same reason: dev sweep 11 scored the culprit
service 3 of 5, and both misses were on targets the pipeline structurally cannot name.

- `featureflagservice` is in the catalog and **not in the dependency graph** - ADR-0006's stub
  reproduces the flag service's gRPC contract and none of its instrumentation, so it emits no
  spans, appears in no span-derived edge, and cannot enter a blast radius. The verdict said
  `productcatalogservice`, and its own open questions said why: *"if the flag lives on
  featureflagservice the right target is not even in the legal blast radius."*
- `redis-cart` was **not in the catalog at all** when this was written. It is a datastore, it has
  no `service.name`, and ADR-0017 marked exactly this - *"whether infrastructure belongs in the
  catalog… `kafka` and `redis-cart`… Not decided here because nothing at T2.4 consumes it; the
  first consumer should decide."* The culprit-service axis was that consumer; Addendum 3 decided,
  Q27 queued the change behind `TOOL_BEHAVIOUR_REVISION`, and **T6.1 landed it**: both are in the
  catalog as `INFRASTRUCTURE`, so a run now reports them as `in_catalog_not_in_graph` and the
  question the sweep asks is whether the synthesizer names them.

**Reported, not forgiven.** A miss on an unnameable target scores exactly as a miss. Anything
else would be the scorer edited to fit a result, which the pre-registration for that sweep ruled
out in advance and ADR-0027 already priced: a second answer is correct only when acting on it
measurably fixes the fault, and reverting config on `productcatalogservice` does not clear a flag
held in a stub. What this adds is that a reader of the run sees *which kind* of miss it was
without opening the catalog, on every future run, instead of in one sweep document.
"""

from __future__ import annotations

from typing import Any

IN_GRAPH = "in_graph"
"""The target is a node the agent's blast radius can reach. The ordinary case."""

NOT_IN_GRAPH = "in_catalog_not_in_graph"
"""Known to the catalog, absent from the graph, with a recorded reason (`KNOWN_ABSENT`)."""

NOT_IN_CATALOG = "absent_from_catalog"
"""The catalog has never heard of it. Until T6.1 that meant infrastructure - `redis-cart`, `kafka`
- which Q27 put in the catalog as `INFRASTRUCTURE`; today it means a name nobody has recorded."""

NAMEABLE = frozenset({IN_GRAPH})
"""The presences from which a verdict could have named the target at all."""


def target_visibility(target: str) -> dict[str, Any]:
    """What the agent could have said about `target`, from the committed catalog.

    Derivation, not assertion: the catalog is `docs/evidence/t2.4-dependency-graph/`'s snapshot
    plus `KNOWN_ABSENT`, both already in the tree. Computing this for an old run adds no claim
    that was not sitting in those files when it ran - the same argument `reachability` makes for
    reading a bundle's own captures.
    """
    from faultline.context.catalog import ServiceCatalog

    entry = ServiceCatalog.from_snapshot().get(target)
    if entry is None:
        return {
            "target": target,
            "presence": NOT_IN_CATALOG,
            "nameable": False,
            "reason": (
                "not in the service catalog: it emits no spans and has no service.name, so no "
                "blast radius can contain it (ADR-0017's marked decision, queued as Q27)"
            ),
        }
    if entry.usable_for_graph_reasoning:
        return {"target": target, "presence": IN_GRAPH, "nameable": True, "reason": None}
    return {
        "target": target,
        "presence": NOT_IN_GRAPH,
        "nameable": False,
        "reason": entry.reason,
    }


def note(visibility: dict[str, Any]) -> str | None:
    """The line the run report prints under a service score, or `None` when there is nothing
    to say - which is the ordinary case and must stay quiet, or the caveat becomes wallpaper."""
    if not visibility or visibility.get("nameable", True):
        return None
    target = visibility.get("target", "the target")
    where = (
        "is in the catalog but not in the dependency graph"
        if visibility.get("presence") == NOT_IN_GRAPH
        else "is not in the service catalog at all"
    )
    return (
        f"    target visibility: {target} {where}, so no blast radius could contain it - "
        f"{visibility.get('reason')}. Reported, not forgiven: this counts exactly as a miss."
    )
