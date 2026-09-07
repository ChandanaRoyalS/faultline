"""What `make demo` says about the verdict and the proposal (T5.3, audited under T5.6).

`evalharness.demo` had no tests. The one bug that let through was found by reading the recorded
transcript: every demo ever run printed `Class of fix: None`, because the narration read a key
(`class_of_fix`) that no verdict has ever had. The artifact beside it named the class correctly
the whole time. These tests read real artifacts, so the narration is held to the shape the
harness writes rather than to a shape a test invented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalharness import demo

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "evals" / "runs"


def _artifacts() -> list[Path]:
    return sorted(RUNS.glob("*/*-verdict.json"))


def _narration(capsys: pytest.CaptureFixture[str], run_dir: Path, incident_id: str) -> str:
    demo.verdict_story(run_dir, incident_id)
    return capsys.readouterr().out


def test_the_class_of_fix_line_prints_the_field_the_verdict_actually_has(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Against every committed artifact whose verdict names a class. `None` is what the bug
    printed; it must never appear against a verdict that carries a value."""
    checked = 0
    for artifact in _artifacts():
        verdict = json.loads(artifact.read_text()).get("verdict") or {}
        remediation = verdict.get("remediation_class")
        if not remediation:
            continue
        incident_id = artifact.name.removesuffix("-verdict.json")
        out = _narration(capsys, artifact.parent, incident_id)
        assert f"Class of fix: {remediation}" in out, artifact
        assert "Class of fix: None" not in out, artifact
        checked += 1
    assert checked > 0, "no committed artifact names a remediation class; the test checked nothing"


def test_the_proposal_is_narrated_with_its_risk_note_and_the_not_executed_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """*"Remediation as proposal"* is a beat of the specification's video, and the artifact has
    carried the proposal since T3.9. The narration stopped at the verdict. Now it reads the
    proposal out - action, target, expected effect, falsifier, risk, blast radius - and closes by
    saying nothing was executed, because nothing can be until Gate 6 builds the plane."""
    checked = 0
    for artifact in _artifacts():
        proposal = json.loads(artifact.read_text()).get("proposal") or {}
        if not proposal.get("action_id"):
            continue
        incident_id = artifact.name.removesuffix("-verdict.json")
        out = _narration(capsys, artifact.parent, incident_id)
        assert "THE PROPOSAL" in out, artifact
        assert f"Action      : {proposal['action_id']} on {proposal['target']}" in out, artifact
        assert f"Class       : {proposal['remediation_class']}" in out, artifact
        if proposal.get("risk"):
            assert "Risk:" in out, artifact
        assert "Nothing above was executed" in out, artifact
        checked += 1
    assert checked > 0, "no committed artifact carries a proposal; the test checked nothing"


def test_an_abstaining_proposal_is_narrated_as_an_abstention(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`remediation_class: none` with no action is a legal, complete output (ADR-0028 §4). It is
    said, not skipped - a watcher who hears nothing cannot tell abstention from a crash."""
    demo.proposal_story({"remediation_class": "none", "action_id": "", "target": "", "risk": ""})

    out = capsys.readouterr().out

    assert "THE PROPOSAL" in out and "abstained" in out
    assert "Action      :" not in out


def test_no_proposal_prints_no_section(capsys: pytest.CaptureFixture[str]) -> None:
    demo.proposal_story(None)
    demo.proposal_story({})

    assert "THE PROPOSAL" not in capsys.readouterr().out


def test_a_missing_artifact_is_silent_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A discarded run has no verdict artifact; the demo already told the watcher why."""
    demo.verdict_story(tmp_path, "nobody")

    assert capsys.readouterr().out == ""


def test_the_narration_reads_no_key_the_verdict_does_not_have() -> None:
    """The structural half of the bug: every `verdict.get('<key>')` in the narration must be a
    field of the `Verdict` contract. `class_of_fix` was not, and nothing said so."""
    import inspect
    import re

    from faultline.agents.contracts import Verdict

    source = inspect.getsource(demo.verdict_story)
    keys = set(re.findall(r"verdict\.get\(\s*['\"]([a-z_]+)['\"]", source))
    assert keys, "the narration reads the verdict somewhere"
    assert keys <= set(Verdict.model_fields), keys - set(Verdict.model_fields)
