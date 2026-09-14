"""Q57's instrument, against fixtures (`PREREGISTRATION-Q57.md`).

No world, no database, no model. Every number the write-up will quote comes out of the functions
exercised here, so a defect in the arithmetic shows up before it shows up in a published figure.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

from evalharness import changeresidue
from evalharness.changeresidue import (
    Investigation,
    Query,
    classify,
    paired_difference,
    split_by_stale,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ONSET = datetime(2026, 9, 14, 6, 23, 30, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return ONSET + timedelta(minutes=minutes)


def investigation(
    stale_and_own: tuple[int, int] = (0, 0),
    *,
    scenario: str = "cart-bad-image-tag",
    correct: bool | None = True,
    abstained: bool = False,
) -> Investigation:
    one = Investigation(
        run_id="r",
        scenario_id=scenario,
        trajectory_id="t",
        correct=correct,
        abstained=abstained,
        injected_at=ONSET,
        reverted_at=at(10),
    )
    one.stale_ids = {f"s{i}" for i in range(stale_and_own[0])}
    one.own_ids = {f"o{i}" for i in range(stale_and_own[1])}
    return one


# --- what a query covered -----------------------------------------------------------------------


def test_a_record_before_this_run_s_injection_is_stale_and_one_inside_it_is_not() -> None:
    """**The whole rule, and deliberately only this.** Parsing summaries or matching a catalog to
    decide which records belong to the harness would put a judgement inside the instrument - and
    the agent reading that log cannot make that judgement either, which is the finding."""
    one = investigation()
    one.stale_ids.clear()
    one.own_ids.clear()
    one.queries = [Query("cartservice", at(-1440), at(20))]

    classify(
        one,
        [
            ("old-1", "cartservice", at(-100)),
            ("old-2", "cartservice", at(-99)),
            ("mine", "cartservice", at(1)),
            ("revert", "cartservice", at(9)),
            ("other-service", "adservice", at(-50)),
            ("outside-window", "cartservice", at(-2000)),
        ],
    )

    assert one.stale_ids == {"old-1", "old-2"}
    assert one.own_ids == {"mine", "revert"}


def test_two_queries_covering_one_service_do_not_count_a_record_twice() -> None:
    """The change specialist can dispatch more than once. Summing per-query counts would inflate
    the headline by however many times the planner happened to ask."""
    one = investigation()
    one.stale_ids.clear()
    one.own_ids.clear()
    one.queries = [
        Query("cartservice", at(-1440), at(20)),
        Query("cartservice", at(-720), at(20)),
    ]

    classify(one, [("old-1", "cartservice", at(-100))])

    assert one.stale == 1


def test_a_run_with_no_injection_time_is_left_alone_rather_than_guessed() -> None:
    """Thirteen archived trajectories predate the run manifest. An instrument that assumed a time
    for them would produce a number about runs it cannot see."""
    one = investigation()
    one.stale_ids.clear()
    one.injected_at = None
    one.queries = [Query("cartservice", at(-1440), at(20))]

    classify(one, [("old-1", "cartservice", at(-100))])

    assert one.stale == 0


def test_the_recorded_request_is_read_rather_than_the_window_policy_re_derived() -> None:
    """`trajectory_tool_calls.request` carries the window the specialist actually asked for.
    Recomputing it from `WindowPolicy` here would be a second implementation of the harness."""
    query = Query.from_request(
        {
            "window": ["2026-09-08T13:27:30.583000+00:00", "2026-09-09T13:29:29.103541+00:00"],
            "service": "productcatalogservice",
            "window_rule": "change_lookback",
            "lookback_seconds": 86400,
        }
    )

    assert query is not None
    assert query.service == "productcatalogservice"
    assert (query.end - query.start).total_seconds() == 86400 + 118.520541


def test_a_request_without_a_window_is_none_rather_than_a_default() -> None:
    """A missing window means the call predates the fields. Substituting 24 hours would invent
    coverage the record does not claim."""
    assert Query.from_request({}) is None
    assert Query.from_request({"service": "cartservice"}) is None
    assert Query.from_request({"window": ["nonsense", "also"], "service": "c"}) is None


# --- the split, and what it is protecting against -----------------------------------------------


def test_each_scenario_is_halved_at_its_own_median() -> None:
    """**Not at a shared threshold.** A cartservice scenario follows every other cartservice
    scenario, so scenarios differ in how much residue they accumulate and a global cut would sort
    scenarios rather than runs - the confound §3 exists to remove."""
    runs = [
        investigation((0, 1), correct=True),
        investigation((1, 1), correct=True),
        investigation((20, 1), correct=False),
        investigation((30, 1), correct=False),
    ]

    split = split_by_stale(runs)

    assert split is not None
    assert split.low_n == 2 and split.high_n == 2
    assert split.low_accuracy == 1.0
    assert split.high_accuracy == 0.0
    assert split.delta == 1.0, "positive means the noisier half did worse"


def test_a_scenario_whose_runs_all_saw_the_same_residue_does_not_split() -> None:
    """Every run on one side of its own median is not a comparison, and reporting it as one would
    put a delta of zero into the mean that came from no contrast at all."""
    assert split_by_stale([investigation((5, 1)) for _ in range(6)]) is None


def test_a_scenario_with_too_few_runs_does_not_split() -> None:
    """Four is the floor: below it the split is one run against one, and `bootstrap_ci` would
    render a zero-width interval around noise."""
    assert changeresidue.MIN_RUNS_PER_SCENARIO == 4
    assert split_by_stale([investigation((0, 1)), investigation((9, 1))]) is None
    assert split_by_stale([investigation((0, 1)) for _ in range(3)]) is None


def test_abstentions_are_counted_and_kept_out_of_accuracy() -> None:
    """ADR-0022 §1.2. An agent that declines to name a class under a noisy log has not got it
    wrong, and folding that into accuracy would hide the response §5's prediction 6 expects."""
    runs = [
        investigation((0, 1), correct=True),
        investigation((0, 1), correct=None, abstained=True),
        investigation((9, 1), correct=True),
        investigation((9, 1), correct=None, abstained=True),
    ]

    split = split_by_stale(runs)

    assert split is not None
    assert split.low_accuracy == 1.0 and split.high_accuracy == 1.0
    assert split.low_abstentions == 1 and split.high_abstentions == 1
    assert split.delta == 0.0


def test_the_interval_is_the_one_the_repository_already_uses() -> None:
    """`variance.bootstrap_ci`, its seed and its resample count. A second interval with a second
    seed would let two readers quote different 95% CIs for one comparison."""
    splits = [
        split_by_stale(
            [
                investigation((0, 1), scenario=f"s{i}", correct=True),
                investigation((0, 1), scenario=f"s{i}", correct=True),
                investigation((9, 1), scenario=f"s{i}", correct=False),
                investigation((9, 1), scenario=f"s{i}", correct=True),
            ]
        )
        for i in range(6)
    ]
    mean, low, high, n = paired_difference([s for s in splits if s])

    assert n == 6
    assert mean == 0.5
    assert low <= mean <= high


def test_no_splits_reports_nan_rather_than_zero() -> None:
    """Zero is a measurement. An archive that produced no comparable scenario has not measured a
    difference of zero, and printing one would be the emptiness-as-evidence defect ADR-0019 names
    on the other side of the tool boundary."""
    mean, low, high, n = paired_difference([])

    assert n == 0
    assert mean != mean and low != low and high != high


# --- the guards ---------------------------------------------------------------------------------


def test_the_instrument_calls_no_model_and_scores_nothing_itself() -> None:
    """It must read the archive, not re-judge it. `evaldb.row_of` owns the flattening and the
    scorer owns correctness; a second path to `fault_class_correct` would be a second scorer."""
    source = (REPO_ROOT / "src" / "evalharness" / "changeresidue.py").read_text()
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "anthropic" not in imported
    assert not any(name.startswith("faultline.agents") for name in imported)
    assert "evalharness.scoring" not in imported
    assert "evalharness.judge" not in imported


def test_scored_runs_only_and_each_needs_a_trajectory() -> None:
    """A discarded run's numbers may not be used, and a run with no trajectory has no change query
    to read - counting it as zero stale would move the median with a run that saw nothing."""
    scored = {
        "scenario_id": "cart-bad-image-tag",
        "injected_at": ONSET.isoformat(),
        "reverted_at": at(10).isoformat(),
        "score": {"trajectory_id": "t1", "fault_class": {"correct": True, "abstained": False}},
    }
    no_trajectory = {**scored, "score": {"fault_class": {"correct": True}}}
    discarded = {**scored, "discarded": {"reason": "world moved"}}

    out = changeresidue.investigations_from([("a", scored), ("b", no_trajectory), ("c", discarded)])

    assert [i.run_id for i in out] == ["a"]
