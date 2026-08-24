"""Service catalog, dependency-graph scoping, retrieval (T2.4, T6.4).

The catalog and the graph are built (ADR-0017), against the measured snapshot in
`docs/evidence/t2.4-dependency-graph/`. **Retrieval is not**, and T2.4b's corpus seeding is
a separate contract.
"""

from faultline.context.catalog import GraphPresence, ServiceCatalog, ServiceEntry
from faultline.context.graph import Edge, ServiceGraph
from faultline.context.policy import Decision, DecisionLog, DependencyPolicy, JoinRule
from faultline.context.settings import ContextSettings

__all__ = [
    "ContextSettings",
    "Decision",
    "DecisionLog",
    "DependencyPolicy",
    "Edge",
    "GraphPresence",
    "JoinRule",
    "ServiceCatalog",
    "ServiceEntry",
    "ServiceGraph",
]
