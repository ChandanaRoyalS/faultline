"""The scenario schema is the contract for the whole eval layer - validate it early."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evalharness.scenario import Scenario, Split, load_catalog
from injector.catalog import by_id
from injector.world import same_service

EXAMPLES = Path(__file__).parent.parent / "evals" / "scenarios" / "examples"
SCENARIO_DIR = Path(__file__).parent.parent / "evals" / "scenarios"


def test_example_scenario_validates() -> None:
    catalog = load_catalog(EXAMPLES)
    assert len(catalog) == 1
    scenario = catalog[0]
    assert scenario.split is Split.DEV
    assert scenario.rehearsed is False, "examples must not claim rehearsal"


def test_unknown_fields_are_rejected() -> None:
    raw = Scenario.from_yaml(next(EXAMPLES.glob("*.yaml"))).model_dump()
    raw["surprise_field"] = "contamination vector"
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


def scored_scenarios() -> list[Scenario]:
    """The scored catalog: examples/ illustrates the schema, artifacts/ are recordings."""
    directory = Path(__file__).parent.parent / "evals" / "scenarios"
    return [
        Scenario.from_yaml(p)
        for p in sorted(directory.rglob("*.yaml"))
        if "examples" not in p.parts and "artifacts" not in p.parts
    ]


def test_every_scenario_cites_a_real_injector_fault() -> None:
    """`injection.method` is what evalharness.rehearse hands to the injector."""
    for scenario in scored_scenarios():
        assert by_id(scenario.injection.method) is not None, (
            f"{scenario.id}: injection.method {scenario.injection.method!r} is not a fault in "
            "injector.catalog - the rehearsal would refuse to run it"
        )


def test_scenario_injections_match_the_fault_they_cite() -> None:
    """A scenario is a label for what the injector actually does, so it may not paraphrase it.

    **`injector.catalog` is authoritative.** The injector reads only its own catalog; the
    YAML copy is documentation. Editing the YAML changes what the scenario *claims* and
    nothing about what runs, which is drift that produces a bundle labelled one way and
    recorded another - and surfaces months later as an unexplainable scoring result.
    """
    for scenario in scored_scenarios():
        fault = by_id(scenario.injection.method)
        assert fault is not None
        assert scenario.injection.target == fault.target, (
            f"{scenario.id}: the YAML targets {scenario.injection.target!r} but the "
            f"injector targets {fault.target!r}. injector.catalog is authoritative - the "
            "YAML is documentation, so fix the YAML unless you meant to change the fault."
            + (
                " These are the world's two names for the same service, so this is a"
                " naming-scheme slip rather than a different target - but the target is"
                " bound to the fault's mechanism, so the documentation has to use the name"
                " the injector uses."
                if same_service(scenario.injection.target, fault.target)
                else ""
            )
        )
        assert scenario.injection.params == fault.params, (
            f"{scenario.id}: the YAML declares params {scenario.injection.params} but the "
            f"injector will run {fault.params}. injector.catalog is authoritative - "
            "editing the YAML changes what the scenario claims and nothing about what "
            "runs. Fix src/injector/catalog.py if you meant to change the fault."
        )
        assert scenario.fault_class is fault.fault_class, (
            f"{scenario.id}: declared {scenario.fault_class}, but fault {fault.id} is "
            f"{fault.fault_class}"
        )


def test_ground_truth_category_matches_the_scenario_fault_class() -> None:
    for scenario in scored_scenarios():
        assert scenario.ground_truth.category is scenario.fault_class, (
            f"{scenario.id}: ground_truth.category and fault_class disagree"
        )


PRE_REHEARSAL_MARKERS = ("UNVERIFIED", "NOT REHEARSED", "PREDICTED", "RISK, BEFORE REHEARSAL")
"""Text that means "someone still has to check this against a bundle"."""


def test_rehearsed_scenarios_carry_no_pre_rehearsal_markers() -> None:
    """`rehearsed: true` asserts the checking is done, so the instructions to check must go.

    A scenario is written before it is run, with its expected behaviour marked UNVERIFIED
    and its evidence items marked PREDICTED. Those markers are instructions: confirm each
    against the bundle, correct what was wrong, then delete the marker. Setting
    `rehearsed: true` claims that happened.

    Two scenarios reached a commit marked rehearsed while still carrying their banners, and
    nothing noticed - the flag and the prose contradicted each other and both were valid on
    their own terms. One of them had a prediction the rehearsal actually falsified, sitting
    in the file as though it were established.

    Deleting a marker is not the fix on its own: a marker you could not check should stay,
    with the item reworded to say what the bundle can and cannot show.
    """
    for path in sorted(SCENARIO_DIR.rglob("*.yaml")):
        if "examples" in path.parts or "artifacts" in path.parts:
            continue
        scenario = Scenario.from_yaml(path)
        if not scenario.rehearsed:
            continue
        text = path.read_text()
        found = [m for m in PRE_REHEARSAL_MARKERS if m in text]
        assert not found, (
            f"{scenario.id}: rehearsed: true, but the file still contains {found}. Those "
            "mark predictions nobody has confirmed yet. Check each against the committed "
            "bundle, correct anything the rehearsal falsified, and remove the marker - or "
            "leave rehearsed: false until that is done."
        )
