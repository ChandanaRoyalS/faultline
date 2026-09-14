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


# --- the draw rule, which lived only in a header until Q52 -----------------------------------


def _row(role: str, origin: str, trajectory: str, seq: int, query: str) -> dict:
    return {
        "role": role,
        "exclude_origin": origin,
        "source_trajectory": trajectory,
        "seq": seq,
        "query": query,
    }


def test_the_draw_takes_a_prefix_per_role_and_scenario() -> None:
    """`golden.yaml`'s header states the rule; **nothing implemented it until Q52.**

    *"Sort the distinct queries by (role, origin, trajectory, seq), then take the first 3 planner
    and 2 synthesizer per scenario. No RNG and no selection."* A rule that exists only as prose
    cannot be applied a second time, which is exactly what a confirmation set needs.
    """
    rows = [_row(retrieval.PLANNER, "scenario:a", "t1", i, f"a-planner-{i}") for i in range(5)] + [
        _row(retrieval.SYNTHESIZER, "scenario:a", "t1", i, f"a-synth-{i}") for i in range(4)
    ]

    drawn = [r["query"] for r in retrieval.draw(rows)]

    assert drawn == ["a-planner-0", "a-planner-1", "a-planner-2", "a-synth-0", "a-synth-1"]


def test_a_skipped_draw_is_disjoint_from_the_first_one() -> None:
    """**The property the confirmation set rests on.**

    The original draw took a *prefix*, not a sample, so everything after the cut was never drawn
    and never read. Skipping by exactly the first draw's size yields a set chosen by the identical
    procedure with no overlap - no RNG, no judgement, and nothing that could have been influenced
    by the numbers the first set produced.
    """
    rows = [_row(retrieval.PLANNER, "scenario:a", "t1", i, f"a-planner-{i}") for i in range(7)] + [
        _row(retrieval.SYNTHESIZER, "scenario:a", "t1", i, f"a-synth-{i}") for i in range(5)
    ]

    first = {r["query"] for r in retrieval.draw(rows)}
    second = {r["query"] for r in retrieval.draw(rows, skip_planner=3, skip_synthesizer=2)}

    assert not (first & second)
    assert second == {"a-planner-3", "a-planner-4", "a-planner-5", "a-synth-2", "a-synth-3"}


def test_the_draw_counts_seats_per_scenario_not_globally() -> None:
    """Two scenarios each get their own three-and-two. Counting globally would take everything
    from whichever scenario sorts first, which is the failure a stratified draw exists to avoid."""
    rows = [
        _row(retrieval.PLANNER, origin, "t1", i, f"{origin}-{i}")
        for origin in ("scenario:a", "scenario:b")
        for i in range(4)
    ]

    drawn = [r["query"] for r in retrieval.draw(rows)]

    assert sum(1 for q in drawn if q.startswith("scenario:a")) == 3
    assert sum(1 for q in drawn if q.startswith("scenario:b")) == 3


def test_one_query_text_sent_in_several_runs_is_drawn_once() -> None:
    """The golden set labels query *texts*, not sendings. A duplicate text taking two seats would
    quietly shrink the draw and over-weight whatever was retried most."""
    rows = [
        _row(retrieval.PLANNER, "scenario:a", "t1", 0, "same"),
        _row(retrieval.PLANNER, "scenario:a", "t2", 0, "same"),
        _row(retrieval.PLANNER, "scenario:a", "t3", 0, "other"),
    ]

    assert [r["query"] for r in retrieval.draw(rows)] == ["same", "other"]


def test_the_arms_diagnostic_reads_the_arm_the_store_actually_uses() -> None:
    """**A probe that drifts from what it probes answers confidently and wrongly.**

    `ARMS_SQL` was a constant written with `plainto_tsquery` - the defect it existed to expose.
    Q39 replaced the arm with a disjunction and the constant kept the old form, so
    `faultline-retrieval arms` would have reported a historical defect as though it were current.

    Reading `store.TEXT_QUERY` is what stops that recurring, and this asserts the reading rather
    than the current text, so the next change to the arm carries the diagnostic with it.
    """
    from faultline.context.store import TEXT_QUERY

    sql = retrieval.arms_sql()
    assert TEXT_QUERY in sql
    assert "plainto_tsquery('english', %(q)s)::text" in sql, "still built from plainto's lexemes"
    assert " & " in sql and " | " in sql, "and it is the disjunctive form, not the conjunctive one"


def test_the_draw_refuses_holdout_derived_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    """**The defect the provenance check found, and the reason it was worth running.**

    `golden.yaml`'s header says holdout-harvested queries are excluded and `load_golden` raises on
    them, so a committed file could not carry one. The first version of `draw` did not filter them
    at all: run against the real harvest it emitted six synthesizer queries from
    `email-wrong-image`, `productcatalog-dependency-latency` and `recommendation-memory-squeeze` -
    each carrying a holdout run's findings in its text, presented as a mechanical selection.

    A read-side guard catches the file. It does not catch the person who ran the draw, read the
    output, and now knows what is in those runs.
    """
    monkeypatch.setattr(
        "evalharness.freeze.holdout_origins", lambda: ["scenario:held"], raising=True
    )
    rows = [
        _row(retrieval.PLANNER, "scenario:held", "t1", 0, "from a holdout run"),
        _row(retrieval.PLANNER, "scenario:dev", "t2", 0, "from a dev run"),
    ]

    assert [r["query"] for r in retrieval.draw(rows)] == ["from a dev run"]


def test_a_query_text_sent_under_two_scenarios_takes_one_seat() -> None:
    """**The ambiguity in the stated rule, pinned.**

    `golden.yaml`'s header says *"sort the distinct queries ... then take the first 3 planner and
    2 synthesizer per scenario"* and does not say whether "distinct" is global or per scenario.
    It matters: a planner's symptom list for two shipping faults can be the same text.

    Global is the reading. A shared text takes **one** seat, credited to the first origin in sort
    order, and the second scenario reaches one deeper to fill its three. Measured against the live
    harvest this reproduces 42 of the 43 committed queries, and the single disagreement is exactly
    this case - which is why it is pinned here rather than left to whoever writes the next draw.
    """
    rows = [
        _row(retrieval.PLANNER, "scenario:a", "t1", 0, "shared"),
        _row(retrieval.PLANNER, "scenario:a", "t1", 1, "a-only-1"),
        _row(retrieval.PLANNER, "scenario:a", "t1", 2, "a-only-2"),
        _row(retrieval.PLANNER, "scenario:b", "t2", 0, "shared"),
        _row(retrieval.PLANNER, "scenario:b", "t2", 1, "b-only-1"),
        _row(retrieval.PLANNER, "scenario:b", "t2", 2, "b-only-2"),
        _row(retrieval.PLANNER, "scenario:b", "t2", 3, "b-only-3"),
    ]

    drawn = [r["query"] for r in retrieval.draw(rows)]

    assert drawn.count("shared") == 1
    assert drawn == ["shared", "a-only-1", "a-only-2", "b-only-1", "b-only-2", "b-only-3"]


# --- the cross-validation (Q52) ---------------------------------------------------------------


def _results(hits: dict[str, float]) -> list[QueryResult]:
    """One QueryResult per query id, hitting at rank 1 or not at all."""
    return [
        QueryResult(
            qid, ("runbook:right",) if hit else ("runbook:wrong",), frozenset({"runbook:right"})
        )
        for qid, hit in hits.items()
    ]


def test_a_flag_that_is_genuinely_better_keeps_its_margin_out_of_sample() -> None:
    """A real effect survives being selected. Flag 2 answers every query, flag 0 none, so whichever
    half chooses it the other half agrees."""
    ids = [f"q{i}" for i in range(20)]
    per_flag = {
        0: _results(dict.fromkeys(ids, 0.0)),
        2: _results(dict.fromkeys(ids, 1.0)),
    }

    cv = retrieval.cross_validate(per_flag, k=3, splits=50)

    assert cv.in_sample == pytest.approx(1.0)
    assert cv.out_of_sample == pytest.approx(1.0)
    assert cv.shrinkage == pytest.approx(0.0)
    assert cv.selection[2] == 50


def test_a_flag_that_only_won_by_noise_loses_its_margin_out_of_sample() -> None:
    """**The property this exists to measure.**

    Every flag here answers exactly half the queries, but *different* halves - so on any given
    selection half one of them looks best by chance, and on the other half that advantage is gone.
    The in-sample margin is positive and the out-of-sample margin is near zero: the difference is
    the selection bias, which is precisely what Q49's six-flag comparison could not rule out.
    """
    ids = [f"q{i}" for i in range(20)]
    per_flag = {
        0: _results({q: float(i % 2 == 0) for i, q in enumerate(ids)}),
        1: _results({q: float(i % 3 == 0) for i, q in enumerate(ids)}),
        2: _results({q: float(i % 4 == 0) for i, q in enumerate(ids)}),
    }

    cv = retrieval.cross_validate(per_flag, k=3, splits=200)

    assert cv.shrinkage > 0, "a margin won by noise must not survive the split"
    assert cv.out_of_sample < cv.in_sample


def test_the_cross_validation_is_deterministic() -> None:
    """A fixed seed, so the number in a write-up can be reproduced by whoever doubts it."""
    ids = [f"q{i}" for i in range(16)]
    per_flag = {
        0: _results({q: float(i % 2 == 0) for i, q in enumerate(ids)}),
        2: _results({q: float(i % 3 == 0) for i, q in enumerate(ids)}),
    }

    first = retrieval.cross_validate(per_flag, k=3, splits=100)
    second = retrieval.cross_validate(per_flag, k=3, splits=100)

    assert first.out_of_sample == second.out_of_sample
    assert first.selection == second.selection


def test_unanswerable_queries_are_excluded_before_splitting() -> None:
    """`measure` keeps unanswerable queries and does not score them. Splitting over them would put
    rows in both halves that contribute 0 to every flag, shrinking every margin toward zero by
    dilution rather than by selection."""
    answerable = _results({"q1": 1.0, "q2": 0.0})
    unanswerable = [QueryResult("q3", ("runbook:a",), frozenset())]
    per_flag = {0: answerable + unanswerable, 2: answerable + unanswerable}

    cv = retrieval.cross_validate(per_flag, k=3, splits=10)

    assert cv.in_sample == pytest.approx(0.0)
    assert cv.splits == 10
