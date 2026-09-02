"""The service dependency graph, from a committed snapshot (T2.4, ADR-0017).

The snapshot is `docs/evidence/t2.4-dependency-graph/dependencies.json` - the capture and
the runtime input are deliberately the same file, so there is no second copy to drift from
the evidence it is documented by.

**The blast-radius query lives here** (T2.4's *"graph traversal API with 'blast radius of
service X' as the core query"*, Phase 2 audit finding D4). `ServiceGraph.blast_radius` is the
traversal; `agents/triage.py` adds what only an incident knows - severity, entry times,
catalog presence, where to start - and owns none of the graph reasoning.

**Not queried at runtime.** Jaeger here is all-in-one with in-memory storage, so the graph
exists only as long as the container and only covers spans inside the lookback: a restart
empties it and a quiet world thins it. A correlation rule that changes its mind because the
tracing backend restarted is worse than one that is merely stale, and ADR-0008 requires that
what a scored run sees be fixed in advance. ADR-0017 has the full argument.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from injector.world import canonical_service


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


SNAPSHOT = repo_root() / "docs" / "evidence" / "t2.4-dependency-graph" / "dependencies.json"

ARTIFACT_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        ("loadgenerator", "frontend"),
        ("frontendproxy", "jaeger-all-in-one"),
    }
)
"""Edges that describe how the world is run rather than what it depends on.

`loadgenerator -> frontend` is our own synthetic client, and at 5937 calls it is the largest
edge in the capture by a factor of three - a blast-radius calculation that counts it ranks
`frontend` as the most-depended-on service in the world on traffic we generate ourselves.
`frontendproxy -> jaeger-all-in-one` is the tracing UI being routed to through the proxy and
traced by the proxy; `jaeger-all-in-one` is the span store, not a service.

**Written in canonical form**, because the capture spells the second one `frontend-proxy`.
Excluding these is the one judgement call in loading the graph, which is part of why the
snapshot is committed: in a file the decision is visible in a diff, in a runtime query it is
a filter nobody sees.
"""


class Direction(StrEnum):
    """Which way an edge was crossed to reach a service, and therefore what membership claims.

    The distinction is forced by what `edge_kind` measures. ADR-0017's addendum defines `sync`
    as *a callee failure was observed to propagate to the caller* - a **directed** statement.
    It licenses "this callee failed, so its caller is affected". It does not license the
    reverse, and treating the graph as undirected reads a measurement backwards.

    Moved here from `agents/triage.py` at the Phase 2 audit's D4: the claim each direction makes
    is a property of the measured graph, not of the agent that asked.
    """

    SEED = "seed"
    ALSO_AFFECTED = "also_affected"
    """Reached **upstream** (callee -> caller). Failure propagates this way, and it is
    transitive - a caller of an affected caller is affected - so it is followed to the full hop
    radius."""

    CANDIDATE_CAUSE = "candidate_cause"
    """Reached **downstream** (caller -> callee), one step, and only from a seed. This is not
    propagation: a callee of an erroring caller has not been shown to be affected, it is a place
    the error might have come from. `email-wrong-image` is the shape - `checkoutservice` alerted
    and `emailservice`, the broken one, never alerted at all.

    One step, and only from seeds, because the claim does not compose: the callee of a
    *candidate* is a candidate for a fault nobody has evidence of."""


@dataclass(frozen=True, slots=True)
class Reach:
    """One service the traversal reached, and the single edge crossing that reached it."""

    service: str
    direction: Direction
    kind: EdgeKind
    hops: int
    reached_from: str
    edge: tuple[str, str]


@dataclass(frozen=True, slots=True)
class RadiusResult:
    """What the traversal found. **Seeds are not included** - the caller supplied them and
    knows more about them (when each alerted, whether the catalog has heard of it) than the
    graph does."""

    reach: list[Reach]
    unmeasured_edges: list[tuple[str, str]]
    """Every unmeasured edge crossed, in crossing order. **Quoted with any use of the radius**,
    the way every figure in this project carries its `n`: five of the graph's fifteen edges have
    no measurement, so a radius that crossed one is a radius with a guess inside it."""


class EdgeKind(StrEnum):
    """Whether a caller blocks on a callee, and therefore whether failure propagates.

    ADR-0017 recorded that the trace graph "records call causality, not failure propagation":
    an edge says A's work reaches B, never that A waits for B. Measured on 2026-08-25 from the
    recorded bundles - see `docs/evidence/t3.1-edge-kinds/`.
    """

    SYNC = "sync"
    """Caller blocks on callee. The callee failing shows up as caller errors, and the callee
    slowing shows up as caller latency."""

    ASYNC = "async"
    """Producer/consumer. The callee can be dead and the caller keeps completing work."""

    UNMEASURED = "unmeasured"
    """**Not a default and not a synonym for sync.** No bundle broke this callee, so nothing
    in the recorded evidence says which kind it is. A consumer that treats this as `SYNC` is
    guessing; one that treats it as `ASYNC` is guessing in the other direction. The point of
    the value is that it can be counted and reported."""


EDGE_KINDS: dict[tuple[str, str], EdgeKind] = {
    # Measured synchronous: the callee failed or slowed in a recorded bundle, and the caller
    # showed it. Error figures are the caller's error ratio pre-fault -> in-fault; latency
    # figures are the caller's p95 multiple.
    ("frontend", "cartservice"): EdgeKind.SYNC,  # err 0 -> 0.27; p95 43.5x
    ("checkoutservice", "cartservice"): EdgeKind.SYNC,  # err 0 -> 0.54; p95 66.9x
    ("frontend", "adservice"): EdgeKind.SYNC,  # err 0 -> 0.069
    ("frontend", "recommendationservice"): EdgeKind.SYNC,  # err 0.013 -> 0.077
    ("checkoutservice", "shippingservice"): EdgeKind.SYNC,  # err 0 -> 0.227
    ("checkoutservice", "emailservice"): EdgeKind.SYNC,  # err 0 -> 0.061 (cross-check)
    ("frontend", "productcatalogservice"): EdgeKind.SYNC,  # p95 27.7x
    ("checkoutservice", "productcatalogservice"): EdgeKind.SYNC,  # p95 34.7x
    ("recommendationservice", "productcatalogservice"): EdgeKind.SYNC,  # p95 91.9x
    # Measured asynchronous: the callee was dead for the whole fault and the caller's error
    # ratio never moved. Kafka carries this one, and trace context propagates through it,
    # which is why the graph cannot see the difference.
    ("checkoutservice", "frauddetectionservice"): EdgeKind.ASYNC,  # callee 0.196 -> 0.014 req/s,
    # caller err 0 -> 0 (cross-check)
}
"""Edge kinds measured from the recorded bundles, not from `span.kind`.

`span.kind` was ADR-0017's preferred source and **the bundles contain no trace data at all** -
see `docs/evidence/t3.1-edge-kinds/README.md`. What they do contain is ten incidents in which
a named service was broken on purpose, which measures the property blast radius actually needs
rather than a proxy for it.

Any edge absent from this table is `UNMEASURED`. Five of the fifteen are, because no bundle
ever broke their callee: nothing recorded says what `checkoutservice -> paymentservice` does
when payment fails.
"""


@dataclass(frozen=True, slots=True)
class Edge:
    """One directed dependency, with both endpoints already canonicalised."""

    parent: str
    child: str
    call_count: int
    kind: EdgeKind = EdgeKind.UNMEASURED


class ServiceGraph:
    """Nodes and undirected hop distances over the measured edges.

    Direction is kept on the edges and ignored for distance. Correlation asks whether two
    services are related, and a caller and a callee are equally related either way round.
    """

    def __init__(self, edges: list[Edge]) -> None:
        self.edges = edges
        self._adjacent: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            self._adjacent[edge.parent].add(edge.child)
            self._adjacent[edge.child].add(edge.parent)

    @classmethod
    def from_snapshot(cls, path: Path = SNAPSHOT) -> ServiceGraph:
        """Load, canonicalise, and drop the artifact edges."""
        payload = json.loads(path.read_text())
        edges: list[Edge] = []
        for entry in payload.get("data", []):
            parent = canonical_service(entry["parent"])
            child = canonical_service(entry["child"])
            if (parent, child) in ARTIFACT_EDGES:
                continue
            edges.append(
                Edge(
                    parent=parent,
                    child=child,
                    call_count=int(entry["callCount"]),
                    # Absent means unmeasured. Deliberately not `.get(..., SYNC)`: defaulting
                    # to the common case is how an unmeasured edge becomes an asserted one.
                    kind=EDGE_KINDS.get((parent, child), EdgeKind.UNMEASURED),
                )
            )
        return cls(edges)

    @property
    def nodes(self) -> frozenset[str]:
        return frozenset(self._adjacent)

    @property
    def edge_set(self) -> frozenset[tuple[str, str]]:
        """Just the endpoints. **What the drift guard compares.**

        `callCount` is excluded deliberately: it changes on every capture with no change to
        the world, so a guard that compared it would fire constantly and never truthfully.
        That is the `ffs_stub_image_id` mistake ADR-0014 names - a field that produces false
        positives and cannot produce true ones is worse than absent.
        """
        return frozenset((e.parent, e.child) for e in self.edges)

    def neighbours(self, service: str) -> frozenset[str]:
        return frozenset(self._adjacent.get(canonical_service(service), frozenset()))

    def has(self, service: str) -> bool:
        """Whether this service is a node with at least one edge.

        There is no other kind: nodes come from edges, so a service with no edges is not in
        the graph at all. `ServiceCatalog` is where a service can exist and be edgeless.
        """
        return canonical_service(service) in self._adjacent

    def hops(self, source: str, target: str) -> int | None:
        """Undirected shortest path length, or `None` if unreachable or unknown."""
        start, goal = canonical_service(source), canonical_service(target)
        if start not in self._adjacent or goal not in self._adjacent:
            return None
        if start == goal:
            return 0
        seen = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbour in self._adjacent[node]:
                if neighbour in seen:
                    continue
                seen[neighbour] = seen[node] + 1
                if neighbour == goal:
                    return seen[neighbour]
                queue.append(neighbour)
        return None

    def within(self, source: str, target: str, radius: int) -> bool:
        distance = self.hops(source, target)
        return distance is not None and distance <= radius

    def kind_of(self, parent: str, child: str) -> EdgeKind:
        """The measured kind of one directed edge, or `UNMEASURED` if there is no such edge."""
        source, target = canonical_service(parent), canonical_service(child)
        for edge in self.edges:
            if edge.parent == source and edge.child == target:
                return edge.kind
        return EdgeKind.UNMEASURED

    def edges_by_kind(self) -> dict[EdgeKind, list[Edge]]:
        """Grouped, so a consumer can report how much of the graph it is guessing about."""
        grouped: dict[EdgeKind, list[Edge]] = {kind: [] for kind in EdgeKind}
        for edge in self.edges:
            grouped[edge.kind].append(edge)
        return grouped

    # --- the blast-radius query (T2.4's core query; Phase 2 audit D4) ----------------

    def blast_radius(self, seeds: Sequence[str], radius: int) -> RadiusResult:
        """Every service reachable from `seeds` by an edge whose measurement licenses the claim.

        **Two traversals, because the graph carries two different claims** and `sync` is a
        *directed* measurement (ADR-0017's addendum: a callee failure was observed to propagate
        to the caller).

        **Upstream, transitive, to `radius` hops** - callee to caller, the direction the
        measurement licenses. If `adservice` dies its caller `frontend` is affected, and a caller
        of an affected caller is affected too.

        **Downstream, one step, from seeds only** - caller to callee, naming where an error could
        have come from. `email-wrong-image` is why this exists: checkout alerted, and
        `emailservice`, the broken one, never alerted. It does not compose, so it is not followed.

        Treating the graph as undirected instead reads the measurement backwards and inflates the
        result - from an `adservice` failure it reaches `cartservice`, which shares a caller with
        `adservice` and has nothing to do with it.

        `async` is not crossed in either direction. `frauddetectionservice` was dead for 852
        seconds while checkout kept completing orders, so neither tells you anything about the
        other.

        **Order is part of the contract.** Upstream first in breadth-first order, then the
        downstream step, each service claimed by the first crossing that reaches it - so a
        service both upstream and downstream of the incident is `also_affected`, the stronger
        claim. Callers rely on this: `TriageResult.blast_radius` is scored against recorded
        bundles, and a set that reordered would not be the same evidence.
        """
        # **Seed order is the caller's and is preserved**, not collapsed into a set: a service
        # reachable from two seeds records the first one that reached it, so iterating a set here
        # would make `reached_from` follow hash order. Caught by the equivalence probe across all
        # 91 seed sets - twelve of them differed on exactly this field.
        ordered: list[str] = []
        found: set[str] = set()
        for seed in seeds:
            service = canonical_service(seed)
            if service not in found:
                found.add(service)
                ordered.append(service)
        reach: list[Reach] = []
        unmeasured: list[tuple[str, str]] = []

        frontier: deque[tuple[str, int]] = deque((service, 0) for service in ordered)
        while frontier:
            service, depth = frontier.popleft()
            if depth >= radius:
                continue
            for caller, kind, edge in self._callers_of(service):
                if kind is EdgeKind.ASYNC:
                    continue
                _note_unmeasured(kind, edge, unmeasured)
                if caller in found:
                    continue
                found.add(caller)
                reach.append(
                    Reach(
                        service=caller,
                        direction=Direction.ALSO_AFFECTED,
                        kind=kind,
                        hops=depth + 1,
                        reached_from=service,
                        edge=edge,
                    )
                )
                frontier.append((caller, depth + 1))

        for service in ordered:
            for callee, kind, edge in self._callees_of(service):
                if kind is EdgeKind.ASYNC:
                    continue
                _note_unmeasured(kind, edge, unmeasured)
                if callee in found:
                    continue
                found.add(callee)
                reach.append(
                    Reach(
                        service=callee,
                        direction=Direction.CANDIDATE_CAUSE,
                        kind=kind,
                        hops=1,
                        reached_from=service,
                        edge=edge,
                    )
                )

        return RadiusResult(reach=reach, unmeasured_edges=unmeasured)

    def _callers_of(self, service: str) -> list[tuple[str, EdgeKind, tuple[str, str]]]:
        return [
            (edge.parent, edge.kind, (edge.parent, edge.child))
            for edge in self.edges
            if edge.child == service
        ]

    def _callees_of(self, service: str) -> list[tuple[str, EdgeKind, tuple[str, str]]]:
        return [
            (edge.child, edge.kind, (edge.parent, edge.child))
            for edge in self.edges
            if edge.parent == service
        ]


def _note_unmeasured(kind: EdgeKind, edge: tuple[str, str], seen: list[tuple[str, str]]) -> None:
    if kind is EdgeKind.UNMEASURED and edge not in seen:
        seen.append(edge)
