"""`faultline-judge`'s selection and its cost line.

Both defects here were found by running the command, not by reading it. The pass had been green
for weeks; its default target was every scored run on disk, and its cost line billed a Haiku judge
at Opus rates. Neither is reachable from a unit test of `judge_run`, because neither is in
`judge_run`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evalharness.judge import JudgeSettings, JudgeUnconfiguredError, prices
from evalharness.judge_cli import already_judged, parser, run


def write_run(
    root: Path,
    run_id: str,
    *,
    scenario_id: str = "cart-redis-misconfig",
    narrative: str | None = "The cart service held a wrong Redis address.",
    judge: dict[str, Any] | None = None,
) -> Path:
    """A run directory shaped the way `load_run` needs it."""
    directory = root / run_id
    directory.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "score": {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "models": {"synthesizer": "claude-opus-5"},
            "categories": {},
        }
    }
    if judge is not None:
        manifest["judge"] = judge
    (directory / "manifest.json").write_text(json.dumps(manifest))
    if narrative is not None:
        (directory / "abc-narrative.md").write_text(narrative)
    return directory


# --- the guard -----------------------------------------------------------------


def test_a_run_carrying_a_judge_block_counts_as_judged() -> None:
    assert already_judged({"judge": {"root_cause_agreement": "adjacent"}}) is True


def test_a_judge_block_that_records_a_non_scoring_still_counts() -> None:
    """**Being through the pass is the property, not having a grade.** A refused narrative has an
    outcome on disk, and going again would overwrite a recorded fact."""
    assert (
        already_judged({"judge": {"scored": False, "not_scored_because": "no narrative"}}) is True
    )


def test_an_unjudged_run_is_not_skipped() -> None:
    assert already_judged({"score": {}}) is False
    assert already_judged({"score": {}, "judge": {}}) is False


def test_the_default_pass_leaves_an_already_judged_run_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The regression that matters.** With no run ids, this command selected all 79 judged runs
    and rewrote every one. No model is configured here, and the point is that it never gets far
    enough to need one."""
    monkeypatch.delenv("FAULTLINE_JUDGE_MODEL", raising=False)
    graded = {"root_cause_agreement": "same_mechanism", "judge_model": "claude-haiku-4-5"}
    write_run(tmp_path, "20260904T000000Z-cart-redis-misconfig", judge=graded)

    assert run(["--runs-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "already carry a judge block" in out
    assert "every selected run is already judged" in out

    kept = json.loads(
        (tmp_path / "20260904T000000Z-cart-redis-misconfig/manifest.json").read_text()
    )
    assert kept["judge"] == graded


def test_naming_a_judged_run_explicitly_does_not_bypass_the_guard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard is on the manifest, not the argument list. Re-running a command out of shell
    history names run ids explicitly, and that is exactly the accident."""
    monkeypatch.delenv("FAULTLINE_JUDGE_MODEL", raising=False)
    write_run(tmp_path, "20260904T000000Z-cart-redis-misconfig", judge={"scored": True})

    assert run(["--runs-root", str(tmp_path), "20260904T000000Z-cart-redis-misconfig"]) == 0
    assert "every selected run is already judged" in capsys.readouterr().out


def test_rejudge_is_a_flag_that_must_be_typed() -> None:
    assert parser().parse_args([]).rejudge is False
    assert parser().parse_args(["--rejudge"]).rejudge is True


def test_an_unjudged_run_still_reaches_the_configuration_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must not swallow a run that has work to do: an unset model still refuses."""
    monkeypatch.delenv("FAULTLINE_JUDGE_MODEL", raising=False)
    write_run(tmp_path, "20260904T000000Z-cart-redis-misconfig")

    assert run(["--runs-root", str(tmp_path)]) == 3
    assert "no judge model is set" in capsys.readouterr().out


# --- the preview ---------------------------------------------------------------


def test_the_dry_run_says_a_narrativeless_run_will_not_be_judged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cart-bad-image-tag` printed "would judge" and then recorded "NOT JUDGED". `judge_run`
    short-circuits on a missing narrative; the preview checked only `narrative_refused`."""
    monkeypatch.setenv("FAULTLINE_JUDGE_MODEL", "some-other-vendor-model")
    monkeypatch.setenv("FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE", "1")
    write_run(tmp_path, "20260904T000000Z-cart-bad-image-tag", narrative=None)

    assert run(["--runs-root", str(tmp_path), "--dry-run"]) == 0
    assert "NO NARRATIVE" in capsys.readouterr().out


# --- the price -----------------------------------------------------------------


def test_an_unset_price_is_unset_not_the_agents() -> None:
    assert prices("") is None
    assert prices("   ") is None
    assert JudgeSettings.from_env({}).usd_per_mtok is None


def test_a_stated_price_is_read_as_in_then_out() -> None:
    assert prices("1,5") == (1.0, 5.0)
    assert JudgeSettings.from_env({"FAULTLINE_JUDGE_USD_PER_MTOK": "0.8,4"}).usd_per_mtok == (
        0.8,
        4.0,
    )


@pytest.mark.parametrize("raw", ["1", "1,2,3", "cheap,free", "1,"])
def test_a_malformed_price_refuses_rather_than_reading_as_unset(raw: str) -> None:
    """Falling back to `None` would print the same line as a price nobody set, and the operator
    who did set one would read it as proof the judge is free."""
    with pytest.raises(JudgeUnconfiguredError) as refusal:
        prices(raw)
    assert "FAULTLINE_JUDGE_USD_PER_MTOK" in str(refusal.value)


def test_a_negative_price_refuses() -> None:
    with pytest.raises(JudgeUnconfiguredError):
        prices("-1,5")


def test_the_cost_line_is_not_hard_coded_to_the_agents_rates() -> None:
    """The literal regression: `tokens_in/1e6*5 + tokens_out/1e6*25` beside a Haiku judge.

    Read as source rather than as prose - the module's docstring quotes those very numbers while
    explaining why they were wrong, and a substring check would fail on the explanation. This is
    the technique ADR-0032 settled after three instances of exactly that mistake.
    """
    import ast
    import inspect

    import evalharness.judge_cli as cli

    tree = ast.parse(inspect.getsource(cli.run))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float)
    }
    assert 25 not in literals, "the agent's output rate is hard-coded in the judging pass again"
