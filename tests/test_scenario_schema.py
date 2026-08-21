"""The scenario schema is the contract for the whole eval layer - validate it early."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evalharness.scenario import Scenario, Split, load_catalog

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
