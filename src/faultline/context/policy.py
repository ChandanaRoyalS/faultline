"""`DependencyPolicy` - correlation against the measured graph (T2.4, ADR-0017).

Drops in wherever `TimeOverlapPolicy` sits: it satisfies the orchestrator's
`CorrelationPolicy` protocol and the orchestrator does not change. That was the point of the
seam ADR-0016 built.

**Every decision records which rule made it.** ADR-0017 requires it, and the reason is that
the failure mode here is silent: when the graph lacks an edge the policy needs, falling back
to time overlap reproduces exactly the behaviour the graph was meant to improve on *and
produces the same answer*, so nothing looks wrong. ADR-0008 makes this argument almost word
for word about filter enforcement - a defence that is never observed to fire is one nobody
can show is working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from faultline.context.catalog import GraphPresence, ServiceCatalog
from faultline.ingest.models import AlertEvent
from faultline.orchestrator.correlation import CorrelationPolicy
from faultline.orchestrator.models import Incident


class JoinRule(StrEnum):
    """Which rule decided a correlation, as ADR-0017 requires it be recorded."""

    GRAPH = "graph"
    """The graph answered - joined within the radius, or declined outside it."""

    NO_GRAPH_PRESENCE = "no_graph_presence"
    """The alerting service is not usable for graph reasoning, so time overlap decided."""

    NO_JUDGEABLE_CANDIDATE = "no_judgeable_candidate"
    """No open incident holds a service the graph knows, so there was nothing to measure
    against and time overlap decided."""


@dataclass(frozen=True, slots=True)
class Decision:
    """One correlation decision and its provenance."""

    episode_key: str
    service: str | None
    rule: JoinRule
    joined: str | None
    """The incident id joined, or `None` for a decline."""

    hops: int | None = None
    detail: str | None = None


@dataclass
class DecisionLog:
    """Where provenance goes. A list, for now, and deliberately not more.

    Persisting the rule onto the incident row is an orchestrator and schema change this task
    does not make - `incidents` has no column for it. Until then the log makes the mix
    enumerable in-process, which is what a T4.1 report would need; ADR-0017 asks for the fact
    to be recorded, and this is where it is recorded first.
    """

    decisions: list[Decision] = field(default_factory=list)

    def record(self, decision: Decision) -> None:
        self.decisions.append(decision)

    def rule_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for decision in self.decisions:
            counts[decision.rule.value] = counts.get(decision.rule.value, 0) + 1
        return counts


class DependencyPolicy:
    """Join a firing episode to an incident whose services it is within `radius` hops of.

    **Correlates on call causality, and that is deliberate.** ADR-0017's edge-semantics
    section: the trace graph records that A's work reaches B, never that A waits for B, so a
    synchronous RPC and a Kafka topic are the same edge here. Measured -
    `checkoutservice` has four edges at 286 calls each, two of each kind, identical in every
    field the dependency API returns. That distinction is out of scope for correlation, which
    asks whether two services are related at all and for which both kinds are relations, and
    in scope for blast-radius reasoning at T3.1, which cannot survive without it.

    So `frauddetectionservice` joins a checkout-adjacent incident exactly as `emailservice`
    does, even though the bundles measure their failure semantics as opposite. For
    correlation that is the right answer: the fault did reach it.
    """

    def __init__(
        self,
        catalog: ServiceCatalog,
        fallback: CorrelationPolicy,
        radius: int,
        log: DecisionLog | None = None,
    ) -> None:
        self._catalog = catalog
        self._fallback = fallback
        self._radius = radius
        self.log = log or DecisionLog()

    def match(self, event: AlertEvent, candidates: list[Incident]) -> Incident | None:
        if not self._catalog.usable(event.service):
            return self._defer(event, candidates, JoinRule.NO_GRAPH_PRESENCE)

        judgeable = [c for c in candidates if self._graph_services(c)]
        if not judgeable:
            return self._defer(event, candidates, JoinRule.NO_JUDGEABLE_CANDIDATE)

        near = [
            (distance, incident)
            for incident in judgeable
            if (distance := self._closest(event.service, incident)) is not None
            and distance <= self._radius
        ]
        if not near:
            self._record(event, JoinRule.GRAPH, None, detail=f"nothing within {self._radius} hops")
            return None

        # Closest first; a tie goes to the incident that moved most recently, which is the
        # same tiebreak TimeOverlapPolicy uses.
        distance, chosen = min(near, key=lambda pair: (pair[0], -_recency(pair[1])))
        self._record(event, JoinRule.GRAPH, chosen.id, hops=distance)
        return chosen

    def _defer(
        self, event: AlertEvent, candidates: list[Incident], rule: JoinRule
    ) -> Incident | None:
        """Hand the decision to time overlap, and say so.

        The fallback is ADR-0016's rule unchanged, reused rather than reimplemented. What is
        added is that the deferral is visible: a join that happened because the graph could
        not help looks identical in the incident to one the graph decided.
        """
        chosen = self._fallback.match(event, candidates)
        entry = self._catalog.get(event.service)
        detail = None
        if entry is not None and entry.presence is not GraphPresence.PRESENT:
            detail = f"{entry.service}: {entry.presence.value}"
        elif entry is None:
            detail = f"{event.service!r} is not in the catalog at all"
        self._record(event, rule, None if chosen is None else chosen.id, detail=detail)
        return chosen

    def _record(
        self,
        event: AlertEvent,
        rule: JoinRule,
        joined: str | None,
        hops: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.log.record(
            Decision(
                episode_key=event.episode_key,
                service=event.service,
                rule=rule,
                joined=joined,
                hops=hops,
                detail=detail,
            )
        )

    def _graph_services(self, incident: Incident) -> list[str]:
        return [
            episode.service
            for episode in incident.episodes.values()
            if episode.service is not None and self._catalog.usable(episode.service)
        ]

    def _closest(self, service: str | None, incident: Incident) -> int | None:
        distances = [
            distance
            for other in self._graph_services(incident)
            if (distance := self._catalog.graph.hops(str(service), other)) is not None
        ]
        return min(distances) if distances else None


def _recency(incident: Incident) -> float:
    moment = incident.last_activity_at
    return 0.0 if moment is None else moment.timestamp()
