"""Q53's pilot driver, against fakes (`PREREGISTRATION-Q53.md`).

**Every defect T6.3 found was in its driver, not in what it drove**: a gate weaker than the
harness's, and a missing model client discovered *after* a fault had been injected. This pilot
spends money on a live world, so its logic is exercised here where neither is true.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from evalharness import depthpilot
from evalharness.depthpilot import (
    BASELINE_ARM,
    CHANGE_ARM,
    Verdict,
    arm_order,
    env_for,
    run_pilot,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Steps:
    """A world that always admits, always alerts, and answers whatever it is told to."""

    def __init__(
        self,
        answers: dict[tuple[str, str], tuple[str, str] | None] | None = None,
        *,
        admits: bool = True,
        incident: bool = True,
        cost: float = 0.6,
    ) -> None:
        self.answers = answers or {}
        self._admits = admits
        self._incident = incident
        self._cost = cost
        self.injected: list[str] = []
        self.reverted: list[str] = []
        self.investigations: list[tuple[str, str]] = []

    def gate_admits(self) -> tuple[bool, list[str]]:
        return self._admits, [] if self._admits else ["a leftover incident"]

    def inject(self, scenario_id: str) -> str:
        self.injected.append(scenario_id)
        return "injected"

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None:
        return f"inc-{scenario_id}" if self._incident else None

    def investigate(self, incident_id: str, arm: str) -> Verdict | None:
        self.investigations.append((incident_id, arm))
        scenario = incident_id.removeprefix("inc-")
        answer = self.answers.get((scenario, arm), ("bad_deploy", "rollback"))
        if answer is None:
            return None
        return Verdict(arm, f"t-{scenario}-{arm}", answer[0], answer[1], self._cost)

    def revert(self, scenario_id: str) -> None:
        self.reverted.append(scenario_id)


def test_a_pair_is_one_injection_and_two_investigations() -> None:
    """**The design's whole point.** Both arms see one world state, one incident, one alert set and
    one change log, so the only difference between the verdicts is what retrieval handed the model.
    Two injections would reintroduce the world variance the pairing exists to remove."""
    steps = _Steps()

    result = run_pilot(steps, ("cart-bad-image-tag",))

    assert steps.injected == ["cart-bad-image-tag"]
    assert [arm for _, arm in steps.investigations] == [BASELINE_ARM, CHANGE_ARM]
    assert len({incident for incident, _ in steps.investigations}) == 1
    assert result.pairs[0].complete


def test_the_arm_order_alternates_across_pairs() -> None:
    """A second investigation runs against an incident that already carries the first's proposal.
    Alternating does not remove an order effect - it stops one being confounded with the arm."""
    assert arm_order(0) == (BASELINE_ARM, CHANGE_ARM)
    assert arm_order(1) == (CHANGE_ARM, BASELINE_ARM)

    steps = _Steps()
    run_pilot(steps, ("a", "b", "c", "d"))

    firsts = [steps.investigations[i][1] for i in range(0, 8, 2)]
    assert firsts == [BASELINE_ARM, CHANGE_ARM, BASELINE_ARM, CHANGE_ARM]


def test_identical_verdicts_do_not_count_as_a_difference() -> None:
    steps = _Steps()

    result = run_pilot(steps, ("a", "b"))

    assert result.complete_pairs and not result.differing
    assert "0 of 2 differ" in result.render()
    assert "closes Q53" in result.render()


def test_a_changed_fault_class_is_the_outcome() -> None:
    steps = _Steps(
        {
            ("b", CHANGE_ARM): ("resource_exhaustion", "config_revert"),
        }
    )

    result = run_pilot(steps, ("a", "b"))

    assert [p.scenario_id for p in result.differing] == ["b"]
    assert "DIFFERS" in result.render()


def test_the_budget_stops_the_pilot_before_spending_not_after() -> None:
    """**A ceiling enforced after the spend is a report, not a limit.**

    Each investigation costs 6.0 here against a ceiling of 10.0: the first pair spends 12.0, and
    the pilot stops before starting the second rather than discovering it overran.
    """
    steps = _Steps(cost=6.0)

    result = run_pilot(steps, ("a", "b", "c"), ceiling_usd=10.0)

    assert result.cost_usd == pytest.approx(12.0)
    assert "budget ceiling" in result.stopped
    assert steps.injected == ["a"], "no further scenario is injected"


def test_the_world_is_reverted_even_when_an_arm_produces_nothing() -> None:
    """**A pilot that leaves a fault injected has cost more than money.** The revert is in a
    `finally`, so a missing verdict, a failed investigation or a budget stop all still clean up."""
    steps = _Steps({("a", CHANGE_ARM): None})

    result = run_pilot(steps, ("a",))

    assert steps.reverted == ["a"]
    assert not result.pairs[0].complete
    assert "produced no verdict" in result.pairs[0].skipped


def test_a_refused_gate_skips_the_scenario_without_injecting() -> None:
    """T6.3's first defect was a driver whose gate was weaker than the harness's, and a leftover
    incident swallowed the next scenario's alerts. The gate is checked before **every** injection,
    not once at the start."""
    steps = _Steps(admits=False)

    result = run_pilot(steps, ("a", "b"))

    assert steps.injected == []
    assert all("gate refused" in p.skipped for p in result.pairs)
    assert result.complete_pairs == []


def test_a_scenario_that_never_alerts_is_skipped_and_reverted() -> None:
    steps = _Steps(incident=False)

    result = run_pilot(steps, ("a",))

    assert steps.reverted == ["a"]
    assert result.pairs[0].skipped == "no incident"
    assert steps.investigations == [], "nothing is investigated without an incident"


def test_each_arm_sets_both_halves_of_its_configuration() -> None:
    """Neither half is tested alone: `retrieval_k` alone buys two queries of 43, normalisation 2
    alone at `k = 3` buys one, and Q52 measured that choosing among flags at that depth is worse
    than not choosing. A pilot that set one and not the other would measure nothing this
    registration is about."""
    baseline = env_for(BASELINE_ARM, {})
    change = env_for(CHANGE_ARM, {})

    assert baseline["FAULTLINE_CONTEXT_RETRIEVAL_K"] == "3"
    assert baseline["FAULTLINE_CONTEXT_TEXT_NORMALISATION"] == "0"
    assert change["FAULTLINE_CONTEXT_RETRIEVAL_K"] == "5"
    assert change["FAULTLINE_CONTEXT_TEXT_NORMALISATION"] == "2"


def test_the_arm_settings_are_the_ones_the_registration_names() -> None:
    """The configurations are read from the module rather than restated, so a drift between the
    driver and `PREREGISTRATION-Q53.md` §2 shows up here rather than in a spend."""
    assert depthpilot.ARMS[BASELINE_ARM] == {"retrieval_k": 3, "text_normalisation": 0}
    assert depthpilot.ARMS[CHANGE_ARM] == {"retrieval_k": 5, "text_normalisation": 2}
    assert depthpilot.BUDGET_CEILING_USD == 25.0


def test_the_registered_scenarios_are_ten_dev_ones_in_catalog_order() -> None:
    """**No selection.** A pilot whose scenarios were chosen would be measuring the chooser.

    Every one must be `dev`: holdout entries are spent deliberately and none is spent on a pilot.
    """
    from evalharness.scenario import load_catalog

    catalog = {s.id: s for s in load_catalog(REPO_ROOT / "evals/scenarios")}
    assert len(depthpilot.SCENARIOS) == 10
    assert len(set(depthpilot.SCENARIOS)) == 10
    for scenario_id in depthpilot.SCENARIOS:
        assert scenario_id in catalog, scenario_id
        assert catalog[scenario_id].split == "dev", f"{scenario_id} is not dev"
    assert list(depthpilot.SCENARIOS) == sorted(depthpilot.SCENARIOS), "catalog order"


def test_the_pilot_calls_no_model_itself() -> None:
    """**The arms must be the pipeline, not a second implementation of it.**

    `faultline-investigate` is shelled, so a driver that imported an agent role or a model client
    would be measuring something that merely lives in the same repository. The same guard the
    retrieval harness and the reject-loop driver carry.
    """
    source = (REPO_ROOT / "src" / "evalharness" / "depthpilot.py").read_text()
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "anthropic" not in imported
    assert not any(name.startswith("faultline.agents.role") for name in imported)
    assert "faultline.agents.model" not in imported


# --- reading the verdict, which the dry run found broken ---------------------------------------


def test_the_verdict_is_read_from_the_artifact_the_pipeline_writes() -> None:
    """**The defect the $1.20 dry run bought.**

    The first version queried a `proposals` table that does not exist. The lesson is not the wrong
    name: `faultline-investigate --out` writes `<incident>-verdict.json`, `evalharness.run` reads
    exactly that file, and a driver reconstructing the same answer from tables is a second
    implementation of the harness - which this module's docstring says it must not be.

    `fault_class` lives here and **not** in `trajectory_proposals`, which carries
    `remediation_class` only, so the table route could never have answered the question at all.
    """
    payload = {
        "trajectory_id": "c5d32a77",
        "verdict": {"fault_class": "resource_exhaustion", "remediation_class": "scale"},
    }

    verdict = depthpilot.verdict_from_artifact(payload, CHANGE_ARM, cost_usd=0.6)

    assert verdict is not None
    assert verdict.fault_class == "resource_exhaustion"
    assert verdict.remediation_class == "scale"
    assert verdict.trajectory_id == "c5d32a77"
    assert verdict.cost_usd == 0.6


def test_an_artifact_without_a_verdict_yields_none_rather_than_a_blank() -> None:
    """A blank `fault_class` compared against another blank would read as *the arms agree*, which
    is the pilot's outcome reported from an absence of evidence."""
    assert depthpilot.verdict_from_artifact({}, CHANGE_ARM) is None
    assert depthpilot.verdict_from_artifact({"trajectory_id": "t"}, CHANGE_ARM) is None
    assert (
        depthpilot.verdict_from_artifact({"verdict": {"fault_class": "bad_deploy"}}, CHANGE_ARM)
        is None
    )


def test_an_abstention_is_still_a_verdict() -> None:
    """ADR-0022 §1.2: an abstention is an outcome, not an absence. The dry run's one completed arm
    abstained on the proposal and still returned a fault class, and a pilot that discarded it would
    be dropping the answer it exists to compare."""
    payload = {
        "trajectory_id": "t1",
        "verdict": {"fault_class": "resource_exhaustion", "remediation_class": "none"},
    }

    verdict = depthpilot.verdict_from_artifact(payload, BASELINE_ARM)

    assert verdict is not None
    assert verdict.remediation_class == "none"


# --- the settle window between pairs ------------------------------------------------------------


def test_the_pilot_settles_between_pairs_but_not_before_the_first() -> None:
    """**The gap the dry run exposed at $0.**

    Every pair leaves a resolved incident, and a firing inside the orchestrator's 300s window
    reopens it rather than opening a new one - so the next pair's alerts are attributed to the
    previous scenario and the gate refuses. Without this the ten-pair run completes pair one,
    refuses pairs two through ten, and reports `n = 1` for $1.20.

    The gate's own refusal is what made it visible: *"Wait 141s."* `sweep.py` carries the same
    constant for the same reason, and this mirrors it rather than inventing a second number.

    No wait before the first pair: there is nothing to settle from.
    """
    steps = _Steps()
    naps: list[int] = []

    run_pilot(steps, ("a", "b", "c"), settle=300, sleeper=naps.append)

    assert naps == [300, 300], "between pairs, not before the first"


def test_settle_defaults_off_so_a_test_cannot_nap_for_twenty_minutes() -> None:
    """`sweep.py`'s lesson, inherited rather than relearned: *"the first version defaulted without
    a sleeper and tried to nap for twenty minutes."* Waiting is a property of running the pilot,
    not of the function, and a default that sleeps is one nobody can call in a test without knowing
    to disarm it. The CLI passes `SETTLE_SECONDS`."""
    steps = _Steps()
    naps: list[int] = []

    run_pilot(steps, ("a", "b"), sleeper=naps.append)

    assert naps == []
    assert depthpilot.SETTLE_SECONDS == 300
