"""Spans at the seams, joined to the trajectory by id (T6.6, piece 1).

## The decision

The trajectory store already records every agent step - role, kind, timestamp, tokens, the tool
envelope, the retrieval - to Postgres. That is a trace in everything but export. T6.6 does not
replace it and does not derive spans from it. **Spans are emitted live at the four chokepoints the
work actually passes through, and every `TrajectoryStep` written inside a span carries that span's
`trace_id` and `span_id`.** Two records of one event, joinable rather than parallel: the span is
what Grafana shows while the agent is thinking, the trajectory is the durable record the harness
scores from, and a reader with either can find the other.

The alternative - one emission point, spans derived from steps as they are added - was
considered and declined: a step is recorded when the work *finishes*, so the span would arrive
late and the "watch the agent think" beat becomes "read about it afterwards"; and the trajectory
never measured model-call latency (`latency_ms` is 0 on every COMPLETION step, set only around
tool queries), so there would be nothing to derive it from. A span around `roles.ask` measures it
for free.

## The four seams

| span | where | what it carries |
|---|---|---|
| `investigation` | `Investigation.run` | incident, trajectory id, model, outcome, tokens, cost |
| `model.call` | `roles.ask` | role, model, attempts, tokens in/out, stop reason |
| `tool.call` | `Investigation._run_dispatch` | tool, service, window, envelope bytes |
| `backend.get` | `telemetry.get_json` | backend host, path, status, bytes |

`ask` is a *logical* call: one `ask` can be two `complete` calls when the first is rejected and
re-asked. The span is around the logical call and `attempts` says how many wire calls it took.

## Why it is a no-op by default, and what that costs

`make check` runs in under three seconds and imports no SDK - the `agents` and `embeddings`
extras hold to that and this one does too. So `span()` always works: with the SDK installed and
`OTEL_EXPORTER_OTLP_ENDPOINT` set it opens a real span; otherwise it yields a handle whose ids are
empty and whose `set()` does nothing. Call sites are written once and do not branch.

The cost of that choice is that **a process nobody configured emits nothing and says nothing**.
`configure()` returns whether tracing is live and the entry points print which, so an operator
who expected traces and sees none has one line to read rather than a silent absence.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

SERVICE_NAME = "faultline"
"""What the spans are filed under in Tempo. One name for the API, the orchestrator and the
investigator, distinguished by `service.instance.id` and the `component` attribute, so the demo
beat - the agent's trace beside the outage's - is one query away rather than three."""

ENDPOINT_VAR = "OTEL_EXPORTER_OTLP_ENDPOINT"
"""The standard variable, not a `FAULTLINE_` one, so the compose files can set the same thing
the collector and every other OTel client already read. Unset means no export."""

_tracer: Any = None
_live = False


@dataclass(slots=True)
class SpanHandle:
    """What a call site gets back. **The same shape whether or not tracing is live.**

    `trace_id` and `span_id` are 32- and 16-character lowercase hex when live and empty strings
    otherwise, so a `TrajectoryStep` can carry them unconditionally and a reader can tell *not
    traced* from *traced* by emptiness rather than by a sentinel.
    """

    trace_id: str = ""
    span_id: str = ""
    _span: Any = field(default=None, repr=False)

    def set(self, **attributes: Any) -> None:
        """Attach attributes. Silently nothing when not live; never raises."""
        if self._span is None:
            return
        for key, value in attributes.items():
            if value is not None:
                self._span.set_attribute(key, value)

    def record_exception(self, exc: BaseException) -> None:
        if self._span is not None:
            self._span.record_exception(exc)
            self._span.set_status(_status_error(str(exc)))


def is_live() -> bool:
    """Whether spans are being exported. `False` until `configure()` succeeds."""
    return _live


def configure(*, endpoint: str | None = None, component: str = "faultline") -> bool:
    """Install the SDK and an OTLP/gRPC exporter if both are available. Returns whether live.

    Called once per process, by the entry point and not by a library module: the API, the
    orchestrator and `faultline-investigate` each know what they are, and a module that
    configured global state on import would do so for every test that touched it.

    **Three ways to come back `False`, and each is deliberate**: no endpoint (nobody asked),
    SDK not installed (the extra is not present - the `agents` pattern), or the SDK raising on
    setup (misconfiguration; reported, not fatal - an investigation that cannot export a trace
    should still investigate).
    """
    global _tracer, _live
    endpoint = endpoint if endpoint is not None else os.environ.get(ENDPOINT_VAR, "")
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return False
    try:
        resource = Resource.create({"service.name": SERVICE_NAME, "faultline.component": component})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(SERVICE_NAME)
        _live = True
    except Exception:  # pragma: no cover - needs a misconfigured SDK to reach
        _tracer = None
        _live = False
    return _live


def shutdown() -> None:
    """Flush the batch processor. Entry points call this on exit so the last spans arrive."""
    global _tracer, _live
    if not _live:
        return
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        flush = getattr(provider, "force_flush", None)
        if flush is not None:
            flush()
    finally:
        _tracer = None
        _live = False


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[SpanHandle]:
    """A span if live, a handle with empty ids otherwise. **Call sites never branch.**

    Attributes passed here are set at open; more can be added through the handle. An exception
    inside the block is recorded on the span and re-raised - the span reports it, it does not
    swallow it.
    """
    if not _live or _tracer is None:
        yield SpanHandle()
        return
    with _tracer.start_as_current_span(name) as otel_span:
        context = otel_span.get_span_context()
        handle = SpanHandle(
            trace_id=format(context.trace_id, "032x"),
            span_id=format(context.span_id, "016x"),
            _span=otel_span,
        )
        handle.set(**attributes)
        try:
            yield handle
        except BaseException as exc:
            handle.record_exception(exc)
            raise


def current_ids() -> tuple[str, str]:
    """`(trace_id, span_id)` of the span in scope, or `("", "")`.

    For the one place that records a step *outside* the span that did the work - the
    trajectory's own bookkeeping steps - so they can still be joined to the investigation's
    root span.
    """
    if not _live:
        return "", ""
    from opentelemetry import trace

    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return "", ""
    return format(context.trace_id, "032x"), format(context.span_id, "016x")


def _status_error(description: str) -> Any:
    from opentelemetry.trace import Status, StatusCode

    return Status(StatusCode.ERROR, description)
