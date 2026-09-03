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

from evalharness import gate, rehearse
from evalharness.run import (
    CORRELATE_CEILING_SECONDS,
    CORRELATE_GAP_SECONDS,
    CORRELATE_SCRAPES,
    SCRAPE_INTERVAL_SECONDS,
    ZERO_STEP_DISCARD,
    NoAlertError,
    RunDir,
    RunError,
    WorldStoppedReportingError,
    bundle_for,
    score,
    wait_for_incident,
)
from injector.worldlock import TOKEN_ENV, WorldLock, WorldLockError

REPO_ROOT = Path(__file__).resolve().parents[1]

QUIET = {
    "firing_alerts": [],
    "p95": {"cartservice": 1.9, "checkoutservice": 35.0},
    "rates": {"cartservice": 4.2, "checkoutservice": 2.1, "frontend-proxy": 0.0},
    # kafka is in the fixture world because the gate now reads its memory and uptime (T7.31,
    # T7.33). Older than cartservice so `youngest_container` assertions are unaffected.
    "uptimes": [("cartservice", 3600), ("kafka", 7200)],
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
        # The pipeline checks reach the ingest app and Redis, so every test stubs them healthy
        # by default and the T7.25 tests override them. Hermetic: no socket, no Redis.
        patch.object(gate, "ingest_accepting", return_value=world.get("ingest", True)),
        patch.object(gate, "consumer_idle_ms", return_value=world.get("idle_ms", 100)),
        patch.object(gate, "firing_alerts", return_value=world["firing_alerts"]),
        patch.object(gate, "_latest_by_service", side_effect=lambda q, **_: latest[q]),
        patch.object(gate, "_window_by_service", side_effect=lambda q, **_: windows),
        patch.object(gate, "container_uptimes", return_value=world["uptimes"]),
        # T7.31: kafka defaults to plenty of headroom so existing tests keep asserting what
        # they were written to assert; the T7.31 tests override it.
        patch.object(
            gate,
            "container_memory_usage",
            return_value=world.get("memory", [("kafka", 30.0, "0.6GiB / 2GiB")]),
        ),
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
    to show it.

    The second driver is written directly rather than acquired in-process: a nested acquire in
    one process is a *child* of the holder and is re-entrant by design (T7.37), so simulating a
    genuine second driver means a lock file this process did not take.
    """
    path = tmp_path / "harness.lock"
    path.write_text(json.dumps({"pid": os.getpid(), "since": "now", "reason": "another run"}))
    with pytest.raises(WorldLockError, match="another driver holds the world"), WorldLock(path):
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


PROPOSER_DIGEST = "20088b22cede"
"""The six-stage pipeline T3.9 built. **Superseded within the same batch** by
`TRIAGE_GATE_DIGEST` below, and kept because a pipeline this repository built is a pipeline the
lineage check has to be able to place - the same reason `SWEEP_2_DIGEST` is still here.

The proposer's system prompt entered `prompt_digest` and the `Proposal` contract entered
`_CONTRACTS`, which is the stamp doing exactly what it is for: a pipeline with a sixth stage is
not the pipeline five sweeps measured. ADR-0028 §6 said so in advance - *"every recorded run
becomes incomparable with everything after ... this is not avoidable and should not be worked
around"* - and required the role to land with a re-sweep.

**Until that re-sweep runs, every figure in `docs/RESULTS.md` describes `SWEEP_5_DIGEST` and
none of them describes HEAD.** That is stated in RESULTS.md rather than left to this constant.

One incidental finding worth keeping: a contract's **class docstring** is a stamp input, because
pydantic writes it into `model_json_schema()` as the schema description. Editing the `Proposal`
docstring moved this digest once during T3.9. That is correct behaviour - the docstring is part
of what a structured-output model is shown - and it is written down here because it is the kind
of thing a future reader would otherwise diagnose twice.
"""

TRIAGE_GATE_DIGEST = "a7330c098770"
"""The gated pipeline T3.1 built. **Superseded within the same batch** by `BATCH_B_DIGEST`.

`TRIAGER_SYSTEM` joined the stamp when triage gained the judgement half the specification asks
for - the gate that declines an incident before fan-out. Six role prompts now, and the second
stamp move of Phase 3's Batch B.

**Corrected at Batch C: this entry used to say "and the `TriageJudgement` contract" and that was
false.** The contract was written at T3.1 and never added to `stamp._CONTRACTS`, so its schema was
outside the digest until Batch C put it in - and this sentence, asserting the opposite, is the
reason nobody checked for three stamps. The digest value is unaffected and stays exactly as
recorded; what changes is the claim about what produced it.

**Three stamp moves, one re-record.** None of the intermediate pipelines was measured: all
three land inside the window ADR-0028 §6 opened, and the re-sweep at the end of Batch B measures
the pipeline as it finally stands rather than each step toward it. The intermediates are recorded
anyway, because a trajectory written on any of these days has to be placeable exactly.
"""

BATCH_B_DIGEST = "bc222a353936"
"""**The pipeline dev sweep 8 measured.**

Q17 put `lookback_minutes` on `Dispatch` - the planner's per-hypothesis widening, the last clause
of T3.2b's temporal-scoping sentence - and told the planner about it in `PLANNER_SYSTEM`. A field
on a contract inside `prompts_hash()` and a change to a system prompt: two reasons for one move,
which is why Q17 waited for a batch already spending the key.

**This is the digest the pre-registration names**, and dev sweep 8's five counted runs all carry
it. A move after this one and before that sweep would have left the batch measuring a pipeline
nobody planned to measure; none happened.
"""

BATCH_C_DIGEST = "7c6894e9dd92"
"""**HEAD.** The `TriageJudgement` schema entered the digest, which is the whole move.

Q21: the contract was written at T3.1, is what `validate_triage` holds the triage model to, and
was never in `stamp._CONTRACTS` - so for the length of dev sweep 8, changing what the triage model
had to return moved no frozen key. Nothing about the triager's behaviour changed here; the digest
moved because the *set of things the stamp covers* grew, which is exactly the kind of move that
must be visible rather than silent.

**Two other Batch C changes deliberately do not appear in this value, and that is the finding.**
`freeze.AGENT_ROLES` gained `triage` and `proposer` (Q22) - that moves the frozen `model_map` key,
not this one. And the planner now receives the top-3 similar past incidents T3.2 always specified
(Q23) - **a real behavioural change that moves no digest at all**, because a briefing's content is
neither a system prompt nor a contract schema. It was measured before and after: both
`7c6894e9dd92`. A reader comparing runs across this boundary cannot rely on the stamp alone, which
is why Q23's row said so in advance and why the sweep document for the next sweep must say it too.
"""


def test_the_stamp_names_which_pipeline_produced_a_run() -> None:
    """`runtime_version` is the package version plus a digest over every role system prompt and
    every contract schema, so it moves when and only when the agent is a different agent.

    Both known values are recorded here. A change that lands on neither is a third pipeline, and
    any table comparing it to either sweep needs its own re-run.
    """
    from faultline.agents.stamp import prompt_digest

    assert prompt_digest() == BATCH_C_DIGEST, (
        f"expected Batch C's pipeline {BATCH_C_DIGEST}. If a prompt or a contract moved again, "
        f"add its digest here - and if it moved after a pre-registration was written, the sweep "
        f"it governs is measuring something nobody planned to measure."
    )
    assert prompt_digest() not in {
        SWEEP_5_DIGEST,
        PROPOSER_DIGEST,
        TRIAGE_GATE_DIGEST,
        BATCH_B_DIGEST,
    }, "HEAD is none of the pipelines before Batch C, dev sweep 8's included"
    assert (
        len(
            {
                SWEEP_1_DIGEST,
                SWEEP_2_DIGEST,
                SWEEP_4_DIGEST,
                SWEEP_5_DIGEST,
                PROPOSER_DIGEST,
                TRIAGE_GATE_DIGEST,
                BATCH_B_DIGEST,
            }
        )
        == 7
    ), "seven pipelines, four of them measured"


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
    assert stamp_module.runtime_version() == f"faultline/0.0.1+prompts:{BATCH_C_DIGEST}"


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


# --- T7.25: the pipeline has to be listening ------------------------------------------------


def pipeline(
    ingest: bool | None = True, idle_ms: int | None = 100, **overrides: Any
) -> gate.GateReading:
    """Read the gate with the pipeline in a stated state, everything else quiet."""
    return reading_with(ingest=ingest, idle_ms=idle_ms, **overrides)


def test_a_quiet_world_with_a_live_pipeline_passes() -> None:
    """The control. Nothing firing, ingest answering, a consumer polling."""
    reading = pipeline()
    assert reading.pipeline_down == []
    assert reading.passed


def test_a_quiet_world_cannot_produce_the_pipeline_refusal() -> None:
    """**The distinction the whole check rests on (T7.25).**

    Redis keeps two clocks on a consumer and only one is a liveness signal. `idle` is time since
    the last *interaction*, which a blocking `XREADGROUP` refreshes whether or not it returns
    anything. `inactive` is time since the last *successful* read, and it grows on any world with
    nothing to say.

    Reading `inactive` would refuse every quiet world - which is precisely the conflation this
    check exists to prevent, since a quiet world is the normal state before an injection. Measured
    on the live world: orchestrator up, `idle` 93-905ms against a 5000ms block, while `inactive`
    stood at 737,918ms because no alert had arrived in twelve minutes.
    """
    # A world so quiet that nothing has been read for hours, with the consumer polling throughout.
    reading = pipeline(idle_ms=120, firing_alerts=[])
    assert reading.pipeline_down == []
    assert reading.passed, "a quiet world must never look like a down pipeline"


def test_a_dead_consumer_is_caught_and_a_slow_one_is_not() -> None:
    """`idle` grows 1:1 with wall clock once the consumer stops. Measured: 6963, 17001, 29046ms
    after a kill, against 93-905ms while alive."""
    from faultline.orchestrator.settings import OrchestratorSettings

    ceiling = gate.PIPELINE_IDLE_MULTIPLE * OrchestratorSettings().block_ms

    assert pipeline(idle_ms=ceiling - 1).pipeline_down == [], "a slow ack is not a dead consumer"
    dead = pipeline(idle_ms=ceiling + 1)
    assert len(dead.pipeline_down) == 1
    assert "not polling" in dead.pipeline_down[0]
    assert "faultline-orchestrate" in dead.pipeline_down[0]


def test_no_consumer_at_all_is_caught() -> None:
    """`None` covers no consumer, no group and no stream. All of them are 'not consuming'."""
    reading = pipeline(idle_ms=None)
    assert any("no consumer is attached" in w for w in reading.pipeline_down)


def test_ingest_not_accepting_is_caught_and_names_the_command() -> None:
    """Both a refused connection (`None`) and a non-2xx (`False`) are down."""
    for answer in (None, False):
        reading = pipeline(ingest=answer)
        assert any("ingest is not accepting" in w for w in reading.pipeline_down)
        assert any("faultline-ingest" in w for w in reading.pipeline_down)


def test_t7_24s_exact_case_refuses_with_its_own_type() -> None:
    """Both halves down, which is what T7.24 injected into."""
    reading = pipeline(ingest=None, idle_ms=None)
    assert len(reading.pipeline_down) == 2
    assert not reading.passed
    assert any("NOT the world failing to alert" in why for why in reading.refusals)


def test_the_three_discard_reasons_are_distinct() -> None:
    """**T7.12 defined two; this is the third, and no two may share a label.**

    `no-alert` says the world had its chances and the fault did not page. `metrics-gap` says the
    world stopped reporting so nothing was measured. `pipeline-down` says the world was fine and
    nobody was listening. Conflating the third with the first is what T7.24 would have recorded:
    a fact about the harness written down as a fact about the scenario.
    """
    from evalharness.run import NoAlertError, RunError, WorldStoppedReportingError

    reasons = [
        NoAlertError.discard_reason,
        WorldStoppedReportingError.discard_reason,
        gate.PipelineDownError.discard_reason,
        gate.GateRefusedError.discard_reason,
        RunError.discard_reason,
    ]
    assert reasons == [
        "no-alert",
        "metrics-gap",
        "pipeline-down",
        "baseline gate refused",
        "run failed",
    ]
    assert len(set(reasons)) == len(reasons), "every discard reason must be distinct"


def test_the_pipeline_refusal_is_still_a_gate_refusal() -> None:
    """It must keep flowing through the existing handler, or a run would crash instead of
    discarding. `run.main` catches `GateRefusedError` and records whatever reason it carries."""
    assert issubclass(gate.PipelineDownError, gate.GateRefusedError)
    assert gate.PipelineDownError.discard_reason != gate.GateRefusedError.discard_reason


def test_the_readings_reach_the_manifest() -> None:
    """A refusal is a measurement, so what the checks saw has to serialise."""
    recorded = json.loads(json.dumps(pipeline(ingest=None, idle_ms=None).as_dict()))
    assert recorded["ingest_accepting"] is None
    assert recorded["consumer_idle_ms"] is None
    assert len(recorded["pipeline_down"]) == 2


# --- T7.31: the kafka precondition refuses instead of sitting in a PLAN entry ----------------


def test_the_run_budget_is_pinned_to_the_constants_it_claims_to_sum() -> None:
    """The default duration is derived, so it must break loudly if any input moves.

    Same idea as `SCRAPE_INTERVAL_SECONDS` being pinned against the Prometheus config: a derived
    constant that silently stops matching its derivation is worse than a literal.
    """
    from evalharness.run import (
        CORRELATE_CEILING_SECONDS,
        RECOVERY_TIMEOUT_SECONDS,
        SETTLE_AFTER_ALERT_SECONDS,
    )
    from faultline.agents.budget import Budget

    assert (
        CORRELATE_CEILING_SECONDS
        + SETTLE_AFTER_ALERT_SECONDS
        + Budget().wall_clock_seconds
        + RECOVERY_TIMEOUT_SECONDS
    ) == gate.RUN_BUDGET_SECONDS


def test_the_threshold_is_computed_from_the_guard_and_not_a_chosen_number() -> None:
    """threshold == guard - (rate * hours / limit), exactly. No taste anywhere in it."""
    h = gate.headroom_for(expected_run_hours=1.0, usage=[("kafka", 50.0, "1GiB / 2GiB")])
    assert h is not None
    expected_growth_percent = gate.HEADROOM_GROWTH_MB_PER_HOUR * 1.0 / 2048.0 * 100.0
    assert h.growth_percent == pytest.approx(expected_growth_percent)
    assert h.threshold_percent == pytest.approx(
        rehearse.MEMORY_HEADROOM_PERCENT - expected_growth_percent
    )


def test_the_limit_is_read_from_the_container_rather_than_assumed() -> None:
    """A bigger container gets a more permissive threshold, with no code change.

    The same start percentage is safe in a 4 GB container and not in a 1 GB one, because the
    same absolute growth is a different share of each.
    """
    small = gate.headroom_for(expected_run_hours=1.0, usage=[("kafka", 80.0, "0.8GiB / 1GiB")])
    large = gate.headroom_for(expected_run_hours=1.0, usage=[("kafka", 80.0, "3.2GiB / 4GiB")])
    assert small is not None and large is not None
    assert small.limit_mb == pytest.approx(1024.0)
    assert large.limit_mb == pytest.approx(4096.0)
    assert small.threshold_percent < large.threshold_percent
    assert not small.fits and large.fits


def test_a_longer_expected_run_demands_more_headroom() -> None:
    short = gate.headroom_for(expected_run_hours=0.25, usage=[("kafka", 75.0, "1.5GiB / 2GiB")])
    sweep = gate.headroom_for(expected_run_hours=2.78, usage=[("kafka", 75.0, "1.5GiB / 2GiB")])
    assert short is not None and sweep is not None
    assert short.fits
    assert not sweep.fits


def test_t729_would_have_been_refused_at_its_start_had_it_declared_its_duration() -> None:
    """The worked example. T7.29 began at 69.95% and ended at 90.69% over 2.78 hours.

    Declaring the real duration, the gate refuses at the start - and its projection lands within
    half a point of what actually happened, which is the check on the rate itself.
    """
    h = gate.headroom_for(expected_run_hours=2.78, usage=[("kafka", 69.95, "1.399GiB / 2GiB")])
    assert h is not None
    assert not h.fits
    assert h.projected_percent == pytest.approx(90.69, abs=0.5)


def test_at_the_default_duration_no_run_passes_and_then_crosses_the_guard() -> None:
    """The falsifier for the threshold: a false *pass* would mean it is set wrong.

    Replays T7.29's measured trajectory run by run. A false refusal is a cost and is recorded in
    PLAN.md; a false pass would be a defect, so it is asserted against here.
    """
    start, end, runs = 69.95, 90.69, 8
    step = (end - start) / runs
    for i in range(runs):
        begins = start + step * i
        finishes = begins + step
        h = gate.headroom_for(usage=[("kafka", begins, "1.399GiB / 2GiB")])
        assert h is not None
        crossed = finishes > rehearse.MEMORY_HEADROOM_PERCENT
        assert not (h.fits and crossed), f"run {i + 1} passed the gate and then crossed the guard"


def test_a_world_with_no_kafka_is_not_refused() -> None:
    """Absence is not a hazard. The check is about one container and must not block without it."""
    assert gate.headroom_for(usage=[("frontend", 12.0, "24MiB / 200MiB")]) is None


def test_an_unparseable_limit_declines_to_refuse_rather_than_guessing() -> None:
    assert gate.headroom_for(usage=[("kafka", 99.0, "1.9GiB")]) is None
    assert gate.headroom_for(usage=[("kafka", 99.0, "1.9GiB / unknown")]) is None


def test_the_reading_is_recorded_whether_it_passes_or_refuses() -> None:
    """Provenance is the second half of the task: a later discard must be diagnosable."""
    reading = gate.GateReading()
    reading.headroom = gate.headroom_for(
        expected_run_hours=1.0, usage=[("kafka", 42.0, "0.82GiB / 2GiB")]
    )
    recorded = reading.as_dict()["headroom"]
    assert recorded is not None
    assert recorded["container"] == "kafka"
    assert recorded["percent_now"] == pytest.approx(42.0)
    assert recorded["guard_percent"] == rehearse.MEMORY_HEADROOM_PERCENT
    assert recorded["fits"] is True


def test_the_refusal_is_an_ordinary_gate_refusal_and_not_a_sixth_discard_reason() -> None:
    """Decided rather than assumed: the existing label already covers it.

    Nothing was injected and the world was unfit, which is exactly what `baseline gate refused`
    means. `pipeline-down` earned its own subclass because it was the *harness* failing while
    looking like the world; this is the world, so it stays under the general label and the
    attribution comes from the recorded reading instead.
    """
    assert gate.GateRefusedError.discard_reason == "baseline gate refused"
    assert not issubclass(gate.PipelineDownError, type(None))
    reading = gate.GateReading(refusals=["kafka is at 95.0% ..."])
    assert not reading.passed
    assert not reading.pipeline_down


def test_docker_sizes_parse_across_the_units_stats_actually_emits() -> None:
    assert gate._parse_docker_size("2GiB") == pytest.approx(2048.0)
    assert gate._parse_docker_size("512MiB") == pytest.approx(512.0)
    assert gate._parse_docker_size("1.399GiB") == pytest.approx(1432.6, abs=0.5)
    assert gate._parse_docker_size("nonsense") is None


def test_a_hot_kafka_refuses_the_whole_gate_end_to_end() -> None:
    """Not just the arithmetic - the gate itself must refuse, in a world that is otherwise clean.

    This is the difference between a precondition and a PLAN entry: everything else here is fine,
    and the run still does not start.
    """
    reading = reading_with(memory=[("kafka", 88.0, "1.76GiB / 2GiB")])
    assert not reading.passed
    assert any("kafka" in why and "guard" in why for why in reading.refusals)
    assert reading.headroom is not None and not reading.headroom.fits
    # It is the world being unfit, not the harness being absent.
    assert not reading.pipeline_down


def test_the_same_world_passes_once_kafka_has_been_recycled() -> None:
    """The refusal names a remedy, so the remedy has to actually clear it."""
    assert not reading_with(memory=[("kafka", 88.0, "1.76GiB / 2GiB")]).passed
    recycled = reading_with(memory=[("kafka", 26.3, "0.53GiB / 2GiB")])
    assert recycled.passed
    assert recycled.headroom is not None and recycled.headroom.fits


# --- T7.32: the gate bound to the sweep, and refusal made actionable ------------------------


def test_the_sweep_run_hour_is_pinned_to_the_measurement_it_claims() -> None:
    """T7.29 ran 8 scenarios in 2.78 h. If that citation changes, this fails rather than drifts."""
    assert pytest.approx(2.78 / 8) == gate.SWEEP_RUN_HOURS


def test_remaining_work_shrinks_the_ask_as_the_sweep_progresses() -> None:
    """Run 1 of eight asks for eight runs' headroom; run 7 asks for two.

    This is the whole point of scoping to remaining work rather than total: a static sweep bound
    gets more wrong with every run completed.
    """
    first = gate.headroom_for(usage=[("kafka", 50.0, "1GiB / 2GiB")], runs_remaining=8)
    seventh = gate.headroom_for(usage=[("kafka", 50.0, "1GiB / 2GiB")], runs_remaining=2)
    assert first is not None and seventh is not None
    assert first.threshold_percent < seventh.threshold_percent
    assert first.expected_run_hours == pytest.approx(8 * gate.SWEEP_RUN_HOURS)
    assert seventh.expected_run_hours == pytest.approx(2 * gate.SWEEP_RUN_HOURS)


def test_one_declared_sweep_run_is_more_permissive_than_the_undeclared_default() -> None:
    """Declaring "one typical run" should beat "I do not know, assume the harness bound".

    Not a contradiction: `RUN_BUDGET_SECONDS` is the worst case a run may reach, and is the right
    assumption only when nobody has said otherwise.
    """
    declared = gate.headroom_for(usage=[("kafka", 50.0, "1GiB / 2GiB")], runs_remaining=1)
    default = gate.headroom_for(usage=[("kafka", 50.0, "1GiB / 2GiB")])
    assert declared is not None and default is not None
    assert declared.threshold_percent > default.threshold_percent


def test_t729_is_refused_at_run_one_when_it_declares_the_work_still_to_come() -> None:
    """The worked example. Every run of T7.29 passed T7.31's per-run check and the sweep was
    already doomed at run 1; scoped to remaining work, run 1 is where it stops."""
    h = gate.headroom_for(usage=[("kafka", 69.95, "1.399GiB / 2GiB")], runs_remaining=8)
    assert h is not None
    assert not h.fits
    assert h.projected_percent == pytest.approx(90.69, abs=0.5)


def test_after_the_recycle_the_whole_t729_sweep_fits() -> None:
    """T7.30 measured a restart returning kafka to 26.27%. From there all eight runs pass and
    the sweep finishes far below the guard - which is what makes the refusal a pause."""
    percent, step = 26.27, (90.69 - 69.95) / 8
    for remaining in range(8, 0, -1):
        h = gate.headroom_for(
            usage=[("kafka", percent, "1.399GiB / 2GiB")], runs_remaining=remaining
        )
        assert h is not None and h.fits, f"refused with {remaining} runs left at {percent:.2f}%"
        percent += step
    assert percent < rehearse.MEMORY_HEADROOM_PERCENT


def test_run_seven_is_still_refused_and_that_is_now_the_right_answer() -> None:
    """**Remaining-work scoping does not recover T7.31's false refusal on run 7.**

    It reclassifies it. Run 7 alone stayed under the guard, so refusing it as a single run was
    wrong. Runs 7 and 8 together cross it, so refusing it as "two runs still to come" is right.
    The verdict is the same and the question is not; no improvement is claimed here.
    """
    seventh = gate.headroom_for(usage=[("kafka", 85.50, "1.75GiB / 2GiB")], runs_remaining=2)
    assert seventh is not None and not seventh.fits
    # ... and the two remaining runs really did cross: 85.50 -> 88.10 -> 90.69.
    assert rehearse.MEMORY_HEADROOM_PERCENT < 90.69


def test_the_false_pass_window_is_bounded_and_cannot_widen_unnoticed() -> None:
    """**A real limit, asserted rather than hidden.**

    The published rate is 151.0 MB/h; T7.29's actual was 421/2.78 = 151.44. The gate is therefore
    ~0.3% optimistic, which over eight runs is a quarter of a point - so a sweep starting just
    under the threshold can still finish marginally over the guard. It is narrow and it is real,
    and this pins the width so a future rate edit cannot widen it silently.
    """
    threshold = gate.headroom_for(usage=[("kafka", 0.0, "0GiB / 2GiB")], runs_remaining=8)
    assert threshold is not None
    actual_per_run = (90.69 - 69.95) / 8
    crosses_above = rehearse.MEMORY_HEADROOM_PERCENT - actual_per_run * 8
    window = threshold.threshold_percent - crosses_above
    assert 0 < window < 0.3, f"false-pass window is {window:.3f} points"


def test_a_headroom_refusal_is_a_pause_and_never_a_discard() -> None:
    """A discard is a run that happened and produced no result. This is one that never started."""
    assert issubclass(gate.HeadroomExhaustedError, gate.GateRefusedError)
    assert gate.HeadroomExhaustedError.is_pause is True
    assert getattr(gate.GateRefusedError, "is_pause", False) is False
    assert getattr(gate.PipelineDownError, "is_pause", False) is False


def test_the_headroom_refusal_raises_its_own_type_and_names_the_remedy() -> None:
    hot = reading_with(memory=[("kafka", 95.0, "1.9GiB / 2GiB")])
    with (
        patch.object(gate, "read", return_value=hot),
        pytest.raises(gate.HeadroomExhaustedError) as caught,
    ):
        gate.require()
    message = str(caught.value)
    assert "docker restart kafka" in message
    assert "accounting-service" in message  # T7.27: the consumers, or they never reconnect
    assert "PAUSE, NOT A DISCARD" in message


def test_a_pipeline_that_is_down_outranks_headroom() -> None:
    """Priority is deliberate: a missing harness is not clearable by recycling a container."""
    broken = reading_with(ingest=False, memory=[("kafka", 95.0, "1.9GiB / 2GiB")])
    with patch.object(gate, "read", return_value=broken), pytest.raises(gate.PipelineDownError):
        gate.require()


def test_the_sweep_position_is_recorded_so_a_recycle_is_visible_afterwards() -> None:
    """Provenance: kafka is not constant across a sweep that paused and was recycled, and the
    only way a reader can see that is two consecutive runs whose percent falls rather than rises.
    """
    reading = gate.GateReading()
    reading.headroom = gate.headroom_for(
        usage=[("kafka", 44.0, "0.88GiB / 2GiB")], runs_remaining=3
    )
    recorded = reading.as_dict()["headroom"]
    assert recorded is not None
    assert recorded["runs_remaining"] == 3
    assert recorded["percent_now"] == pytest.approx(44.0)


def test_the_runs_remaining_flag_is_accepted_and_defaults_to_unset() -> None:
    from evalharness.run import parser

    assert parser().parse_args(["cart-redis-misconfig"]).runs_remaining is None
    assert (
        parser().parse_args(["cart-redis-misconfig", "--runs-remaining", "8"]).runs_remaining == 8
    )


# --- T7.33: the opt-in hole closed, and the recycle recorded as a fact ----------------------


def test_a_run_declaring_neither_intent_is_refused_before_anything_happens() -> None:
    """T7.32's hole: omitting --runs-remaining silently bought the weaker per-run check.

    Same contract as `--holdout`, which is refused without it because a different experiment
    should be hard to start by accident. Exit 2, and nothing is injected or recorded.
    """
    from evalharness.run import main

    assert main(["cart-redis-misconfig"]) == 2


def test_either_declaration_satisfies_it() -> None:
    from evalharness.run import parser

    single = parser().parse_args(["cart-redis-misconfig", "--single-run"])
    sweep = parser().parse_args(["cart-redis-misconfig", "--runs-remaining", "8"])
    assert single.single_run is True and single.runs_remaining is None
    assert sweep.single_run is False and sweep.runs_remaining == 8


def test_the_demo_declares_its_intent_rather_than_relying_on_a_default() -> None:
    """CLAUDE.md rule 2: the demo always works. It is one run, and it now says so."""
    from evalharness import demo

    source = Path(demo.__file__).read_text()
    assert '"--single-run",' in source


def test_kafka_uptime_is_recorded_so_a_restart_is_a_fact_not_an_inference() -> None:
    reading = reading_with()
    assert reading.headroom is not None
    assert reading.headroom.uptime_seconds == 7200  # kafka in the default fixture world
    assert reading.as_dict()["headroom"]["uptime_seconds"] == 7200


def test_continuity_reports_the_same_instance_when_kafka_did_not_restart(tmp_path: Path) -> None:
    from evalharness.run import world_continuity

    _write_prior_run(tmp_path, "20260901T000000Z-a", uptime=600)
    out = world_continuity("20260901T010000Z-b", 4200, root=tmp_path)
    assert out["kafka_restarted_since_previous_run"] is False
    assert out["cause"].startswith("continuous")
    assert out["previous_run_id"] == "20260901T000000Z-a"


def test_a_recycle_after_a_pause_is_named_as_deliberate(tmp_path: Path) -> None:
    """The cause, not just the discontinuity: the gate asked, the operator cleared it."""
    from evalharness.run import world_continuity

    _write_prior_run(tmp_path, "20260901T000000Z-a", uptime=50_000, paused=True)
    out = world_continuity("20260901T010000Z-b", 300, root=tmp_path)
    assert out["kafka_restarted_since_previous_run"] is True
    assert "deliberate recycle" in out["cause"]


def test_a_restart_nobody_recorded_is_surfaced_rather_than_smoothed_over(tmp_path: Path) -> None:
    from evalharness.run import world_continuity

    _write_prior_run(tmp_path, "20260901T000000Z-a", uptime=50_000, paused=False)
    out = world_continuity("20260901T010000Z-b", 300, root=tmp_path)
    assert out["kafka_restarted_since_previous_run"] is True
    assert "no run recorded a pause" in out["cause"]


def test_a_missing_reading_says_unknown_instead_of_assuming_continuity(tmp_path: Path) -> None:
    """The distinction T7.32 could not make: absent evidence is not evidence of continuity."""
    from evalharness.run import world_continuity

    assert world_continuity("20260901T010000Z-b", 300, root=tmp_path)["cause"].startswith("unknown")
    _write_prior_run(tmp_path, "20260901T000000Z-a", uptime=None)
    out = world_continuity("20260901T010000Z-b", 300, root=tmp_path)
    assert out["kafka_restarted_since_previous_run"] is None
    assert out["cause"].startswith("unknown")


def test_the_previous_run_is_the_most_recent_one_before_this_one(tmp_path: Path) -> None:
    from evalharness.run import previous_run_manifest

    for name in ("20260901T000000Z-a", "20260901T010000Z-b", "20260901T030000Z-d"):
        _write_prior_run(tmp_path, name, uptime=100)
    found = previous_run_manifest("20260901T020000Z-c", root=tmp_path)
    assert found is not None and found["run_id"] == "20260901T010000Z-b"


def _write_prior_run(
    root: Path, run_id: str, uptime: int | None = None, paused: bool = False
) -> None:
    directory = root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"run_id": run_id, "baseline_gate": {"headroom": {}}}
    if uptime is not None:
        manifest["baseline_gate"]["headroom"]["uptime_seconds"] = uptime
    if paused:
        manifest["paused"] = {"reason": "clearable precondition"}
    (directory / "manifest.json").write_text(json.dumps(manifest))


# --- T7.37: one driver of the world, enforced ----------------------------------------------


def test_the_recorder_now_takes_the_same_lock_as_a_scored_run() -> None:
    """**The T7.36 hole.** `WorldLock` existed and only `run.py` took it.

    A lock one of two drivers takes is a lock the other route defeats, which is why it moved
    below both of them into `injector`.
    """
    from evalharness import rehearse as rehearse_mod
    from evalharness import run as run_mod

    assert "WorldLock" in Path(rehearse_mod.__file__).read_text()
    assert run_mod.WorldLock is rehearse_mod.WorldLock


def test_a_dead_holder_is_reclaimed_without_a_flag(tmp_path: Path) -> None:
    """Stranding the operator is the failure mode a lock most easily creates."""
    path = tmp_path / "harness.lock"
    dead = 999_999_999  # no such pid
    path.write_text(json.dumps({"pid": dead, "since": "earlier", "reason": "a run that died"}))
    with WorldLock(path, reason="new run") as lock:
        assert lock.info()["acquired"] is True
        assert lock.info()["reclaimed"]["pid"] == dead
        assert lock.info()["reclaimed"]["was"] == "dead"


def test_the_reclaim_is_recorded_rather_than_silent(tmp_path: Path) -> None:
    """A stale lock and a live one look identical from the outside, so the difference is
    written down instead of assumed."""
    path = tmp_path / "harness.lock"
    path.write_text(json.dumps({"pid": 999_999_999, "since": "earlier", "reason": "gone"}))
    with WorldLock(path):
        written = json.loads(path.read_text())
    assert written["reclaimed"]["was"] == "dead"
    assert written["reclaimed"]["reason"] == "gone"


def test_a_live_holder_is_refused_and_the_message_names_who_and_since(tmp_path: Path) -> None:
    path = tmp_path / "harness.lock"
    path.write_text(
        json.dumps(
            {"pid": os.getpid(), "since": "2026-09-01T00:00:00Z", "reason": "rehearse cart-x"}
        )
    )
    with pytest.raises(WorldLockError) as caught, WorldLock(path):
        pass
    message = str(caught.value)
    assert str(os.getpid()) in message
    assert "2026-09-01T00:00:00Z" in message
    assert "rehearse cart-x" in message
    assert "--force-lock" in message  # the documented way out, not an incantation
    assert "Nothing was changed" in message


def test_force_takes_a_live_holder_and_records_that_it_did(tmp_path: Path) -> None:
    """Advisory rather than hard: the operator is also the only one who can fix a wedged world."""
    path = tmp_path / "harness.lock"
    path.write_text(json.dumps({"pid": os.getpid(), "since": "earlier", "reason": "a live run"}))
    with WorldLock(path, force=True) as lock:
        assert lock.info()["reclaimed"]["was"] == "forced"
        assert json.loads(path.read_text())["reclaimed"]["was"] == "forced"


def test_a_child_process_is_re_entrant_rather_than_locked_out_by_its_parent(
    tmp_path: Path,
) -> None:
    """A run that shells out to `faultline-inject` must not be refused by its own lock."""
    path = tmp_path / "harness.lock"
    with WorldLock(path, reason="parent"):
        assert os.environ.get(TOKEN_ENV)
        with WorldLock(path, reason="child") as child:
            assert child.info()["acquired"] is False
            assert child.info()["held_by_parent"]
        assert path.exists(), "the child must not release its parent's lock"
    assert not path.exists()


def test_an_unparseable_lock_is_treated_as_held_not_as_absent(tmp_path: Path) -> None:
    """A hand-written lock file is a holder we cannot identify. Refusing is the safe reading."""
    path = tmp_path / "harness.lock"
    path.write_text("someone was here\n")
    with pytest.raises(WorldLockError), WorldLock(path):
        pass


def test_releasing_does_not_delete_a_lock_somebody_forced_from_us(tmp_path: Path) -> None:
    """If a second driver forced past, the first must not take their lock with it on the way out."""
    path = tmp_path / "harness.lock"
    lock = WorldLock(path, reason="first")
    lock.__enter__()
    path.write_text(json.dumps({"pid": os.getpid(), "since": "later", "token": "someone-else"}))
    lock.__exit__()
    assert path.exists(), "the forcing driver's lock was deleted by the driver it displaced"
    path.unlink()


def test_the_lock_state_reaches_the_run_record(tmp_path: Path) -> None:
    """T7.33 recorded a recycle as a fact; a second driver is the same kind of fact."""
    path = tmp_path / "harness.lock"
    with WorldLock(path, reason="faultline-eval cart-x") as lock:
        info = lock.info()
    assert info["acquired"] is True
    assert info["reason"] == "faultline-eval cart-x"
    assert info["pid"] == os.getpid()
    assert "since" in info and "token" in info


def test_the_run_manifest_records_every_bound_it_was_held_to() -> None:
    """**T4.7's rule, checked where the first live run of Batch B broke it.**

    The manifest's budget block was written by hand and its comment said *"all four bounds"*.
    Batch B made them eight, the hand-written list did not notice, and the first live run
    printed a budget that omitted the dollar cap it might have stopped on - which would have
    made the pre-registration's fourth prediction unverifiable from the record.

    It now comes from `freeze.budget_bounds`, so a bound cannot be added without appearing
    here. The per-specialist override is the CLI's and is added beside it."""
    from evalharness import freeze

    bounds = set(freeze.budget_bounds(4, 120_000))

    assert bounds == {
        "max_tool_calls_per_specialist",
        "max_tokens",
        "wall_clock_seconds",
        "max_dispatch_rounds",
        "briefing_tokens",
        "max_usd",
        "usd_per_mtok_in",
        "usd_per_mtok_out",
    }
    source = (REPO_ROOT / "src" / "evalharness" / "run.py").read_text()
    assert "freeze.budget_bounds(args.max_tool_calls, args.max_tokens)" in source, (
        "the manifest must read the bounds rather than restate them"
    )


# --- T4.1b: the filter is asked to fire, and now checked --------------------------------------


def test_a_run_whose_exclusion_removed_nothing_is_invalid_not_annotated() -> None:
    """**The clause this task exists to deliver.** T4.1b: *"a scored run where the filter did not
    fire is marked invalid, not merely annotated - silent non-enforcement is how this defect
    returns."*

    A retrieval that excluded `scenario:X` and removed zero chunks has asserted nothing: on a
    scored dev run the scenario's own narrative is in the corpus by construction, so a zero means
    either the corpus does not hold it or the exclusion did not apply. Both leave ADR-0008 axis 2
    unsupported, and the run's numbers are not usable.
    """
    from evalharness.run import classify_retrievals

    verdict = classify_retrievals([(1, "scenario:cart-redis-misconfig", 0), (2, None, None)])

    assert verdict["silent"] == [{"seq": 1, "exclude_origin": "scenario:cart-redis-misconfig"}]
    assert verdict["enforced"] is False


def test_a_run_whose_exclusion_removed_chunks_is_enforced() -> None:
    """Two excluding retrievals, both of which removed something. This is what a scored dev run
    looks like since Batch C gave the planner its own retrieval."""
    from evalharness.run import classify_retrievals

    verdict = classify_retrievals(
        [(1, "scenario:ad-memory-squeeze", 3), (2, "scenario:ad-memory-squeeze", 3)]
    )

    assert verdict["enforced"] is True
    assert verdict["silent"] == []
    assert verdict["filtered"] == {"1": 3, "2": 3}


def test_a_production_run_excludes_nothing_and_is_not_invalid() -> None:
    """`exclude_origin IS NULL` is the product case and is legal - a live incident has no origin
    to exclude. It is not `enforced` either, because there was nothing to enforce, and reporting
    it as enforcement would be the same overclaim in the other direction."""
    from evalharness.run import classify_retrievals

    verdict = classify_retrievals([(1, None, None)])

    assert verdict["silent"] == []
    assert verdict["enforced"] is False
    assert verdict["excluding"] == 0


def test_an_uncounted_row_is_unassessable_and_never_invalid() -> None:
    """**`NULL` is not zero**, and a run is never refused on a number nobody recorded.

    Every retrieval row written before this task has no count, and the 60-odd of them in the
    store cannot be backfilled - the corpus state they ran against no longer exists. Refusing
    those runs retroactively would be inventing enforcement rather than performing it, so they
    are reported as unassessable and left alone.
    """
    from evalharness.run import classify_retrievals

    verdict = classify_retrievals([(1, "scenario:shipping-wrong-image", None)])

    assert verdict["unassessable"] == [
        {"seq": 1, "exclude_origin": "scenario:shipping-wrong-image"}
    ]
    assert verdict["silent"] == []
    assert verdict["enforced"] is False
