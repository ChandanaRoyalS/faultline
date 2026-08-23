"""Mechanical enforcement of the T1.6 contamination rules (ADR-0008, axis 1).

Axis 2 (run-time self-exclusion) is enforced at T4.1b, not here.

These tests are deliberately incremental: they pass on an empty catalog and tighten as
scenarios are authored, so they can land before T1.5 rather than after it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from evalharness.scenario import FaultClass, Scenario, Split

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "evals" / "scenarios"
ARTIFACT_DIR = SCENARIO_DIR / "artifacts"
SPLIT_DOC = SCENARIO_DIR / "SPLIT.md"

# Source of truth for machine checks. Mirrors evals/scenarios/SPLIT.md, and
# test_split_doc_matches_allocation asserts the two have not drifted.
# (fault class) -> (dev slots, holdout slots)
ALLOCATION: dict[FaultClass, tuple[int, int]] = {
    FaultClass.BAD_DEPLOY: (2, 1),
    FaultClass.DEPENDENCY_LATENCY: (1, 1),
    FaultClass.RESOURCE_EXHAUSTION: (2, 1),
    FaultClass.BAD_CONFIG: (2, 0),
}


def scenario_paths() -> list[Path]:
    """Every scored scenario file. The examples/ tree illustrates the schema and is excluded."""
    return sorted(
        p
        for p in SCENARIO_DIR.rglob("*.yaml")
        if "examples" not in p.parts and "artifacts" not in p.parts
    )


def catalog() -> list[Scenario]:
    return [Scenario.from_yaml(p) for p in scenario_paths()]


def test_every_scenario_validates() -> None:
    """A malformed scenario is a broken eval case, not a warning."""
    for path in scenario_paths():
        Scenario.from_yaml(path)  # raises on invalid


def test_scenario_ids_are_unique() -> None:
    ids = [s.id for s in catalog()]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"duplicate scenario ids: {sorted(duplicates)}"


def test_split_allocation_is_not_exceeded() -> None:
    """Authoring fills the committed slots. It may not invent new ones.

    Passes while the catalog is partially authored; the exact-match check below takes
    over once a class is full.
    """
    scenarios = catalog()
    for fault_class, (dev_slots, holdout_slots) in ALLOCATION.items():
        in_class = [s for s in scenarios if s.fault_class is fault_class]
        dev = sum(1 for s in in_class if s.split is Split.DEV)
        holdout = sum(1 for s in in_class if s.split is Split.HOLDOUT)
        assert dev <= dev_slots, (
            f"{fault_class}: {dev} dev scenarios authored, {dev_slots} slots allocated. "
            "Splits are committed before authoring (ADR-0008) - do not widen the table."
        )
        assert (
            holdout <= holdout_slots
        ), f"{fault_class}: {holdout} holdout scenarios authored, {holdout_slots} slots allocated."


def test_full_classes_match_allocation_exactly() -> None:
    """Once a class has all its scenarios, the split breakdown must match the table."""
    scenarios = catalog()
    for fault_class, (dev_slots, holdout_slots) in ALLOCATION.items():
        in_class = [s for s in scenarios if s.fault_class is fault_class]
        if len(in_class) != dev_slots + holdout_slots:
            continue  # class not fully authored yet
        dev = sum(1 for s in in_class if s.split is Split.DEV)
        holdout = sum(1 for s in in_class if s.split is Split.HOLDOUT)
        assert (dev, holdout) == (dev_slots, holdout_slots), (
            f"{fault_class} is fully authored but split breakdown is {(dev, holdout)}, "
            f"allocated {(dev_slots, holdout_slots)}."
        )


def test_artifacts_live_under_their_scenario_split() -> None:
    """An artifact in the wrong tree is a quarantine breach, not a filing mistake."""
    if not ARTIFACT_DIR.exists():
        pytest.skip("no artifacts yet")
    by_id = {s.id: s for s in catalog()}
    for split in (Split.DEV, Split.HOLDOUT):
        tree = ARTIFACT_DIR / split.value
        if not tree.exists():
            continue
        for entry in tree.iterdir():
            if not entry.is_dir():
                continue
            scenario = by_id.get(entry.name)
            assert scenario is not None, (
                f"artifacts/{split.value}/{entry.name}/ has no matching scenario. "
                "Orphaned artifacts are unquarantinable - delete them or author the scenario."
            )
            assert scenario.split is split, (
                f"scenario {entry.name} is split={scenario.split.value} but its artifacts "
                f"are under artifacts/{split.value}/. This is a contamination breach."
            )


def test_rehearsed_scenarios_have_artifacts() -> None:
    """rehearsed: true is a claim that a manual end-to-end run happened. It leaves traces."""
    for scenario in catalog():
        if not scenario.rehearsed:
            continue
        expected = ARTIFACT_DIR / scenario.split.value / scenario.id
        assert expected.is_dir(), (
            f"{scenario.id} is marked rehearsed but {expected.relative_to(REPO_ROOT)} "
            "does not exist."
        )


def test_split_doc_matches_allocation() -> None:
    """SPLIT.md is the human-readable copy. Drift between it and ALLOCATION is a bug."""
    text = SPLIT_DOC.read_text()
    for fault_class, (dev_slots, holdout_slots) in ALLOCATION.items():
        pattern = rf"^\|\s*`{re.escape(fault_class.value)}`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$"
        match = re.search(pattern, text, re.MULTILINE)
        assert match is not None, f"{fault_class.value} missing from SPLIT.md summary table"
        assert (int(match.group(1)), int(match.group(2))) == (
            dev_slots,
            holdout_slots,
        ), f"SPLIT.md and ALLOCATION disagree on {fault_class.value}"
