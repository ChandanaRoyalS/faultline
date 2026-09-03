"""The manual-RCA reference (T4.7).

*"The MTTR claim gets its missing left-hand side the honest way: self-timed manual RCA on five dev
scenarios, reported as n=5, self-timed, indicative — an unsourced number next to a rigorously
sourced one damages the rigorous one."*

Every latency figure here is a time for the *pipeline*. Saying it is fast requires something to be
fast against, and until there is one, "three minutes to a report" is a number with no denominator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evalharness import manual_rca as rca


def attempt(
    scenario_id: str = "ad-memory-squeeze",
    seconds: float = 600.0,
    fault_class: str = "resource_exhaustion",
    gave_up: bool = False,
) -> rca.Attempt:
    return rca.Attempt(
        scenario_id=scenario_id,
        started_at="2026-09-03T12:00:00+00:00",
        finished_at="2026-09-03T12:10:00+00:00",
        elapsed_seconds=seconds,
        fault_class="" if gave_up else fault_class,
        service="adservice",
        gave_up=gave_up,
    )


# --- the contamination is the headline, not a footnote ----------------------------------------


def test_the_contamination_is_printed_above_the_number() -> None:
    """**The responder authored these scenarios.** Timing her investigating `ad-memory-squeeze`
    measures how long it takes someone who already knows the answer to confirm it - a different
    and much smaller quantity. There is no fix available inside this project, so it is disclosed
    where it cannot be skipped rather than mitigated."""
    rendered = "\n".join(rca.Reference(attempts=(attempt(),)).render())

    assert rendered.index("AUTHORED THESE SCENARIOS") < rendered.index("Median")
    assert "FLOOR on human time" in rendered
    assert "beaten a fully-informed expert rather than a working one" in rendered


def test_the_plans_own_label_is_used_verbatim_and_mechanically() -> None:
    """`n=5, self-timed, indicative`, the plan's words. Mechanical for the reason
    `smoke.NON_CITABLE` is: a convention that lives in a reviewer's memory survives until the
    first person who was not in the conversation."""
    assert rca.LABEL == "n=5, self-timed, indicative"
    assert rca.LABEL in "\n".join(rca.Reference(attempts=(attempt(),)).render())


# --- deliberately not a variance.Figure ---------------------------------------------------------


def test_no_confidence_interval_is_emitted_and_none_should_be_inferred() -> None:
    """**Applying the four-part-figure rule here would do the opposite of its purpose.**

    Every other quantity in this repository is a `variance.Figure` and cannot be built without a
    CI - the rule that stops unsourced numbers reaching a report. Five self-timed observations
    from one contaminated rater have no sampling model, and a CI would manufacture exactly the
    appearance of rigour the plan warns about. That is the mechanism by which an unsourced number
    damages a sourced one: making them look alike.
    """
    rendered = "\n".join(rca.Reference(attempts=(attempt(), attempt(seconds=900))).render())

    assert "95% CI" not in rendered
    assert "No confidence interval is given and none should be inferred" in rendered
    assert "reference point, not a measurement" in rendered


def test_the_reference_is_not_a_figure_type() -> None:
    """Structural, not cosmetic: it cannot accidentally be passed somewhere a `Figure` is
    rendered, because it is not one."""
    from evalharness import variance

    assert not isinstance(rca.Reference(), variance.Figure)


# --- what enters the number --------------------------------------------------------------------


def test_the_median_is_used_because_five_observations_have_no_mean_worth_trusting() -> None:
    """One long investigation should not move the reference, and with five observations a mean is
    one bad afternoon away from being a different number."""
    times = (attempt(seconds=300), attempt(seconds=600), attempt(seconds=3600))

    assert rca.Reference(attempts=times).median_seconds == 600.0


def test_an_abandoned_attempt_is_recorded_and_excluded_from_the_median() -> None:
    """**Data about difficulty, not a missing observation.** Dropping it would make the median a
    median over the easy ones - and it is named in the output so a reader sees which."""
    attempts = (attempt(seconds=300), attempt(scenario_id="cart-bad-image-tag", gave_up=True))
    reference = rca.Reference(attempts=attempts)

    assert reference.median_seconds == 300.0
    rendered = "\n".join(reference.render())
    assert "1 attempt(s) abandoned" in rendered
    assert "cart-bad-image-tag" in rendered
    assert "median over the easy ones" in rendered


def test_a_wrong_answer_is_counted_but_does_not_filter_the_timings() -> None:
    """A fast wrong answer is not a reference for anything, so correctness is reported - but
    excluding the wrong ones would time only the investigations that went well."""
    wrong = attempt(fault_class="bad_config", seconds=120)
    right = attempt(fault_class="resource_exhaustion", seconds=600)
    reference = rca.Reference(attempts=(wrong, right))

    assert reference.median_seconds == 360.0, "both timings count"
    assert len(reference.completed) == 2


def test_an_untimed_attempt_is_refused() -> None:
    with pytest.raises(rca.AttemptError):
        rca.record(attempt(seconds=0))


def test_an_attempt_that_concluded_must_say_what_it_concluded(tmp_path: Path) -> None:
    """If it reached none, it is `gave_up` - and the refusal says so, because the alternative is a
    silently blank conclusion that later reads as a wrong answer."""
    blank = rca.Attempt(
        scenario_id="s",
        started_at="t",
        finished_at="t",
        elapsed_seconds=60,
        fault_class="",
        service="x",
    )

    with pytest.raises(rca.AttemptError) as caught:
        rca.record(blank, tmp_path / "a.jsonl")

    assert "gave_up" in str(caught.value)


def test_the_ledger_is_append_only(tmp_path: Path) -> None:
    ledger = tmp_path / "attempts.jsonl"

    rca.record(attempt(seconds=300), ledger)
    rca.record(attempt(seconds=400), ledger)

    assert len(rca.load(ledger)) == 2


# --- the absent state is a real state ------------------------------------------------------------


def test_no_attempts_renders_as_the_claim_having_no_denominator() -> None:
    """**Not silence.** Until this exists the MTTR claim has no left-hand side, and a report that
    simply omitted the section would read as one that never asked."""
    import re

    rendered = "\n".join(rca.Reference().render())

    assert "Not yet measured" in rendered
    assert "no denominator" in rendered
    # A *numeric* duration, not the substring "min" - which appears inside "three minutes to a
    # report", the very phrase this section exists to qualify. The third over-broad substring
    # assertion on prose in one day; the pattern is that a fragment of English is not a property.
    assert re.search(r"\d[\d.,]*\s*(min|s\b|sec)", rendered) is None, "no time may be implied"


def test_progress_is_reported_against_the_plans_five() -> None:
    reference = rca.Reference(attempts=(attempt(), attempt(scenario_id="cart-redis-misconfig")))

    assert f"of {rca.TARGET_SCENARIOS}" in "\n".join(reference.render())
    assert rca.TARGET_SCENARIOS == 5


# --- the clock is wall-clock, not a number typed afterwards -----------------------------------


def cli_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--ledger",
        str(tmp_path / "attempts.jsonl"),
        "--clock",
        str(tmp_path / "clock.json"),
        *extra,
    ]


def test_the_duration_is_measured_between_start_and_finish(tmp_path: Path) -> None:
    """**Not a number typed in afterwards.** A self-reported duration is a memory of a duration,
    and the difference between the two runs in exactly the direction that flatters the person
    reporting it."""
    from evalharness import manual_rca_cli as cli

    assert cli.run(cli_args(tmp_path, "--start", "ad-memory-squeeze")) == 0
    assert (
        cli.run(
            cli_args(
                tmp_path,
                "--finish",
                "ad-memory-squeeze",
                "--fault-class",
                "resource_exhaustion",
                "--service",
                "adservice",
            )
        )
        == 0
    )

    recorded = rca.load(tmp_path / "attempts.jsonl")
    assert len(recorded) == 1
    assert recorded[0].elapsed_seconds > 0
    assert not (tmp_path / "clock.json").exists(), "the clock is cleared"


def test_two_clocks_at_once_are_refused(tmp_path: Path) -> None:
    """Two timers running means neither is a duration."""
    from evalharness import manual_rca_cli as cli

    cli.run(cli_args(tmp_path, "--start", "a"))

    assert cli.run(cli_args(tmp_path, "--start", "b")) == 3


def test_finishing_a_scenario_that_is_not_being_timed_is_refused(tmp_path: Path) -> None:
    from evalharness import manual_rca_cli as cli

    cli.run(cli_args(tmp_path, "--start", "a"))

    assert cli.run(cli_args(tmp_path, "--finish", "b", "--fault-class", "bad_config")) == 3


def test_giving_up_is_a_first_class_outcome(tmp_path: Path) -> None:
    """Not a failure to use the tool. An abandoned investigation is data about difficulty."""
    from evalharness import manual_rca_cli as cli

    cli.run(cli_args(tmp_path, "--start", "cart-bad-image-tag"))
    code = cli.run(cli_args(tmp_path, "--give-up", "cart-bad-image-tag", "--notes", "stuck"))

    recorded = rca.load(tmp_path / "attempts.jsonl")
    assert code == 0
    assert recorded[0].gave_up is True
    assert recorded[0].elapsed_seconds > 0, "an abandoned attempt is still timed"


def test_a_refused_record_leaves_the_clock_running(tmp_path: Path) -> None:
    """**Discarding the elapsed time would make the operator start again** — and time a second,
    shorter investigation of a scenario they have now already looked at."""
    from evalharness import manual_rca_cli as cli

    cli.run(cli_args(tmp_path, "--start", "a"))
    code = cli.run(cli_args(tmp_path, "--finish", "a"))  # no fault class

    assert code == 3
    assert (tmp_path / "clock.json").exists(), "the clock survives the refusal"
