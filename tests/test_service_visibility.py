"""A service miss on a target the pipeline cannot name is still a miss, and now says so (T5.7).

Dev sweep 11 scored the culprit service 3 of 5 and both misses landed on the two targets the
pre-registration had named in advance: `featureflagservice`, which is in the catalog and not in
the graph, and `redis-cart`, which is not in the catalog at all. The registered consequence was
*"a finding about the service axis's name space"* rather than a plain miss - and a finding that
lives in one sweep document is a finding the next reader does not have.

**What these tests hold is the boundary.** The note is reporting; the score is untouched. A test
that let an unnameable target score as correct would be the scorer edited to fit a result, which
is the thing the pre-registration exists to prevent.
"""

from __future__ import annotations

from evalharness import visibility
from evalharness.scoring import LabelScore, ScoredRun


def test_an_ordinary_target_is_nameable_and_says_nothing() -> None:
    """`cartservice` is a graph node. The common case must stay silent, or the caveat becomes
    wallpaper and stops being read on the runs where it matters."""
    seen = visibility.target_visibility("cartservice")

    assert seen["presence"] == visibility.IN_GRAPH
    assert seen["nameable"] is True
    assert visibility.note(seen) is None


def test_an_uninstrumented_service_is_in_the_catalog_and_not_in_the_graph() -> None:
    """ADR-0006's flag-service stub emits no spans, so it is in no span-derived edge and no
    blast radius. The verdict on `product-catalog-flag-failure` said as much itself."""
    seen = visibility.target_visibility("featureflagservice")

    assert seen["presence"] == visibility.NOT_IN_GRAPH
    assert seen["nameable"] is False
    assert "instrumentation" in (seen["reason"] or "")

    line = visibility.note(seen)
    assert line is not None
    assert "not in the dependency graph" in line
    assert "counts exactly as a miss" in line


def test_a_datastore_is_not_in_the_catalog_at_all() -> None:
    """ADR-0017 marked this: *"whether infrastructure belongs in the catalog… not decided here
    because nothing at T2.4 consumes it; the first consumer should decide."* The culprit-service
    axis is the consumer, and Q27 is where the catalog change is queued - a node changes what the
    graph tool answers, which moves `TOOL_BEHAVIOUR_REVISION`."""
    seen = visibility.target_visibility("redis-cart")

    assert seen["presence"] == visibility.NOT_IN_CATALOG
    assert seen["nameable"] is False
    assert "Q27" in (seen["reason"] or "")
    assert "not in the service catalog at all" in (visibility.note(seen) or "")


def _run(correct: bool, target: str) -> ScoredRun:
    return ScoredRun(
        run_id="r",
        scenario_id="s",
        trajectory_id="t",
        service=LabelScore(
            truth=target,
            returned=target if correct else "cartservice",
            abstained=False,
            dispute=None,
        ),
        service_visibility=visibility.target_visibility(target),
    )


def test_the_note_prints_under_a_missed_service_and_not_under_a_correct_one() -> None:
    missed = _run(correct=False, target="redis-cart").report()
    assert "target visibility: redis-cart" in missed

    # The same unnameable target, named correctly anyway, is not a caveat - it is the answer.
    hit = _run(correct=True, target="redis-cart").report()
    assert "target visibility" not in hit


def test_reporting_it_does_not_forgive_it() -> None:
    """**The whole point.** ADR-0027's bar for a second correct answer is measurement - acting on
    it clears the fault - and neither `productcatalogservice` nor `cartservice` clears the fault
    on these two scenarios. So the miss stays a miss in the score and in the printed line."""
    scored = _run(correct=False, target="featureflagservice")

    assert scored.service is not None and scored.service.correct is False
    assert scored.as_dict()["service"]["correct"] is False
    assert "WRONG" in scored.report()


def test_the_visibility_travels_in_the_manifest() -> None:
    """A figure computed and written nowhere is the defect this repository keeps finding; the
    sweep write-up reads this back out of the manifests rather than recomputing it."""
    payload = _run(correct=False, target="redis-cart").as_dict()

    assert payload["service_visibility"]["presence"] == visibility.NOT_IN_CATALOG
