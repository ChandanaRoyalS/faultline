"""Triage: the blast radius of an incident, as a set with entry times (T3.1, ADR-0020 §6).

**What triage produces and what it deliberately does not.** ADR-0020 gives it three outputs -
severity, blast radius, and the service to start from - and no tools: it reasons over what
ingest already gathered plus the dependency graph. It does not name a culprit. Every rehearsed
narrative that ranks services by how bad they look is describing a wrong turn; the
`productcatalog-dependency-latency` narrative says it outright - "ranking services by how bad
they look points at a symptom".

**Why this is computed rather than asked.** ADR-0020 chose a model for the agent layer and is
silent on whether every role calls it. Blast radius is a traversal of a measured graph, so it
is computed: the answer is deterministic, T3.1 scores it against a bundle, and a scored number
that moves when nothing changed is not a measurement. The seam for a model-based triage exists
if T4.2 ever wants to compare one against this.

**Edge kinds are consumed by their definition, not by their name.** ADR-0017's addendum:
`edge_kind` records *measured failure propagation, not messaging mechanism*. `sync` means a
callee failure was observed to reach the caller, `async` means it was observed not to, and
`unmeasured` means no bundle broke that callee. `frontend -> recommendationservice` is `sync`
while its own narrative says the frontend does not fail when recommendations fail - both true,
because the frontend degrades *and* errors. A traversal reading `sync` as "blocking RPC" would
drop that edge and under-report the radius by a service the alerting itself named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from faultline.context.catalog import GraphPresence, ServiceCatalog
from faultline.context.graph import Direction, EdgeKind, Reach
from faultline.orchestrator.models import Incident, Severity

__all__ = [
    "BlastRadiusMember",
    "Direction",
    "EntryReason",
    "Triage",
    "TriageResult",
]
"""`Direction` is re-exported rather than defined here: it moved to the graph layer with the
traversal at the Phase 2 audit's D4, and `from faultline.agents.triage import Direction` is how
the call sites and the tests already spell it."""


class EntryReason(StrEnum):
    """How a service got into the blast radius. Always recorded, never inferred later."""

    ALERTED = "alerted"
    """It has an episode in the incident. The only reason with an observed entry time."""

    SYNC_EDGE = "sync_edge"
    """Reached across an edge measured to propagate failure."""

    UNMEASURED_EDGE = "unmeasured_edge"
    """Reached across an edge with no measurement either way. **Included and flagged**, never
    silently promoted to `sync_edge`: it is in the radius because excluding it would assert a
    measurement nobody made, and it is marked because including it is not one either."""


@dataclass(frozen=True, slots=True)
class BlastRadiusMember:
    """One service in the radius, with how and when it got there."""

    service: str
    reason: EntryReason
    direction: Direction
    presence: GraphPresence | None
    """From `ServiceCatalog`. `UNINSTRUMENTED` or `ARTIFACT_ONLY` services stay in the output
    carrying that provenance rather than being dropped - a service the graph cannot see is not
    a service that was unaffected. `None` means the catalog has never heard of it at all."""

    entered_at: datetime | None = None
    """When it entered, for services that alerted. **`None` for graph-derived members**, and
    that is not a gap to fill: a service reached across an edge never alerted, so no entry time
    was observed, and inheriting one from the service it was reached from would invent a fact.
    ADR-0009's scoring compares against alerting services, which are exactly the ones that have
    a time."""

    hops: int = 0
    reached_from: str | None = None
    via_edge: tuple[str, str] | None = None
    """The edge crossed to reach it. Populated for `UNMEASURED_EDGE` so the output says *which*
    edge is unmeasured and *which* service arrived through it."""


@dataclass(frozen=True, slots=True)
class TriageResult:
    """Triage's whole output. **A set with entry times, not a ranked list.**"""

    incident_id: str
    severity: Severity
    blast_radius: list[BlastRadiusMember]
    start_from: str | None
    """Where to look first. **Not a culprit claim.** The earliest-alerting service that the
    graph can actually reason about - synthetic clients and uninstrumented services are skipped,
    because three narratives open by setting `loadgenerator` aside as "the synthetic client; its
    error rate restates what the storefront is doing and carries no information about cause"."""

    unmeasured_edges: list[tuple[str, str]] = field(default_factory=list)
    """Every unmeasured edge crossed. **Quoted with any use of the radius**, the way every
    figure in this project carries its `n`: five of the graph's fifteen edges have no
    measurement, and a radius that crossed one is a radius with a guess in it."""

    @property
    def services(self) -> set[str]:
        return {member.service for member in self.blast_radius}

    @property
    def alerting(self) -> list[BlastRadiusMember]:
        """The members with observed entry times - what ADR-0009's ground truth can score."""
        return [m for m in self.blast_radius if m.reason is EntryReason.ALERTED]

    def summary(self) -> str:
        unmeasured = len(self.unmeasured_edges)
        return (
            f"{len(self.blast_radius)} services, severity {self.severity.value}, "
            f"start from {self.start_from or 'nowhere the graph knows'}, "
            f"{unmeasured} unmeasured edge(s) crossed"
        )


class Triage:
    """An incident's blast radius: the graph's traversal, plus what only an incident knows.

    **The traversal is `ServiceGraph.blast_radius` and lives in the context layer** - two
    directions, `async` never crossed, upstream transitive and downstream one step, with the
    reasoning for each recorded there. It moved at the Phase 2 audit's D4: T2.4's deliverable
    names *"blast radius of service X"* as the graph API's core query, and it was assembled
    inside this agent instead. The executor T6.2 specifies - which must reject an action whose
    target sits outside the incident's scoped topology - needs the query where the plan put it.

    **What stays here is everything the graph cannot answer.** Which services alerted and when;
    whether the catalog has heard of a service at all and how it appears in the graph; which
    reason to record for a member; and where an investigation should start. Those are incident
    facts and catalog facts, and none of them is a traversal.
    """

    def __init__(self, catalog: ServiceCatalog, hop_radius: int) -> None:
        self._catalog = catalog
        self._radius = hop_radius
        """`DependencyPolicy`'s radius, passed in rather than chosen. Triage does not invent its
        own: correlation and blast radius disagreeing about how far apart two services are would
        make an incident and its radius describe different graphs (ADR-0017)."""

    def run(self, incident: Incident) -> TriageResult:
        members: dict[str, BlastRadiusMember] = {}

        for episode in incident.episodes.values():
            if episode.service is None:
                continue
            existing = members.get(episode.service)
            if existing is None or (
                existing.entered_at is not None and episode.starts_at < existing.entered_at
            ):
                members[episode.service] = BlastRadiusMember(
                    service=episode.service,
                    reason=EntryReason.ALERTED,
                    direction=Direction.SEED,
                    presence=self._presence(episode.service),
                    entered_at=episode.starts_at,
                )
        seeds = list(members)

        radius = self._catalog.graph.blast_radius(seeds, self._radius)
        for reached in radius.reach:
            members[reached.service] = self._member(reached)

        return TriageResult(
            incident_id=incident.id,
            severity=incident.severity,
            blast_radius=sorted(
                members.values(), key=lambda m: (m.hops, m.entered_at or datetime.max, m.service)
            ),
            start_from=self._start_from(members),
            unmeasured_edges=sorted(radius.unmeasured_edges),
        )

    # --- helpers --------------------------------------------------------------

    def _member(self, reached: Reach) -> BlastRadiusMember:
        """One reached service, as triage records it: the graph's claim plus the catalog's."""
        unmeasured = reached.kind is EdgeKind.UNMEASURED
        return BlastRadiusMember(
            service=reached.service,
            reason=EntryReason.UNMEASURED_EDGE if unmeasured else EntryReason.SYNC_EDGE,
            direction=reached.direction,
            presence=self._presence(reached.service),
            hops=reached.hops,
            reached_from=reached.reached_from,
            via_edge=reached.edge if unmeasured else None,
        )

    def _presence(self, service: str) -> GraphPresence | None:
        entry = self._catalog.get(service)
        return None if entry is None else entry.presence

    def _start_from(self, members: dict[str, BlastRadiusMember]) -> str | None:
        """Earliest alerting service the graph can reason about; ties broken by name.

        Skipping the graph-absent ones is measured rather than tidy. `loadgenerator` alerts in
        almost every captured incident and three narratives open by setting it aside - it is the
        synthetic client, and its error rate restates the storefront's. Starting an
        investigation there is the first wrong turn the corpus records.
        """
        candidates = [
            m
            for m in members.values()
            if m.reason is EntryReason.ALERTED
            and m.entered_at is not None
            and m.presence is GraphPresence.PRESENT
        ]
        if not candidates:
            return None
        earliest = min(candidates, key=lambda m: (m.entered_at or datetime.max, m.service))
        return earliest.service
