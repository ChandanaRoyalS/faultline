"""The run protocol's gate, discards, and stamp (T4.1). Hermetic - no world, no model.

`evalharness.gate` is exercised against the readings it would take rather than against a live
Prometheus: every check is a pure function of the numbers, and the two facts ADR-0022 makes it
encode are exactly the ones a live test would be least likely to produce on demand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from evalharness import gate
from evalharness.run import ZERO_STEP_DISCARD, RunDir, RunError, WorldLock, bundle_for, score

REPO_ROOT = Path(__file__).resolve().parents[1]

QUIET = {
    "firing_alerts": [],
    "p95": {"cartservice": 1.9, "checkoutservice": 35.0},
    "rates": {"cartservice": 4.2, "checkoutservice": 2.1, "frontend-proxy": 0.0},
    "uptimes": [("cartservice", 3600)],
    "injections": "no active injections",
}


def reading_with(settled: Exception | None = None, **overrides: Any) -> gate.GateReading:
    world = {**QUIET, **overrides}
    latest = {
        gate.METRIC_QUERIES["latency-p95"]: world["p95"],
        gate.METRIC_QUERIES["call-rate"]: world["rates"],
    }
    with (
        patch.object(gate, "firing_alerts", return_value=world["firing_alerts"]),
        patch.object(gate, "_latest_by_service", side_effect=lambda q, **_: latest[q]),
        patch.object(gate, "container_uptimes", return_value=world["uptimes"]),
        patch.object(gate, "require_settled_containers", side_effect=settled),
        patch.object(gate.baseline_mod, "active_injections", return_value=world["injections"]),
    ):
        return gate.read(overrides.get("open_incidents"))


# --- the gate ------------------------------------------------------------------


def test_a_quiet_world_passes() -> None:
    assert reading_with().passed


def test_frontend_proxy_at_zero_is_the_healthy_state_and_does_not_block() -> None:
    """**The first of ADR-0022's two known-good facts.** The committed clean baseline
    `evals/baselines/20260824T033742Z` records frontend-proxy at 181 consecutive samples of
    0.0, min and max alike. A gate that read zero traffic there as a fault would refuse every
    run forever."""
    reading = reading_with()

    assert reading.silent_services == ["frontend-proxy"]
    assert reading.unexpected_silent == []
    assert reading.passed


def test_any_other_service_at_zero_does_block() -> None:
    """T3.4's degraded world had accountingservice at 0.000 req/s, and a human caught it."""
    reading = reading_with(rates={"cartservice": 4.2, "accountingservice": 0.0})

    assert reading.unexpected_silent == ["accountingservice"]
    assert not reading.passed
    assert any("accountingservice" in why for why in reading.refusals)


def test_the_post_restart_hazard_is_the_recorders_own_gate_reused() -> None:
    """**The second known-good fact.** CATALOG.md: readings taken 0.8, 4.0 and 14.2 minutes
    after cart reverts were written up as evidence cartservice is bimodal and reaches 353ms.
    It is not. `require_settled_containers` is that fact as a gate and is reused, not
    restated - two copies of a five-minute rule is one of them going stale."""
    reading = reading_with(settled=gate.RehearsalError("up 42s\nmore"))

    assert not reading.passed
    assert any("up 42s" in why for why in reading.refusals)


def test_a_degraded_p95_blocks_and_names_the_service() -> None:
    """T3.4's world had checkoutservice and frontend pinned at 15000ms."""
    reading = reading_with(p95={"checkoutservice": 15000.0, "cartservice": 1.9})

    assert reading.p95_over_ceiling == {"checkoutservice": 15000.0}
    assert any("checkoutservice at 15000ms" in why for why in reading.refusals)


def test_an_open_incident_blocks_because_new_alerts_would_join_it() -> None:
    """T3.4b had to clear a stale `triaging` incident by hand, and T3.5's smoke lost an
    incident to a terminal state. A new alert correlating into an old incident is not a run."""
    reading = reading_with(open_incidents=["fb7ad21e"])
    assert not reading.passed
    assert any("fb7ad21e" in why for why in reading.refusals)


def test_the_gate_refuses_rather_than_warns() -> None:
    """ADR-0022 §3.1: a run that proceeds and is marked suspect produces a number someone will
    quote. `require` raises and nothing is injected."""
    with (
        patch.object(gate, "read", return_value=reading_with(firing_alerts=["A/svc"])),
        pytest.raises(gate.GateRefusedError, match="nothing was injected"),
    ):
        gate.require()


def test_the_readings_are_recorded_even_when_the_gate_passes() -> None:
    """A run's manifest saying what quiet looked like that day is what makes two runs
    comparable."""
    payload = reading_with().as_dict()
    assert payload["passed"] is True
    assert payload["services_reporting"] == 3
    assert payload["silent_services"] == ["frontend-proxy"]


# --- discards ------------------------------------------------------------------


def test_a_discarded_run_is_recorded_not_deleted(tmp_path: Path) -> None:
    """ADR-0022 §3.3, applied everywhere rather than only to holdout: the directory stays and
    says why it is not a result, so the number of runs cannot be changed by tidying."""
    run = RunDir("20260826T000000Z-test", root=tmp_path)
    run.manifest["scenario_id"] = "cart-redis-misconfig"

    run.discard("run failed", "the model boundary fell over")

    assert run.path.exists()
    marker = (run.path / "DISCARDED.md").read_text()
    assert "run failed" in marker and "the model boundary fell over" in marker
    assert json.loads((run.path / "manifest.json").read_text())["discarded"]["reason"] == (
        "run failed"
    )


def test_the_zero_step_row_is_an_explicit_discard_with_its_reason() -> None:
    """`f7261a74` exists: a trajectory written by a run that raised before the first model
    call. An empty row is indistinguishable from an investigation that produced no evidence,
    so it is neither counted nor silently dropped."""
    assert "f7261a74" in ZERO_STEP_DISCARD
    assert "no steps" in ZERO_STEP_DISCARD


# --- the world lock ------------------------------------------------------------


def test_the_world_lock_does_not_wait(tmp_path: Path) -> None:
    """Waiting is how two harness processes interleave injections with nothing in either log
    to show it."""
    path = tmp_path / "harness.lock"
    with (
        WorldLock(path),
        pytest.raises(RunError, match="another harness run holds"),
        WorldLock(path),
    ):
        pass


def test_the_lock_is_released_on_the_way_out(tmp_path: Path) -> None:
    path = tmp_path / "harness.lock"
    with WorldLock(path):
        assert path.exists()
    assert not path.exists()


# --- scoring assembly ----------------------------------------------------------


def test_a_run_scores_from_the_artifact_the_cli_wrote() -> None:
    """The harness reads a file the CLI produced, not the product's internals - ADR-0009's
    "public interfaces only"."""
    artifact = {
        "trajectory_id": "68ac9a67",
        "blast_radius": [
            "cartservice",
            "checkoutservice",
            "frontend",
            "loadgenerator",
            "adservice",
        ],
        "unmeasured_edges": 4,
        "verdict": {"fault_class": "bad_config", "remediation_class": "config_revert"},
        "flags": [],
        "failed_dispatches": [],
    }
    facts = {
        "tokens_in": 30888,
        "tokens_out": 12625,
        "runtime_version": "faultline/0.0.1+prompts:x",
    }

    scored = score(
        "r", "cart-dependency-latency", bundle_for("cart-dependency-latency"), artifact, facts, {}
    )

    assert scored.triage is not None and scored.triage.recall == 1.0
    assert scored.fault_class is not None and not scored.fault_class.correct
    assert scored.fault_class.dispute is not None
    assert scored.cost_usd == pytest.approx(30888 / 1e6 * 5 + 12625 / 1e6 * 25)
    assert scored.runtime_version.startswith("faultline/")


def test_the_two_alert_free_bundles_are_recognised_as_unrunnable() -> None:
    """`currency-cpu-throttle` and `flag-service-crashloop` have empty `alerts_over_window`
    and carry an `INVALID.md`. Neither can produce an incident, so neither can be
    investigated - seven dev bundles are runnable, not nine."""
    for scenario in ("currency-cpu-throttle", "flag-service-crashloop"):
        assert not bundle_for(scenario)["alerts_over_window"]
        assert (REPO_ROOT / "evals/scenarios/artifacts/dev" / scenario / "INVALID.md").exists()


# --- the stamp -----------------------------------------------------------------


def test_the_runtime_stamp_names_the_package_and_the_prompts() -> None:
    """It said `t3.3` on every trajectory ever written, including T3.5's three tasks later.
    A field whose job is to say what produced a record, and which is wrong for free, answers
    the question confidently and wrongly."""
    from faultline.agents.stamp import runtime_version

    stamp = runtime_version()
    assert stamp.startswith("faultline/")
    assert "+prompts:" in stamp
    assert "t3.3" not in stamp


def test_the_stamp_moves_when_a_prompt_moves() -> None:
    """The whole point: it is derived from the code the model was held to, so it cannot fall
    behind unless that code stops changing."""
    from faultline.agents import roles, stamp

    before = stamp.prompt_digest()
    stamp.prompt_digest.cache_clear()
    with patch.object(roles, "SCRIBE_SYSTEM", roles.SCRIBE_SYSTEM + " and also this"):
        after = stamp.prompt_digest()
    stamp.prompt_digest.cache_clear()

    assert before != after


def test_the_episode_wait_comes_from_the_bundle_not_a_constant() -> None:
    """**The first sweep discarded a scenario over this.** `min_episodes` was hard-coded to 2,
    and `frauddetection-memory-squeeze` alerts on exactly one service - a sparse service failing
    quietly pages nobody downstream. It could never satisfy the wait, timed out at 900s, and was
    recorded as though the world had not reacted. It had reacted exactly as its bundle says.
    """
    from evalharness.run import expected_episodes

    assert expected_episodes(bundle_for("frauddetection-memory-squeeze")) == 1
    assert expected_episodes(bundle_for("ad-memory-squeeze")) == 2, "two where the radius is wider"
    assert expected_episodes(bundle_for("cart-redis-misconfig")) == 2
    assert expected_episodes({"alerts_over_window": []}) == 1, "never waits for zero"


# --- transient retry (T4.3) ----------------------------------------------------

# Verbatim from run 20260826T061939Z's investigate.txt - the 529 that cost a scenario slot.
SWEEP_529 = (
    "FAILED MID-INVESTIGATION: did not start - OverloadedError: Error code: 529 - "
    "{'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}"
)

# Verbatim from run 20260826T045545Z - the exhausted credit balance, which is terminal.
SWEEP_400 = (
    "FAILED MID-INVESTIGATION: did not start - BadRequestError: Error code: 400 - "
    "{'type': 'error', 'error': {'type': 'invalid_request_error', 'message': "
    "'Your credit balance is too low to access the Anthropic API.'}}"
)


# Verbatim from run 20260826T121554Z - a 529 that landed *after* the run had done work, so the
# incident was already FAILED and the retry could only ever be refused.
SWEEP_529_MIDRUN = (
    "FAILED MID-INVESTIGATION: OverloadedError: Error code: 529 - "
    "{'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}"
)


def test_a_transient_failure_after_work_is_not_retried() -> None:
    """**T4.5's sweep lost two scenarios to this.** A run that got somewhere and then failed
    leaves the incident `FAILED`, which ADR-0016 makes terminal - so the retry can only ever be
    told the incident is not investigable, and it was, twice, at the cost of two world
    injections and forty minutes.

    Only a failed *start* is retryable, and that is not a policy choice: it is the one case that
    leaves the incident in `triaging`, untouched.
    """
    from evalharness.run import transient_signal

    assert transient_signal(SWEEP_529_MIDRUN) is None, "it did work; the incident is terminal"
    assert "overloaded_error" in SWEEP_529_MIDRUN, "and it is transient - that is not enough"


def test_the_sweeps_529_is_recognised_as_transient() -> None:
    """**The failure that cost a scenario slot.** One 529 on the first model call, and the run
    spent an injection, a correlation wait, a revert and ten minutes to learn the provider was
    busy (`evals/runs/SWEEP-2026-08-26.md`)."""
    from evalharness.run import transient_signal

    assert transient_signal(SWEEP_529) == "overloaded_error"


def test_an_exhausted_credit_balance_is_not_retried() -> None:
    """A 400 covers a malformed request and an empty account, and both are terminal. T4.1's
    second run died on the latter; retrying would have burned three more world injections to
    learn the same thing."""
    from evalharness.run import transient_signal

    assert transient_signal(SWEEP_400) is None


def test_a_transient_failure_is_retried_and_every_attempt_is_recorded(tmp_path: Path) -> None:
    """A scored run says how many attempts it needed, not just that it eventually worked."""
    from evalharness import run as run_mod

    calls: list[int] = []

    def flaky(incident_id: str, scenario_id: str, out: Path, args: Any) -> tuple[int, str]:
        calls.append(1)
        return (4, SWEEP_529) if len(calls) < 3 else (0, "verdict produced")

    with (
        patch.object(run_mod, "_investigate", flaky),
        patch.object(run_mod.time, "sleep"),
        patch.object(run_mod, "RETRY_DELAYS_SECONDS", (1, 2, 3)),
    ):
        code, _text, attempts = run_mod._investigate_with_retry("i", "s", tmp_path, None)

    assert code == 0 and len(calls) == 3
    assert [a["attempt"] for a in attempts] == [1, 2, 3]
    assert [a["waited_seconds"] for a in attempts] == [0, 1, 2], (
        "delays are recorded, not just taken"
    )
    assert attempts[0]["transient_signal"] == "overloaded_error"
    assert attempts[-1]["transient_signal"] is None


def test_a_terminal_failure_is_not_retried_at_all(tmp_path: Path) -> None:
    """One attempt, and the reason it stopped is on the record."""
    from evalharness import run as run_mod

    calls: list[int] = []

    def terminal(incident_id: str, scenario_id: str, out: Path, args: Any) -> tuple[int, str]:
        calls.append(1)
        return 4, SWEEP_400

    with patch.object(run_mod, "_investigate", terminal), patch.object(run_mod.time, "sleep"):
        code, _t, attempts = run_mod._investigate_with_retry("i", "s", tmp_path, None)

    assert code == 4 and len(calls) == 1
    assert attempts == [
        {"attempt": 1, "waited_seconds": 0, "exit_code": 4, "transient_signal": None}
    ]


def test_exhausting_the_retries_still_discards(tmp_path: Path) -> None:
    """The bound is a bound. A provider still refusing after three and a half minutes is having
    an outage, and a sweep should report that rather than sit in it - the run discards exactly
    as it did before retry existed."""
    from evalharness import run as run_mod

    calls: list[int] = []

    def always_busy(incident_id: str, scenario_id: str, out: Path, args: Any) -> tuple[int, str]:
        calls.append(1)
        return 4, SWEEP_529

    with (
        patch.object(run_mod, "_investigate", always_busy),
        patch.object(run_mod.time, "sleep"),
    ):
        code, _t, attempts = run_mod._investigate_with_retry("i", "s", tmp_path, None)

    assert code == 4
    assert len(calls) == 1 + len(run_mod.RETRY_DELAYS_SECONDS) == 4
    assert all(a["transient_signal"] == "overloaded_error" for a in attempts)


SWEEP_1_DIGEST = "59bf438b2a96"
"""The pipeline every row of `evals/runs/SWEEP-2026-08-26.md` was produced by."""

SWEEP_2_DIGEST = "53fafe9c12bc"
"""The pipeline after T4.5 added the taxonomy instruction to the synthesizer.

**The stamp moved on purpose, and it moving is the measurement.** T4.3's version of this test
pinned the first digest and said that if it ever changed, the sweep's rows would be from a
different experiment than the next run. It changed, deliberately, and they are - which is why
T4.5 re-ran all seven scenarios rather than comparing against the old numbers.
"""


def test_the_stamp_names_which_pipeline_produced_a_run() -> None:
    """`runtime_version` is the package version plus a digest over every role system prompt and
    every contract schema, so it moves when and only when the agent is a different agent.

    Both known values are recorded here. A change that lands on neither is a third pipeline, and
    any table comparing it to either sweep needs its own re-run.
    """
    from faultline.agents.stamp import prompt_digest

    assert prompt_digest() == SWEEP_2_DIGEST, (
        f"expected the taxonomy-instruction pipeline {SWEEP_2_DIGEST}. If a prompt or a contract "
        f"moved again, neither sweep in evals/runs/ describes the current agent."
    )
    assert SWEEP_1_DIGEST != SWEEP_2_DIGEST, "the two sweeps are two experiments"


def test_the_harness_side_paths_are_not_covered_by_the_stamp() -> None:
    """Retry, the gate, the scorer and the judge all live in `evalharness`, which the digest
    does not read - so a harness fix does not invalidate a sweep, and a prompt change does."""
    import evalharness.judge
    import evalharness.run
    from faultline.agents import stamp

    covered = stamp.prompt_digest.__doc__ or ""
    assert "roles" in covered and "contracts" in covered
    assert "evalharness" not in covered
    assert evalharness.run.__name__.startswith("evalharness")
    assert evalharness.judge.__name__.startswith("evalharness")
