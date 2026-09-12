"""The retrieval measurement's arithmetic, and the three decisions that decide what it means.

Fakes only. `evalharness.retrieval` runs no model and touches no database except in `harvest`,
which is exercised against real Postgres in `test_integration_store.py`'s sibling job rather than
here.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from evalharness import retrieval
from evalharness.retrieval import (
    GoldenQuery,
    Label,
    QueryResult,
    documents_of,
    measure,
    run_query,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class _Chunk:
    document_id: str


@dataclass(frozen=True)
class _Hit:
    chunk: _Chunk


class _Store:
    """Returns a fixed ranked list of document ids, one chunk each unless repeated."""

    def __init__(self, ranking: dict[str, list[str]]) -> None:
        self.ranking = ranking
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, k: int = 5, exclude_origin: str | None = None):
        self.calls.append((query, k))
        return [_Hit(_Chunk(d)) for d in self.ranking.get(query, [])[:k]]


def _q(qid: str, text: str, role: str, *relevant: str) -> GoldenQuery:
    return GoldenQuery(
        id=qid,
        query=text,
        role=role,
        source_trajectory="t-1",
        seq=1,
        relevant=tuple(Label(document_id=d, reason="because") for d in relevant),
    )


def test_chunks_collapse_to_documents_in_rank_order() -> None:
    """**Decision 1.** The store ranks chunks; the golden set labels documents.

    Three chunks of one document followed by one of another is a top-4 covering two documents,
    and the order is the chunk order. A `set` here would silently destroy the ranking that MRR
    is computed over.
    """
    hits = [_Hit(_Chunk(d)) for d in ["runbook:a", "runbook:a", "runbook:b", "runbook:a"]]
    assert documents_of(hits) == ("runbook:a", "runbook:b")


def test_k_is_chunks_not_documents() -> None:
    """The cut is applied to what the model reads.

    Five chunks that all come from one document yield one document, and the query is scored over
    that one. Asking the store for more until five documents appeared would measure a pipeline
    this one is not.
    """
    store = _Store({"q": ["runbook:a"] * 5 + ["runbook:right"]})
    result = run_query(store, _q("g1", "q", retrieval.PLANNER, "runbook:right"), k=5)
    assert store.calls == [("q", 5)]
    assert result.documents == ("runbook:a",)
    assert result.recall_at(5) == 0.0


def test_recall_is_a_hit_rate_and_says_so() -> None:
    result = QueryResult("g", ("a", "b", "c"), frozenset({"c", "z"}))
    assert result.recall_at(5) == 1.0
    assert result.recall_at(2) == 0.0


def test_reciprocal_rank_uses_the_first_relevant_position() -> None:
    assert QueryResult("g", ("a", "b", "c"), frozenset({"c"})).reciprocal_rank == pytest.approx(
        1 / 3
    )
    assert QueryResult("g", ("a", "b"), frozenset({"z"})).reciprocal_rank == 0.0
    assert QueryResult("g", (), frozenset({"z"})).reciprocal_rank == 0.0


def test_an_unanswerable_query_is_kept_and_not_scored() -> None:
    """**Decision 2**, and the one a golden set is most tempted to drop.

    Recall over an empty relevant set is 0/0. Scoring it as 0 would punish the pipeline for a
    query that has no right answer; scoring it as 1 would reward it for anything. It is excluded
    from both means and reported with what it returned, so a reader can see whether the corpus
    answered a question it should not have.
    """
    store = _Store({"nothing here": ["runbook:a", "runbook:b"], "real": ["runbook:right"]})
    golden = [
        _q("g1", "real", retrieval.PLANNER, "runbook:right"),
        _q("g2", "nothing here", retrieval.PLANNER),
    ]

    m = measure(store, golden, k=5, predates_task=frozenset({"runbook:right"}))

    assert m.overall.queries == 1
    assert m.overall.recall_at_k == 1.0
    assert len(m.unanswerable) == 1
    assert m.unanswerable[0].query_id == "g2"
    assert "runbook:a" in m.render()


def test_the_split_is_by_where_the_answer_lives() -> None:
    """**Decision 3.** §2.3's three numbers, and the gap it exists to expose.

    A query whose answer is an old document scores in the first row; one whose answer is a new
    document scores in the second. If the second is markedly higher, that is a finding about the
    corpus rather than about the pipeline, and this split is the only instrument pointed at it.
    """
    store = _Store({"old": ["runbook:old"], "new": ["runbook:miss", "runbook:new"]})
    golden = [
        _q("g1", "old", retrieval.PLANNER, "runbook:old"),
        _q("g2", "new", retrieval.SYNTHESIZER, "runbook:new"),
    ]

    m = measure(store, golden, k=5, predates_task=frozenset({"runbook:old"}))

    old, new = m.by_corpus_age
    assert old.queries == 1 and old.recall_at_k == 1.0 and old.mrr == 1.0
    assert new.queries == 1 and new.recall_at_k == 1.0 and new.mrr == pytest.approx(0.5)


def test_the_roles_are_reported_apart() -> None:
    """`investigation.py` is explicit that the planner's query and the synthesizer's are
    different shapes and that collapsing them would degrade both. A measurement that averaged
    them would be averaging two things."""
    store = _Store({"p": ["runbook:x"], "s": ["runbook:y"]})
    golden = [
        _q("g1", "p", retrieval.PLANNER, "runbook:x"),
        _q("g2", "s", retrieval.SYNTHESIZER, "runbook:zzz"),
    ]

    planner, synth = measure(store, golden, k=5, predates_task=frozenset()).by_role

    assert planner.recall_at_k == 1.0
    assert synth.recall_at_k == 0.0


def test_an_empty_partition_reports_zero_queries_rather_than_dividing_by_zero() -> None:
    store = _Store({"p": ["runbook:x"]})
    m = measure(store, [_q("g1", "p", retrieval.PLANNER, "runbook:x")], 5, frozenset())
    _, synth = m.by_role
    assert synth.queries == 0


def test_the_harvest_query_joins_the_role_in() -> None:
    """A retrieval row knows its query and its results and not who asked. Without the join to
    `trajectory_steps` the golden set could not be split by role at all."""
    sql = retrieval.HARVEST_SQL
    assert "trajectory_retrievals" in sql
    assert "JOIN trajectory_steps" in sql
    assert "s.role" in sql


def test_this_module_cannot_reach_a_model() -> None:
    """**$0.00 is a registered prediction, not an aspiration.** A model call in this module is a
    defect, so the import graph is checked rather than trusted - the same guard the replay and
    reject-loop drivers carry."""
    source = (REPO_ROOT / "src" / "evalharness" / "retrieval.py").read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    banned = {"anthropic", "faultline.agents.model", "faultline.agents.roles"}
    assert not (imported & banned), f"{sorted(imported & banned)} reachable from retrieval.py"
    assert not any(name.startswith("faultline.agents") for name in imported)
