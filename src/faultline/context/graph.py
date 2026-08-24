"""The service dependency graph, from a committed snapshot (T2.4, ADR-0017).

The snapshot is `docs/evidence/t2.4-dependency-graph/dependencies.json` - the capture and
the runtime input are deliberately the same file, so there is no second copy to drift from
the evidence it is documented by.

**Not queried at runtime.** Jaeger here is all-in-one with in-memory storage, so the graph
exists only as long as the container and only covers spans inside the lookback: a restart
empties it and a quiet world thins it. A correlation rule that changes its mind because the
tracing backend restarted is worse than one that is merely stale, and ADR-0008 requires that
what a scored run sees be fixed in advance. ADR-0017 has the full argument.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class Edge:
    """One directed dependency, with both endpoints already canonicalised."""

    parent: str
    child: str
    call_count: int


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
            edges.append(Edge(parent=parent, child=child, call_count=int(entry["callCount"])))
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
