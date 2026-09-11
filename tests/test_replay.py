"""The repair replay driver (T6.2 §4), without a world.

`RealSteps` is the harness, the executor and the injector; these tests substitute a fake and hold
the driver to its decisions - the scoring precedence the pre-registration fixed, what evidence is
written, that the proof presents exactly its three refusals, and that the nine triples it will
replay are the nine the registration named.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evalharness import replay

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


class FakeSteps:
    def __init__(
        self,
        *,
        executor_outcome: str = "executed",
        alerts_clear_after: int | None = 60,
        fault_in_force_after: bool = False,
        gate_refusals: int = 0,
        incident: str | None = "inc-1",
        leftover: list[str] | None = None,
    ) -> None:
        self.clock = NOW
        self.slept: list[float] = []
        self.calls: list[str] = []
        self._executor_outcome = executor_outcome
        self._clear_after = alerts_clear_after
        self._fault_after = fault_in_force_after
        self._gate_refusals = gate_refusals
        self._incident = incident
        self._leftover = leftover or []
        self._executed_at: datetime | None = None
        self._minted = 0
        self.kill_switch_seen: list[bool] = []

    def gate_admits(self) -> tuple[bool, list[str]]:
        self.calls.append("gate")
        if self._gate_refusals > 0:
            self._gate_refusals -= 1
            return False, ["kafka is young"]
        return True, []

    def inject(self, scenario_id: str) -> str:
        self.calls.append(f"inject {scenario_id}")
        return f"injected {scenario_id}\n"

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None:
        self.calls.append("wait")
        self.clock += timedelta(seconds=200)
        return self._incident

    def approve(self, incident_id: str, run_dir: Path, *, target_override: str | None = None):
        self._minted += 1
        self.calls.append(f"approve {target_override or 'recorded'}")
        return f"tok{self._minted}", {"token_id": f"t{self._minted}", "outcome": "approved"}

    def execute(self, token: str, *, kill_switch: bool = False) -> dict[str, Any]:
        self.calls.append(f"execute {token}")
        self.kill_switch_seen.append(kill_switch)
        if kill_switch:
            return {"id": "a-ks", "outcome": "kill_switch", "reason": "kill switch is on"}
        if token != "tok1" or self._executed_at is not None:
            return {"id": f"a-{token}", "outcome": "refused", "reason": f"{token} refused"}
        self._executed_at = self.clock
        return {"id": "a1", "outcome": self._executor_outcome, "reason": ""}

    def firing_alerts(self) -> list[str]:
        self.calls.append("alerts")
        if self._clear_after is None or self._executed_at is None:
            return ["ServiceHighErrorRate"]
        if self.clock >= self._executed_at + timedelta(seconds=self._clear_after):
            return []
        return ["ServiceHighErrorRate"]

    def fault_in_force(self, scenario_id: str) -> bool:
        return self._fault_after

    def stop_all(self) -> list[str]:
        self.calls.append("stop_all")
        return list(self._leftover)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.clock += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self.clock


RUN = REPO / "evals/runs/20260909T105155Z-shipping-wrong-image"


def test_an_executed_action_whose_alerts_clear_is_recovered(tmp_path: Path) -> None:
    steps = FakeSteps(alerts_clear_after=60)
    outcome = replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=5
    )

    assert outcome.result == "recovered" and outcome.executed
    assert outcome.action_id == "rollback_image" and outcome.target == "shippingservice"
    assert outcome.confirm_within_seconds == 300
    assert outcome.alerts_cleared_after_seconds is not None
    assert outcome.alerts_cleared_after_seconds <= 300
    assert outcome.fault_in_force_after is False
    assert steps.calls[:3] == ["gate", "inject shipping-wrong-image", "wait"]
    assert steps.calls[-1] == "stop_all" and steps.slept[-1] == 5
    written = {p.name for p in (tmp_path / "e").iterdir()}
    assert written >= {"outcome.json", "audit.json", "approval.json", "inject.txt", "replay.log"}
    assert json.loads((tmp_path / "e" / "outcome.json").read_text())["result"] == "recovered"


def test_alerts_still_firing_at_the_window_is_not_recovered(tmp_path: Path) -> None:
    """Prediction 6's shape: the recreate ran, the window elapsed, nothing cleared."""
    steps = FakeSteps(alerts_clear_after=None, fault_in_force_after=True)
    outcome = replay.replay_one(
        "redis-cart-dependency-latency",
        REPO / "evals/runs/20260909T171220Z-redis-cart-dependency-latency",
        steps,
        evidence_dir=tmp_path / "e",
        settle_seconds=0,
    )
    assert outcome.result == "not-recovered" and outcome.executed
    assert "still firing" in outcome.reason and "still in force" in outcome.reason
    assert outcome.alerts_cleared_after_seconds is None
    # The window is the proposal's own: 180s here, polled through.
    assert sum(s for s in steps.slept if s == 15) >= 180 - 15


def test_alerts_clearing_while_the_fault_is_still_in_force_is_not_recovered(tmp_path: Path) -> None:
    """Both halves are required: quiet alerts with the injector still reporting the fault is a
    world that went quiet for another reason."""
    steps = FakeSteps(alerts_clear_after=30, fault_in_force_after=True)
    outcome = replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=0
    )
    assert outcome.result == "not-recovered"
    assert "cleared" in outcome.reason and "still in force" in outcome.reason


def test_a_refusal_is_scored_as_refused_with_the_executors_reason(tmp_path: Path) -> None:
    steps = FakeSteps(executor_outcome="refused")
    steps.execute = lambda token, kill_switch=False: {  # type: ignore[method-assign]
        "id": "a1",
        "outcome": "refused",
        "reason": "unexecutable: cartservice shows no drift",
    }
    outcome = replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=0
    )
    assert outcome.result == "refused" and not outcome.executed
    assert "no drift" in outcome.reason
    assert outcome.alerts_cleared_after_seconds is None


def test_an_error_is_scored_as_error_and_stop_all_still_runs(tmp_path: Path) -> None:
    steps = FakeSteps(executor_outcome="error", leftover=["shipping-wrong-image"])
    steps.execute = lambda token, kill_switch=False: {
        "id": "a1",
        "outcome": "error",
        "reason": "command exited 1",
    }  # type: ignore[method-assign]
    outcome = replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=0
    )
    assert outcome.result == "error" and outcome.executed
    assert outcome.stop_all_reverted == ["shipping-wrong-image"]
    assert "stop_all" in steps.calls


def test_no_incident_means_the_executor_is_never_asked(tmp_path: Path) -> None:
    steps = FakeSteps(incident=None)
    outcome = replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=0
    )
    assert outcome.result == "no-incident"
    assert not any(c.startswith("execute") for c in steps.calls)
    assert "stop_all" in steps.calls, "whatever was injected is reverted"


def test_the_gate_is_waited_out_with_the_sweeps_patience(tmp_path: Path) -> None:
    steps = FakeSteps(gate_refusals=2)
    outcome = replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=0
    )
    assert outcome.result == "recovered"
    assert steps.calls.count("gate") == 3
    assert steps.slept[:2] == [replay.GATE_RETRY_SECONDS] * 2


def test_the_proof_presents_exactly_three_refusals_after_the_first_execution(
    tmp_path: Path,
) -> None:
    """§3: the same token again, the kill switch, the wrong target - in that order, recorded."""
    steps = FakeSteps()
    outcome = replay.replay_one(
        "shipping-wrong-image",
        RUN,
        steps,
        evidence_dir=tmp_path / "e",
        proof=True,
        settle_seconds=0,
    )
    checks = [r["check"] for r in outcome.refusals]
    assert checks == ["replayed token", "kill switch", "wrong target"]
    assert outcome.refusals[0]["outcome"] == "refused"
    assert outcome.refusals[1]["outcome"] == "kill_switch"
    assert steps.kill_switch_seen == [False, False, True, False]
    assert "approve paymentservice" in steps.calls
    assert (tmp_path / "e" / "refusals.json").exists()
    # Before the recovery wait, while the incident is still EXECUTING - the first run presented
    # them after the world had recovered and both were refused as "incident is resolved".
    assert steps.calls.index("execute tok3") < steps.calls.index("alerts")


def test_the_proof_is_skipped_when_nothing_executed(tmp_path: Path) -> None:
    steps = FakeSteps()
    steps.execute = lambda token, kill_switch=False: {
        "id": "a1",
        "outcome": "refused",
        "reason": "x",
    }  # type: ignore[method-assign]
    outcome = replay.replay_one(
        "shipping-wrong-image",
        RUN,
        steps,
        evidence_dir=tmp_path / "e",
        proof=True,
        settle_seconds=0,
    )
    assert outcome.refusals == []


def test_a_recovery_that_stop_all_still_reverts_is_flagged_in_the_log(tmp_path: Path) -> None:
    """Prediction 3's failure shape: the coupling unbuilt."""
    steps = FakeSteps(leftover=["shipping-wrong-image"])
    replay.replay_one(
        "shipping-wrong-image", RUN, steps, evidence_dir=tmp_path / "e", settle_seconds=0
    )
    assert "WARNING" in (tmp_path / "e" / "replay.log").read_text()


def test_the_nine_triples_are_the_registered_ones_and_exist() -> None:
    """§4.1's table, checked against the tree: each run directory exists, is an arm-A scored run,
    and its recorded proposal carries the action and target the table says."""
    expected = {
        "shipping-wrong-image": ("rollback_image", "shippingservice"),
        "cart-bad-image-tag": ("rollback_image", "cartservice"),
        "cart-redis-misconfig": ("revert_config", "cartservice"),
        "shipping-quote-misconfig": ("revert_config", "shippingservice"),
        "payment-telemetry-blackout": ("revert_config", "paymentservice"),
        "frauddetection-memory-squeeze": ("revert_config", "frauddetectionservice"),
        "ad-memory-squeeze": ("revert_config", "adservice"),
        "cart-dependency-latency": ("revert_config", "cartservice"),
        "redis-cart-dependency-latency": ("restart_service", "cartservice"),
    }
    assert dict.fromkeys(s for s, _ in replay.TRIPLES) == dict.fromkeys(expected)
    for scenario, run_name in replay.TRIPLES:
        run_dir = REPO / "evals/runs" / run_name
        assert run_dir.is_dir(), run_name
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["scenario_id"] == scenario and not manifest.get("ablation")
        proposal = replay._recorded_proposal(run_dir)
        assert (proposal["action_id"], proposal["target"]) == expected[scenario], scenario


def test_the_summary_quotes_recovered_over_executed_and_lists_refusals_beside_it() -> None:
    outcomes = [
        replay.Outcome(
            "a",
            "r",
            "rollback_image",
            "x",
            executed=True,
            result="recovered",
            alerts_cleared_after_seconds=40,
            confirm_within_seconds=300,
        ),
        replay.Outcome(
            "b", "r", "revert_config", "y", result="refused", reason="unexecutable: no drift"
        ),
        replay.Outcome(
            "c",
            "r",
            "restart_service",
            "z",
            executed=True,
            result="not-recovered",
            reason="alerts still firing",
        ),
    ]
    text = replay.summary(outcomes)
    assert "Recovered 1 of 2 executed" in text and "1 refused" in text and "0 error(s)" in text
    assert "n = 3" in text
    assert "- **b**: unexecutable: no drift" in text
    assert "No model call was made" in text


def test_the_driver_never_imports_a_model_client() -> None:
    """Prediction 10: any model call in this task is a defect. The module imports nothing that
    could make one, checked on its import statements."""
    import ast

    tree = ast.parse((REPO / "src/evalharness/replay.py").read_text())
    names = {
        alias.name if isinstance(node, ast.Import) else node.module
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    names.discard(None)
    assert not any("anthropic" in n or "agents.model" in n or "agents.cli" in n for n in names), (
        names
    )
