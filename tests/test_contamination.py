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
    FaultClass.BAD_DEPLOY: (4, 2),
    FaultClass.DEPENDENCY_LATENCY: (3, 1),
    FaultClass.RESOURCE_EXHAUSTION: (3, 1),
    FaultClass.BAD_CONFIG: (4, 2),
}
"""**n=20 as of T7.21**, extended from n=10 by principle and before any candidate was assigned.

The guards below are capacity checks: authoring may not exceed these, and must match exactly once
a class is full. Extending them opens slots; it does not create scenarios, and which faults fill
them is the separate earlier decision ADR-0008 requires. See SPLIT.md for the reasoning and for the
n=30 allocation, which is decided but not yet opened here."""

CAPACITY_HEADING = "### Current capacity"
"""Where the drift check reads from. SPLIT.md keeps the n=10 table above it as committed history,
so the check has to be anchored rather than matching the first table it finds."""


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
    whole = SPLIT_DOC.read_text()
    assert CAPACITY_HEADING in whole, "SPLIT.md has no current-capacity table to check against"
    text = whole.split(CAPACITY_HEADING, 1)[1]
    for fault_class, (dev_slots, holdout_slots) in ALLOCATION.items():
        pattern = rf"^\|\s*`{re.escape(fault_class.value)}`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$"
        match = re.search(pattern, text, re.MULTILINE)
        assert match is not None, f"{fault_class.value} missing from SPLIT.md summary table"
        assert (int(match.group(1)), int(match.group(2))) == (
            dev_slots,
            holdout_slots,
        ), f"SPLIT.md and ALLOCATION disagree on {fault_class.value}"


# --- T7.35: the slot rule, made executable -------------------------------------------------

SLOT_SPLITS: dict[FaultClass, tuple[Split, ...]] = {
    FaultClass.BAD_DEPLOY: (
        Split.DEV,
        Split.HOLDOUT,
        Split.DEV,
        Split.DEV,
        Split.DEV,
        Split.HOLDOUT,
    ),
    FaultClass.BAD_CONFIG: (
        Split.DEV,
        Split.DEV,
        Split.DEV,
        Split.DEV,
        Split.HOLDOUT,
        Split.HOLDOUT,
    ),
    FaultClass.DEPENDENCY_LATENCY: (Split.DEV, Split.HOLDOUT, Split.DEV, Split.DEV),
    FaultClass.RESOURCE_EXHAUSTION: (Split.DEV, Split.DEV, Split.HOLDOUT, Split.DEV),
}
"""Which split each numbered slot belongs to, from SPLIT.md's n=10 table plus T7.21's ten new slots.

**Holdout takes the highest-numbered slots within each class** - the mechanical rule SPLIT.md states
so that no extension needs judgement either. The totals here are the same numbers `ALLOCATION`
carries; `test_slot_table_agrees_with_the_allocation` asserts the two cannot drift apart.
"""


BACKFILLED_AT_T735 = frozenset(
    {
        "ad-memory-squeeze",
        "cart-bad-image-tag",
        "cart-dependency-latency",
        "cart-redis-misconfig",
        "email-wrong-image",
        "frauddetection-memory-squeeze",
        "product-catalog-flag-failure",
        "productcatalog-dependency-latency",
        "recommendation-memory-squeeze",
        "shipping-quote-misconfig",
        "shipping-wrong-image",
    }
)
"""The eleven the T7.35 derivation was run over. **A historical set, and it does not grow.**

The alphabetical derivation is a *backfill*, not a standing rule, and T7.36 proved why by being the
first scenario authored after it: `payment-telemetry-blackout` sorts second in `bad_config`, so
re-deriving would take `bad_config-2` and shuffle two already-recorded scenarios down a slot. That
is exactly the instability T7.35 documented - and then encoded in a standing check anyway. The
check below is pinned to the set it was derived for; `test_slots_are_a_contiguous_prefix_per_class`
is what constrains everything authored afterwards.
"""


def derived_slots() -> dict[str, str]:
    """The backfill derivation: alphabetical by fault id within class, lowest free slot first.

    **Run once and asserted, never used to overwrite.** See `Scenario.slot` for why recomputing
    this on every read would cause the contamination it exists to prevent.
    """
    by_class: dict[FaultClass, list[Scenario]] = {}
    for scenario in allocated():
        # **Derived over the backfilled set only.** Including anything authored later would
        # re-sort the class and move slots that are frozen - the very instability this
        # derivation is quarantined for (T7.36).
        if scenario.id not in BACKFILLED_AT_T735:
            continue
        by_class.setdefault(scenario.fault_class, []).append(scenario)
    out: dict[str, str] = {}
    for fault_class, scenarios in by_class.items():
        for index, scenario in enumerate(sorted(scenarios, key=lambda s: s.id)):
            out[scenario.id] = f"{fault_class.value}-{index + 1}"
    return out


def test_the_derivation_still_reproduces_every_recorded_split() -> None:
    """**The loud check.** If the rule and the record ever disagree, that is a real finding.

    T7.34 established that assigning each valid scenario to the lowest free slot of its class,
    alphabetically, reproduces all eleven existing split assignments. That is the evidence the
    backfill rests on, so it is asserted rather than assumed - and it fails with the disagreement
    named, rather than the backfill quietly winning.
    """
    disagreements = []
    for scenario in allocated():
        if scenario.id not in BACKFILLED_AT_T735:
            continue
        slot = derived_slots()[scenario.id]
        index = int(slot.rsplit("-", 1)[1]) - 1
        belongs_to = SLOT_SPLITS[scenario.fault_class][index]
        if belongs_to is not scenario.split:
            disagreements.append(
                f"{scenario.id}: recorded split={scenario.split.value}, but the rule puts it in "
                f"{slot}, which is a {belongs_to.value} slot"
            )
    assert not disagreements, (
        "THE SLOT RULE AND THE RECORDED SPLITS DISAGREE. This is a finding, not a fixture "
        "problem - do not 'fix' it by editing the split, which is what the rule exists to "
        "prevent:\n  " + "\n  ".join(disagreements)
    )


def test_every_scenario_that_occupies_a_slot_records_which_one() -> None:
    missing = [s.id for s in allocated() if s.slot is None]
    assert not missing, f"no slot recorded: {missing}. Authoring assigns one (SPLIT.md)."


def test_a_blocked_scenario_records_no_slot_because_it_releases_it() -> None:
    """`blocked` releases the slot rather than consuming it, so it must not also claim one."""
    claiming = [s.id for s in catalog() if s.blocked and s.slot is not None]
    assert not claiming, f"blocked but still claiming a slot: {claiming}"


def test_the_recorded_slot_is_the_one_the_rule_assigns_for_the_backfilled_set() -> None:
    """Identity, not count - over the eleven the derivation was actually run on."""
    derived = derived_slots()
    wrong = [
        f"{s.id}: records {s.slot}, backfill derived {derived[s.id]}"
        for s in allocated()
        if s.id in BACKFILLED_AT_T735 and s.slot != derived[s.id]
    ]
    assert not wrong, "\n  ".join(["backfilled slot does not match the derivation:", *wrong])


def test_slots_are_a_contiguous_prefix_per_class() -> None:
    """**The forward rule, and it is stable under addition.**

    A new scenario takes the lowest-numbered free slot in its class, so the occupied numbers in
    every class are always `1..n` with no holes. This is what catches steering without
    re-deriving anything: an author who reaches past a free dev slot to author into a holdout
    one leaves a hole, and the hole fails here.

    `bad_deploy-5` is deliberately empty (T7.35) but it is the *last* dev slot of its class and
    nothing follows it, so it makes no hole. If a scenario is ever authored into `bad_deploy-6`
    while `-5` stands empty, that is a real steering event and this test is what says so.
    """
    by_class: dict[FaultClass, set[int]] = {}
    for scenario in allocated():
        assert scenario.slot is not None
        by_class.setdefault(scenario.fault_class, set()).add(int(scenario.slot.rsplit("-", 1)[1]))
    for fault_class, numbers in by_class.items():
        assert numbers == set(range(1, len(numbers) + 1)), (
            f"{fault_class.value} occupies {sorted(numbers)}, which is not a contiguous prefix. "
            "A scenario reached past a free slot - which is how the split gets chosen rather "
            "than assigned (ADR-0008)."
        )


def test_no_two_scenarios_claim_the_same_slot() -> None:
    seen: dict[str, str] = {}
    for scenario in allocated():
        assert scenario.slot is not None
        assert scenario.slot not in seen, (
            f"{scenario.id} and {seen[scenario.slot]} both claim {scenario.slot}"
        )
        seen[scenario.slot] = scenario.id


def test_the_split_recorded_matches_the_split_that_slot_belongs_to() -> None:
    """**The anti-steering check.** A scenario authored into the split its author preferred,
    rather than the one its slot carries, fails here - where a per-class count passed it."""
    for scenario in allocated():
        assert scenario.slot is not None
        fault_class, number = scenario.slot.rsplit("-", 1)
        assert fault_class == scenario.fault_class.value
        belongs_to = SLOT_SPLITS[scenario.fault_class][int(number) - 1]
        assert scenario.split is belongs_to, (
            f"{scenario.id} is in {scenario.slot}, a {belongs_to.value} slot, but records "
            f"split={scenario.split.value}. The slot decides the split (ADR-0008); a scenario "
            f"does not choose its side."
        )


def test_a_slot_number_is_inside_its_class_allocation() -> None:
    for scenario in allocated():
        assert scenario.slot is not None
        number = int(scenario.slot.rsplit("-", 1)[1])
        assert 1 <= number <= len(SLOT_SPLITS[scenario.fault_class]), (
            f"{scenario.id} claims {scenario.slot}, outside the class's allocated slots"
        )


def test_slot_table_agrees_with_the_allocation() -> None:
    """Two tables describing one decision. They may not drift."""
    for fault_class, (dev_slots, holdout_slots) in ALLOCATION.items():
        splits = SLOT_SPLITS[fault_class]
        assert sum(1 for s in splits if s is Split.DEV) == dev_slots
        assert sum(1 for s in splits if s is Split.HOLDOUT) == holdout_slots


def test_the_slot_is_not_part_of_the_scenario_fingerprint() -> None:
    """Recording an allocation fact must not invalidate every recorded bundle (T7.17's rule)."""
    from evalharness.provenance import scenario_fingerprint

    scenario = next(s for s in allocated() if s.slot is not None)
    before = scenario_fingerprint(scenario)
    moved = scenario.model_copy(update={"slot": "bad_deploy-6"})
    assert scenario_fingerprint(moved) == before
