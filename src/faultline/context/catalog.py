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


class GraphPresence(StrEnum):
    """Why a service is or is not usable for graph reasoning."""

    PRESENT = "present"
    UNINSTRUMENTED = "uninstrumented"
    """Emits no spans, so it cannot appear in a graph built from spans."""

    ARTIFACT_ONLY = "artifact_only"
    """Its only edges were excluded as artifacts of how the world is run."""

    INFRASTRUCTURE = "infrastructure"
    """A datastore or broker the services depend on. Emits no spans of its own - its traffic
    appears as *client* spans inside the instrumented service that calls it - so it can be a
    culprit and never a node in a span-derived graph (ADR-0017 Addendum 3, Q27)."""

    UNLINKED = "unlinked"
    """Emits spans, but no other service's span is its parent or child, so the graph has no edge
    to it. v2's `accounting` is the first: its work arrives over Kafka, and its consumer spans
    open traces of their own (Q122). Not `ARTIFACT_ONLY`: nothing about how the world is run was
    excluded; the hop exists and the trace does not join it."""

    UNEXERCISED = "unexercised"
    """Nothing reached it while the graph was captured: no span and no log line in the hour. So
    the graph has no edge for it, and **whether it emits spans is not measured**. v2's `flagd-ui`
    (Q122)."""


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
    "redis-cart": (
        GraphPresence.INFRASTRUCTURE,
        "The cart's datastore. `cartservice` reaches it through a Redis client, and the only "
        "trace of that is the client span (HGET, HMSET) inside cartservice; Redis itself emits "
        "no spans and has no service.name. It is the injection target of two dev scenarios "
        "(`cart-redis-misconfig`, `redis-cart-dependency-latency`) and was unnameable as a "
        "culprit until T6.1 - ADR-0017 marked the decision and its first consumer, the "
        "culprit-service axis, settled it (Addendum 3).",
    ),
    "kafka": (
        GraphPresence.INFRASTRUCTURE,
        "The broker two of checkoutservice's edges pass through, to accountingservice and "
        "frauddetectionservice. Its producer and consumer spans belong to the services on "
        "either side; the broker has none. In the catalog for the same reason as redis-cart, "
        "and because its memory is the world's most-watched number (T7.27, T7.30).",
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

_PROBE = "docs/evidence/t7.2-topology/q122-presence.txt"

KNOWN_ABSENT_V2: dict[str, tuple[GraphPresence, str]] = {
    "load-generator": (
        GraphPresence.ARTIFACT_ONLY,
        "Its only cross-service edges are load-generator -> frontend-proxy and load-generator -> "
        "flagd, excluded as the synthetic client (ARTIFACT_EDGES_V2), as v1's loadgenerator -> "
        "frontend was. Excluding them removes the node.",
    ),
    "accounting": (
        GraphPresence.UNLINKED,
        "It emits spans (994 calls inside itself in the snapshot's hour) and no other service's "
        "span is its parent or child. checkout publishes to Kafka's `orders` topic; accounting's "
        "consumer spans sit under its own spans in traces of their own, each with one link to "
        f"another trace ({_PROBE}, part C2). So checkout -> accounting is a real hop the graph "
        "cannot show, and a blast radius never reaches accounting.",
    ),
    "image-provider": (
        GraphPresence.UNLINKED,
        "It emits spans (20 traces in the probe's hour), and in the 138 whole traces fetched none "
        f"of its spans has a parent or a child in another service ({_PROBE}, parts A and B). "
        "Jaeger's graph has no edge to it either.",
    ),
    "llm": (
        GraphPresence.UNINSTRUMENTED,
        "It served `POST /v1/chat/completions` in the probe's hour (1,012 log lines, the last a "
        "200) and Tempo holds no span of its own. Its caller sees it: product-reviews' client "
        f"spans name `server.address` llm ({_PROBE}, parts A and C1). The demo's model service, "
        "uninstrumented as v1's flag-service stub was.",
    ),
    "flagd-ui": (
        GraphPresence.UNEXERCISED,
        "No span and no log line in the probe's hour, with the container running "
        f"({_PROBE}, part A). Nothing reached it, so whether it emits spans is not measured.",
    ),
    "valkey-cart": (
        GraphPresence.INFRASTRUCTURE,
        "The cart's datastore, as v1's redis-cart. No span of its own; cart's client spans carry "
        f"`db.system` redis and `server.address` valkey-cart ({_PROBE}, part C1).",
    ),
    "postgresql": (
        GraphPresence.INFRASTRUCTURE,
        "The database behind accounting, product-catalog and product-reviews, each of which holds "
        f"client spans with `db.system` postgresql ({_PROBE}, part C1). No span of its own.",
    ),
    "kafka": (
        GraphPresence.INFRASTRUCTURE,
        "The broker between checkout's producer spans on `orders` and the consumer spans of "
        f"accounting and fraud-detection ({_PROBE}, part C2). No span of its own. The consumers' "
        "traces do not join checkout's, which is why accounting is UNLINKED.",
    ),
}
"""v2's services that exist and are not in its graph, each with the reason, measured by Q122's
presence probe rather than assumed.

**Also astronomy-shop under SREGym's table** (Q125, the owner's decision): its graph is read in v2's
world, so the catalog reuses this. Checked against what T7.2 topology item 3 recorded there, and
consistent: SREGym's Jaeger listed `accounting` and `image-provider` (spans, no edge) and no `llm`,
`flagd-ui`, `valkey-cart`, `postgresql` or `kafka`, and `load-generator`'s only edge is an artifact
one. **Not checked there**: whether `llm` served requests, whether anything reached `flagd-ui`, and
the datastores' client spans in their callers.

**`fraud-detection` is not here**: its flag read keeps it a node, though, like `accounting`,
nothing reaches it from checkout. The nine telemetry services are left out, as on v1."""

KNOWN_ABSENT_BY_WORLD: dict[str, dict[str, tuple[GraphPresence, str]]] = {
    "v1": KNOWN_ABSENT,
    "v2": KNOWN_ABSENT_V2,
}


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
        for name, (presence, reason) in KNOWN_ABSENT_BY_WORLD[graph.world].items():
            service = graph.canonical(name)
            entries.setdefault(service, ServiceEntry(service, presence, reason))
        self._entries = entries

    @classmethod
    def from_snapshot(
        cls, world: str | None = None, application: str | None = None
    ) -> ServiceCatalog:
        """The catalog over the graph `ServiceGraph.from_snapshot` loads for the same arguments.

        The absent-service table follows the graph's world, so an application reuses its world's.
        """
        return cls(ServiceGraph.from_snapshot(world=world, application=application))

    def get(self, service: str | None) -> ServiceEntry | None:
        """The entry for a service, or `None` if the catalog has never heard of it."""
        if service is None:
            return None
        return self._entries.get(self.graph.canonical(service))

    @property
    def services(self) -> frozenset[str]:
        return frozenset(self._entries)

    def usable(self, service: str | None) -> bool:
        entry = self.get(service)
        return entry is not None and entry.usable_for_graph_reasoning
