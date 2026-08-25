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
from faultline.context.graph import EdgeKind
from faultline.orchestrator.models import Incident, Severity


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


class Direction(StrEnum):
    """Which way the edge was crossed, and therefore what membership claims.

    The distinction is forced by what `edge_kind` measures. ADR-0017's addendum defines `sync`
    as *a callee failure was observed to propagate to the caller* - a **directed** statement.
    It licenses "this callee failed, so its caller is affected". It does not license the
    reverse, and treating the graph as undirected reads a measurement backwards.
    """

    SEED = "seed"
    ALSO_AFFECTED = "also_affected"
    """Reached **upstream** (callee -> caller). Failure propagates this way, and it is
    transitive - a caller of an affected caller is affected - so it is followed to the full hop
    radius."""

    CANDIDATE_CAUSE = "candidate_cause"
    """Reached **downstream** (caller -> callee), one step, and only from a service that
    actually alerted. This is not propagation: a callee of an erroring caller has not been shown
    to be affected, it is a place the error might have come from. `email-wrong-image` is the
    shape - `checkoutservice` alerted and `emailservice`, the broken one, never alerted at all.

    One step, and only from seeds, because the claim does not compose: the callee of a
    *candidate* is a candidate for a fault nobody has evidence of."""


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
    """Blast radius by traversal over measured edge kinds.

    Two traversals, because the graph carries two different claims and `sync` is a
        **directed** measurement (ADR-0017's addendum: *a callee failure was observed to propagate
        to the caller*).

        **Upstream, transitive, to the hop radius** - callee to caller, which is the direction the
        measurement licenses. If `adservice` dies its caller `frontend` is affected, and a caller of
        an affected caller is affected too.

        **Downstream, one step, from alerting services only** - caller to callee, which names where
        an error could have come from. `email-wrong-image` is why this exists at all: checkout
        alerted, and `emailservice`, the broken one, never alerted. It does not compose, so it is
        not followed: the callee of a candidate is a candidate for a fault nobody has evidence of.

        Treating the graph as undirected instead reads the measurement backwards and inflates the
        result - from an `adservice` failure it reaches `cartservice`, which shares a caller with
        `adservice` and has nothing to do with it.

        `async` is not crossed in either direction. `frauddetectionservice` was dead for 852 seconds
        while checkout kept completing orders, so neither tells you anything about the other.
    """

    def __init__(self, catalog: ServiceCatalog, hop_radius: int) -> None:
        self._catalog = catalog
        self._radius = hop_radius
        """`DependencyPolicy`'s radius, passed in rather than chosen. Triage does not invent its
        own: correlation and blast radius disagreeing about how far apart two services are would
        make an incident and its radius describe different graphs (ADR-0017)."""

    def run(self, incident: Incident) -> TriageResult:
        members: dict[str, BlastRadiusMember] = {}
        unmeasured: list[tuple[str, str]] = []

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

        # Upstream: failure propagating to callers, transitively, to the hop radius.
        frontier = [(service, 0) for service in seeds]
        while frontier:
            service, depth = frontier.pop(0)
            if depth >= self._radius:
                continue
            for caller, kind, edge in self._callers_of(service):
                if kind is EdgeKind.ASYNC:
                    continue
                self._note_unmeasured(kind, edge, unmeasured)
                if caller in members:
                    continue
                members[caller] = self._member(
                    caller, kind, Direction.ALSO_AFFECTED, depth + 1, service, edge
                )
                frontier.append((caller, depth + 1))

        # Downstream: one step from what actually alerted, naming where the error could have
        # come from. Not transitive - see `Direction.CANDIDATE_CAUSE`.
        for service in seeds:
            for callee, kind, edge in self._callees_of(service):
                if kind is EdgeKind.ASYNC:
                    continue
                self._note_unmeasured(kind, edge, unmeasured)
                if callee in members:
                    continue
                members[callee] = self._member(
                    callee, kind, Direction.CANDIDATE_CAUSE, 1, service, edge
                )

        return TriageResult(
            incident_id=incident.id,
            severity=incident.severity,
            blast_radius=sorted(
                members.values(), key=lambda m: (m.hops, m.entered_at or datetime.max, m.service)
            ),
            start_from=self._start_from(members),
            unmeasured_edges=sorted(unmeasured),
        )

    # --- helpers --------------------------------------------------------------

    def _member(
        self,
        service: str,
        kind: EdgeKind,
        direction: Direction,
        hops: int,
        reached_from: str,
        edge: tuple[str, str],
    ) -> BlastRadiusMember:
        unmeasured = kind is EdgeKind.UNMEASURED
        return BlastRadiusMember(
            service=service,
            reason=EntryReason.UNMEASURED_EDGE if unmeasured else EntryReason.SYNC_EDGE,
            direction=direction,
            presence=self._presence(service),
            hops=hops,
            reached_from=reached_from,
            via_edge=edge if unmeasured else None,
        )

    @staticmethod
    def _note_unmeasured(
        kind: EdgeKind, edge: tuple[str, str], seen: list[tuple[str, str]]
    ) -> None:
        if kind is EdgeKind.UNMEASURED and edge not in seen:
            seen.append(edge)

    def _callers_of(self, service: str) -> list[tuple[str, EdgeKind, tuple[str, str]]]:
        return [
            (edge.parent, edge.kind, (edge.parent, edge.child))
            for edge in self._catalog.graph.edges
            if edge.child == service
        ]

    def _callees_of(self, service: str) -> list[tuple[str, EdgeKind, tuple[str, str]]]:
        return [
            (edge.child, edge.kind, (edge.parent, edge.child))
            for edge in self._catalog.graph.edges
            if edge.parent == service
        ]

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
