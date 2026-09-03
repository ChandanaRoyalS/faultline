"""Judge calibration, graded blind (T4.2).

*"~30 manually graded runs establish the agreement baseline **before trusting it**"*, and
*"judge calibration (agreement rate with your spot-audits) is what makes it credible"*.

Every root-cause agreement figure this repository publishes is one model's opinion of another
model's prose. That is defensible only if a human has checked it on the same runs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evalharness import calibration as cal


def grade(run_id: str, level: str, blind: bool = True, at: str = "") -> cal.Grade:
    return cal.Grade(
        run_id=run_id,
        scenario_id="ad-memory-squeeze",
        agreement=level,
        reason="the narrative names the limit cut",
        graded_at=at or datetime.now(UTC).isoformat(),
        grader="chandana",
        blind=blind,
    )


# --- blind is the whole design ----------------------------------------------------------------


def test_the_grading_order_is_shuffled_and_never_chronological() -> None:
    """**Run directories sort by time, so chronological order is generation order.** A grader who
    can tell they are working forwards through the project's history has been told something about
    each run before reading it."""
    ids = [f"2026090{n}T000000Z-scenario" for n in range(1, 10)]

    shuffled = cal.order(ids)

    assert shuffled != ids, "chronological order leaks the generation"
    assert sorted(shuffled) == sorted(ids), "every run still appears exactly once"


def test_the_order_is_reproducible_so_it_cannot_have_been_chosen_afterwards() -> None:
    """Reproducible matters more than random: a reader should be able to confirm the order was not
    picked once the grades were in."""
    ids = [f"run-{n}" for n in range(20)]

    assert cal.order(ids) == cal.order(ids)


def test_the_next_run_is_one_nobody_has_graded() -> None:
    ids = [f"run-{n}" for n in range(5)]
    done = [grade(run_id, "same_mechanism") for run_id in cal.order(ids)[:2]]

    nxt = cal.next_ungraded(ids, done)

    assert nxt is not None
    assert nxt not in {g.run_id for g in done}
    assert nxt == cal.order(ids)[2], "and it is next in the shuffled order, not the sorted one"


def test_grading_is_finished_when_every_run_has_a_standing_grade() -> None:
    ids = ["a", "b"]
    done = [grade("a", "same_mechanism"), grade("b", "adjacent")]

    assert cal.next_ungraded(ids, done) is None


# --- the ledger is append-only -----------------------------------------------------------------


def test_a_grade_is_appended_and_never_overwritten(tmp_path: Path) -> None:
    """ADR-0022 §3.3's discipline applied to grading: a grade that can be edited in place is a
    grade whose history is unrecoverable, and the interesting case - a grader changing their mind
    after the reveal - is exactly the one an overwrite would erase."""
    ledger = tmp_path / "grades.jsonl"

    cal.record(grade("run-1", "same_mechanism", at="t1"), ledger)
    cal.record(grade("run-1", "adjacent", at="t2"), ledger)

    loaded = cal.load(ledger)
    assert len(loaded) == 2, "both records survive"
    assert cal.current(loaded)["run-1"].agreement == "adjacent", "the last one stands"


def test_a_regrade_is_a_second_record_that_is_not_blind(tmp_path: Path) -> None:
    """A changed mind after the reveal is informative - it may say the rubric is ambiguous - and
    erasing it would make the ledger claim a confidence the grading did not have."""
    ledger = tmp_path / "grades.jsonl"
    first = cal.record(grade("run-1", "same_mechanism", at="t1"), ledger)

    revised = cal.record(
        cal.regrade(first, "adjacent", "on reflection the mechanism differs"), ledger
    )

    assert revised.blind is False
    assert revised.supersedes == "t1"
    assert len(cal.load(ledger)) == 2


def test_a_grade_outside_the_judges_scale_is_refused() -> None:
    """Two raters using different vocabularies disagree about the vocabulary, not about the run."""
    with pytest.raises(cal.InvalidGradeError):
        cal.record(grade("run-1", "mostly_right"))


def test_a_grade_with_no_reason_is_refused() -> None:
    """The same purpose `Candidate.why_not` serves: a verdict with no stated basis cannot be
    argued with, and the point of a human audit is that it can be."""
    blank = cal.Grade(
        run_id="r",
        scenario_id="s",
        agreement="adjacent",
        reason="   ",
        graded_at="t",
    )

    with pytest.raises(cal.InvalidGradeError):
        cal.record(blank)


# --- raw agreement is the wrong headline, and the record shows why ----------------------------


def test_a_grader_who_always_says_the_same_thing_scores_high_raw_and_kappa_of_nothing() -> None:
    """**The finding this module exists to pre-empt.**

    The judged record is 15 `same_mechanism`, 3 `adjacent`, 1 `different`. A grader contributing
    nothing at all - answering `same_mechanism` every time - posts a high raw agreement. A headline
    of "79% agreement with human audit" would be a number produced by a constant function.
    """
    judged = {f"r{n}": "same_mechanism" for n in range(15)}
    judged.update({f"r{n}": "adjacent" for n in range(15, 18)})
    judged["r18"] = "different"
    constant = [grade(run_id, "same_mechanism") for run_id in judged]

    result = cal.agreement(judged, constant)

    assert result.raw is not None and result.raw > 0.75, "raw looks respectable"
    assert result.kappa == 0.0, "and kappa says the grader added nothing"
    assert "slight" in result.interpretation()


def test_a_grader_who_tracks_the_judge_scores_a_high_kappa() -> None:
    judged = {"a": "same_mechanism", "b": "adjacent", "c": "different", "d": "same_mechanism"}
    tracking = [grade(run_id, level) for run_id, level in judged.items()]

    result = cal.agreement(judged, tracking)

    assert result.raw == 1.0
    assert result.kappa == 1.0
    assert result.interpretation() == "almost perfect"


def test_systematic_disagreement_is_reported_as_worse_than_chance() -> None:
    judged = {"a": "same_mechanism", "b": "same_mechanism", "c": "adjacent", "d": "adjacent"}
    inverted = {"a": "adjacent", "b": "adjacent", "c": "same_mechanism", "d": "same_mechanism"}
    grades = [grade(run_id, level) for run_id, level in inverted.items()]

    result = cal.agreement(judged, grades)

    assert result.kappa is not None and result.kappa < 0
    assert "worse than chance" in result.interpretation()


def test_one_category_on_both_sides_is_undefined_rather_than_perfect() -> None:
    """**Returning 1.0 here would report a constant function as a calibrated instrument**, which
    is the specific failure this module was written to avoid."""
    judged = {"a": "same_mechanism", "b": "same_mechanism"}
    grades = [grade("a", "same_mechanism"), grade("b", "same_mechanism")]

    result = cal.agreement(judged, grades)

    assert result.raw == 1.0
    assert result.kappa is None
    assert "not a perfect score" in result.interpretation()


# --- what enters the figure --------------------------------------------------------------------


def test_an_unblinded_regrade_is_excluded_from_the_figure_and_counted() -> None:
    """A grade made after seeing the judge's answer measures confirmation, not agreement - a
    different and much higher number that looks identical in the output."""
    judged = {"a": "same_mechanism", "b": "adjacent"}
    grades = [grade("a", "same_mechanism"), grade("b", "adjacent", blind=False)]

    result = cal.agreement(judged, grades)

    assert result.n == 1
    assert result.unblinded == 1
    assert "measures confirmation" in "\n".join(result.render())


def test_a_run_the_judge_never_scored_does_not_enter_the_figure() -> None:
    result = cal.agreement(
        {"a": "same_mechanism"}, [grade("a", "same_mechanism"), grade("z", "adjacent")]
    )

    assert result.n == 1


def test_no_grades_yet_renders_as_none_recorded_rather_than_as_a_number() -> None:
    rendered = "\n".join(cal.agreement({}, []).render())

    assert "No blind grades recorded yet" in rendered
    assert "%" not in rendered, "no percentage may appear when nothing was graded"


def test_the_panel_reports_progress_against_the_plans_target() -> None:
    """T4.2 asks for ~30. A partial calibration is a real result, and refusing to print one below
    the target would hide the state the project is actually in."""
    judged = {f"r{n}": "same_mechanism" for n in range(4)}
    judged["r4"] = "adjacent"
    grades = [grade(run_id, level) for run_id, level in judged.items()]

    rendered = "\n".join(cal.agreement(judged, grades).render())

    assert f"of ~{cal.TARGET_GRADES} runs graded blind" in rendered
    assert "5 of" in rendered


def test_the_panel_never_claims_the_judge_is_right() -> None:
    """Judge and grader can agree and both be wrong - and on a benchmark whose reference narrative
    that same human wrote, they share a prior by construction. It is the caveat most likely to be
    dropped when the figure is quoted, so it is in the rendered output rather than only here."""
    judged = {"a": "same_mechanism", "b": "adjacent"}
    rendered = "\n".join(
        cal.agreement(judged, [grade("a", "same_mechanism"), grade("b", "adjacent")]).render()
    )

    assert "does not say the judge is" in rendered.lower() or "share a prior" in rendered
    assert "κ is the figure, not raw agreement" in rendered


# --- the CLI, and the leak that would make it worthless --------------------------------------


def judged_run(
    root: Path, run_id: str, agreement: str, narrative: str = "the agent's prose"
) -> None:
    directory = root / run_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "scenario_id": "ad-memory-squeeze",
                "score": {"run_id": run_id},
                "judge": {"agreement": agreement, "agreement_reason": "the judge's reasoning here"},
            }
        )
    )
    (directory / f"{run_id}-narrative.md").write_text(narrative)


def test_next_shows_both_narratives_and_never_the_judges_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """**The one property this whole exercise depends on.**

    A harness that showed the judge's answer alongside the narratives would measure how often a
    person confirms a machine - a different and much higher number that looks identical in the
    output. It cannot be added later either: runs already graded unblinded would have to be
    discarded.
    """
    from evalharness import calibration_cli

    def blind_output(verdict: str, where: Path) -> str:
        runs = where / "runs"
        judged_run(runs, "20260903T000000Z-ad-memory-squeeze", verdict)
        calibration_cli.run(
            ["--next", "--runs-root", str(runs), "--ledger", str(where / "grades.jsonl")]
        )
        return capsys.readouterr().out

    adjacent = blind_output("adjacent", tmp_path / "a")
    different = blind_output("different", tmp_path / "b")

    assert "RECORDED NARRATIVE" in adjacent and "AGENT NARRATIVE" in adjacent
    # **The property, stated so it cannot be fooled.** Checking that a level's *name* is absent
    # is the wrong test - the rubric legitimately lists all three, and a first draft of this
    # assertion failed on exactly that. What must be true is that the blind view does not vary
    # with the verdict at all.
    assert adjacent == different, "the blind view changes with the judge's answer"
    assert "the judge's reasoning here" not in adjacent, "the judge's reasoning leaked"
    assert "the judge said" not in adjacent


def test_the_verdict_is_revealed_only_after_a_grade_is_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from evalharness import calibration_cli

    runs = tmp_path / "runs"
    ledger = tmp_path / "grades.jsonl"
    judged_run(runs, "r1", "adjacent")

    code = calibration_cli.run(
        [
            "--grade",
            "r1",
            "--level",
            "same_mechanism",
            "--reason",
            "it names the mechanism",
            "--runs-root",
            str(runs),
            "--ledger",
            str(ledger),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "the judge said: adjacent" in out
    assert "disagreed" in out
    assert "neither is corrected to match the other" in out
    assert len(cal.load(ledger)) == 1, "and the grade was written before the reveal"


def test_grading_the_same_run_twice_is_refused_and_points_at_regrade(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Re-grading after the reveal is the move that would quietly turn a calibration into a
    confirmation, so it needs a different flag and a different record."""
    from evalharness import calibration_cli

    runs = tmp_path / "runs"
    ledger = tmp_path / "grades.jsonl"
    judged_run(runs, "r1", "adjacent")
    common = ["--runs-root", str(runs), "--ledger", str(ledger)]

    calibration_cli.run(["--grade", "r1", "--level", "adjacent", "--reason", "r", *common])
    capsys.readouterr()
    code = calibration_cli.run(["--grade", "r1", "--level", "different", "--reason", "r", *common])
    out = capsys.readouterr().out

    assert code == 3
    assert "--regrade" in out


def test_a_regrade_is_written_not_blind_and_leaves_the_figure_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from evalharness import calibration_cli

    runs = tmp_path / "runs"
    ledger = tmp_path / "grades.jsonl"
    judged_run(runs, "r1", "adjacent")
    common = ["--runs-root", str(runs), "--ledger", str(ledger)]

    calibration_cli.run(["--grade", "r1", "--level", "same_mechanism", "--reason", "r", *common])
    calibration_cli.run(["--regrade", "r1", "--level", "adjacent", "--reason", "changed", *common])
    capsys.readouterr()

    loaded = cal.load(ledger)
    assert len(loaded) == 2
    assert cal.agreement({"r1": "adjacent"}, loaded).n == 0, "the standing grade is not blind"
    assert cal.agreement({"r1": "adjacent"}, loaded).unblinded == 1


def test_an_unjudged_run_cannot_be_calibrated_against(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run the judge never scored has nothing to disagree with, and counting it would invent a
    disagreement."""
    from evalharness import calibration_cli

    runs = tmp_path / "runs"
    runs.mkdir()
    code = calibration_cli.run(
        ["--grade", "nope", "--level", "adjacent", "--reason", "r", "--runs-root", str(runs)]
    )

    assert code == 3
    assert "no judged verdict" in capsys.readouterr().out


def test_a_run_with_no_judge_block_is_skipped_rather_than_counted(tmp_path: Path) -> None:
    from evalharness.calibration_cli import judged_runs

    runs = tmp_path / "runs"
    (runs / "unjudged").mkdir(parents=True)
    (runs / "unjudged" / "manifest.json").write_text(json.dumps({"score": {"run_id": "x"}}))
    judged_run(runs, "judged", "same_mechanism")

    assert sorted(judged_runs(runs)) == ["judged"]
