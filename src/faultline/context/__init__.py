"""Service catalog, dependency-graph scoping, retrieval (T2.4, T6.4).

The catalog and the graph are built (ADR-0017), against the measured snapshot in
`docs/evidence/t2.4-dependency-graph/`. T2.4b's past-incident store and its seeder are
built here too (ADR-0018); the runbook corpus T6.4 commits to is not.
"""

from faultline.context.catalog import GraphPresence, ServiceCatalog, ServiceEntry
from faultline.context.corpus import Chunk, Narrative, chunk_narrative, parse_narrative
from faultline.context.embedding import Embedder, HashingEmbedder, SentenceTransformerEmbedder
from faultline.context.graph import Edge, ServiceGraph
from faultline.context.policy import Decision, DecisionLog, DependencyPolicy, JoinRule
from faultline.context.seed import QuarantineError, SeedResult, seed
from faultline.context.settings import ContextSettings
from faultline.context.store import (
    Hit,
    InMemoryPastIncidentStore,
    PastIncidentStore,
    PgVectorPastIncidentStore,
)

__all__ = [
    "Chunk",
    "ContextSettings",
    "Decision",
    "DecisionLog",
    "DependencyPolicy",
    "Edge",
    "Embedder",
    "GraphPresence",
    "HashingEmbedder",
    "Hit",
    "InMemoryPastIncidentStore",
    "JoinRule",
    "Narrative",
    "PastIncidentStore",
    "PgVectorPastIncidentStore",
    "QuarantineError",
    "SeedResult",
    "SentenceTransformerEmbedder",
    "ServiceCatalog",
    "ServiceEntry",
    "ServiceGraph",
    "chunk_narrative",
    "parse_narrative",
    "seed",
]
