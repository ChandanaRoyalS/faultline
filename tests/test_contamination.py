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
from injector.world import SERVICE_CONTAINERS, canonical_service

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


def allocated() -> list[Scenario]:
    """Scenarios that occupy a slot. **Use this for anything about the allocation.**

    A `blocked: true` scenario cannot be rehearsed or scored, so it is not filling the slot
    it was written into - its replacement has to be allowed in without widening SPLIT.md,
    which is fixed. The file stays so the history is visible.

    Use `catalog()` for checks about the files themselves: that they validate, that ids are
    unique, that artifacts are filed under the right split.
    """
    return [s for s in catalog() if not s.blocked]


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
    scenarios = allocated()
    for fault_class, (dev_slots, holdout_slots) in ALLOCATION.items():
        in_class = [s for s in scenarios if s.fault_class is fault_class]
        dev = sum(1 for s in in_class if s.split is Split.DEV)
        holdout = sum(1 for s in in_class if s.split is Split.HOLDOUT)
        assert dev <= dev_slots, (
            f"{fault_class}: {dev} dev scenarios authored, {dev_slots} slots allocated. "
            "Splits are committed before authoring (ADR-0008) - do not widen the table."
        )
        assert holdout <= holdout_slots, (
            f"{fault_class}: {holdout} holdout scenarios authored, {holdout_slots} slots allocated."
        )


def test_full_classes_match_allocation_exactly() -> None:
    """Once a class has all its scenarios, the split breakdown must match the table."""
    scenarios = allocated()
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


# Services targeted on both sides of the split, by canonical identity, blocked scenarios
# excluded. Measured empty at n=10 - see the test below for what that does and does not
# mean. An entry here is not automatically a defect (ADR-0008, "the split quarantines the
# fault, not the service"), so this is a record of what has been looked at, not a list of
# things to fix.
CROSS_SPLIT_SERVICES: set[str] = set()


def targets_by_split() -> dict[Split, dict[str, list[str]]]:
    """canonical service -> scenario ids, per split, over the scenarios that fill a slot.

    Blocked scenarios are excluded because they are never rehearsed: they produce no
    bundle, so nothing of theirs can reach a corpus and they cannot contaminate anything.
    """
    grouped: dict[Split, dict[str, list[str]]] = {Split.DEV: {}, Split.HOLDOUT: {}}
    for scenario in allocated():
        service = canonical_service(scenario.injection.target)
        grouped[scenario.split].setdefault(service, []).append(scenario.id)
    return grouped


def test_canonical_identity_is_load_bearing_for_the_overlap_check() -> None:
    """Guard against the overlap check below quietly degrading into a raw string compare.

    The catalog uses both naming schemes, because a fault's target follows its mechanism.
    If it ever used only one, `canonical_service` would be an identity function over these
    targets and the check below would keep passing while measuring nothing.
    """
    targets = {s.injection.target for s in allocated()}
    container_named = {t for t in targets if t not in SERVICE_CONTAINERS}
    service_named = targets - container_named
    assert container_named and service_named, (
        f"every allocated target now uses one naming scheme ({sorted(targets)}), so "
        "canonicalising them changes nothing and the cross-split overlap check no longer "
        "proves anything a raw comparison would not."
    )


def test_cross_split_service_overlap_is_the_recorded_set() -> None:
    """Which services are targeted on both sides of the split, by canonical identity.

    Raw target comparison cannot answer this. `cart-dependency-latency` targets
    `cart-service` and `cart-redis-misconfig` targets `cartservice`; a dev scenario on
    `product-catalog-service` and a holdout one on `productcatalogservice` would report no
    overlap while sharing a service. So the comparison is made on canonical identity.

    At n=10 the answer is none: no service is targeted on both sides once blocked
    scenarios are dropped. Canonical identity confirms the raw result rather than adding
    to it - raw comparison finds one collision, `featureflagservice`, and its holdout side
    (`flag-service-bad-deploy`) is blocked, so it produces no bundle and drops out here too.

    A failure means the catalog changed, not that the catalog is wrong. Same-service
    retrieval across the split is a limit of what the split measures, recorded in ADR-0008
    and deliberately not treated as a breach: decide what it means, then record it in
    `CROSS_SPLIT_SERVICES`.
    """
    grouped = targets_by_split()
    shared = set(grouped[Split.DEV]) & set(grouped[Split.HOLDOUT])
    assert shared == CROSS_SPLIT_SERVICES, (
        "services targeted on both sides of the split changed.\n"
        + "\n".join(
            f"  {service}: dev {sorted(grouped[Split.DEV].get(service, []))}, "
            f"holdout {sorted(grouped[Split.HOLDOUT].get(service, []))}"
            for service in sorted(shared | CROSS_SPLIT_SERVICES)
        )
        + f"\n(recorded: {sorted(CROSS_SPLIT_SERVICES)})\n"
        "The split quarantines faults and artifacts, not services - see ADR-0008. This is "
        "a measurement, so update the recorded set once you have decided what the change "
        "means. Do not move a scenario to make it pass: SPLIT.md is fixed."
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
