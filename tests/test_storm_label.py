"""T7.1's storm label (ADR-0008's T7.1 addendum): measured off each bundle, recorded on each YAML.

*"A scenario whose rehearsal pages ten or more alerts is labeled `storm` on its record."* The YAML
carries the label so the record says it; this test recomputes it from every recorded v2 bundle, so
the label is a measurement and cannot be edited into a claim.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalharness import sweep
from evalharness.scenario import STORM_ALERTS, Scenario

REPO = Path(__file__).resolve().parents[1]
V2 = sorted(sweep.runnable(world="v2", holdout=True))


def _pre_revert_alerts(scenario_id: str) -> int:
    manifest = next(REPO.glob(f"evals/scenarios/artifacts/*/{scenario_id}/manifest.json"))
    window = json.loads(manifest.read_text()).get("alerts_over_window") or []
    return len({(a["alert"], a["service"]) for a in window if not a.get("began_after_revert")})


@pytest.mark.parametrize("scenario_id", V2)
def test_the_storm_label_is_what_the_bundle_measured(scenario_id: str) -> None:
    scenario = Scenario.from_yaml(REPO / "evals/scenarios/v2" / f"{scenario_id}.yaml")
    assert scenario.storm == (_pre_revert_alerts(scenario_id) >= STORM_ALERTS)


def test_seven_of_the_thirty_nine_are_storms_and_one_is_holdout() -> None:
    storms = [s for s in V2 if Scenario.from_yaml(REPO / "evals/scenarios/v2" / f"{s}.yaml").storm]
    assert len(V2) == 39
    assert len(storms) == 7
    assert [s for s in storms if s in set(V2) - set(sweep.runnable(world="v2"))] == [
        "v2-checkout-currency-misconfig"
    ]


def test_the_label_moves_no_recorded_bundle() -> None:
    from evalharness.provenance import scenario_fingerprint

    path = REPO / "evals/scenarios/v2/v2-cart-freeze.yaml"
    labelled = Scenario.from_yaml(path)
    unlabelled = labelled.model_copy(update={"storm": False})
    assert labelled.storm
    assert scenario_fingerprint(labelled) == scenario_fingerprint(unlabelled)
