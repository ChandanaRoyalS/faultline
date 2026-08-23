"""The rehearsal bundle format, enforced (ADR-0009).

Incremental, like the contamination guards: these pass on an empty artifacts tree and
tighten as bundles land. Nothing here checks the honesty of the narrative - no test can -
but everything that is mechanically checkable is checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalharness.scenario import Scenario, Split

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "evals" / "scenarios"
ARTIFACT_ROOT = SCENARIO_DIR / "artifacts"

REQUIRED_MANIFEST_KEYS = {
    "origin",
    "scenario_id",
    "split",
    "fault_class",
    "injection",
    "t_inject",
    "t_revert",
    "alerts_at_fire",
    "window",
}

REQUIRED_METRICS = {
    "error-ratio.json",
    "call-rate.json",
    "latency-p95.json",
    "alerts-firing.json",
}


def scenarios() -> list[Scenario]:
    out: list[Scenario] = []
    for path in sorted(SCENARIO_DIR.rglob("*.yaml")):
        if "examples" in path.parts or "artifacts" in path.parts:
            continue
        out.append(Scenario.from_yaml(path))
    return out


def bundles() -> list[Path]:
    """Every directory under artifacts/ that has something in it."""
    if not ARTIFACT_ROOT.exists():
        return []
    found: list[Path] = []
    for split in (Split.DEV, Split.HOLDOUT):
        tree = ARTIFACT_ROOT / split.value
        if not tree.exists():
            continue
        found += [d for d in sorted(tree.iterdir()) if d.is_dir() and any(d.iterdir())]
    return found


def manifest_of(bundle: Path) -> dict[str, Any]:
    raw: Any = json.loads((bundle / "manifest.json").read_text())
    assert isinstance(raw, dict), f"{bundle.name}: manifest.json is not an object"
    return raw


def test_every_bundle_has_a_manifest() -> None:
    for bundle in bundles():
        assert (bundle / "manifest.json").is_file(), (
            f"{bundle.name}: no manifest.json. A bundle without one cannot be traced back "
            "to the run that produced it."
        )


def test_manifest_carries_provenance() -> None:
    """T4.1b's exclusion filter has nothing to filter on without this stamp."""
    for bundle in bundles():
        manifest = manifest_of(bundle)
        assert manifest.get("origin") == f"scenario:{bundle.name}", (
            f"{bundle.name}: origin must be 'scenario:{bundle.name}', "
            f"got {manifest.get('origin')!r}"
        )


def test_manifest_has_required_keys() -> None:
    for bundle in bundles():
        missing = REQUIRED_MANIFEST_KEYS - set(manifest_of(bundle))
        assert not missing, f"{bundle.name}: manifest missing {sorted(missing)}"


def test_manifest_split_matches_its_directory() -> None:
    for bundle in bundles():
        expected = bundle.parent.name
        assert manifest_of(bundle).get("split") == expected, (
            f"{bundle.name}: manifest says split="
            f"{manifest_of(bundle).get('split')!r} but it is filed under {expected}/"
        )


def test_bundles_carry_the_metric_captures() -> None:
    for bundle in bundles():
        present = {p.name for p in (bundle / "metrics").glob("*.json")}
        missing = REQUIRED_METRICS - present
        assert not missing, f"{bundle.name}: metrics/ missing {sorted(missing)}"


def test_rehearsed_scenarios_have_a_finished_narrative() -> None:
    """`rehearsed: true` claims a complete bundle. Template comments mean it isn't."""
    by_id = {b.name: b for b in bundles()}
    for scenario in scenarios():
        if not scenario.rehearsed:
            continue
        bundle = by_id.get(scenario.id)
        assert bundle is not None, f"{scenario.id} is marked rehearsed but has no artifact bundle."
        incident = bundle / "incident.md"
        assert incident.is_file(), f"{scenario.id}: no incident.md"
        text = incident.read_text()
        assert "<!--" not in text, (
            f"{scenario.id}: incident.md still has template comments in it. "
            "Finish the narrative before marking the scenario rehearsed."
        )
        assert len(text.split()) > 120, (
            f"{scenario.id}: incident.md is too short to be a real narrative "
            f"({len(text.split())} words). This file seeds the retrieval corpus."
        )


def test_narratives_do_not_leak_the_answer_key() -> None:
    """A responder did not know the fault class or the scenario id. Neither should the prose."""
    banned = ("faultline-inject", "injector", "injected", "fault_class", "scenario id")
    for bundle in bundles():
        incident = bundle / "incident.md"
        if not incident.is_file():
            continue
        body = incident.read_text().split("---", 2)[-1].lower()
        leaked = [word for word in banned if word in body]
        assert not leaked, (
            f"{bundle.name}: incident.md mentions {leaked} in its prose. Write it from the "
            "responder's chair - this text is retrieved later as a past incident."
        )
