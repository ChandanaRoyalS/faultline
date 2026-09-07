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
