"""The golden set's own guards (T6.4).

A golden set is a committed artefact that decides a published number, and nothing that guards
the retrieval corpus looks at it - so the properties `PREREGISTRATION-T6.4.md` §2.2 registers
are held here rather than trusted to whoever next runs the harvest.
"""

from __future__ import annotations

import collections

import pytest

from evalharness.freeze import holdout_origins
from evalharness.retrieval import PREDATES_T6_4, GoldenQuery, load_golden
from faultline.context.runbooks import load_runbooks


def golden() -> tuple[GoldenQuery, ...]:
    return load_golden()


def test_the_registered_size_and_both_roles() -> None:
    """§2.2: *at least 30 queries, drawn from both roles*.

    Both, because `investigation.py` is explicit that the planner's query is symptom-shaped and
    the synthesizer's is evidence-shaped, and that collapsing them would degrade both. A set
    drawn from one role would be measuring half a pipeline.
    """
    queries = golden()
    assert len(queries) >= 30
    roles = collections.Counter(q.role for q in queries)
    assert roles["planner"] >= 10
    assert roles["synthesizer"] >= 10


def test_no_query_was_harvested_from_a_holdout_run() -> None:
    """**The channel nobody had considered.**

    A synthesizer query carries four specialist findings in its text. Committing one harvested
    from a holdout run would put that run's findings into a file in this repository, permanently,
    where anyone authoring against the golden set would read them - and a golden set is not a
    retrieval corpus, so the seed-time quarantine never sees it.

    `load_golden` raises rather than warning, because a warning in a harvest nobody watches is
    the same as nothing.
    """
    held = set(holdout_origins())
    assert held, "no holdout origins found; this test would pass vacuously"
    assert not [q for q in golden() if q.harvested_from in held]


def test_every_label_names_a_document_that_exists() -> None:
    """A label pointing at a document the corpus does not have is a query that can never be
    answered, scored as though it could."""
    known = {f"runbook:{r.id}" for r in load_runbooks()}
    for query in golden():
        for label in query.relevant:
            assert label.document_id in known, f"{query.id} labels unknown {label.document_id}"


def test_every_label_states_a_reason() -> None:
    """**A label with no stated reason is a label nobody can dispute.** The labels and most of
    the documents have one author, which §5 names as the residual weakness; a reason per label is
    what makes each one arguable rather than merely asserted."""
    for query in golden():
        for label in query.relevant:
            assert len(label.reason) > 20, f"{query.id} -> {label.document_id} has no real reason"


def test_ids_are_unique_and_queries_are_distinct() -> None:
    queries = golden()
    assert len({q.id for q in queries}) == len(queries)
    assert len({q.query for q in queries}) == len(queries)


def test_both_halves_of_the_corpus_age_split_are_non_empty() -> None:
    """§2.3's comparison needs both rows to have queries in them.

    This is the test that caught the split being degenerate per query: **no query has an answer
    lying entirely among the fifteen older runbooks.** The partition is per label for that
    reason, and this guard holds the weaker property that actually has to be true - each half is
    reachable - rather than the one that turned out to be false.
    """
    queries = golden()
    with_old = [q for q in queries if q.relevant_ids & PREDATES_T6_4]
    with_new = [q for q in queries if q.relevant_ids - PREDATES_T6_4]
    assert len(with_old) >= 5, "nothing would exercise the older half of the corpus"
    assert len(with_new) >= 5


def test_predates_task_names_only_documents_the_corpus_still_has() -> None:
    known = {f"runbook:{r.id}" for r in load_runbooks()}
    assert known >= PREDATES_T6_4


def test_the_label_concentration_is_visible_rather_than_hidden() -> None:
    """**Not a threshold - a tripwire.**

    If one document is the labelled answer to most of the set, the measurement is largely a test
    of whether that document ranks well, and recall would move with it rather than with the
    pipeline. The most-labelled document here is the one that explains what a change record
    holds, because that is what the harvested queries turn out to be about. This fails if any
    single document ever accounts for more than half the labelled queries, which would mean the
    set had stopped measuring retrieval and started measuring one document.
    """
    queries = golden()
    counts = collections.Counter(label.document_id for q in queries for label in q.relevant)
    top, n = counts.most_common(1)[0]
    assert n <= len(queries) / 2, f"{top} is the answer to {n} of {len(queries)} queries"


@pytest.mark.parametrize("role", ["planner", "synthesizer"])
def test_every_query_carries_its_provenance(role: str) -> None:
    """`source_trajectory` and `seq` are what make *this is the text the pipeline actually sent*
    checkable against `trajectory_retrievals` rather than a claim in a header."""
    for query in (q for q in golden() if q.role == role):
        assert query.source_trajectory
        assert query.seq >= 0
        assert query.harvested_from
