"""T2.6's record/replay harness: a run recorded once plays back identically with no model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.agents.cassette import (
    FORMAT,
    CassetteMissError,
    RecordingModel,
    ReplayModel,
    request_key,
)
from faultline.agents.model import DeterministicModel, ModelRequest, ModelResponse
from tests.test_baseline_agent import CONCLUDE, VERDICT, ScriptedModel, call, investigate


def request(text: str = "what failed?", role: str = "planner") -> ModelRequest:
    return ModelRequest(
        system="you investigate", messages=[{"role": "user", "content": text}], role=role
    )


def test_a_recorded_call_replays_identically_without_the_model(tmp_path: Path) -> None:
    cassette = tmp_path / "c.json"
    inner = DeterministicModel()
    recorded = RecordingModel(inner, cassette).complete(request())

    replay = ReplayModel(cassette)
    played = replay.complete(request())

    assert played.text == recorded.text
    assert played.model == recorded.model
    assert (played.input_tokens, played.output_tokens) == (
        recorded.input_tokens,
        recorded.output_tokens,
    )
    assert len(inner.calls) == 1, "replay must not reach the recorded model"
    assert replay.remaining() == 0


def test_identical_requests_replay_in_the_order_they_were_recorded(tmp_path: Path) -> None:
    cassette = tmp_path / "c.json"
    recorder = RecordingModel(ScriptedModel(["first", "second"]), cassette)
    recorder.complete(request())
    recorder.complete(request())

    replay = ReplayModel(cassette)
    assert [replay.complete(request()).text for _ in range(2)] == ["first", "second"]


def test_a_request_the_cassette_never_saw_is_a_miss_not_an_invention(tmp_path: Path) -> None:
    """A changed prompt must fail loudly: replaying the old answer to a new question is the
    failure a fixture harness exists to prevent."""
    cassette = tmp_path / "c.json"
    RecordingModel(DeterministicModel(), cassette).complete(request("what failed?"))

    with pytest.raises(CassetteMissError, match="planner"):
        ReplayModel(cassette).complete(request("what failed, and when?"))


def test_one_more_call_than_was_recorded_is_a_miss(tmp_path: Path) -> None:
    cassette = tmp_path / "c.json"
    RecordingModel(DeterministicModel(), cassette).complete(request())
    replay = ReplayModel(cassette)
    replay.complete(request())
    with pytest.raises(CassetteMissError):
        replay.complete(request())


def test_the_key_covers_everything_an_answer_can_depend_on() -> None:
    base = request()
    variants = [
        ModelRequest(system="other", messages=base.messages, role=base.role),
        ModelRequest(system=base.system, messages=base.messages, role="synthesizer"),
        ModelRequest(system=base.system, messages=base.messages, role=base.role, max_tokens=10),
        ModelRequest(system=base.system, messages=base.messages, role=base.role, effort="low"),
        ModelRequest(
            system=base.system, messages=base.messages, role=base.role, tools=[{"name": "t"}]
        ),
    ]
    assert len({request_key(r) for r in [base, *variants]}) == len(variants) + 1


def test_the_cassette_is_a_versioned_json_file_without_raw_provider_payloads(
    tmp_path: Path,
) -> None:
    cassette = tmp_path / "c.json"
    RecordingModel(DeterministicModel(), cassette).complete(request())
    document = json.loads(cassette.read_text())
    assert document["format"] == FORMAT
    assert "raw" not in document["entries"][0]["response"]


def test_an_agent_run_recorded_once_replays_to_the_same_investigation(tmp_path: Path) -> None:
    """The plan's sentence, end to end: an agent (B1's loop, tools and all) is recorded against a
    model once, then run again against the cassette alone and reaches the same verdict through
    the same tool calls, with every recorded answer consumed."""
    cassette = tmp_path / "b1.json"
    script = [call("changes", "adservice"), CONCLUDE, VERDICT]
    first = investigate(RecordingModel(ScriptedModel(list(script)), cassette))

    replay = ReplayModel(cassette)
    second = investigate(replay)

    assert second.error is None
    assert second.verdict == first.verdict
    assert [(look.tool, look.service) for look in second.looks] == [
        (look.tool, look.service) for look in first.looks
    ]
    assert replay.remaining() == 0


def test_tool_result_ids_are_keyed_by_position_and_mapped_back_on_replay(tmp_path: Path) -> None:
    """Envelope ids are random per call (ADR-0019), so a replay sees different ids from the
    recording. The key must not depend on them, and a recorded citation must come back citing
    the replay's own envelope - or the citation check would fail every replayed verdict."""
    cassette = tmp_path / "c.json"
    recorded_id, replay_id = "tr_" + "a" * 12, "tr_" + "b" * 12

    class Citer:
        name = "citer"

        def complete(self, req: ModelRequest) -> ModelResponse:
            return ModelResponse(text=f"the cause is in {recorded_id}", model=self.name)

    RecordingModel(Citer(), cassette).complete(request(f"<tool_result id={recorded_id}>x"))
    played = ReplayModel(cassette).complete(request(f"<tool_result id={replay_id}>x"))

    assert played.text == f"the cause is in {replay_id}"
    assert recorded_id not in cassette.read_text()
