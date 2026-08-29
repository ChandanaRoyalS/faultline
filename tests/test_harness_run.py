"""The run protocol's gate, discards, and stamp (T4.1). Hermetic - no world, no model.

`evalharness.gate` is exercised against the readings it would take rather than against a live
Prometheus: every check is a pure function of the numbers, and the two facts ADR-0022 makes it
encode are exactly the ones a live test would be least likely to produce on demand.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from evalharness import gate
from evalharness.run import (
    CORRELATE_CEILING_SECONDS,
    CORRELATE_GAP_SECONDS,
    CORRELATE_SCRAPES,
    SCRAPE_INTERVAL_SECONDS,
    ZERO_STEP_DISCARD,
    NoAlertError,
    RunDir,
    RunError,
    WorldLock,
    WorldStoppedReportingError,
    bundle_for,
    score,
    wait_for_incident,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

QUIET = {
    "firing_alerts": [],
    "p95": {"cartservice": 1.9, "checkoutservice": 35.0},
    "rates": {"cartservice": 4.2, "checkoutservice": 2.1, "frontend-proxy": 0.0},
    "uptimes": [("cartservice", 3600)],
    "injections": "no active injections",
}


NOW = datetime(2026, 8, 26, 12, 30, 0, tzinfo=UTC)
"""A fixed clock, so a settle-window test is arithmetic rather than a race."""

SETTLE = timedelta(seconds=300)
"""The orchestrator's default. Patched in the helper so these tests do not read the
environment; `test_the_gate_reads_the_settle_window_from_the_orchestrator` is the one that
checks the real wiring."""


SAMPLES_IN_WINDOW = 12
"""15s steps over the gate's 180s p95 window - what `_window_by_service` actually returns."""


def reading_with(settled: Exception | None = None, **overrides: Any) -> gate.GateReading:
    world = {**QUIET, **overrides}
    # A bare number means "this value for the whole window", which is what every test written
    # before T7.14 meant by a p95 reading. A list is an explicit window, sample by sample.
    windows = {
        service: list(value) if isinstance(value, list) else [value] * SAMPLES_IN_WINDOW
        for service, value in world["p95"].items()
    }
    latest = {
        gate.METRIC_QUERIES["latency-p95"]: {s: v[-1] for s, v in windows.items()},
        gate.METRIC_QUERIES["call-rate"]: world["rates"],
    }
    with (
        patch.object(gate, "firing_alerts", return_value=world["firing_alerts"]),
        patch.object(gate, "_latest_by_service", side_effect=lambda q, **_: latest[q]),
        patch.object(gate, "_window_by_service", side_effect=lambda q, **_: windows),
        patch.object(gate, "container_uptimes", return_value=world["uptimes"]),
        patch.object(gate, "require_settled_containers", side_effect=settled),
        patch.object(gate.baseline_mod, "active_injections", return_value=world["injections"]),
        patch.object(gate, "now", return_value=world.get("now", NOW)),
        patch.object(gate, "settle_window", return_value=world.get("window", SETTLE)),
    ):
        return gate.read(overrides.get("open_incidents"), overrides.get("resolved_incidents"))


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


# --- the settle window (T4.13) ------------------------------------------------
#
# T4.7's first sweep attempt lost a scenario to this. An incident had been resolved by hand
# a few minutes earlier; the next scenario's alerts arrived inside the orchestrator's settle
# window, correlated into that resolved incident and reopened it, and the run that should
# have had its own incident had nothing to investigate - 22 events, one incident. The gate
# refused on non-terminal incidents and was blind to recently-terminal ones. The fix at the
# time was a person noticing and waiting the window out.

T47_INCIDENT = "8e8abd45-3e37-48c0-aa52-c5403bf6ae83"
"""The shape of the record that caused it: an id and a `resolved_at`."""


def test_an_incident_resolved_inside_the_settle_window_blocks() -> None:
    """It is terminal, so the open-incident check passes it, and it will still swallow this
    run's alerts - which is the whole of the T4.7 defect."""
    resolved_at = NOW - timedelta(seconds=120)
    reading = reading_with(resolved_incidents=[(T47_INCIDENT, resolved_at)])

    assert reading.open_incidents == [], "terminal: the old check sees nothing wrong"
    assert not reading.passed
    assert reading.settling_incidents == [
        {
            "incident_id": T47_INCIDENT,
            "resolved_at": resolved_at.isoformat(),
            "seconds_remaining": 180,
        }
    ]


def test_an_incident_resolved_outside_the_settle_window_does_not_block() -> None:
    """The refusal has to end on its own, or it is a permanent block rather than a wait."""
    reading = reading_with(resolved_incidents=[(T47_INCIDENT, NOW - timedelta(seconds=301))])

    assert reading.settling_incidents == []
    assert reading.passed


def test_the_boundary_is_the_window_exactly() -> None:
    """One second either side, so an off-by-one cannot hide behind a generous fixture."""
    assert not reading_with(
        resolved_incidents=[(T47_INCIDENT, NOW - timedelta(seconds=299))]
    ).passed
    assert reading_with(resolved_incidents=[(T47_INCIDENT, NOW - timedelta(seconds=300))]).passed


def test_the_refusal_says_which_incident_when_it_resolved_and_how_long_to_wait() -> None:
    """A refusal a person can act on by waiting, which is exactly what T4.7 did by hand.
    Every part of that sentence is load-bearing: without the id you cannot tell which run
    left it, without the resolution time you cannot tell whether it is yours, and without
    the remaining seconds you do not know whether to wait or to go and look."""
    resolved_at = NOW - timedelta(seconds=45)
    reading = reading_with(resolved_incidents=[(T47_INCIDENT, resolved_at)])

    why = "\n".join(reading.refusals)
    assert T47_INCIDENT in why
    assert resolved_at.isoformat() in why
    assert "300s settle window" in why
    assert "Wait 255s." in why
    assert "reopen it rather than open a new incident" in why


def test_several_settling_incidents_are_all_named_oldest_first() -> None:
    reading = reading_with(
        resolved_incidents=[
            ("younger", NOW - timedelta(seconds=10)),
            ("older", NOW - timedelta(seconds=200)),
        ]
    )

    assert [row["incident_id"] for row in reading.settling_incidents] == ["older", "younger"]


def test_the_gate_reads_the_settle_window_from_the_orchestrator() -> None:
    """**Not a copied constant.** ADR-0016 calls this window a placeholder to be replaced by
    measurement, so a second copy here would go stale the moment it is. The gate must follow a
    deployment that changes it, with no edit."""
    from faultline.orchestrator.settings import OrchestratorSettings

    assert gate.settle_window() == timedelta(seconds=OrchestratorSettings().settle_window_seconds)

    # Through the environment, which is how a deployment would actually move it.
    with patch.dict(os.environ, {"FAULTLINE_ORCH_SETTLE_WINDOW_SECONDS": "900"}):
        assert gate.settle_window() == timedelta(seconds=900)


def test_a_gate_read_with_no_incident_arguments_never_refuses_on_settling() -> None:
    """`confirm_recovery` calls the gate this way on purpose. After a revert this run's own
    incident has just resolved and is inside the window by construction, so a recovery check
    that applied this refusal would fail every run against the fault it had just fixed."""
    assert reading_with().settling_incidents == []
    assert reading_with().passed


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

SWEEP_4_DIGEST = "bf7605651ef2"
"""The pipeline T4.12 built, measured, and **rejected**. Never HEAD after that experiment closed.

T4.12 taught the planner that an empty stream is silence rather than a bad query. It did what it
said - re-issues after silence fell, `trace_query` adoption rose 3/7 to 5/7 - and it moved dispatch
away from the failing service, which cost three scenarios to win one: dev coverage 6/7 to 4/7. The
pre-registration had named that floor in advance, so the instruction was reverted and the stamp
returned to `SWEEP_2_DIGEST`.

The digest stays here because `evals/runs/SWEEP-2026-08-27-evidence.md` is a record of seven live
runs and the freeze guard's lineage check has to be able to place it. A rejected pipeline is still
a pipeline this repository ran.

There is no `SWEEP_3_DIGEST`: dev sweep 3 raised the `changes` bound and moved no prompt, so it
ran on `SWEEP_2_DIGEST`. That is the point of T4.7's decision to keep budget bounds out of the
stamp - S2 and S3 are the same agent given different room, and the stamp says so.
"""

SWEEP_5_DIGEST = "1b0e7cbb4c47"
"""The pipeline T4.14 built: silence changes the evidence CLASS, not the SUBJECT.

T4.12's formulation taught switching vantage and never taught returning, and its three
regressions were all failing-service dispatch collapses. This one separates the halves and keeps
the localized service's claim on the plan. Its primary endpoint is the dispatch count at the
failing service, which S4 measured as the thing that actually predicts the outcome.
"""


def test_the_stamp_names_which_pipeline_produced_a_run() -> None:
    """`runtime_version` is the package version plus a digest over every role system prompt and
    every contract schema, so it moves when and only when the agent is a different agent.

    Both known values are recorded here. A change that lands on neither is a third pipeline, and
    any table comparing it to either sweep needs its own re-run.
    """
    from faultline.agents.stamp import prompt_digest

    assert prompt_digest() == SWEEP_5_DIGEST, (
        f"expected the return-to-locus pipeline {SWEEP_5_DIGEST}. If a prompt or a contract "
        f"moved again, no sweep in evals/runs/ describes the current agent."
    )
    assert len({SWEEP_1_DIGEST, SWEEP_2_DIGEST, SWEEP_4_DIGEST, SWEEP_5_DIGEST}) == 4, (
        "four experiments"
    )


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


# --- the demo run's exclusion (T5.3) ------------------------------------------


def test_a_demo_run_is_marked_in_its_manifest() -> None:
    """`--demo` is the only thing that separates a demo from any other run.

    Everything else is deliberately identical - same gate, same revert, same recovery check,
    same run directory - because a demo that takes a shortcut demonstrates the shortcut.
    """
    from evalharness.run import parser

    assert parser().parse_args(["cart-redis-misconfig"]).demo is False
    assert parser().parse_args(["cart-redis-misconfig", "--demo"]).demo is True


def test_no_aggregate_counts_a_demo_run() -> None:
    """The rule the demo depends on, as a predicate rather than a convention.

    A demo is re-run to be watched, on whichever scenario tells the best story. Counting one
    would weight every published figure toward the scenario picked for being watchable - and
    "remember to exclude the demo" is the kind of rule that holds only until the next person
    to write an aggregate has not heard it.
    """
    from evalharness.run import counts_toward_aggregates

    assert counts_toward_aggregates({"scenario_id": "x"}) is True
    assert counts_toward_aggregates({"scenario_id": "x", "demo": False}) is True
    assert counts_toward_aggregates({"scenario_id": "x", "demo": True}) is False


def test_the_judge_skips_demo_runs_unless_one_is_named(tmp_path: Path) -> None:
    """The enforcement point: the judge is what enumerates runs, so it is where the
    exclusion has to hold. Naming a demo run explicitly still reaches it - the rule is
    that no aggregate counts it, not that nobody may look at it."""
    from evalharness.judge import load_run

    scored = {
        "scenario_id": "cart-redis-misconfig",
        "run_id": "demo-run",
        "models": {"planner": "claude-opus-5"},
        "categories": {},
    }
    run_dir = tmp_path / "20260828T000000Z-cart-redis-misconfig"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"demo": True, "score": scored}))

    assert load_run(run_dir) is None, "a sweep must not pick up a demo run"
    assert load_run(run_dir, allow_demo=True) is not None, "naming it explicitly still works"

    (run_dir / "manifest.json").write_text(json.dumps({"score": scored}))
    assert load_run(run_dir) is not None, "an ordinary run is unaffected"


# --- T7.12: the wait counts scrapes, not seconds ------------------------------------------


class VirtualWorld:
    """A world on a virtual clock, so a sixteen-minute outage is arithmetic, not sixteen minutes.

    Scrapes accrue one per `SCRAPE_INTERVAL_SECONDS` while the world is reporting and not at all
    while it is silent - which is the single property the whole mechanism turns on.
    """

    def __init__(
        self,
        *,
        silent_from: float | None = None,
        silent_until: float = float("inf"),
        incident_at: float | None = None,
    ) -> None:
        self.t = 0.0
        self.silent_from = silent_from
        self.silent_until = silent_until
        self.incident_at = incident_at
        self.polls = 0

    # the clock
    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def reporting_at(self, when: float) -> bool:
        if self.silent_from is None:
            return True
        return not (self.silent_from <= when < self.silent_until)

    def scrapes_over(self, window_seconds: int) -> int:
        """Count the scrape ticks inside the trailing window that actually happened."""
        low = max(0.0, self.t - window_seconds)
        ticks = 0
        tick = 0.0
        while tick <= self.t:
            if tick >= low and self.reporting_at(tick):
                ticks += 1
            tick += SCRAPE_INTERVAL_SECONDS
        return ticks

    # the database
    def rows(self) -> list[tuple[str, int]]:
        self.polls += 1
        if self.incident_at is not None and self.t >= self.incident_at:
            return [("incident-1", 2)]
        return []


class _FakeCursor:
    def __init__(self, world: VirtualWorld) -> None:
        self.world = world

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, *args: object) -> None:
        return None

    def fetchall(self) -> list[tuple[str, int]]:
        return self.world.rows()


class _FakeConn:
    def __init__(self, world: VirtualWorld) -> None:
        self.world = world

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.world)


def drive(world: VirtualWorld) -> str:
    """Run the real `wait_for_incident` against the virtual world."""
    fake_time = SimpleNamespace(monotonic=world.monotonic, sleep=world.sleep)
    with (
        patch("evalharness.run.time", fake_time),
        patch("evalharness.run.scrapes_over", world.scrapes_over),
        patch("psycopg.connect", lambda dsn: _FakeConn(world)),
    ):
        return wait_for_incident("dsn://test", NOW, min_episodes=2)


def test_the_scrape_interval_matches_the_world_it_is_denominated_in() -> None:
    """The constant is hand-held, so the config is what proves it right.

    `SCRAPE_INTERVAL_SECONDS` is not read from the mounted config at runtime (see its docstring);
    this is the pin that keeps it honest. Wrong here would silently shorten every wait.
    """
    config = (REPO_ROOT / "compose" / "prometheus" / "prometheus-config.yaml").read_text()
    assert f"scrape_interval: {SCRAPE_INTERVAL_SECONDS}s" in config


def test_a_sixteen_minute_gap_does_not_spend_the_budget_and_the_alert_still_lands() -> None:
    """**T7.11's shape, which the wall-clock deadline turned into a discard.**

    The world goes silent for sixteen minutes and then pages. Under the old 900s wall-clock
    deadline the wait expired at T+900s - inside the gap, before the world had said anything -
    and `frauddetection-memory-squeeze` was recorded as a fault that does not alert. It alerts.

    Counting scrapes, those sixteen minutes cost nothing, because nothing happened in them.
    """
    world = VirtualWorld(silent_from=60.0, silent_until=1020.0, incident_at=1100.0)
    assert drive(world) == "incident-1"

    # The gap is longer than the deadline it replaced, which is exactly why the old unit failed.
    assert 1020.0 - 60.0 > 900.0
    # And the budget was nowhere near spent: silence buys the world no chances and costs it none.
    assert world.scrapes_over(int(world.t) + 1) < CORRELATE_SCRAPES


def test_a_world_that_stops_reporting_is_discarded_as_a_gap_not_as_a_quiet_fault() -> None:
    """The distinction the whole task exists to make: nothing was measured about the scenario."""
    world = VirtualWorld(silent_from=60.0)  # never comes back
    with pytest.raises(WorldStoppedReportingError) as caught:
        drive(world)

    assert caught.value.discard_reason == "metrics-gap"
    assert "stopped reporting" in str(caught.value)
    # It says what it is NOT, because that is the mistake this replaces.
    assert "NOT evidence that the fault does not alert" in str(caught.value)
    # The backstop is what ended it, not the budget.
    assert world.t >= CORRELATE_CEILING_SECONDS


def test_a_reporting_world_that_never_pages_is_the_genuine_negative() -> None:
    """The other path: the world had every one of its chances and the fault took none."""
    world = VirtualWorld()  # reporting throughout, no incident ever
    with pytest.raises(NoAlertError) as caught:
        drive(world)

    assert caught.value.discard_reason == "no-alert"
    assert "no telemetry gap seen" in str(caught.value)
    # The budget, not the ceiling, is what stopped it - the scrapes were really spent.
    assert world.t < CORRELATE_CEILING_SECONDS
    assert world.scrapes_over(int(world.t) + 1) >= CORRELATE_SCRAPES
    # And on a healthy world the new unit spends its budget at exactly the old deadline, which
    # is the point: 900s of coverage was never wrong, denominating it in wall clock was.
    assert world.t == CORRELATE_SCRAPES * SCRAPE_INTERVAL_SECONDS == 900


def test_the_two_discards_are_distinguishable_in_the_manifest(tmp_path: Path) -> None:
    """`run.discard` records the carried reason, so the manifest says which finding this was."""
    assert WorldStoppedReportingError.discard_reason != NoAlertError.discard_reason
    for error, expected in (
        (WorldStoppedReportingError("gap"), "metrics-gap"),
        (NoAlertError("quiet"), "no-alert"),
        (RunError("something else"), "run failed"),
    ):
        assert isinstance(error, RunError)
        run = RunDir(tmp_path / expected)
        run.discard(error.discard_reason, str(error))
        manifest = json.loads((tmp_path / expected / "manifest.json").read_text())
        assert manifest["discarded"]["reason"] == expected


def test_the_budget_covers_the_longest_onset_ever_recorded() -> None:
    """The derivation, pinned. 469s is the longest onset across every recording ever taken."""
    longest_onset_ever_seen = 469
    world_seconds = CORRELATE_SCRAPES * SCRAPE_INTERVAL_SECONDS
    assert world_seconds == 900
    assert world_seconds > 1.9 * longest_onset_ever_seen
    # The ceiling is a backstop on a dead world, not a second budget: it must exceed the budget,
    # and it must outlast T7.11's sixteen-minute gap plus the onset that followed it.
    assert world_seconds < CORRELATE_CEILING_SECONDS
    assert 960 + longest_onset_ever_seen < CORRELATE_CEILING_SECONDS
    # A gap is twelve missed scrapes: jitter loses one or two, a suspended host loses all of them.
    assert CORRELATE_GAP_SECONDS == 12 * SCRAPE_INTERVAL_SECONDS


def test_the_correlate_budget_is_not_a_stamp_input() -> None:
    """**T7.12 is harness-side, so `runtime_version` must not move** - and this is why.

    The stamp hashes the role prompts and the contract schemas (`faultline.agents.stamp`); no
    part of `evalharness` reaches it. Changing how long the harness is willing to wait changes
    nothing a model saw, so runs recorded before and after T7.12 stay comparable. Same precedent
    as T4.7, which kept budget bounds out of the stamp for the same reason.
    """
    from faultline.agents import stamp as stamp_module

    before = stamp_module.prompt_digest()
    stamp_module.prompt_digest.cache_clear()
    with (
        patch("evalharness.run.CORRELATE_SCRAPES", 1),
        patch("evalharness.run.CORRELATE_GAP_SECONDS", 1),
    ):
        assert stamp_module.prompt_digest() == before
    stamp_module.prompt_digest.cache_clear()
    assert stamp_module.runtime_version() == "faultline/0.0.1+prompts:1b0e7cbb4c47"


# --- T7.14: the rule that fires at rest ----------------------------------------------------

BASELINE_P95_MS = 37.8
"""checkoutservice's measured resting p95 over 12 hours - and its committed baseline (38ms)."""

EXCURSION_P95_MS = 15000.0
"""Where p95 lands when the slow tail crosses 5%: the top finite bucket of the demo's
histogram. The same number T3.4 read as degradation and T7.13 read as a starved histogram."""


def excursion_window(over: int, at: float = EXCURSION_P95_MS) -> list[float]:
    """A p95 window with `over` of its samples in the tail and the rest at baseline."""
    return [BASELINE_P95_MS] * (SAMPLES_IN_WINDOW - over) + [at] * over


def test_the_characterised_excursion_still_refuses_and_is_recorded_as_sustained() -> None:
    """**The shape T7.14 diagnosed, pinned.** checkoutservice sitting in its slow mode.

    It still refuses - that is not softened. Injecting during an excursion would put a
    pre-existing `ServiceHighLatency/checkoutservice` into the scenario's blast radius, and two
    recorded bundles already carry that alert as genuine fault evidence.
    """
    reading = reading_with(p95={"checkoutservice": excursion_window(SAMPLES_IN_WINDOW)})

    assert not reading.passed
    excursion = reading.p95_excursions["checkoutservice"]
    assert excursion.sustained
    assert excursion.samples_over == excursion.samples == SAMPLES_IN_WINDOW
    assert excursion.median_ms == EXCURSION_P95_MS
    assert any("12 of 12 samples over, sustained" in why for why in reading.refusals)


def test_a_refusal_on_the_known_tail_says_so_instead_of_saying_degraded() -> None:
    """The whole point: two readers took this scalar for a degraded world (T3.4, T7.13).

    The refusal now names the characterised excursion, and says both true things about it -
    that it is real, and that it is not evidence the world is broken.
    """
    reading = reading_with(p95={"checkoutservice": excursion_window(SAMPLES_IN_WINDOW)})

    note = [why for why in reading.refusals if why.startswith("note:")]
    assert len(note) == 1
    assert "checkoutservice" in note[0]
    assert "not evidence the world is degraded" in note[0]
    assert "would land in the injected fault's blast radius" in note[0]


def test_a_spike_and_an_episode_refuse_alike_but_are_told_apart_afterwards() -> None:
    """**Why this exists at all.** Four refusals were recorded before T7.14 and every one of
    them stored a single scalar, so none can say whether the world spiked or had been slow for
    an hour. Diagnosing them meant going to the live world, by which time the window was gone.
    Both still refuse; the manifest can now tell them apart.
    """
    spike = reading_with(p95={"checkoutservice": excursion_window(1)})
    episode = reading_with(p95={"checkoutservice": excursion_window(SAMPLES_IN_WINDOW)})

    assert not spike.passed and not episode.passed
    assert spike.p95_over_ceiling == episode.p95_over_ceiling  # the old record: identical
    assert not spike.p95_excursions["checkoutservice"].sustained
    assert episode.p95_excursions["checkoutservice"].sustained
    assert spike.p95_excursions["checkoutservice"].median_ms == BASELINE_P95_MS
    assert "intermittent" in spike.p95_excursions["checkoutservice"].describe()


def test_a_service_with_no_measured_tail_gets_no_note() -> None:
    """The note names a measured set, not any service that happens to be slow. A latency fault
    on cartservice is a finding, and must not be labelled a known excursion."""
    reading = reading_with(p95={"cartservice": excursion_window(SAMPLES_IN_WINDOW)})

    assert not reading.passed
    assert not any(why.startswith("note:") for why in reading.refusals)
    assert "cartservice" not in gate.KNOWN_TAIL_SERVICES


def test_a_genuinely_slow_service_still_pages() -> None:
    """The check that keeps the fix from being a suppression.

    `cart-dependency-latency` adds 300ms to cartservice and its bundle records
    `ServiceHighLatency` on four services as ground truth. Nothing here may stop that firing:
    the world's rule is untouched, and the gate refuses on a slow service exactly as before.
    """
    slow = reading_with(p95={"cartservice": 650.0, "checkoutservice": BASELINE_P95_MS})
    assert slow.p95_over_ceiling == {}, "650ms is under the gate's 1000ms ceiling, as before"

    very_slow = reading_with(p95={"cartservice": 15000.0})
    assert not very_slow.passed
    assert any("cartservice at 15000ms" in why for why in very_slow.refusals)


def test_the_gate_still_passes_a_world_at_its_baseline() -> None:
    """The three known-tail services at their measured resting p95 do not refuse anything."""
    reading = reading_with(
        p95={"checkoutservice": BASELINE_P95_MS, "frontend": 42.3, "loadgenerator": 48.0}
    )
    assert reading.passed
    assert reading.p95_excursions == {}


def test_the_excursion_reaches_the_manifest() -> None:
    """A refusal is a measurement (GateReading's docstring), so it has to serialise."""
    reading = reading_with(p95={"checkoutservice": excursion_window(SAMPLES_IN_WINDOW)})
    recorded = json.loads(json.dumps(reading.as_dict()))

    assert recorded["p95_excursions"]["checkoutservice"] == {
        "samples_over": 12,
        "samples": 12,
        "sustained": True,
        "median_ms": EXCURSION_P95_MS,
        "max_ms": EXCURSION_P95_MS,
    }
    assert recorded["p95_over_ceiling_ms"] == {"checkoutservice": EXCURSION_P95_MS}


# --- T7.23: the checkout stall's remedy ------------------------------------------------------


def test_the_checkout_stall_remedy_fires_on_its_signature_and_nothing_else() -> None:
    """**The signature is ServiceHighLatency on those three and nothing else (T7.23).**

    Measured: `checkout-service`'s `PlaceOrder` handler completes in ~20ms while the span reports
    15-30s, and the two services that wait on it inherit the number. Restarting that one container
    returned all three to their committed baselines within a scrape.

    The remedy is named at the refusal because waiting it out has cost this project whole days -
    the condition ran at ~95% duty across eight hours - and because the memory-headroom guard
    already sets the precedent of printing the container and the command.
    """
    from evalharness.rehearse import checkout_stall_remedy

    remedy = checkout_stall_remedy(
        ["ServiceHighLatency/checkoutservice", "ServiceHighLatency/loadgenerator"]
    )
    assert "docker restart checkout-service" in remedy
    assert "not a fault" in remedy


def test_the_remedy_is_silent_on_anything_that_is_not_the_stall() -> None:
    """A restart is the wrong advice for a real fault, so the match has to be exact.

    Any error-rate alert, or a latency alert on a service outside the measured three, means this
    is something else - and telling somebody to restart a container in the middle of a real
    incident is worse than saying nothing.
    """
    from evalharness.rehearse import CHECKOUT_STALL_SERVICES, checkout_stall_remedy

    assert checkout_stall_remedy([]) == ""
    assert checkout_stall_remedy(["ServiceHighErrorRate/checkoutservice"]) == ""
    assert checkout_stall_remedy(["ServiceHighLatency/cartservice"]) == ""
    assert checkout_stall_remedy(["ServiceNoTraffic/checkoutservice"]) == ""
    # One in-set service plus one outside it is not the signature either.
    assert (
        checkout_stall_remedy(
            ["ServiceHighLatency/checkoutservice", "ServiceHighLatency/adservice"]
        )
        == ""
    )
    assert set(CHECKOUT_STALL_SERVICES) == {"checkoutservice", "frontend", "loadgenerator"}
