"""The service catalog: every service the system knows of, and why it is or is not in the
graph (T2.4, ADR-0017).

The distinction this exists to make is **not connected** versus **not visible**. A service
absent from the graph might have no dependencies or might emit no spans, and those are
different facts that a bare node set cannot tell apart. Every consumer that reasons about a
service needs to know which one it is looking at, so the catalog answers it explicitly and
`DependencyPolicy` branches on the answer rather than guessing from a missing key.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from faultline.context.graph import ServiceGraph
from injector.world import canonical_service


class GraphPresence(StrEnum):
    """Why a service is or is not usable for graph reasoning."""

    PRESENT = "present"
    UNINSTRUMENTED = "uninstrumented"
    """Emits no spans, so it cannot appear in a graph built from spans."""

    ARTIFACT_ONLY = "artifact_only"
    """Its only edges were excluded as artifacts of how the world is run."""


@dataclass(frozen=True, slots=True)
class ServiceEntry:
    service: str
    presence: GraphPresence
    reason: str | None = None

    @property
    def usable_for_graph_reasoning(self) -> bool:
        return self.presence is GraphPresence.PRESENT


KNOWN_ABSENT: dict[str, tuple[GraphPresence, str]] = {
    "featureflagservice": (
        GraphPresence.UNINSTRUMENTED,
        "ADR-0006's stub reproduces the flag service's gRPC contract and none of its "
        "instrumentation. Measured against Prometheus: `count by (service_name) "
        "(calls_total)` returns 15 services and it is not among them, so it cannot appear "
        "in a span-derived graph and cannot page either - not 'did not fire', but cannot "
        "(evals/scenarios/flag-service-crashloop.yaml:3).",
    ),
    "frontendproxy": (
        GraphPresence.ARTIFACT_ONLY,
        "Its only measured edge is frontendproxy -> jaeger-all-in-one, excluded as the "
        "tracing UI routing itself. It is Envoy, and the alert rules already exclude it from "
        "ServiceNoTraffic for the same underlying reason: it emits a few spans at startup "
        "and none after (compose/prometheus/alert-rules.yml).",
    ),
    "loadgenerator": (
        GraphPresence.ARTIFACT_ONLY,
        "Its only measured edge is loadgenerator -> frontend, excluded as the synthetic "
        "client (ADR-0017). Excluding the edge removes the node, so the service that alerts "
        "in almost every captured incident has no graph presence. Recorded here rather than "
        "left as an absence, because the two are different facts.",
    ),
}
"""Services that exist and are not in the graph, each with the reason it is not.

ADR-0017 requires `featureflagservice` to be carried explicitly for exactly this reason.
`loadgenerator` is here by the same argument applied to a case the ADR did not anticipate -
see the note on it, and ADR-0017's marked decisions.
"""


class ServiceCatalog:
    """Graph nodes plus the known-absent services, under one identity scheme.

    Identity is `canonical_service` throughout, which is load-bearing rather than tidy here:
    the capture contains `frontend-proxy`, canonicalising to `frontendproxy`, and node names
    are OTel `service.name` values that agree with compose service names in 12 of 13 cases.
    """

    def __init__(self, graph: ServiceGraph) -> None:
        self.graph = graph
        entries = {
            service: ServiceEntry(service=service, presence=GraphPresence.PRESENT)
            for service in graph.nodes
        }
        for name, (presence, reason) in KNOWN_ABSENT.items():
            service = canonical_service(name)
            entries.setdefault(service, ServiceEntry(service, presence, reason))
        self._entries = entries

    @classmethod
    def from_snapshot(cls) -> ServiceCatalog:
        return cls(ServiceGraph.from_snapshot())

    def get(self, service: str | None) -> ServiceEntry | None:
        """The entry for a service, or `None` if the catalog has never heard of it."""
        if service is None:
            return None
        return self._entries.get(canonical_service(service))

    @property
    def services(self) -> frozenset[str]:
        return frozenset(self._entries)

    def usable(self, service: str | None) -> bool:
        entry = self.get(service)
        return entry is not None and entry.usable_for_graph_reasoning
