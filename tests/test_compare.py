"""The comparison report (T4.4), and the properties that keep it from overclaiming."""

from __future__ import annotations

from datetime import UTC, datetime

from evalharness import compare

WHEN = datetime(2026, 9, 3, tzinfo=UTC)


def run(scenario: str, split: str = "dev", **values: object) -> compare.Run:
    abstained = {
        "fault_class_correct": bool(values.pop("fault_abstained", False)),
        "fix_class_correct": bool(values.pop("fix_abstained", False)),
    }
    return compare.Run(scenario_id=scenario, split=split, values=values, abstained=abstained)


def arm(fingerprint: str, runs: list[compare.Run], **kwargs: object) -> compare.Arm:
    return compare.Arm(fingerprint=fingerprint, runs=runs, **kwargs)  # type: ignore[arg-type]


# --- pairing --------------------------------------------------------------------------------


def test_only_scenarios_both_arms_ran_reach_a_figure() -> None:
    """A scenario one arm ran and the other did not is excluded and named. Averaging different
    catalogs and calling the difference an effect is what pairing exists to prevent."""
    a = arm("aaa", [run("s1", fault_class_correct=1.0), run("s2", fault_class_correct=0.0)])
    b = arm("bbb", [run("s1", fault_class_correct=1.0), run("s3", fault_class_correct=1.0)])

    found = compare.compare_metric(a, b, compare.METRICS[0], "all")

    assert found is not None
    assert found.figure.n == 1, "only s1 is shared"
    text = "\n".join(compare.report(a, b, at=WHEN))
    assert "only in A: `s2`" in text
    assert "only in B: `s3`" in text


def test_repeats_of_one_scenario_average_before_the_pairing() -> None:
    """R > 1 means several runs of one scenario; the scenario contributes one value, not several,
    or a scenario run five times would outvote four run once."""
    a = arm("aaa", [run("s1", fault_class_correct=0.0), run("s1", fault_class_correct=1.0)])
    b = arm("bbb", [run("s1", fault_class_correct=1.0)])

    found = compare.compare_metric(a, b, compare.METRICS[0], "all")

    assert found is not None
    assert found.figure.n == 1
    assert abs(found.figure.mean - 0.5) < 1e-9, "0.5 under A, 1.0 under B"


# --- what is excluded ------------------------------------------------------------------------


def test_an_abstention_is_excluded_from_accuracy_and_not_scored_as_wrong() -> None:
    """ADR-0022 §1.2: an abstention is neither right nor wrong. Scoring it either way would make
    saying nothing a strategy with a payoff."""
    a = arm("aaa", [run("s1", fault_class_correct=1.0), run("s2", fault_class_correct=1.0)])
    b = arm(
        "bbb",
        [
            run("s1", fault_class_correct=0.0, fault_abstained=True),
            run("s2", fault_class_correct=1.0),
        ],
    )

    found = compare.compare_metric(a, b, compare.METRICS[0], "all")

    assert found is not None
    assert found.scenarios == ["s2"], "the abstained scenario leaves the accuracy figure"


def test_a_metric_a_run_never_recorded_is_skipped_and_not_read_as_zero() -> None:
    """A run from before latency was measured has no latency. Averaging it in as zero would
    report an instantaneous investigation."""
    a = arm("aaa", [run("s1", latency_ms=None), run("s2", latency_ms=100.0)])
    b = arm("bbb", [run("s1", latency_ms=200.0), run("s2", latency_ms=150.0)])

    found = compare.compare_metric(a, b, compare.METRICS[5], "all")

    assert found is not None
    assert found.scenarios == ["s2"]


# --- the four-part figure ---------------------------------------------------------------------


def test_every_figure_in_a_report_carries_mean_ci_n_and_r() -> None:
    """**The plan's "a figure without all four is a bug in the generator", checked on real
    output.** It cannot be violated - `variance.Figure` requires all four - and this asserts the
    rendered report actually shows them."""
    a = arm("aaa", [run(f"s{i}", fault_class_correct=float(i % 2)) for i in range(6)])
    b = arm("bbb", [run(f"s{i}", fault_class_correct=1.0) for i in range(6)])

    text = "\n".join(compare.report(a, b, at=WHEN))
    figures = [line for line in text.splitlines() if line.startswith("- ") and "CI" in line]

    assert figures, "the report printed no figures"
    for line in figures:
        assert "95% CI" in line and "n=" in line and "R=" in line, line


def test_a_below_mde_delta_is_reported_as_no_measurable_effect() -> None:
    """At n = 6, R = 1 the MDE is far above any small delta - so the report must say the catalog
    cannot detect it rather than reporting a win."""
    a = arm("aaa", [run(f"s{i}", fault_class_correct=1.0) for i in range(6)])
    b = arm(
        "bbb",
        [run("s0", fault_class_correct=0.0)]
        + [run(f"s{i}", fault_class_correct=1.0) for i in range(1, 6)],
    )

    text = "\n".join(compare.report(a, b, at=WHEN))

    assert "no measurable effect at this catalog size" in text


# --- the split policy -------------------------------------------------------------------------


def test_below_thirty_scenarios_the_report_prints_the_split_and_disclaims_headlines() -> None:
    """T1.6: full-set with labeled split and explicit n until the catalog reaches 30."""
    a = arm(
        "aaa",
        [run("s1", "dev", fault_class_correct=1.0), run("s2", "holdout", fault_class_correct=0.0)],
    )
    b = arm(
        "bbb",
        [run("s1", "dev", fault_class_correct=1.0), run("s2", "holdout", fault_class_correct=1.0)],
    )

    text = "\n".join(compare.report(a, b, catalog_size=18, at=WHEN))

    assert "below the 30" in text
    assert "no figure here is a headline number" in text
    assert "(dev)" in text and "(holdout)" in text


# --- the header -------------------------------------------------------------------------------


def test_declared_and_observed_repeat_counts_are_both_printed() -> None:
    """A configuration declared at R = 5 that ran each scenario once is not an R = 5 comparison,
    and printing only the declaration would hide that."""
    a = arm("aaa", [run("s1", fault_class_correct=1.0)], declared_r=5)
    b = arm("bbb", [run("s1", fault_class_correct=1.0)], declared_r=5)

    text = "\n".join(compare.report(a, b, at=WHEN))

    assert "observed runs per scenario" in text
    assert "Declared R and observed runs per scenario differ" in text


def test_discarded_and_invalid_runs_are_counted_in_the_header_and_excluded_from_figures() -> None:
    """The discard rate is a property of a comparison, not an operational footnote."""
    a = arm("aaa", [run("s1", fault_class_correct=1.0)], discarded=4, invalid=1)
    b = arm("bbb", [run("s1", fault_class_correct=1.0)])

    text = "\n".join(compare.report(a, b, at=WHEN))

    assert "| discarded | 4 | 0 |" in text
    assert "| invalid | 1 | 0 |" in text


def test_the_report_refuses_to_attribute_a_difference_to_a_cause() -> None:
    """Two configurations differ by whatever differs between their fingerprints, and a
    fingerprint can move for several reasons at once."""
    a = arm("aaa", [run("s1", fault_class_correct=1.0)])
    b = arm("bbb", [run("s1", fault_class_correct=0.0)])

    text = "\n".join(compare.report(a, b, at=WHEN))

    assert "does not attribute a difference to a cause" in text


def test_the_header_prints_whatever_runtime_each_arm_carries() -> None:
    """**The reporting half of a defect found on the first live comparison.**

    Arm B printed `not recorded` for a configuration whose runtime the table knew. The cause was
    in `arm()`, not here: a discarded run has no score block and therefore no `runtime_version`,
    and an unfiltered `LIMIT 1` over an arm that has discards can return one of them. The fix is
    `AND runtime_version IS NOT NULL` in the query, which **only real Postgres exercises** - so
    this asserts the half that is testable here, that the header prints what the arm carries, and
    the query itself is covered by `tests/test_integration_store.py`.
    """
    a = arm("aaa", [run("s1", fault_class_correct=1.0)], runtime_version="faultline/0.0.1+x")
    b = arm(
        "bbb",
        [run("s1", fault_class_correct=1.0)],
        runtime_version="faultline/0.0.1+y",
        discarded=5,
    )

    header = "\n".join(compare.report(a, b, at=WHEN)).split("## ")[0]
    runtime_row = next(line for line in header.splitlines() if line.startswith("| runtime |"))

    assert "faultline/0.0.1+x" in runtime_row
    assert "faultline/0.0.1+y" in runtime_row
    assert "not recorded" not in runtime_row
