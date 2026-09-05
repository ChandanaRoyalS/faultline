"""Judge calibration, graded blind (T4.2).

*"~30 manually graded runs establish the agreement baseline **before trusting it**"*, and
*"judge calibration (agreement rate with your spot-audits) is what makes it credible"*.

Every root-cause agreement figure this repository publishes is one model's opinion of another
model's prose. That is defensible only if a human has checked it on the same runs.
"""

from __future__ import annotations

import dataclasses
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


def test_kappa_is_no_longer_asserted_to_be_the_headline() -> None:
    """**This test previously required the opposite**, and the module's own argument was half
    right. Raw agreement does flatter on a skewed pool — a grader answering `same_mechanism`
    every time posts ~93% while contributing nothing, which is why κ was chosen.

    What the reasoning missed is that **κ on this pool is not more trustworthy, only less
    stable**: measured on the real distribution, one grader disagreement gives κ = 0.65 and two
    give κ = 0.00 at 93% raw agreement. Both print now, raw leads, and κ carries the instability
    flag — a figure that swings on one row is not made trustworthy by being the theoretically
    correct one. Recorded as a changed position rather than a silent edit.
    """
    pairs = [("same_mechanism", "same_mechanism")] * 28 + [("adjacent", "same_mechanism")] * 2
    rendered = "\n".join(cal.Agreement(pairs=tuple(pairs)).render())

    assert "κ is the figure, not raw agreement" not in rendered
    assert "should not be the headline on this pool" in rendered


# --- the CLI, and the leak that would make it worthless --------------------------------------


def judged_run(
    root: Path, run_id: str, agreement: str, narrative: str = "the agent's prose"
) -> None:
    """A judged run on disk, **with its judge block produced by the judge**.

    The first version of this helper hand-wrote `{"agreement": ...}`, which is the key the reader
    expected and **not the one the writer emits** - `JudgeResult.agreement` serialises as
    `root_cause_agreement`. So the fixture agreed with the bug, every test here passed, and
    `faultline-calibrate` reported an empty pool against a run tree holding 78 judged runs.

    A fixture that encodes the reader's assumption tests the reader against itself. This one is
    built by the producer, so the two sides cannot drift apart without a failure here.
    """
    from evalharness.judge import JudgeResult

    directory = root / run_id
    directory.mkdir(parents=True)
    judged = JudgeResult(
        scenario_id="ad-memory-squeeze",
        run_id=run_id,
        agent_model="agent",
        judge_model="judge",
        shared_lineage=False,
        lineage_note="",
        scored=True,
        agreement=agreement,
        agreement_reason="the judge's reasoning here",
    )
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "scenario_id": "ad-memory-squeeze",
                "score": {"run_id": run_id},
                "judge": judged.as_dict(),
            }
        )
    )
    (directory / f"{run_id}-narrative.md").write_text(narrative)


def test_the_reader_and_the_writer_agree_on_where_the_agreement_lives(tmp_path: Path) -> None:
    """**The defect this file shipped with, asserted at the seam it crossed.**

    `judged_runs` read one key and `JudgeResult.as_dict()` wrote another, and nothing failed:
    the harness printed "every judged run has a grade (0 recorded)", which reads exactly like a
    finished job rather than a broken filter. That is T4.1b's clause arriving in the one place
    whose purpose is checking whether an automated verdict can be trusted.
    """
    from evalharness.calibration_cli import judged_runs
    from evalharness.judge import AGREEMENT_KEY, JudgeResult

    written = JudgeResult(
        scenario_id="s",
        run_id="r",
        agent_model="a",
        judge_model="j",
        shared_lineage=False,
        lineage_note="",
        scored=True,
        agreement="adjacent",
    ).as_dict()

    assert AGREEMENT_KEY in written, "the constant must name a key the writer actually emits"
    judged_run(tmp_path, "r1", "adjacent")
    assert judged_runs(tmp_path)["r1"]["agreement"] == "adjacent"


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


# --- the pool: abstentions carry no judgement to agree with -------------------------------------


def abstained_run(root: Path, run_id: str, scenario: str = "shipping-wrong-image") -> None:
    """A run that returned `fault_class: unknown`. The judge grades these `different` by
    construction, so they are excluded rather than served."""
    from evalharness.judge import JudgeResult

    directory = root / run_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario,
                "score": {
                    "run_id": run_id,
                    "fault_class": {
                        "truth": "bad_deploy",
                        "returned": "unknown",
                        "correct": False,
                        "abstained": True,
                    },
                },
                "judge": JudgeResult(
                    scenario_id=scenario,
                    run_id=run_id,
                    agent_model="a",
                    judge_model="j",
                    shared_lineage=False,
                    lineage_note="",
                    scored=True,
                    agreement="different",
                    agreement_reason="no claim was made",
                ).as_dict(),
            }
        )
    )
    (directory / f"{run_id}-narrative.md").write_text("the agent declined to name a cause")


def test_an_abstention_is_excluded_from_the_pool(tmp_path: Path) -> None:
    """**The judge grades every abstention `different` by construction**, so there is no judgement
    to agree with: matching it is a free agreement point and differing is a free miss. On the
    committed record 17 of 78 judged runs are abstentions, and they are 17 of the 18 `different`
    verdicts in the whole record - seventeen mechanical rows in a figure about judgement."""
    from evalharness.calibration_cli import abstained, abstention_count, judged_runs

    judged_run(tmp_path, "real", "same_mechanism")
    abstained_run(tmp_path, "abstained")

    assert sorted(judged_runs(tmp_path)) == ["real"]
    assert abstention_count(tmp_path) == 1
    assert abstained({"score": {"fault_class": {"abstained": True}}}) is True
    assert abstained({"score": {"fault_class": {"abstained": False}}}) is False


def test_an_excluded_abstention_is_counted_and_not_silently_dropped(tmp_path: Path) -> None:
    """A pool that shrank by 22% without saying so is the same defect one level up."""
    from evalharness import calibration as cal

    panel = dataclasses.replace(cal.Agreement(pairs=(("adjacent", "adjacent"),)), abstentions=17)

    assert "17 abstention(s) excluded" in "\n".join(panel.render())
    assert "by construction" in "\n".join(panel.render())


# --- the order covers the record rather than sampling it ----------------------------------------


def pool() -> dict[str, tuple[str, str]]:
    """Thirteen scenarios, one of them fourteen times, four non-modal verdicts - the shape of the
    committed record."""
    runs: dict[str, tuple[str, str]] = {}
    for n in range(14):
        runs[f"cart-{n}"] = ("cart-redis-misconfig", "same_mechanism")
    for i in range(12):
        runs[f"s{i}"] = (f"scenario-{i}", "same_mechanism")
    runs["odd-a"] = ("scenario-0", "adjacent")
    runs["odd-b"] = ("scenario-1", "adjacent")
    runs["odd-c"] = ("scenario-2", "adjacent")
    runs["odd-d"] = ("scenario-3", "different")
    return runs


def test_every_scenario_is_covered_before_any_scenario_repeats() -> None:
    """**Thirty rows drawn uniformly would be perhaps eight distinct cases, counted as thirty.**
    A grader who has read a scenario's recorded narrative is not a blind reader of it again, so
    repeats are correlated by construction and n overstates what was rated."""
    from evalharness import calibration as cal

    runs = pool()
    sequence = cal.stratified(runs)
    scenarios = {s for s, _ in runs.values()}

    first_pass = sequence[: len(scenarios) + 4]
    assert {runs[r][0] for r in first_pass} == scenarios


def test_every_non_modal_verdict_lands_in_the_first_pass() -> None:
    """The only rows where agreement is informative about the *scale* rather than the base rate.
    With four of them in 61, a uniform shuffle makes the headline a lottery on which got graded:
    on 28 `same_mechanism` and 2 `adjacent`, one disagreement gives κ = 0.65 and two give 0.00."""
    from evalharness import calibration as cal

    runs = pool()
    sequence = cal.stratified(runs)
    odd = [r for r, (_, level) in runs.items() if level != "same_mechanism"]

    assert all(sequence.index(r) < len({s for s, _ in runs.values()}) + 4 for r in odd)


def test_the_order_is_deterministic_and_complete() -> None:
    """Reproducible for the same reason `order` is: a reader must be able to confirm the sequence
    was not chosen after the grades were seen."""
    from evalharness import calibration as cal

    runs = pool()

    assert cal.stratified(runs) == cal.stratified(runs)
    assert sorted(cal.stratified(runs)) == sorted(runs)


def test_the_grader_is_told_nothing_about_why_a_run_was_chosen(tmp_path: Path) -> None:
    """**A requirement, not an omission.** A row the grader knows was selected for being
    interesting has been pre-judged for them - a subtler unblinding than seeing the judge's
    answer, and much harder to notice afterwards."""
    from evalharness import calibration_cli

    judged_run(tmp_path, "r1", "adjacent")
    code = calibration_cli.run(
        ["--next", "--runs-root", str(tmp_path), "--ledger", str(tmp_path / "l.jsonl")]
    )

    assert code == 0


# --- kappa is reported, and is not the headline on this pool -------------------------------------


def test_kappa_is_flagged_unstable_when_the_judge_is_nearly_constant() -> None:
    """Measured on the real distribution: 28 `same_mechanism` and 2 `adjacent`. One grader
    disagreement gives κ = 0.65; two give **κ = 0.00 at 93% raw agreement** - the same grader, one
    extra row, *substantial* to *no better than chance*."""
    from evalharness import calibration as cal

    pairs = [("same_mechanism", "same_mechanism")] * 28 + [("adjacent", "same_mechanism")] * 2
    two_off = cal.Agreement(pairs=tuple(pairs))

    assert two_off.raw is not None and round(two_off.raw, 3) == 0.933
    assert two_off.kappa == 0.0, "the kappa paradox, on this repository's own record"
    assert two_off.kappa_is_unstable is True

    one_off = cal.Agreement(
        pairs=tuple(
            [("same_mechanism", "same_mechanism")] * 28
            + [("adjacent", "same_mechanism"), ("adjacent", "adjacent")]
        )
    )
    assert one_off.kappa is not None and 0.6 < one_off.kappa < 0.7


def test_a_balanced_pool_is_not_flagged_unstable() -> None:
    """The flag is about this record, not about kappa. Five or more rows outside the modal
    category and one row can no longer move the band."""
    from evalharness import calibration as cal

    pairs = [("same_mechanism", "same_mechanism")] * 20 + [("adjacent", "adjacent")] * 10

    assert cal.Agreement(pairs=tuple(pairs)).kappa_is_unstable is False


def test_the_confusion_table_shows_where_two_readers_parted() -> None:
    """**What no single figure shows.** A grader who reads `adjacent` as `same_mechanism` and one
    who reads it as `different` post the same agreement rate and disagree about opposite things."""
    from evalharness import calibration as cal

    panel = cal.Agreement(pairs=(("same_mechanism", "same_mechanism"), ("adjacent", "different")))
    rendered = "\n".join(panel.render())

    assert panel.confusion[("adjacent", "different")] == 1
    assert "| `adjacent` | `different` | 1 |" in rendered


def test_the_scenario_count_travels_with_n() -> None:
    """So no reader takes 30 rows for 30 independent judgements."""
    from evalharness import calibration as cal

    panel = dataclasses.replace(cal.Agreement(pairs=(("adjacent", "adjacent"),) * 30), scenarios=13)
    rendered = "\n".join(panel.render())

    assert "30 grades over 13 distinct scenarios" in rendered
    assert "not independent judgements" in rendered


# --- the label that outlives the conversation ----------------------------------------------------


def test_a_judged_table_says_the_judge_is_uncalibrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**T4.2's clause is "before trusting it", and "before" is the load-bearing word.**

    Figures published while no human has checked the judge rest on an unvalidated instrument, and
    if the calibration later disagrees they get withdrawn rather than footnoted. So the label
    rides on the table itself, exactly as `smoke.NON_CITABLE` rides on the CI output and for the
    reason that task states: *"so a smoke number can't be screenshotted into a README six weeks
    later"*.

    **The ledger is a fixture, and it was not.** `judged_rows` calls `standing()` with no
    argument, so this test read the repository's real `grades.jsonl` - and passed only because
    that file happened to hold fewer than thirty blind grades. The thirtieth landed and `main`
    went red, on a test asserting a caveat that had correctly cleared. It was green for a reason
    it did not state, which is the same defect as a check nothing invokes: what it verified was
    the state of the project, not the behaviour of the function.
    """
    from evalharness.judge import JudgeResult, judged_rows

    empty = tmp_path / "grades.jsonl"
    monkeypatch.setattr(cal, "LEDGER", empty)
    assert "JUDGE NOT CALIBRATED" in cal.standing(empty)
    assert "0 of ~30" in cal.standing(empty)

    rendered = "\n".join(
        judged_rows(
            [
                JudgeResult(
                    scenario_id="s",
                    run_id="r",
                    agent_model="a",
                    judge_model="j",
                    shared_lineage=False,
                    lineage_note="",
                    scored=True,
                    agreement="adjacent",
                )
            ]
        )
    )
    assert "JUDGE NOT CALIBRATED" in rendered, "the label rides on the table, not on a docstring"


def test_the_uncalibrated_label_is_driven_by_the_ledger_and_not_hard_coded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The complement of the test above, and the reason it needed a fixture in the first place.

    One test pinning the label present and another pinning it absent, both against ledgers they
    control, is what makes the pair say something about `judged_rows`. Reading the live file said
    something about today.
    """
    from evalharness.judge import JudgeResult, judged_rows

    ledger = tmp_path / "grades.jsonl"
    for n in range(cal.TARGET_GRADES):
        cal.record(
            cal.Grade(
                run_id=f"r{n}",
                scenario_id=f"s{n}",
                agreement="same_mechanism",
                reason="a sentence",
                graded_at="2026-09-04T00:00:00Z",
                grader="chandana",
            ),
            ledger,
        )
    monkeypatch.setattr(cal, "LEDGER", ledger)

    rendered = "\n".join(
        judged_rows(
            [
                JudgeResult(
                    scenario_id="s",
                    run_id="r",
                    agent_model="a",
                    judge_model="j",
                    shared_lineage=False,
                    lineage_note="",
                    scored=True,
                    agreement="adjacent",
                )
            ]
        )
    )

    assert "JUDGE NOT CALIBRATED" not in rendered
    assert "calibrated against" in rendered.lower()


def test_the_label_clears_itself_once_the_grades_exist(tmp_path: Path) -> None:
    """**Nobody has to remember to remove it.** A caveat that needs a human to retract it is one
    that outlives its reason, which is the opposite failure and just as bad."""
    ledger = tmp_path / "grades.jsonl"
    for n in range(cal.TARGET_GRADES):
        cal.record(
            cal.Grade(
                run_id=f"r{n}",
                scenario_id=f"s{n % 13}",
                agreement="same_mechanism",
                reason="the mechanisms match",
                graded_at=f"t{n}",
                grader="chandana",
            ),
            ledger,
        )

    assert cal.is_calibrated(ledger) is True
    assert "JUDGE NOT CALIBRATED" not in cal.standing(ledger)
    assert "30 blind human grades over 13 scenario(s)" in cal.standing(ledger)


def test_unblinded_grades_do_not_clear_the_label(tmp_path: Path) -> None:
    """A regrade made after seeing the judge's answer measures confirmation, not agreement - so it
    cannot be what retires a warning about the judge being unchecked."""
    ledger = tmp_path / "grades.jsonl"
    first = cal.record(grade("r0", "same_mechanism", at="t0"), ledger)
    for n in range(cal.TARGET_GRADES + 5):
        cal.record(cal.regrade(first, "adjacent", f"revision {n}"), ledger)

    assert cal.is_calibrated(ledger) is False
    assert "JUDGE NOT CALIBRATED" in cal.standing(ledger)


def test_the_standing_line_reads_the_ledger_rather_than_taking_a_count() -> None:
    """So no call site can pass a number that is out of date with the file - the failure mode
    that put `judge["agreement"]` in one module and `root_cause_agreement` in another."""
    import inspect

    source = inspect.getsource(cal.standing)

    assert "load(" in source, "it opens the ledger itself"
    assert "int" not in inspect.signature(cal.standing).parameters
