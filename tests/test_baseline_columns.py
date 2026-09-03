"""Baseline columns, mandatory in every headline table (T4.7).

The plan's reason is a threat rather than a preference: baselines *"pre-empt the sharpest
available attack ('is any of this doing anything?') by answering it in your own README."* Three
baselines that exist as configs nobody prints answer nothing.
"""

from __future__ import annotations

import pytest

from evalharness import variance
from evalharness.baseline_columns import (
    BASELINE_IDS,
    NOT_RUN,
    BaselinePanel,
    BaselineRow,
    IncompleteBaselinePanelError,
    panel,
)
from evalharness.compare import METRICS, Arm, Metric, Run

ACCURACY = METRICS[0]


def figure(mean: float = 0.5) -> variance.Figure:
    return variance.Figure(label="x", mean=mean, low=mean - 0.1, high=mean + 0.1, n=4, r=1)


def row(baseline: str, measured: bool = True) -> BaselineRow:
    if measured:
        return BaselineRow(baseline=baseline, description="d", figure=figure(), runs=4)
    return BaselineRow(baseline=baseline, description="d", note="never run")


# --- mandatory means cannot be constructed without it ----------------------------------------


def test_a_panel_missing_a_baseline_cannot_be_built() -> None:
    """**The enforcement, in the shape `variance.Figure` already uses.**

    `compare.py` says the four-part-figure rule *"cannot be violated here, because
    `variance.Figure` requires all four to construct"*. A convention would not survive: this
    project has watched one fail twice in a week - `no-commit-on-main` guarded one door of
    several, and `TriageJudgement` sat outside `_CONTRACTS` for a whole sweep.
    """
    with pytest.raises(IncompleteBaselinePanelError) as caught:
        BaselinePanel(metric_label="fault class accuracy", rows=(row("B0"), row("B1")))

    assert "B2" in str(caught.value)


def test_an_empty_panel_is_refused_rather_than_treated_as_nothing_to_show() -> None:
    with pytest.raises(IncompleteBaselinePanelError):
        BaselinePanel(metric_label="fault class accuracy", rows=())


def test_two_rows_for_one_baseline_are_refused() -> None:
    """Two measurements presented as one baseline's standing. The duplicate would most likely be
    two fingerprints - different models or budgets - which is exactly what the fingerprint exists
    to keep apart."""
    rows = (row("B0"), row("B0"), row("B1"), row("B2"))

    with pytest.raises(IncompleteBaselinePanelError) as caught:
        BaselinePanel(metric_label="cost per run", rows=rows)

    assert "B0" in str(caught.value)


def test_a_panel_with_every_baseline_builds() -> None:
    built = BaselinePanel(
        metric_label="fault class accuracy", rows=tuple(row(name) for name in BASELINE_IDS)
    )

    assert built.complete is True
    assert len(built.rows) == 3


# --- an unrun baseline is a row that says so ------------------------------------------------


def test_an_unrun_baseline_still_gets_a_row() -> None:
    """**The decision that matters, and it is the opposite of the tempting one.**

    No baseline has been scored yet. The tempting rendering leaves the rows out until there is
    something to put in them - and a headline table with no baseline rows reads as one whose
    author did not think to ask, while three rows reading "not run" read as a project that knows
    what it has not measured. The second is true.
    """
    built = BaselinePanel(
        metric_label="fault class accuracy",
        rows=tuple(row(name, measured=False) for name in BASELINE_IDS),
    )
    rendered = "\n".join(built.render())

    assert built.complete is False
    for name in BASELINE_IDS:
        assert name in rendered
    # The italicised cell, not the bare phrase: the caption says "3 of 3 baselines have not run"
    # and would be counted too.
    assert rendered.count(f"*{NOT_RUN}*") == 3


def test_an_unrun_baseline_must_say_what_stopped_it() -> None:
    """*"Not run"* with no reason is a blank a reader has to guess at, and 'too expensive',
    'not built' and 'forgotten' are not the same claim about whether the table can be trusted."""
    with pytest.raises(IncompleteBaselinePanelError):
        BaselineRow(baseline="B1", description="d")


def test_an_incomplete_panel_captions_itself_as_incomplete() -> None:
    """`complete` captions the table; it never decides whether the table is printed."""
    rows = (row("B0"), row("B1", measured=False), row("B2", measured=False))
    rendered = "\n".join(BaselinePanel(metric_label="cost per run", rows=rows).render())

    assert "2 of 3 baselines have not run" in rendered


def test_a_complete_panel_says_what_the_baselines_shared_with_the_pipeline() -> None:
    rows = tuple(row(name) for name in BASELINE_IDS)
    rendered = "\n".join(BaselinePanel(metric_label="cost per run", rows=rows).render())

    assert "same gate" in rendered and "same scorer" in rendered


# --- building a panel from arms --------------------------------------------------------------


def arm_of(fingerprint: str, values: dict[str, float]) -> Arm:
    return Arm(
        fingerprint=fingerprint,
        runs=[
            Run(scenario_id=name, split="dev", values={ACCURACY.key: value})
            for name, value in values.items()
        ],
        declared_r=1,
    )


def test_a_baseline_with_runs_gets_a_figure_carrying_n_and_r() -> None:
    built = panel(ACCURACY, {"B0": arm_of("f0", {"a": 1.0, "b": 0.0, "c": 1.0})})

    b0 = next(r for r in built.rows if r.baseline == "B0")
    assert b0.figure is not None
    assert b0.figure.n == 3
    assert "n=3" in b0.figure.render() and "R=1" in b0.figure.render()


def test_baselines_absent_from_the_database_still_get_rows() -> None:
    built = panel(ACCURACY, {"B0": arm_of("f0", {"a": 1.0})})

    assert [r.baseline for r in built.rows] == list(BASELINE_IDS)
    assert [r.figure is None for r in built.rows] == [False, True, True]


def test_a_supplied_reason_reaches_the_row() -> None:
    built = panel(ACCURACY, {}, reasons={"B1": "runs need credits", "B2": "runs need credits"})

    assert all("credits" in r.note for r in built.rows if r.baseline in {"B1", "B2"})


def test_an_arm_that_ran_but_recorded_nothing_for_this_metric_is_not_run_here() -> None:
    """An arm with runs but no values for the metric has not measured it. A zero would be a
    measurement; the absence is not one, which is ADR-0019's distinction applied to a column."""
    empty = Arm(fingerprint="f", runs=[Run(scenario_id="a", split="dev", values={})], declared_r=1)

    built = panel(ACCURACY, {"B0": empty})

    assert next(r for r in built.rows if r.baseline == "B0").figure is None


def test_abstentions_are_excluded_here_exactly_as_they_are_in_a_comparison() -> None:
    """ADR-0022 §1.2: an abstention is neither right nor wrong. The panel reads through
    `Arm.per_scenario`, which is the same code path `compare_metric` uses - so a baseline cannot
    be scored under a different abstention rule than the pipeline it is a control for."""
    metric = Metric("fault_class_correct", "fault class accuracy", skip_when_abstained=True)
    arm = Arm(
        fingerprint="f",
        runs=[
            Run(scenario_id="a", split="dev", values={metric.key: 1.0}),
            Run(
                scenario_id="b", split="dev", values={metric.key: 0.0}, abstained={metric.key: True}
            ),
        ],
        declared_r=1,
    )

    built = panel(metric, {"B0": arm})

    b0 = next(r for r in built.rows if r.baseline == "B0")
    assert b0.figure is not None
    assert b0.figure.n == 1, "the abstained scenario is excluded, not counted as wrong"


# --- the panel reaches every headline table ---------------------------------------------------


def test_the_comparison_report_carries_a_baseline_panel_for_every_metric() -> None:
    """**The deliverable's own words: mandatory in EVERY headline table.** One panel per metric
    the report prints, with no baseline data in the database at all - which is today's state and
    the case most likely to have been rendered as silence."""
    from evalharness.compare import report

    a = arm_of("aaa", {"s1": 1.0, "s2": 0.0})
    b = arm_of("bbb", {"s1": 1.0, "s2": 1.0})

    rendered = "\n".join(report(a, b, baselines={}))

    assert rendered.count("### Baselines") >= 1
    for name in BASELINE_IDS:
        assert name in rendered
    assert NOT_RUN in rendered


def test_the_report_does_not_compute_a_baseline_delta() -> None:
    """Nothing here subtracts a baseline from the pipeline. `compare_metric` owns deltas, and
    `variance.mde` decides whether one is resolvable - at n≈10, R=1 this catalog's MDE is 28pp,
    so a bare printed difference would invite exactly the reading that machinery prevents."""
    from evalharness.compare import report

    a = arm_of("aaa", {"s1": 1.0})
    b = arm_of("bbb", {"s1": 0.0})

    rendered = "\n".join(report(a, b, baselines={"B0": arm_of("f0", {"s1": 1.0})}))

    baseline_section = rendered[rendered.index("### Baselines") :]
    assert "B minus" not in baseline_section
