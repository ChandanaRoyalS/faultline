"""The rejection-loop driver (T6.3 §4), against fakes and no world.

The measurement itself spends two model calls on a live world; **this file spends nothing.** What
it holds is the protocol - that the rejection goes through the route before anything is
re-investigated, that a route refusal is recorded rather than raised through, that the scoring
calls an abstention a change and an identical proposal unchanged, and that the reasons the
operator types are the ones the pre-registration fixed before the runs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from evalharness import rejectloop

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


class FakeSteps:
    def __init__(
        self,
        *,
        second: dict[str, Any] | None = None,
        kept: tuple[str, ...] = ("verdict-and-radius", "operator-rejection", "allowlist"),
        reject_raises: str | None = None,
        gate_refusals: int = 0,
        incident: str | None = "inc-1",
    ) -> None:
        self.calls: list[str] = []
        self.slept: list[float] = []
        self._second = second
        self._kept = kept
        self._reject_raises = reject_raises
        self._gate_refusals = gate_refusals
        self._incident = incident
        self._clock = NOW

    def gate_admits(self) -> tuple[bool, list[str]]:
        self.calls.append("gate")
        if self._gate_refusals > 0:
            self._gate_refusals -= 1
            return False, ["kafka headroom"]
        return True, []

    def inject(self, scenario_id: str) -> str:
        self.calls.append(f"inject {scenario_id}")
        return "injected"

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None:
        self.calls.append("wait")
        return self._incident

    def seed_proposal(self, incident_id: str, run_dir: Path) -> dict[str, Any]:
        self.calls.append(f"seed {run_dir.name}")
        return {
            "action_id": "restart_service",
            "target": "cartservice",
            "trajectory_id": "tr-first",
        }

    def reject(self, incident_id: str, reason: str) -> dict[str, Any]:
        self.calls.append(f"reject {reason[:20]}")
        if self._reject_raises:
            raise RuntimeError(self._reject_raises)
        return {"state": "rejected", "reason": reason}

    def reinvestigate(self, incident_id: str) -> int:
        self.calls.append("reinvestigate")
        return 0

    def second_proposal(self, incident_id: str, after_trajectory: str | None) -> dict[str, Any]:
        self.calls.append(f"second after {after_trajectory}")
        if self._second is None:
            return {
                "trajectory_id": "tr-second",
                "proposal": {"action_id": "restart_service", "target": "redis-cart"},
                "kept": list(self._kept),
                "dropped": [],
                "cost_usd": 0.71,
            }
        return self._second

    def stop_all(self) -> list[str]:
        self.calls.append("stop_all")
        return []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def now(self) -> datetime:
        return self._clock


def run(steps: FakeSteps, tmp_path: Path, pair: rejectloop.Pair | None = None) -> Any:
    chosen = pair or rejectloop.PAIRS[0]
    return rejectloop.run_one(
        chosen,
        REPO / "evals" / "runs" / chosen.run_name,
        steps,
        evidence_dir=tmp_path / "e",
        settle_seconds=0,
    )


# --- the material was fixed before the runs ----------------------------------


def test_both_pairs_name_a_recorded_run_that_exists_and_carries_the_failed_proposal() -> None:
    """§4.1's table, checked against the tree. Both rejections are **earned**: T6.2 executed one
    and it did not recover, and refused the other on drift. A pair whose run directory had moved
    would make the reason a story about a proposal nobody can read."""
    for pair in rejectloop.PAIRS:
        run_dir = REPO / "evals" / "runs" / pair.run_name
        assert run_dir.is_dir(), pair.run_name
        verdicts = sorted(run_dir.glob("*-verdict.json"))
        assert verdicts, pair.run_name
        proposal = json.loads(verdicts[0].read_text()).get("proposal") or {}
        assert proposal.get("action_id"), "a rejection needs something to reject"
        assert pair.scenario_id in pair.run_name


def test_the_reasons_are_the_ones_the_pre_registration_fixed() -> None:
    """**A reason chosen after seeing the second proposal would make this prompt-fitting.** The
    strings live in the driver and in `PREREGISTRATION-T6.3.md` §4.1; this is what keeps them the
    same strings."""
    registration = (REPO / "evals/runs/PREREGISTRATION-T6.3.md").read_text()

    for pair in rejectloop.PAIRS:
        for fragment in pair.reason.split(". "):
            core = fragment.strip().rstrip(".")
            assert core in registration, f"{pair.scenario_id}: {core!r} is not in the registration"


def test_the_driver_calls_no_model_itself() -> None:
    """Prediction 10's structural half, on `test_replay.py`'s pattern: the only spending in this
    measurement is the one `faultline-investigate` subprocess per pair, so this module must not
    be able to reach a model client at all."""
    import ast

    tree = ast.parse((REPO / "src/evalharness/rejectloop.py").read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)

    assert not [n for n in names if "anthropic" in n or "agents.model" in n]


# --- the protocol -------------------------------------------------------------


def test_the_rejection_goes_through_the_route_before_anything_is_re_investigated(
    tmp_path: Path,
) -> None:
    """The order is the measurement: seed, reject **through the surface**, then spend. A driver
    that re-investigated first would be measuring an investigation, not a loop."""
    steps = FakeSteps()

    outcome = run(steps, tmp_path)

    assert steps.calls[:3] == ["gate", "inject redis-cart-dependency-latency", "wait"]
    rejected_at = next(i for i, c in enumerate(steps.calls) if c.startswith("reject "))
    assert rejected_at < steps.calls.index("reinvestigate")
    assert rejected_at > steps.calls.index("seed 20260909T171220Z-redis-cart-dependency-latency")
    assert outcome.incident_id == "inc-1"
    assert outcome.first_action == "restart_service" and outcome.first_target == "cartservice"


def test_a_route_refusal_is_recorded_and_nothing_is_spent(tmp_path: Path) -> None:
    """If the surface refuses the rejection - a wrong password, an incident in the wrong state -
    the run ends there, the world is cleaned up, and **no model call is made.** A driver that
    carried on would spend money to re-investigate an incident nobody had rejected."""
    steps = FakeSteps(reject_raises="409: can be rejected from ...")

    outcome = run(steps, tmp_path)

    assert outcome.result == "error"
    assert "409" in outcome.reason
    assert "reinvestigate" not in steps.calls
    assert "stop_all" in steps.calls


def test_no_incident_ends_the_run_and_reverts_the_fault(tmp_path: Path) -> None:
    steps = FakeSteps(incident=None)

    outcome = run(steps, tmp_path)

    assert outcome.result == "no-incident"
    assert "reinvestigate" not in steps.calls
    assert "stop_all" in steps.calls


def test_the_gate_is_retried_with_the_repair_replays_patience(tmp_path: Path) -> None:
    steps = FakeSteps(gate_refusals=2)

    run(steps, tmp_path)

    assert steps.calls.count("gate") == 3
    assert steps.slept[:2] == [rejectloop.GATE_RETRY_SECONDS] * 2


# --- what is scored -----------------------------------------------------------


def test_a_different_target_is_a_change(tmp_path: Path) -> None:
    outcome = run(FakeSteps(), tmp_path)

    assert outcome.result == "changed"
    assert outcome.second_target == "redis-cart"
    assert outcome.rejection_reached_the_brief
    assert outcome.cost_usd == 0.71


def test_the_same_action_against_the_same_target_is_unchanged(tmp_path: Path) -> None:
    """**The result the write-up is committed in advance to reporting as *the loop is plumbing*.**
    A driver that could not express it would be a driver that could only confirm."""
    steps = FakeSteps(
        second={
            "trajectory_id": "tr-second",
            "proposal": {"action_id": "restart_service", "target": "cartservice"},
            "kept": ["operator-rejection"],
            "dropped": [],
            "cost_usd": 0.68,
        }
    )

    outcome = run(steps, tmp_path)

    assert outcome.result == "unchanged"
    assert "the same action against the same target" in outcome.reason


def test_an_abstention_counts_as_the_loop_working(tmp_path: Path) -> None:
    """ADR-0022 §1.2: an abstention is a proposal, and for `cart-dependency-latency` - a sidecar
    no allowlisted action can remove - it is the **correct** second answer. Prediction 8 says so
    before the run, so the scoring has to be able to say it too."""
    steps = FakeSteps(
        second={
            "trajectory_id": "tr-second",
            "proposal": {"action_id": "", "target": "", "remediation_class": "none"},
            "kept": ["operator-rejection"],
            "dropped": [],
            "cost_usd": 0.6,
        }
    )

    outcome = run(steps, tmp_path, rejectloop.PAIRS[1])

    assert outcome.result == "abstained"
    assert "no permitted action fits" in outcome.reason


def test_a_rejection_dropped_from_the_brief_is_recorded_as_not_reaching_the_agent(
    tmp_path: Path,
) -> None:
    """Prediction 6 is *most likely to fail for a boring reason* - a section dropped by the
    briefing budget. `essential=True` should prevent it; this is how it would be seen if it did
    not, rather than the run quietly measuring an agent that was never told."""
    steps = FakeSteps(
        second={
            "trajectory_id": "tr-second",
            "proposal": {"action_id": "restart_service", "target": "redis-cart"},
            "kept": ["verdict-and-radius"],
            "dropped": ["operator-rejection"],
            "cost_usd": 0.7,
        }
    )

    outcome = run(steps, tmp_path)

    assert outcome.rejection_reached_the_brief is False
    assert outcome.dropped_sections == ["operator-rejection"]


def test_the_evidence_is_written_for_every_step(tmp_path: Path) -> None:
    run(FakeSteps(), tmp_path)

    written = sorted(p.name for p in (tmp_path / "e").iterdir())
    assert written == [
        "first-proposal.json",
        "inject.txt",
        "loop.log",
        "outcome.json",
        "rejection.json",
        "second.json",
    ]


# --- the summary --------------------------------------------------------------


def test_the_summary_says_n_equals_two_and_never_calls_it_a_rate(tmp_path: Path) -> None:
    outcomes = [run(FakeSteps(), tmp_path)]

    text = rejectloop.summary(outcomes)

    assert "n = 2" in text and "R = 1" in text
    assert "existence demonstration, not a rate" in text
    assert "Model spend" in text


def test_the_driver_refuses_to_rewrite_captured_evidence(tmp_path: Path, monkeypatch: Any) -> None:
    """The repair replay's rule, and for the same reason: the first three attempts of T6.2's proof
    kept their evidence only because somebody renamed the directories by hand."""
    captured = tmp_path / "t6.3-rejection-loop" / "cart-dependency-latency"
    captured.mkdir(parents=True)
    (captured / "outcome.json").write_text("{}")
    monkeypatch.setenv("FAULTLINE_API_PASSWORD", "unused")
    monkeypatch.setattr(rejectloop, "RealSteps", lambda *a, **k: FakeSteps())

    with pytest.raises(SystemExit):
        rejectloop.run_cli(
            [
                "--only",
                "cart-dependency-latency",
                "--evidence-root",
                str(tmp_path),
                "--settle",
                "0",
                "--postgres-dsn",
                "postgresql://unused",
            ]
        )

    assert (captured / "outcome.json").read_text() == "{}"


def test_the_cli_refuses_without_the_api_password(tmp_path: Path, monkeypatch: Any) -> None:
    """The rejection is authenticated, because the surface is what is being measured. A driver
    that fell back to calling the machine directly would quietly measure something else."""
    monkeypatch.delenv("FAULTLINE_API_PASSWORD", raising=False)

    with pytest.raises(SystemExit):
        rejectloop.run_cli(["--evidence-root", str(tmp_path), "--postgres-dsn", "postgresql://x"])
