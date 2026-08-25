"""The four tools T3.x calls (T2.6, ADR-0019).

**Read-only is a property of this surface, not of a credential.** Prometheus in this world
runs with `--web.enable-lifecycle` (`compose/telemetry.yml:69`), so `POST /-/reload` is open
to anything that can reach the port, and Loki's push endpoint is open by necessity
(`compose/promtail-config.yml:20`). An agent with a raw HTTP client could reload Prometheus's
configuration or write fabricated lines into the corpus it is investigating.

So three things hold instead, and they are structural:

1. **Fixed paths.** Each tool reaches one or two constants. Nothing here builds a path from
   agent input.
2. **No agent-supplied URLs, hosts, or ports.** Endpoints come from `ToolSettings`, which
   ADR-0004's runtime contract already required.
3. **No write verb anywhere.** `faultline.telemetry.get_json` issues GETs; there is no POST
   path in the layer to reach.

`tests/test_tools.py` asserts the layer exposes no callable that could reach a lifecycle or
push endpoint. Real credentials, network policy and egress restriction are T6.8's, and are
listed there.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any

from faultline import telemetry
from faultline.tools.results import (
    ChangeResult,
    LogLine,
    LogResult,
    MetricResult,
    MetricSeries,
    TraceResult,
    TraceSpan,
    Window,
)
from faultline.tools.settings import ToolSettings
from injector.world import SERVICE_CONTAINERS, canonical_service

PROMETHEUS_QUERY_RANGE = "/api/v1/query_range"
LOKI_QUERY_RANGE = "/loki/api/v1/query_range"
JAEGER_TRACES = "/api/traces"

ALLOWED_PATHS = frozenset({PROMETHEUS_QUERY_RANGE, LOKI_QUERY_RANGE, JAEGER_TRACES})
"""Every path this layer can reach. Asserted by test, so adding one is a visible act."""


class Tools:
    """The agent-facing tool set. One object, four methods, no others that reach the world."""

    def __init__(self, settings: ToolSettings | None = None, changes: Any = None) -> None:
        self._settings = settings or ToolSettings()
        self._changes = changes
        """A change-record reader. `None` means change history is unavailable, which is
        reported as an error rather than as an empty result - the difference is the whole
        point (ADR-0019)."""

    # --- window discipline ----------------------------------------------------

    def _check_window(self, start: datetime, end: datetime) -> str | None:
        if end <= start:
            return "window end is not after its start"
        span = (end - start).total_seconds()
        if span > self._settings.max_window_seconds:
            return (
                f"window is {span / 3600:.1f}h and retention is "
                f"{self._settings.max_window_seconds / 3600:.0f}h, so the answer would be "
                "partial without saying so"
            )
        return None

    # --- promql ---------------------------------------------------------------

    def promql_query(
        self, query: str, start: datetime, end: datetime, step: int = 15
    ) -> MetricResult:
        """Range query against Prometheus. `series: []` is a legal, meaningful answer."""
        window = Window(start=start, end=end)
        refusal = self._check_window(start, end)
        if refusal is not None:
            return MetricResult(query=query, window=window, error=refusal, empty=True)
        try:
            payload = telemetry.query_range(
                query, start, end, step=step, base=self._settings.prometheus_url
            )
        except Exception as exc:
            return MetricResult(query=query, window=window, error=str(exc), empty=True)

        raw = payload.get("data", {}).get("result", [])
        series = [
            MetricSeries(
                labels={str(k): str(v) for k, v in entry.get("metric", {}).items()},
                points=[(float(at), float(value)) for at, value in entry.get("values", [])],
            )
            for entry in raw
        ]
        return MetricResult(query=query, window=window, series=series, empty=not series)

    # --- logql ----------------------------------------------------------------

    def logql_query(
        self, service: str, start: datetime, end: datetime, limit: int | None = None
    ) -> LogResult:
        """Logs for one service. The window may open before onset, and usually should.

        Three narratives read logs from before the incident and `shipping-wrong-image` says
        the pre-onset stream "is where it breaks open" - a JVM banner in a service whose logs
        had never contained one. A tool that only looked forward from the alert would miss it.
        """
        container = SERVICE_CONTAINERS.get(canonical_service(service), service)
        selector = f'{{service="{container}"}}'
        window = Window(start=start, end=end)
        refusal = self._check_window(start, end)
        if refusal is not None:
            return LogResult(selector=selector, window=window, error=refusal, empty=True)

        cap = limit or self._settings.max_log_lines
        try:
            payload = telemetry.get_json(
                self._settings.loki_url,
                LOKI_QUERY_RANGE,
                {
                    "query": selector,
                    "start": str(int(start.timestamp() * 1e9)),
                    "end": str(int(end.timestamp() * 1e9)),
                    "limit": str(cap),
                    # Backward, so Loki's own cap keeps the NEWEST lines. Found by the T2.6
                    # smoke: forward returned the oldest 15 lines of a 15-minute window, all
                    # of them 13 minutes before the injection. The result was correctly
                    # flagged truncated and investigatively useless - an agent asking what
                    # happened received healthy pre-onset traffic.
                    "direction": "backward",
                },
            )
        except Exception as exc:
            return LogResult(selector=selector, window=window, error=str(exc), empty=True)

        lines: list[LogLine] = []
        for stream in payload.get("data", {}).get("result", []):
            for at_ns, text in stream.get("values", []):
                lines.append(
                    LogLine(at=datetime.fromtimestamp(int(at_ns) / 1e9, tz=start.tzinfo), line=text)
                )
        # Truncate from the newest end, then display oldest-first. A responder needs the
        # most recent lines and reads them in order; those are different questions and the
        # first one has to be answered before the second.
        lines.sort(key=lambda entry: entry.at, reverse=True)
        kept = sorted(lines[:cap], key=lambda entry: entry.at)
        return LogResult(
            selector=selector,
            window=window,
            lines=kept,
            empty=not lines,
            truncated=len(lines) >= cap,
        )

    # --- traces ---------------------------------------------------------------

    def trace_query(
        self, service: str, start: datetime, end: datetime, only_errors: bool = False
    ) -> TraceResult:
        """Traces touching one service. **The fourth tool, decided at implementation.**

        `ARCHITECTURE.md` named three. Two narratives' first real narrowing is a trace query -
        "checkout spans failing on their call to cart", in both cart scenarios - and forcing
        the longer path through error rates and the dependency graph would measure the tool
        set rather than the agent (ADR-0019).
        """
        canonical = canonical_service(service)
        window = Window(start=start, end=end)
        refusal = self._check_window(start, end)
        if refusal is not None:
            return TraceResult(service=canonical, window=window, error=refusal, empty=True)

        try:
            payload = telemetry.get_json(
                self._settings.jaeger_url,
                JAEGER_TRACES,
                {
                    "service": canonical,
                    "start": str(int(start.timestamp() * 1e6)),
                    "end": str(int(end.timestamp() * 1e6)),
                    "limit": str(self._settings.max_spans),
                },
            )
        except Exception as exc:
            return TraceResult(service=canonical, window=window, error=str(exc), empty=True)

        spans = [
            span for trace in payload.get("data", []) for span in _spans_of(trace, start.tzinfo)
        ]
        if only_errors:
            spans = [span for span in spans if span.error]
        # Same truncation direction as the logs, and the same reason. Jaeger returns whole
        # traces and this flattens them, so without an explicit ordering the retained 200
        # would be whichever traces the API happened to list first - which in the T2.6 smoke
        # was the oldest end of the window.
        newest_first = sorted(spans, key=lambda span: span.started_at, reverse=True)
        kept = sorted(newest_first[: self._settings.max_spans], key=lambda span: span.started_at)
        return TraceResult(
            service=canonical,
            window=window,
            spans=kept,
            empty=not spans,
            truncated=len(spans) > self._settings.max_spans,
        )

    # --- change history -------------------------------------------------------

    def change_history(self, service: str, start: datetime, end: datetime) -> ChangeResult:
        """What changed on a service, and **an empty answer is an answer**.

        Five of the nine rehearsed investigations turn on nothing having changed. That is why
        an unavailable change log is an `error` and an observed-empty window is `empty`: a
        negative from a source that was not consulted is not evidence.
        """
        canonical = canonical_service(service)
        window = Window(start=start, end=end)
        if self._changes is None:
            return ChangeResult(
                service=canonical,
                window=window,
                error="no change log configured, so this window was not observed",
                empty=True,
            )
        try:
            records = self._changes.records_for(canonical, start, end)
        except Exception as exc:
            return ChangeResult(service=canonical, window=window, error=str(exc), empty=True)
        return ChangeResult(
            service=canonical,
            window=window,
            records=[record.as_row() for record in records],
            empty=not records,
        )


def _spans_of(trace: dict[str, Any], tzinfo: Any) -> list[TraceSpan]:
    processes = trace.get("processes", {})
    spans: list[TraceSpan] = []
    for span in trace.get("spans", []):
        process = processes.get(span.get("processID"), {})
        tags = {tag.get("key"): tag.get("value") for tag in span.get("tags", [])}
        spans.append(
            TraceSpan(
                trace_id=str(trace.get("traceID", "")),
                service=str(process.get("serviceName", "")),
                operation=str(span.get("operationName", "")),
                started_at=datetime.fromtimestamp(int(span.get("startTime", 0)) / 1e6, tz=tzinfo),
                duration_ms=float(span.get("duration", 0)) / 1000.0,
                error=bool(tags.get("error")) or str(tags.get("otel.status_code")) == "ERROR",
            )
        )
    return spans


def prometheus_url(settings: ToolSettings, query: str, start: int, end: int, step: int) -> str:
    """Exposed for the read-only test: the only Prometheus URL this layer can build."""
    params = urllib.parse.urlencode(
        {"query": query, "start": str(start), "end": str(end), "step": str(step)}
    )
    return f"{settings.prometheus_url}{PROMETHEUS_QUERY_RANGE}?{params}"
