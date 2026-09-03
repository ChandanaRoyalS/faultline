"""The A/A check (Gate 4).

*"A harness that invents a delta between a config and itself will invent every delta it ever
reports — this is the cheapest possible [check]."* Everything else in this repository measures the
pipeline; this measures the **instrument**, and it is the only figure whose failure would
invalidate all the others at once.
"""

from __future__ import annotations

import pytest

from evalharness import aa
from evalharness.compare import METRICS, Arm, Run

ACCURACY = METRICS[0]


def arm_of(runs: list[tuple[str, float]], fingerprint: str = "abc123") -> Arm:
    return Arm(
        fingerprint=fingerprint,
        runs=[
            Run(scenario_id=name, split="dev", values={ACCURACY.key: value}) for name, value in runs
        ],
        declared_r=2,
    )


def repeated(scenarios: int, per_scenario: int, value: float = 1.0) -> Arm:
    return arm_of(
        [(f"s{n}", value) for n in range(scenarios) for _ in range(per_scenario)],
    )


# --- it needs R >= 2, and every sweep so far has been R = 1 -----------------------------------


def test_a_single_run_per_scenario_has_no_a_a_check_at_all() -> None:
    """**Not a weak check — none.** Pairing needs each scenario in both arms, and at R = 1 a
    scenario has one run. Every sweep in this repository has been R = 1, so the A/A check cannot
    be run on any data that currently exists."""
    with pytest.raises(aa.NotEnoughRepeatsError) as caught:
        aa.split(repeated(scenarios=5, per_scenario=1))

    message = str(caught.value)
    assert "At R = 1 there is no A/A check" in message
    assert "weekly" in message and "published" in message


def test_one_thin_scenario_refuses_rather_than_shrinking_the_check() -> None:
    """An A/A check computed over the two scenarios that happened to repeat is a check over two
    scenarios wearing the name of a check over the catalog."""
    mixed = arm_of([("s0", 1.0), ("s0", 1.0), ("s1", 1.0)])

    with pytest.raises(aa.NotEnoughRepeatsError) as caught:
        aa.split(mixed)

    assert "s1" in str(caught.value), "the refusal names which scenario was thin"


def test_an_empty_arm_refuses() -> None:
    with pytest.raises(aa.NotEnoughRepeatsError):
        aa.split(arm_of([]))


# --- alternating, not chronological ------------------------------------------------------------


def test_runs_alternate_within_each_scenario_so_both_arms_span_the_sweep() -> None:
    """**A chronological split would put every early run in one arm**, so any drift over the
    sweep — world state, time of day, a service that got slower — lands entirely on one side and
    reads as a delta. That artefact is exactly what this check exists to detect, and a split
    manufacturing it would make the check fail for the one reason it must not."""
    arm = arm_of([("s0", 1.0), ("s0", 0.0), ("s1", 1.0), ("s1", 0.0)])

    left, right = aa.split(arm)

    assert [r.values[ACCURACY.key] for r in left.runs] == [1.0, 1.0], "the first of each scenario"
    assert [r.values[ACCURACY.key] for r in right.runs] == [0.0, 0.0], "the second of each"
    assert {r.scenario_id for r in left.runs} == {r.scenario_id for r in right.runs}


def test_an_odd_number_of_runs_puts_the_extra_in_the_first_arm() -> None:
    """R = 3 is a real tier. The odd run goes somewhere, and saying where is better than leaving
    it to the reader to work out from an arm-size mismatch."""
    left, right = aa.split(repeated(scenarios=2, per_scenario=3))

    assert len(left.runs) == 4 and len(right.runs) == 2


def test_both_arms_keep_the_configs_identity() -> None:
    """The two halves are the *same* configuration. Their fingerprints are marked `#A` and `#B` so
    a report cannot present them as two configs, and the runtime is carried unchanged."""
    arm = Arm(
        fingerprint="abc123",
        runs=[Run("s0", "dev", {ACCURACY.key: 1.0}), Run("s0", "dev", {ACCURACY.key: 1.0})],
        declared_r=2,
        runtime_version="faultline/0.0.1+prompts:ba8684b01201",
    )

    left, right = aa.split(arm)

    assert (left.fingerprint, right.fingerprint) == ("abc123#A", "abc123#B")
    assert left.runtime_version == right.runtime_version == arm.runtime_version


# --- what a pass and a failure mean --------------------------------------------------------------


def test_identical_halves_pass_with_a_delta_of_zero() -> None:
    result = aa.check(repeated(scenarios=6, per_scenario=2, value=1.0))

    assert result.passed is True
    assert result.failures == ()
    assert result.worst is not None and result.worst.figure.mean == 0.0


def test_a_large_invented_delta_fails_and_says_why_it_matters() -> None:
    """The failure mode Gate 4 names. Every scenario answers 1.0 on its first run and 0.0 on its
    second — a 100pp split between two halves of one configuration."""
    arm = arm_of([(f"s{n}", value) for n in range(8) for value in (1.0, 0.0)])

    result = aa.check(arm)

    assert result.passed is False
    rendered = "\n".join(result.render())
    assert "FAILED" in rendered
    assert "will invent every delta it ever reports" in rendered
    assert "every other figure in this report is suspect" in rendered


def test_the_observed_delta_is_reported_and_not_only_the_verdict() -> None:
    """**Passing is nearly automatic at this catalog size**, so a green verdict is weak evidence.
    A delta near zero is reassuring; a large one that happens to sit under the MDE is not, and the
    verdict alone cannot tell them apart."""
    result = aa.check(repeated(scenarios=6, per_scenario=2))
    rendered = "\n".join(result.render())

    assert "Largest observed delta" in rendered
    assert "Read the delta, not the verdict" in rendered
    assert "weak evidence" in rendered


def test_a_pass_is_never_rendered_as_the_harness_being_sound() -> None:
    """The claim a green A/A check licenses is narrow, and the rendered text is where that has to
    be said - a reader quoting the result will quote the output, not the docstring."""
    rendered = "\n".join(aa.check(repeated(scenarios=5, per_scenario=2)).render())

    assert "sound" not in rendered.lower()
    assert "almost any comparison reports no measurable effect" in rendered


def test_the_mde_travels_with_a_pass() -> None:
    """A pass says the delta was under the MDE. Without the MDE beside it, a reader cannot tell
    whether that means *small* or merely *smaller than a threshold nothing could exceed*."""
    assert "MDE" in aa.mde_at(10, 1)
    assert "n=10" in aa.mde_at(10, 1) and "R=5" in aa.mde_at(10, 5)
    assert aa.mde_at(10, 1) != aa.mde_at(10, 5), "more repeats, a smaller detectable effect"


def test_a_result_with_no_comparable_metric_says_so_rather_than_passing() -> None:
    """`passed` over an empty list is vacuously true, and rendering that as a pass would be the
    harness reporting a check it never performed."""
    empty = aa.Result(fingerprint="abc123")

    assert "no metric could be compared" in "\n".join(empty.render())
    # **The defect this file nearly shipped with.** `all()` over an empty list is True, so
    # `passed` without the emptiness guard would announce a clean bill of health for an
    # examination that never happened - the same shape as a guard over an empty vocabulary.
    assert empty.passed is False, "a check that compared nothing did not pass"


# --- it is invokable, and its exit codes distinguish three things -----------------------------


def test_the_check_is_reachable_from_the_compare_cli() -> None:
    """**A check nothing invokes is not a check.** `aa.check` was library-only when first
    written, so Gate 4's fourth condition had no way to be run."""
    import inspect

    from evalharness.compare import main

    source = inspect.getsource(main)

    assert '"--aa"' in source
    assert "aa_check.check(" in source


def test_the_cli_separates_failed_from_could_not_be_performed() -> None:
    """Three outcomes, three codes, and conflating the middle two is the trap.

    - `0` the check ran and passed
    - `1` the check ran and **failed** - so CI can gate on it, because a condition nothing can
      fail is not a condition
    - `3` the check **could not be performed** (no runs, or R = 1), which must not read as the
      harness having invented a delta
    """
    import inspect

    from evalharness.compare import main

    source = inspect.getsource(main)
    refusal = source[source.index("if args.aa:") : source.index("if args.list:")]

    assert "return 0 if result.passed else 1" in refusal
    assert refusal.count("return 3") == 2, "no runs, and not enough repeats"
    assert "NotEnoughRepeatsError" in refusal
