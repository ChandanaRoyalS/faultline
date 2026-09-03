"""T4.6's variance protocol: the properties that stop a figure from lying."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from evalharness import variance as v

# --- a figure cannot exist without its interval ------------------------------------------


def test_a_figure_cannot_be_built_without_n_r_and_an_interval() -> None:
    """**CLAUDE.md rule 6 as a constructor signature.** The plan says *"a figure without all four
    is a bug in the generator"*; making them required arguments means the bug cannot be written."""
    with pytest.raises(TypeError):
        v.Figure(label="accuracy", mean=0.1)  # type: ignore[call-arg]


def test_every_rendered_figure_states_n_r_and_the_interval() -> None:
    rendered = v.Figure(label="fault class", mean=0.08, low=-0.02, high=0.18, n=10, r=3).render()

    assert "95% CI" in rendered
    assert "n=10" in rendered
    assert "R=3" in rendered


# --- pairing ------------------------------------------------------------------------------


def test_only_scenarios_both_arms_ran_are_compared() -> None:
    """A configuration that ran seven against one that ran eight is compared on seven. Averaging
    eight against seven and calling the difference an effect is the error pairing prevents."""
    deltas = v.paired_deltas(
        {"a": 1.0, "b": 0.0, "c": 1.0},
        {"a": 1.0, "b": 1.0, "d": 1.0},
    )

    assert set(deltas) == {"a", "b"}
    assert deltas == {"a": 0.0, "b": 1.0}


def test_a_scenario_hard_under_both_arms_contributes_nothing_to_the_delta() -> None:
    """The whole point of pairing. Between-scenario difficulty cancels instead of inflating the
    variance of both means."""
    deltas = v.paired_deltas({"hard": 0.0, "easy": 1.0}, {"hard": 0.0, "easy": 1.0})

    assert set(deltas.values()) == {0.0}


# --- intervals ----------------------------------------------------------------------------


def test_the_interval_is_reproducible_from_the_same_rows() -> None:
    """Fixed seed, so two readers quoting "the 95% CI" mean the same numbers and a regenerated
    report does not drift."""
    values = [0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0]

    assert v.bootstrap_ci(values) == v.bootstrap_ci(values)


def test_a_single_observation_gets_a_zero_width_interval_not_a_confident_band() -> None:
    """One scenario is one observation. A band around it would invent the thing this module
    exists to prevent."""
    assert v.bootstrap_ci([0.4]) == (0.4, 0.4)
    assert v.bootstrap_ci([]) == (0.0, 0.0)


def test_the_interval_widens_as_n_falls() -> None:
    wide = v.bootstrap_ci([0.0, 1.0, 0.0, 1.0])
    narrow = v.bootstrap_ci([0.0, 1.0] * 25)

    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])


# --- the MDE ------------------------------------------------------------------------------


def test_the_mde_is_larger_than_the_half_width_by_the_power_factor() -> None:
    """**The distinction the plan's own table blurs.** A CI half-width is what a comparison can
    resolve; an MDE at 80% power is what it can reliably detect, and the second is larger by
    (z_alpha + z_beta) / z_alpha. Reporting one under the other's name understates what the
    catalog can detect by 43%."""
    ratio = v.mde(30, r=5) / v.ci_half_width(30, r=5)

    assert math.isclose(ratio, (v.Z_ALPHA + v.Z_BETA) / v.Z_ALPHA, rel_tol=1e-9)
    assert math.isclose(ratio, 1.4294, rel_tol=1e-3)


def test_the_plans_three_figures_are_reproduced_and_two_are_half_widths() -> None:
    """The finding, pinned. The plan states 10 ~ 20pp, 30 ~ 10pp, and 30 paired at R=5 ~ 6-7pp;
    the first two are CI half-widths and the third is an MDE at 80% power."""
    assert 19.0 < v.ci_half_width(10) * 100 < 20.5, "the plan's ~20pp is a half-width"
    assert 10.5 < v.ci_half_width(30) * 100 < 11.5, "the plan's ~10pp is a half-width"
    assert 6.5 < v.mde(30, r=5) * 100 < 7.5, "the plan's ~6-7pp is an MDE at 80% power"


def test_a_delta_below_its_mde_is_reported_as_no_measurable_effect() -> None:
    """The plan's rule, verbatim: *"a delta below its MDE is reported as 'no measurable effect at
    this catalog size'"* - which it calls stronger than a fabricated 3-point win."""
    assert "no measurable effect" in v.verdict(0.03, n=10, r=1)
    assert "no measurable effect" not in v.verdict(0.40, n=10, r=1)


def test_repeats_shrink_the_mde_and_the_assumption_is_visible() -> None:
    assert v.mde(10, r=5) < v.mde(10, r=1)
    assert v.mde(10, rho=0.5) > v.mde(10, rho=0.8), "less correlation, less pairing buys"


# --- the checked-in table -------------------------------------------------------------------


def test_the_mde_table_is_checked_in_before_any_ablation() -> None:
    """T4.6 requires it *"checked into the repo before the first ablation runs"*. Computed
    afterwards it would be a description of whatever was found."""
    table = Path("evals/MDE.md")

    assert table.is_file()
    text = table.read_text()
    assert "MDE (80% power)" in text and "CI half-width" in text
    assert "no measurable effect at this catalog size" in text


def test_the_checked_in_table_still_matches_what_the_code_computes() -> None:
    """**Generated, not transcribed.** If the constants move and the file does not, this fails -
    which is the difference between a derived table and a remembered one."""
    text = Path("evals/MDE.md").read_text()

    for line in v.table():
        assert line in text, f"evals/MDE.md is stale: missing {line!r}"


# --- tiers ---------------------------------------------------------------------------------


def test_every_tier_names_its_repeat_count_and_what_it_may_be_used_for() -> None:
    for name, (repeats, note) in v.TIERS.items():
        assert repeats >= 1, name
        assert note, name
    assert v.TIERS["ci-smoke"][0] == 1
    assert v.TIERS["published"][0] == 5, "the only tier a printed comparison may come from"


def test_the_default_tier_is_manual_and_claims_no_cadence() -> None:
    """Every scored run in this repository so far was launched by hand. Labelling those `nightly`
    would claim a cadence that does not exist."""
    assert v.TIERS["manual"] == (1, "one run by hand; an observation, never a rate")


def test_the_seed_policy_records_that_nothing_here_is_seedable() -> None:
    """T4.6 asks for *"the same seeds where seedable"*. Nothing is, and saying so is the point -
    an absent field cannot distinguish "considered and rejected" from "never thought about"."""
    assert "unseeded" in v.SEED_POLICY
