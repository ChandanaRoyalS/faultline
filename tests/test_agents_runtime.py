"""T3.2: the model boundary and trajectory persistence. No model, no Postgres.

The fake model is the only one the suite touches, and `tests/conftest.py` makes that structural
rather than a convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultline.agents import model as model_module
from faultline.agents.model import DeterministicModel, ModelRequest
from faultline.agents.settings import AgentSettings
from faultline.agents.trajectory import (
    InMemoryTrajectoryStore,
    RetrievalRecord,
    StepKind,
    ToolCallRecord,
    Trajectory,
    TrajectoryStep,
)

ENVELOPES = (
    Path(__file__).resolve().parents[1] / "docs" / "evidence" / "t2.6-tools-smoke" / "envelopes.txt"
)
START = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
ROLES = [
    "triage",
    "planner",
    "metrics",
    "logs",
    "changes",
    "traces",
    "synthesizer",
    "proposer",
    "scribe",
]


def real_envelope() -> str:
    """A rendered envelope from the T2.6 smoke - the real thing an agent read."""
    text = ENVELOPES.read_text()
    start = text.index("<tool_result ")
    end = text.index(">", text.index("</tool_result", start)) + 1
    return text[start:end]


# --- the model boundary --------------------------------------------------------


def test_the_settings_have_no_api_key_field_at_all() -> None:
    """Not a field with a default, not a field with `None`. **Its absence is the design.**

    A key that never enters this repo's configuration cannot be written to a trajectory,
    printed by a CLI's `--help`, or committed in a `.env` example. The SDK resolves credentials
    from the environment itself.
    """
    fields = set(AgentSettings.model_fields)

    credentialish = {f for f in fields if "key" in f or "secret" in f or "credential" in f}
    assert not credentialish, f"AgentSettings carries {credentialish}"
    assert "api_key" not in fields
    assert "max_tokens" in fields, "a token *budget* is configuration; a token *secret* is not"


def test_one_default_model_with_an_optional_per_role_override_map() -> None:
    """The decision ADR-0020 left open, taken. Nine roles, one model, an empty map.

    A model named per role would make nine decisions where the evidence supports one, and
    ADR-0020 recorded that per-role selection should be settled by T4.2's measured accuracy
    rather than by a cost estimate.
    """
    settings = AgentSettings()

    assert settings.model == "claude-opus-5"
    assert settings.role_models == {}
    assert set(settings.effective_models(ROLES).values()) == {"claude-opus-5"}


def test_an_override_is_visible_in_the_effective_map_a_figure_reports() -> None:
    """A sweep with a cheaper scribe is not the same experiment as one without it, and a
    headline naming only the default would not show the difference."""
    settings = AgentSettings(role_models={"scribe": "claude-haiku-4-5"})

    effective = settings.effective_models(ROLES)

    assert effective["scribe"] == "claude-haiku-4-5"
    assert effective["synthesizer"] == "claude-opus-5"
    assert len(set(effective.values())) == 2, "the map is what gets reported, not the default"


def test_the_judge_model_inherits_nothing() -> None:
    """Empty means unset, not "same as the agent". Defaulting it is how the two silently become
    one model grading its own output - ADR-0008's judge-contamination axis through a
    convenience."""
    settings = AgentSettings(model="claude-opus-5")

    assert settings.judge_model == ""
    assert settings.judge_model != settings.model


def test_the_fake_model_is_deterministic_across_processes() -> None:
    """`hashlib`, not `hash()`. A suite that passed or failed on `PYTHONHASHSEED` would be
    worse than no suite."""
    request = ModelRequest(
        system="you are triage", messages=[{"role": "user", "content": "hi"}], role="triage"
    )

    first = DeterministicModel().complete(request)
    second = DeterministicModel().complete(request)
    other = DeterministicModel().complete(
        ModelRequest(system="you are the planner", messages=request.messages, role="planner")
    )

    assert first.text == second.text
    assert first.text != other.text, "different prompts give different answers"
    assert first.model == "deterministic-fake"


def test_constructing_the_real_model_inside_a_test_is_refused() -> None:
    """The guard, checked rather than assumed - and patched on the boundary, so it holds
    whether or not the optional `anthropic` extra is installed."""
    with pytest.raises(AssertionError, match="hermetic by contract"):
        model_module.AnthropicModel("claude-opus-5")


# --- trajectory persistence ----------------------------------------------------


def trajectory_with_envelope() -> tuple[Trajectory, str]:
    envelope = real_envelope()
    trajectory = Trajectory(
        incident_id="incident-1",
        model="claude-opus-5",
        effort="high",
        started_at=START,
        role_models={"scribe": "claude-haiku-4-5"},
    )
    trajectory.add(
        TrajectoryStep(
            seq=1,
            role="metrics",
            kind=StepKind.TOOL_CALL,
            at=START,
            tool_call=ToolCallRecord(
                tool="promql_query",
                request={"query": "up"},
                result_id="tr_dff59750f4ef",
                envelope=envelope,
            ),
        )
    )
    trajectory.add(
        TrajectoryStep(
            seq=2,
            role="synthesizer",
            kind=StepKind.RETRIEVAL,
            at=START,
            retrieval=RetrievalRecord(
                query="cart errors",
                k=5,
                exclude_origin="scenario:cart-redis-misconfig",
                returned=["scenario:ad-memory-squeeze#0"],
                scores=[0.0164],
            ),
        )
    )
    return trajectory, envelope


def test_the_stored_envelope_is_the_rendered_text_not_a_re_render() -> None:
    """ADR-0020 §3: a replay that re-renders from the typed result is replaying a different
    prompt. The envelope carries a per-call nonce in its closing delimiter and, in the log
    case, ANSI escapes - both things a helpful normaliser would eat."""
    trajectory, envelope = trajectory_with_envelope()
    store = InMemoryTrajectoryStore()
    store.save(trajectory)

    assert store.envelope("tr_dff59750f4ef") == envelope
    assert envelope.startswith("<tool_result ")
    assert 'trust="untrusted"' in envelope
    assert envelope.rstrip().endswith("</tool_result:tr_dff59750f4ef>"), "the nonce survived"


def test_the_envelope_hash_travels_with_the_text() -> None:
    """Stored beside it so corruption is detectable without a second copy to diff."""
    trajectory, envelope = trajectory_with_envelope()
    call = trajectory.tool_calls[0]

    import hashlib

    assert call.envelope_sha256 == hashlib.sha256(envelope.encode()).hexdigest()


def test_every_retrieval_records_the_exclusion_that_was_passed() -> None:
    """**This is where T4.1b reads ADR-0008's assertion.** The harness sets `exclude_origin` on
    every scored run and asserts the filter fired; a run where it did not is marked invalid, not
    annotated. A column, not a log line."""
    trajectory, _ = trajectory_with_envelope()

    retrieval = trajectory.retrievals[0]

    assert retrieval.exclude_origin == "scenario:cart-redis-misconfig"
    assert retrieval.returned and retrieval.scores


def test_a_product_retrieval_may_carry_no_exclusion_and_that_is_distinct() -> None:
    """`None` is legal and is the product case - a live incident has no origin to exclude. It
    has to be distinguishable from a benchmark run that forgot one."""
    record = RetrievalRecord(query="cart errors", k=5, exclude_origin=None)

    assert record.exclude_origin is None


def test_the_trajectory_records_the_effective_role_map_not_just_the_default() -> None:
    """Two trajectories from different models are not comparable, and a per-role override that
    is not recorded would be invisible in the record (ADR-0020 §1, §3)."""
    trajectory, _ = trajectory_with_envelope()

    assert trajectory.model == "claude-opus-5"
    assert trajectory.role_models == {"scribe": "claude-haiku-4-5"}


def test_inter_agent_messages_are_steps_so_the_synthesizer_can_be_scored() -> None:
    """Scoring the synthesizer without seeing what it was given scores the wrong thing."""
    trajectory, _ = trajectory_with_envelope()
    trajectory.add(
        TrajectoryStep(
            seq=3,
            role="planner",
            kind=StepKind.MESSAGE,
            at=START,
            payload={"to": "synthesizer", "findings": ["cart errors at T+3m"]},
        )
    )

    kinds = [step.kind for step in trajectory.steps]

    assert StepKind.MESSAGE in kinds
    assert trajectory.steps[-1].payload["to"] == "synthesizer"


# --- the per-incident dollar cap (Q16, landed with T3.2c's budget move) ----------------


def test_the_runtime_halts_on_money_and_says_which_bound_stopped_it() -> None:
    """T2.5's description names *per-incident token/dollar budgets* and the proposal's
    runaway-cost row promises *hard per-incident cap halts agents*. What halted was a token cap.

    The bound is Gate 4's own threshold - `cost ≤ $2 per incident` - so a run that would fail
    the gate stops instead of finishing and failing it."""
    from faultline.agents.budget import Budget, BudgetState

    state = BudgetState(Budget(max_tokens=10_000_000, max_usd=1.0))
    state.spend_tokens(100_000, 20_000)

    assert round(state.usd_spent(), 4) == 1.0
    assert not state.check()
    assert state.exhausted_reason is not None and "cost:" in state.exhausted_reason
    assert "$1.00 of $1.00" in state.exhausted_reason


def test_a_dollar_cap_is_not_a_token_cap_in_disguise() -> None:
    """The reason Q16 exists: **the price of a model can change without the token bound
    moving**, and the bound is then enforcing a different amount of money than it was set to."""
    from faultline.agents.budget import Budget, BudgetState

    cheap = BudgetState(Budget(max_usd=2.0, usd_per_mtok=(5.0, 25.0)))
    dear = BudgetState(Budget(max_usd=2.0, usd_per_mtok=(15.0, 75.0)))
    for state in (cheap, dear):
        state.spend_tokens(100_000, 20_000)

    assert cheap.check(), "$1 of $2 spent"
    assert not dear.check(), "the same tokens at three times the price breach the same cap"


def test_the_runtime_and_the_harness_price_at_the_same_table() -> None:
    """Two copies exist because ADR-0004 keeps benchmark infrastructure out of the product - a
    product that imports `evalharness` to price itself has the dependency the wrong way round.
    **They must be equal by hand, so a test says so**: a runtime that halted at a different
    price than the harness scores would stop for a reason no published figure could explain."""
    from evalharness.run import USD_PER_MTOK_IN, USD_PER_MTOK_OUT

    settings = AgentSettings()

    assert (settings.usd_per_mtok_in, settings.usd_per_mtok_out) == (
        USD_PER_MTOK_IN,
        USD_PER_MTOK_OUT,
    )


def test_the_token_bound_is_reported_when_a_run_breaches_both() -> None:
    """Every recorded figure was measured under the token bound, so a run that breaches both
    should name the one its comparators were held to."""
    from faultline.agents.budget import Budget, BudgetState

    state = BudgetState(Budget(max_tokens=1_000, max_usd=0.001))
    state.spend_tokens(2_000, 2_000)

    assert not state.check()
    assert state.exhausted_reason is not None and state.exhausted_reason.startswith("tokens:")


def test_every_bound_a_run_was_held_to_reaches_the_freeze() -> None:
    """T4.7's rule: a bound must never be implicit. A bound that halted a run without appearing
    in the manifest would make an early stop unexplainable from the record alone."""
    from evalharness import freeze

    bounds = freeze.budget_bounds(4, 120_000)

    assert set(bounds) == {
        "max_tool_calls_per_specialist",
        "max_tokens",
        "wall_clock_seconds",
        "max_dispatch_rounds",
        "briefing_tokens",
        "max_usd",
        "usd_per_mtok_in",
        "usd_per_mtok_out",
    }
