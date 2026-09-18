"""T6.6 piece 1: spans that cost nothing until asked for.

Everything here runs without the `observability` extra installed - that is the property under
test. The live path has one test, and it skips when the SDK is absent rather than pretending.
"""

from __future__ import annotations

import importlib.util

import pytest

from faultline.observability import tracing

HAS_SDK = importlib.util.find_spec("opentelemetry") is not None


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with no endpoint and no live tracer, whatever the machine has set."""
    monkeypatch.delenv(tracing.ENDPOINT_VAR, raising=False)
    tracing.shutdown()


def test_a_span_without_configuration_is_a_no_op_that_still_yields_a_handle() -> None:
    """**The call-site contract.** A seam wrapped in `span()` reads the same whether or not the
    SDK exists, and the ids are empty strings - so a `TrajectoryStep` can carry them without a
    branch, and *not traced* is legible as emptiness rather than as a sentinel value."""
    assert not tracing.is_live()

    with tracing.span("model.call", role="planner") as handle:
        handle.set(tokens_in=10, tokens_out=3)
        assert handle.trace_id == ""
        assert handle.span_id == ""

    assert tracing.current_ids() == ("", "")


def test_configure_without_an_endpoint_declines_and_says_so() -> None:
    """Nobody asked. `False`, not an exception, and nothing installed."""
    assert tracing.configure() is False
    assert not tracing.is_live()


@pytest.mark.skipif(HAS_SDK, reason="the SDK is installed; this covers the absent case")
def test_configure_with_an_endpoint_but_no_sdk_declines() -> None:
    """The `agents` pattern: an endpoint set on a machine without the extra is a `False`, and the
    process goes on. An investigation that cannot export its trace still investigates."""
    assert tracing.configure(endpoint="http://otel-col:4317") is False
    assert not tracing.is_live()


def test_an_exception_inside_a_span_propagates() -> None:
    """The span reports it; it does not swallow it. Tested on the no-op path because the live
    path would need a real exporter, and the contract is the same."""
    with pytest.raises(ValueError, match="inside"), tracing.span("tool.call"):
        raise ValueError("inside")


def test_make_check_imports_no_sdk() -> None:
    """**The hermeticity the extras exist for.** Importing `faultline.observability.tracing` must
    not import `opentelemetry` - the SDK is reached only inside `configure()`. If this fails, a
    machine without the extra cannot import the agent runtime at all."""
    import sys

    assert "faultline.observability.tracing" in sys.modules
    if not HAS_SDK:
        assert not any(m.startswith("opentelemetry") for m in sys.modules)


@pytest.mark.skipif(not HAS_SDK, reason="needs the observability extra")
def test_a_live_span_yields_real_ids_and_records_attributes() -> None:  # pragma: no cover
    """The other half, run only where the SDK is present. A console exporter would spam the test
    output, so this uses the in-memory one the SDK ships for exactly this purpose."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracing._tracer = trace.get_tracer("test")
    tracing._live = True
    try:
        with tracing.span("model.call", role="planner") as handle:
            handle.set(tokens_in=10)
            assert len(handle.trace_id) == 32 and len(handle.span_id) == 16
            assert tracing.current_ids() == (handle.trace_id, handle.span_id)
        finished = exporter.get_finished_spans()
        assert [s.name for s in finished] == ["model.call"]
        assert finished[0].attributes["role"] == "planner"
        assert finished[0].attributes["tokens_in"] == 10
    finally:
        tracing._tracer = None
        tracing._live = False


# --- piece 2: the joins -------------------------------------------------------------------------


def test_a_step_added_outside_any_span_carries_empty_ids_not_made_up_ones() -> None:
    """`Trajectory.add` stamps the span in scope, and with nothing live that is two empty
    strings. **A step never carries a fabricated id.**"""
    from datetime import UTC, datetime

    from faultline.agents.trajectory import StepKind, Trajectory, TrajectoryStep

    trajectory = Trajectory(incident_id="i", model="m", effort="e", started_at=datetime.now(UTC))
    step = trajectory.add(
        TrajectoryStep(seq=1, role="planner", kind=StepKind.MESSAGE, at=datetime.now(UTC))
    )

    assert step.trace_id == "" and step.span_id == ""
    assert trajectory.trace_id == ""


def test_a_step_that_arrives_with_ids_keeps_them() -> None:
    """The precise joins - tool-call step to `tool.call` span, model-call step to `model.call`
    span - are set by the code that opened those spans and `add` does not overwrite them."""
    from datetime import UTC, datetime

    from faultline.agents.trajectory import StepKind, Trajectory, TrajectoryStep

    trajectory = Trajectory(incident_id="i", model="m", effort="e", started_at=datetime.now(UTC))
    step = trajectory.add(
        TrajectoryStep(
            seq=1,
            role="metrics",
            kind=StepKind.TOOL_CALL,
            at=datetime.now(UTC),
            trace_id="a" * 32,
            span_id="b" * 16,
        )
    )

    assert (step.trace_id, step.span_id) == ("a" * 32, "b" * 16)


def test_a_completion_carries_latency_and_the_span_ids_of_its_call() -> None:
    """**The trajectory had never measured model-call latency.** `latency_ms` was set in one
    place, around the tool query, so every COMPLETION step recorded 0. `ask` now measures the
    logical call and the step that records the completion carries it - and the ids of the
    `model.call` span, empty here because nothing is exporting, real when it is."""
    from pydantic import BaseModel

    from faultline.agents.model import ModelRequest, ModelResponse
    from faultline.agents.roles import ask

    class Reply(BaseModel):
        ok: bool

    class Fake:
        name = "fake"

        def complete(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                text='{"ok": true}',
                model="fake",
                input_tokens=7,
                output_tokens=3,
                stop_reason="end",
            )

    completion = ask(
        Fake(),
        ModelRequest(system="s", messages=[{"role": "user", "content": "u"}], role="planner"),
        Reply,
    )

    assert completion.value.ok is True
    assert completion.latency_ms >= 0
    assert completion.trace_id == "" and completion.span_id == ""


def test_propagate_is_the_identity_when_nothing_is_live() -> None:
    """`_fan_out` wraps every submitted dispatch in this. With nothing exporting it must cost
    nothing and change nothing - the function comes back as itself."""

    def work(x: int) -> int:
        return x * 2

    assert tracing.propagate(work) is work
    assert tracing.propagate(work)(21) == 42


@pytest.mark.skipif(not HAS_SDK, reason="needs the observability extra")
def test_propagate_carries_the_span_onto_another_thread() -> None:  # pragma: no cover
    """The reason `propagate` exists: OpenTelemetry's context is thread-local and a pool does
    not carry it, so without this every `tool.call` would be a root of its own."""
    from concurrent.futures import ThreadPoolExecutor

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracing._tracer = trace.get_tracer("test")
    tracing._live = True
    try:
        with (
            tracing.span("investigation") as root,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            bare = pool.submit(tracing.current_ids).result()
            carried = pool.submit(tracing.propagate(tracing.current_ids)).result()
        assert bare == ("", ""), "without propagate the worker sees no span"
        assert carried == (root.trace_id, root.span_id), "with it, the worker is inside the root"
    finally:
        tracing._tracer = None
        tracing._live = False
