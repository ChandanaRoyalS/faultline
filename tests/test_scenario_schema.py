"""The scenario schema is the contract for the whole eval layer - validate it early."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evalharness.scenario import Scenario, Split, load_catalog
from injector.catalog import by_id

EXAMPLES = Path(__file__).parent.parent / "evals" / "scenarios" / "examples"


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

    Drift here is silent and expensive: the scenario would describe one incident and the
    rehearsal would record another, and the mismatch surfaces only as an unexplainable
    scoring result months later.
    """
    for scenario in scored_scenarios():
        fault = by_id(scenario.injection.method)
        assert fault is not None
        assert scenario.injection.target == fault.target, (
            f"{scenario.id}: targets {scenario.injection.target!r}, but fault {fault.id} "
            f"targets {fault.target!r}"
        )
        assert scenario.injection.params == fault.params, (
            f"{scenario.id}: params {scenario.injection.params} do not match fault "
            f"{fault.id} params {fault.params}"
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
