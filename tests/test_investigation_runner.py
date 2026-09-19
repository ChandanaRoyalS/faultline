"""The runner that advances TRIAGING inside the product (T5.5c, defect twenty-nine).

The first live deployment opened an incident from a real fault and left it in TRIAGING with
"not yet investigated" on the public page: the orchestrator admits, the harness investigates, and
the harness is not deployed. These tests pin what the runner does and - just as much - what it must
not do: run before the settle window, run twice for one incident, run at all on a development
machine, or run with bounds other than the ones every published figure was measured under.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from faultline.orchestrator.models import Incident, IncidentState
from faultline.orchestrator.runner import InvestigationRunner, investigate_command
from faultline.orchestrator.settings import OrchestratorSettings
from faultline.orchestrator.store import InMemoryIncidentStore

REPO_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 7, 8, 5, tzinfo=UTC)


def _incident(incident_id: str, state: IncidentState, opened_ago: timedelta) -> Incident:
    return Incident(id=incident_id, state=state, opened_at=NOW - opened_ago)


def _runner(
    store: InMemoryIncidentStore, calls: list[list[str]], code: int = 0
) -> InvestigationRunner:
    def fake_run(command: list[str]) -> int:
        calls.append(list(command))
        return code

    return InvestigationRunner(
        store,
        settle=timedelta(seconds=90),
        command=["faultline-investigate", "--max-tokens", "1"],
        run=fake_run,
        now=lambda: NOW,
    )


def test_an_admitted_incident_is_investigated_after_the_settle_window() -> None:
    store = InMemoryIncidentStore()
    store.save(_incident("settled", IncidentState.TRIAGING, timedelta(seconds=91)))
    store.save(_incident("fresh", IncidentState.TRIAGING, timedelta(seconds=30)))
    calls: list[list[str]] = []

    ran = _runner(store, calls).run_once()

    assert ran == ["settled"], "the fresh one is still inside its settle window"
    assert calls == [["faultline-investigate", "--max-tokens", "1", "settled"]], (
        "the incident id goes last, after the bounds, exactly as the harness invokes it"
    )


def test_only_triaging_incidents_are_candidates() -> None:
    """OPEN and QUEUED have not been admitted - the cap has not said yes. PLANNING onward has
    already been picked up. Terminal states are over. None of them is the runner's business."""
    store = InMemoryIncidentStore()
    for state in IncidentState:
        store.save(_incident(state.value, state, timedelta(hours=1)))
    calls: list[list[str]] = []

    ran = _runner(store, calls).run_once()

    assert ran == ["triaging"]


def test_an_investigation_that_keeps_failing_is_not_retried_forever() -> None:
    """`faultline-investigate` exits 3 (refused) without touching the incident's state, so the
    incident is still TRIAGING on the next poll. Without a bound the runner would bill for a
    refusal every fifteen seconds until someone noticed."""
    store = InMemoryIncidentStore()
    store.save(_incident("stuck", IncidentState.TRIAGING, timedelta(minutes=5)))
    calls: list[list[str]] = []
    runner = _runner(store, calls, code=3)

    assert runner.run_once() == ["stuck"]
    assert runner.run_once() == ["stuck"]
    assert runner.run_once() == [], "two attempts, then it is left where it is"
    assert runner.exit_codes == [("stuck", 3), ("stuck", 3)]
    assert runner.attempts == {"stuck": 2}


def test_oldest_first_and_one_at_a_time() -> None:
    store = InMemoryIncidentStore()
    store.save(_incident("second", IncidentState.TRIAGING, timedelta(minutes=2)))
    store.save(_incident("first", IncidentState.TRIAGING, timedelta(minutes=3)))
    calls: list[list[str]] = []

    assert _runner(store, calls).run_once() == ["first", "second"]
    assert [c[-1] for c in calls] == ["first", "second"], "sequential, in admission order"


# --- the configuration is the measured one, and it is off where the harness runs -----------------


def test_the_runner_is_off_by_default() -> None:
    """A development machine runs `make demo` and `make eval`, which launch the investigation
    themselves. A runner active beside them investigates every incident twice and bills twice."""
    assert OrchestratorSettings(_env_file=None).investigate is False  # type: ignore[call-arg]


def test_nothing_outside_the_deployment_turns_it_on() -> None:
    dev_surfaces = [
        REPO_ROOT / "docker-compose.yml",
        REPO_ROOT / "Makefile",
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "RELEASE.md",
        REPO_ROOT / ".github" / "workflows" / "ci.yml",
        REPO_ROOT / ".github" / "workflows" / "eval-smoke.yml",
        REPO_ROOT / ".github" / "workflows" / "eval-nightly.yml",
    ]
    for path in dev_surfaces:
        text = path.read_text()
        fenced = "\n".join(b for i, b in enumerate(text.split("```")) if i % 2 == 1)
        haystack = fenced if path.suffix == ".md" else text
        assert "FAULTLINE_ORCH_INVESTIGATE" not in haystack, path
        assert "--investigate" not in haystack, path


def test_the_deployment_turns_it_on_in_the_container_that_holds_the_key() -> None:
    import yaml

    compose = yaml.safe_load((REPO_ROOT / "deploy" / "compose.yml").read_text())
    orchestrator = compose["services"]["orchestrator"]["environment"]
    assert str(orchestrator.get("FAULTLINE_ORCH_INVESTIGATE")).lower() in {"1", "true"}
    assert "ANTHROPIC_API_KEY" in orchestrator, "the runner must live where the key is"
    assert "FAULTLINE_ORCH_INVESTIGATE" not in compose["services"]["faultline"]["environment"]


def test_the_settle_window_is_the_harness_s() -> None:
    """A live investigation that starts earlier or later than a scored one sees a different
    blast radius and is a different experiment."""
    from evalharness.run import SETTLE_AFTER_ALERT_SECONDS

    assert (
        OrchestratorSettings(_env_file=None).investigate_settle_seconds
        == SETTLE_AFTER_ALERT_SECONDS
    )  # type: ignore[call-arg]


def test_the_bounds_are_the_ones_make_eval_passes() -> None:
    """T4.7: every published figure was measured under these. The live configuration is read off
    the Makefile so it cannot drift from them without this failing."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    match = re.search(
        r"faultline-eval \$\(SCENARIO\) \$\(INTENT\) \\\n\s*(--max-tool-calls .*)", makefile
    )
    assert match, "the eval target's bounds moved; update this test's anchor"
    expected = match.group(1).split()

    command = investigate_command(OrchestratorSettings(_env_file=None))  # type: ignore[call-arg]
    assert command[0] == "faultline-investigate"
    assert command[1:] == expected, (command[1:], expected)


# --- T6.7 piece 3b: the process that kills investigations reconciles them --------------------


class RecordingTrajectories:
    """A trajectory store that remembers each `close_orphans` call and answers what it is told."""

    def __init__(self, closes: list[str]) -> None:
        self.calls: list[int] = []
        self._closes = closes

    def close_orphans(self, *, older_than_seconds: int) -> list[str]:
        self.calls.append(older_than_seconds)
        return list(self._closes)

    def recent_outcomes(self, limit: int) -> list[tuple[str | None, datetime | None]]:
        return []


def test_every_poll_reconciles_orphans_before_it_investigates(caplog: object) -> None:
    """**The 2026-09-19 drill's row had to be closed by hand.** Q72's reconciler ran in the
    sweep, which the deployment never runs, and this runner - whose subprocess is the thing that
    dies - never called it. Now every poll does, at the same ceiling the sweep uses, before it
    looks at what is due, so a killed run's row is `orphaned` by the next poll after the ceiling
    rather than whenever an operator remembers."""
    from faultline.agents.trajectory import orphan_ceiling_seconds

    store = InMemoryIncidentStore()
    trajectories = RecordingTrajectories(closes=["traj-killed"])
    runner = InvestigationRunner(
        store,
        settle=timedelta(seconds=90),
        command=["faultline-investigate"],
        run=lambda command: 0,
        now=lambda: NOW,
        trajectories=trajectories,
    )

    assert runner.run_once() == []
    assert runner.run_once() == []

    assert trajectories.calls == [orphan_ceiling_seconds(), orphan_ceiling_seconds()]
    assert runner.reconcile_orphans() == ["traj-killed"]


def test_without_a_trajectory_store_the_runner_reconciles_nothing_and_says_nothing() -> None:
    """A development machine's runner has none; the sweep is the reconciler there."""
    store = InMemoryIncidentStore()
    calls: list[list[str]] = []

    assert _runner(store, calls).reconcile_orphans() == []


# --- T6.7 piece 5: the cross-run half of the provider breaker -------------------------------------


class OutcomeTrajectories(RecordingTrajectories):
    def __init__(self, outcomes: list[tuple[str | None, datetime | None]]) -> None:
        super().__init__(closes=[])
        self.outcomes = outcomes

    def recent_outcomes(self, limit: int) -> list[tuple[str | None, datetime | None]]:
        return self.outcomes[:limit]


def _breaker_runner(
    store: InMemoryIncidentStore,
    calls: list[list[str]],
    trajectories: OutcomeTrajectories,
    *,
    code: int = 0,
    now: datetime = NOW,
) -> InvestigationRunner:
    def fake_run(command: list[str]) -> int:
        calls.append(list(command))
        return code

    return InvestigationRunner(
        store,
        settle=timedelta(seconds=90),
        command=["faultline-investigate"],
        run=fake_run,
        now=lambda: now,
        trajectories=trajectories,
        provider_cooldown_seconds=300.0,
        provider_open_after=2,
    )


def test_two_provider_unavailable_runs_defer_every_due_incident_until_the_cooldown() -> None:
    """**Computed from the record, not kept.** The last two trajectories ended
    `provider_unavailable` a minute ago, so nothing is started for four more minutes: the
    incidents stay `triaging`, the attempt budget is untouched, one warning line says so."""
    store = InMemoryIncidentStore()
    store.save(_incident("a", IncidentState.TRIAGING, timedelta(minutes=5)))
    store.save(_incident("b", IncidentState.TRIAGING, timedelta(minutes=4)))
    calls: list[list[str]] = []
    a_minute_ago = NOW - timedelta(seconds=60)
    trajectories = OutcomeTrajectories(
        [("provider_unavailable", a_minute_ago), ("provider_unavailable", a_minute_ago)]
    )
    runner = _breaker_runner(store, calls, trajectories)

    assert runner.provider_open() == pytest.approx(240.0)
    assert runner.run_once() == []
    assert runner.run_once() == []

    assert calls == [] and runner.attempts == {} and runner.deferred == 2


def test_one_provider_unavailable_run_is_not_an_outage() -> None:
    store = InMemoryIncidentStore()
    store.save(_incident("a", IncidentState.TRIAGING, timedelta(minutes=5)))
    calls: list[list[str]] = []
    trajectories = OutcomeTrajectories(
        [("provider_unavailable", NOW - timedelta(seconds=60)), ("dispatched", NOW)]
    )

    assert _breaker_runner(store, calls, trajectories).provider_open() is None
    assert _breaker_runner(store, calls, trajectories).run_once() == ["a"]


def test_after_the_cooldown_the_next_run_is_the_trial_and_a_6_does_not_cost_an_attempt() -> None:
    store = InMemoryIncidentStore()
    store.save(_incident("a", IncidentState.TRIAGING, timedelta(minutes=10)))
    calls: list[list[str]] = []
    six_minutes_ago = NOW - timedelta(seconds=360)
    trajectories = OutcomeTrajectories(
        [("provider_unavailable", six_minutes_ago), ("provider_unavailable", six_minutes_ago)]
    )
    runner = _breaker_runner(store, calls, trajectories, code=6)

    assert runner.provider_open() is None, "cooldown passed: half-open"
    assert runner.run_once() == ["a"], "the trial run"
    assert runner.attempts["a"] == 0, "exit 6 is the provider's, not the incident's attempt"
    assert runner.run_once() == ["a"], "and it is still due, not given up on"


def test_the_exit_code_and_the_cooldown_are_the_same_on_both_sides() -> None:
    """The orchestrator restates the agent runtime's exit code and the agent's cooldown; the two
    packages import in one direction only, so a test holds the restatements."""
    from faultline.agents.runner import Exit
    from faultline.agents.settings import AgentSettings
    from faultline.orchestrator import runner as orchestrator_runner

    assert orchestrator_runner.PROVIDER_UNAVAILABLE_EXIT == Exit.PROVIDER_UNAVAILABLE
    assert OrchestratorSettings().provider_cooldown_seconds == (
        AgentSettings().breaker_cooldown_seconds
    )


# --- T6.7 piece 6: the deployment's ceiling ------------------------------------------------------


class SpendingTrajectories(OutcomeTrajectories):
    def __init__(self, tokens: tuple[int, int]) -> None:
        super().__init__(outcomes=[])
        self._tokens = tokens
        self.asked: list[datetime] = []

    def tokens_since(self, moment: datetime) -> tuple[int, int]:
        self.asked.append(moment)
        return self._tokens


def _ceiling_runner(
    store: InMemoryIncidentStore,
    calls: list[list[str]],
    trajectories: SpendingTrajectories,
    ceiling: float,
) -> InvestigationRunner:
    def fake_run(command: list[str]) -> int:
        calls.append(list(command))
        return 0

    return InvestigationRunner(
        store,
        settle=timedelta(seconds=90),
        command=["faultline-investigate"],
        run=fake_run,
        now=lambda: NOW,
        trajectories=trajectories,
        max_usd_per_day=ceiling,
        usd_per_mtok=(5.0, 25.0),
    )


def test_at_the_day_s_ceiling_every_due_incident_waits_and_the_attempt_budget_is_untouched() -> (
    None
):
    """**Failure row 10, one level up.** On 2026-09-19 the deployment investigated three times
    unattended for $0.69 and nothing above the per-incident budget existed to stop it. The last
    24 hours' tokens, at the harness's prices, against `max_usd_per_day`, before every run."""
    store = InMemoryIncidentStore()
    store.save(_incident("a", IncidentState.TRIAGING, timedelta(minutes=5)))
    calls: list[list[str]] = []
    trajectories = SpendingTrajectories(tokens=(1_000_000, 0))  # $5.00 in
    runner = _ceiling_runner(store, calls, trajectories, ceiling=5.0)

    assert runner.spent_today() == pytest.approx(5.0)
    assert runner.over_ceiling() == pytest.approx(5.0)
    assert runner.run_once() == []
    assert calls == [] and runner.attempts == {} and runner.deferred == 1
    assert trajectories.asked and trajectories.asked[0] == NOW - timedelta(days=1)


def test_under_the_ceiling_runs_proceed_and_zero_means_no_ceiling() -> None:
    store = InMemoryIncidentStore()
    store.save(_incident("a", IncidentState.TRIAGING, timedelta(minutes=5)))
    calls: list[list[str]] = []

    under = _ceiling_runner(store, calls, SpendingTrajectories((900_000, 0)), ceiling=5.0)
    assert under.over_ceiling() is None
    assert under.run_once() == ["a"]

    store.save(_incident("b", IncidentState.TRIAGING, timedelta(minutes=5)))
    off = _ceiling_runner(store, calls, SpendingTrajectories((10_000_000, 0)), ceiling=0.0)
    assert off.over_ceiling() is None, "0 is off: $50 in a day and it still runs"
    assert "b" in off.run_once()


def test_the_default_ceiling_is_five_dollars_and_the_yesterday_loop_would_have_stopped() -> None:
    """The loop of 2026-09-19 spent $0.69 in three runs; the ceiling would not have caught that
    day. It exists for the day the series does not go stale."""
    assert OrchestratorSettings().max_usd_per_day == 5.0
