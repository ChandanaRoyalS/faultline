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
