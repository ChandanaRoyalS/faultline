"""`McpToolSet`: Faultline's five tools over SREGym's MCP servers (T7.2, ADR-0044).

**A subclass of `Tools`, not a rewrite.** What an agent sees from a tool is decided far more by the
code around the backend read than by the read: the window policy and its refusals, the breakers,
the baseline window and its summaries, change points, the span tree, truncation flags. Inheriting
keeps all of that the same code the agent always ran. What is overridden is the read itself, and
what the read cannot do through SREGym's servers is said in the result rather than hidden:

- **`promql_query`, `metric_baseline`**: `get_metrics` is an **instant** query. The range is read
  as one instant query of `(q)[d:step] @ end`, a subquery whose points are aligned to multiples of
  `step` rather than to `start`.
- **`metric_baseline`**: span-metric templates read SREGym's spelling (`Profile.span_metrics`).
  For a service with no series in the last hour, they are an **error**, never an empty answer
  (ADR-0019; the owner's decision of 2026-10-03, after the dev read). So is `latency-p95` where
  SREGym's histogram cannot measure it (`Profile.latency_readable`, Addendum 4's F4). Runtime
  memory is cAdvisor's working set, for every application.
- **`logql_query`**: `get_logs` reads a window **ending now**, the newest **100** lines, with
  timestamps in whole seconds. It is asked back to the window's start and filtered to it. A reply
  of 100 lines is `truncated`, even when none falls in the window. There is no forward read, so
  no two-ended split.
- **`trace_query`**: `get_traces` returns Jaeger's reply as a Python repr, **20** traces, ending
  now. It is parsed with `ast.literal_eval` and converted to the span model the span tree reads.
  20 traces is `truncated`. `source` stays `tempo`: it is a contract literal, and the agent's
  prompts name no backend.
- **`change_history`**: `faultline.sregym.kube.KubernetesChangeLog`, read-only, through `Tools`'
  own `changes` seam, unchanged, and marked `truncated` when SREGym cut one of its answers.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from faultline.sregym.mcp import McpClient, backend_error, python_literal
from faultline.sregym.profiles import Profile
from faultline.tools.metrics import (
    MetricTemplate,
    change_points,
    defined,
    render_query,
    summarise,
)
from faultline.tools.ranking import RankingContext
from faultline.tools.results import (
    BaselineResult,
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
from faultline.tools.spantree import max_depth_for
from faultline.tools.tools import CONTAINS_MAX_CHARS, Tools, _as_stats, logql_string
from injector.world import canonical_service

LOKI_LINE_CAP = 100
"""`get_logs`' fixed `limit` (`mcp_server/loki_server.py` at `46c853db`)."""

JAEGER_TRACE_CAP = 20
"""`get_traces`' fixed `limit` (`mcp_server/jaeger_server.py` at `46c853db`)."""

SPAN_TEMPLATES = frozenset(
    {MetricTemplate.ERROR_RATIO, MetricTemplate.CALL_RATE, MetricTemplate.LATENCY_P95}
)

LOKI_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] \[([^\]]*)\] (.*)$", re.DOTALL)
"""`get_logs` renders each entry as `[YYYY-mm-dd HH:MM:SS] [k=v, ...] line`."""


def subquery(query: str, start: datetime, end: datetime, step: int) -> str:
    """A range read as one instant query: `(q)[d:step] @ end`, `d` the window in seconds."""
    seconds = max(step, math.ceil((end - start).total_seconds()))
    return f"({query})[{seconds}s:{step}s] @ {end.timestamp():.3f}"


def matrix(payload: Any) -> list[dict[str, Any]]:
    """`get_metrics`' `data` as a list of `{metric, values}`, whatever its result type."""
    if not isinstance(payload, dict):
        return []
    result = payload.get("result") or []
    if payload.get("resultType") == "vector":
        return [{"metric": e.get("metric", {}), "values": [e.get("value")]} for e in result]
    return [e for e in result if isinstance(e, dict)]


WORKLOAD_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
"""A Kubernetes object name (DNS-1123 subdomain): the only RE2 metacharacter it can hold is `.`."""


def pod_pattern(deployment: str) -> str:
    """A Deployment's pods (`name-<hash>-<id>`) or a StatefulSet's (`name-<n>`), and no other.

    **Written for the double-quoted LogQL or PromQL string it is placed in** (adapter
    registration, Addendum 4, F1). Both backends unquote that string as Go does before RE2 sees
    it, and Go refuses an escape it does not know. `re.escape` wrote `product-catalog` as
    `product\\-catalog`, so the pilot's every log query and the memory query on a hyphenated name
    came back HTTP 400. A hyphen needs no escape outside a character class, so it is written as
    itself. `.` is written `\\\\.`, which the string decodes to `\\.` for RE2. A name that is not
    DNS-1123 is refused rather than escaped.
    """
    if not WORKLOAD_NAME.match(deployment):
        raise ValueError(f"not a Kubernetes workload name: {deployment!r}")
    name = deployment.replace(".", "\\\\.")
    return f"{name}-([a-z0-9]+-[a-z0-9]+|[0-9]+)"


def memory_query(namespace: str, deployment: str) -> str:
    """Runtime memory for every application: cAdvisor's working set, summed over the pods."""
    return (
        "sum(container_memory_working_set_bytes"
        f'{{namespace="{namespace}",pod=~"{pod_pattern(deployment)}",'
        'container!="",container!="POD"})'
    )


class McpToolSet(Tools):
    """The five tools, reading one SREGym application through its MCP servers."""

    def __init__(
        self,
        client: McpClient,
        profile: Profile,
        namespace: str,
        settings: ToolSettings | None = None,
        changes: Any = None,
        now: Any = None,
    ) -> None:
        super().__init__(settings, changes=changes)
        self._client = client
        self._profile = profile
        self._namespace = namespace
        self._now = now or (lambda: datetime.now(UTC))
        self._span_series: dict[str, bool | None] = {}
        """Injected for the tests. The log and trace servers read windows ending at their own
        now, so the lookback asked for is measured from this one."""

    # --- metrics -------------------------------------------------------------------

    def _metrics(self, query: str, start: datetime, end: datetime, step: int) -> Any:
        """One range read through `get_metrics`. Raises on a reported backend error."""
        text = self._client.call(
            "prometheus", "get_metrics", {"query": subquery(query, start, end, step)}
        )
        error = backend_error(text)
        if error is not None:
            raise RuntimeError(error)
        return python_literal(text)

    def _points(
        self, query: str, start: datetime, end: datetime, step: int
    ) -> list[tuple[float, float]] | str:
        try:
            payload = self._backend("prometheus", lambda: self._metrics(query, start, end, step))
        except Exception as exc:
            return str(exc)
        points: list[tuple[float, float]] = []
        for entry in matrix(payload):
            for pair in entry.get("values", []) or []:
                if pair:
                    points.append((float(pair[0]), float(pair[1])))
        return sorted(points)

    def promql_query(
        self, query: str, start: datetime, end: datetime, step: int = 15
    ) -> MetricResult:
        window = Window(start=start, end=end)
        refusal = self._check_window("promql_query", query, start, end)
        if refusal is not None:
            return MetricResult(query=query, window=window, error=refusal, empty=True)
        try:
            payload = self._backend("prometheus", lambda: self._metrics(query, start, end, step))
        except Exception as exc:
            return MetricResult(query=query, window=window, error=str(exc), empty=True)
        series = [
            MetricSeries(
                labels={str(k): str(v) for k, v in entry.get("metric", {}).items()},
                points=[(float(at), float(value)) for at, value in entry.get("values", []) or []],
            )
            for entry in matrix(payload)
        ]
        return MetricResult(query=query, window=window, series=series, empty=not series)

    def has_span_series(self, service: str) -> bool | None:
        """Whether `service` has any span-metric series in the last hour, or `None` if unknown.

        The owner's decision of 2026-10-03: on Hotel Reservation and Social Network most services
        send no traces as SREGym ships them (Q127), so their span-metric templates would read as
        empty, which a responder takes for *no traffic*. Asked once per service per tool set.
        """
        if service in self._span_series:
            return self._span_series[service]
        world = self._profile.span_metrics
        if world is None:
            return False
        query = f'count(last_over_time({world.calls}{{service_name="{service}"}}[1h]))'

        def ask() -> bool:
            text = self._client.call("prometheus", "get_metrics", {"query": query})
            error = backend_error(text)
            if error is not None:
                raise RuntimeError(error)
            return bool(matrix(python_literal(text)))

        try:
            found: bool | None = self._backend("prometheus", ask)
        except Exception:
            found = None
        self._span_series[service] = found
        return found

    def unreadable(self, template: MetricTemplate, service: str) -> str | None:
        """Why this template cannot be read on this application, or `None` if it can.

        Both reasons are SREGym's as shipped, and both make a number that is not a measurement,
        so the tool says *unavailable* rather than returning it:

        - **no span-metric series** for the service (the owner's decision after the dev read);
        - **a latency histogram whose top bound every span exceeds** (`Profile.latency_readable`;
          the owner's decision of 2026-10-03, adapter registration Addendum 4, F4).
        """
        if template is MetricTemplate.RUNTIME_MEMORY:
            return None
        if self._profile.span_metrics is None or self.has_span_series(service) is False:
            return (
                f"{template.value} reads span metrics, and SREGym's Prometheus holds none "
                f"for {service}: it sends no traces that become metrics. This is "
                "unavailable, not zero"
            )
        if template is MetricTemplate.LATENCY_P95 and not self._profile.latency_readable:
            return (
                f"{template.value} cannot be read on this application: SREGym's span-metric "
                "histogram for it tops out at 0.005 ms, so every span is above its top bound "
                "and the 95th percentile is that bound whatever the latency. This is "
                "unavailable, not fast"
            )
        return None

    def template_query(self, template: MetricTemplate, service: str) -> str | None:
        """The PromQL for one template on this application, or `None` if it cannot be read."""
        if template is MetricTemplate.RUNTIME_MEMORY:
            return memory_query(self._namespace, self._profile.deployment(service))
        if self.unreadable(template, service) is not None:
            return None
        assert self._profile.span_metrics is not None
        return render_query(template, service, self._profile.span_metrics)

    def metric_baseline(
        self,
        service: str,
        template: MetricTemplate,
        start: datetime,
        end: datetime,
        step: int = 15,
    ) -> BaselineResult:
        """`Tools.metric_baseline`, with the query this application can answer.

        **The body below is `Tools.metric_baseline`'s, line for line, from the window check on.**
        Only the query differs. `tests/test_sregym.py` runs both on the same points and requires
        the same result, so the two cannot drift apart unnoticed.
        """
        canonical = canonical_service(service)
        query = self.template_query(template, canonical)
        window = Window(start=start, end=end)
        span = end - start
        before = Window(start=start - span, end=start)
        if query is None:
            return BaselineResult(
                service=canonical,
                template=template.value,
                query="",
                window=window,
                baseline_window=before,
                error=self.unreadable(template, canonical),
                empty=True,
            )
        refusal = self._check_window("metric_baseline", query, before.start, end)
        if refusal is not None:
            return BaselineResult(
                service=canonical,
                template=template.value,
                query=query,
                window=window,
                baseline_window=before,
                error=refusal,
                empty=True,
            )

        incident_points = self._points(query, start, end, step)
        if isinstance(incident_points, str):
            return BaselineResult(
                service=canonical,
                template=template.value,
                query=query,
                window=window,
                baseline_window=before,
                error=incident_points,
                empty=True,
            )
        baseline_points = self._points(query, before.start, before.end, step)
        if isinstance(baseline_points, str):
            return BaselineResult(
                service=canonical,
                template=template.value,
                query=query,
                window=window,
                baseline_window=before,
                error=f"the baseline window could not be read: {baseline_points}",
                empty=True,
            )

        incident_defined, incident_undefined = defined(incident_points)
        baseline_defined, baseline_undefined = defined(baseline_points)
        baseline = summarise(baseline_defined)
        incident = summarise(incident_defined)
        found = change_points(incident_defined, template, baseline, tz=start.tzinfo)
        return BaselineResult(
            service=canonical,
            template=template.value,
            query=query,
            window=window,
            baseline_window=before,
            incident=_as_stats(incident),
            baseline=_as_stats(baseline),
            incident_undefined=incident_undefined,
            baseline_undefined=baseline_undefined,
            changes=[
                {"at": point.at.isoformat(), "value": point.value, "threshold": point.threshold}
                for point in found
            ],
            empty=not incident_points,
        )

    # --- changes -------------------------------------------------------------------

    def change_history(
        self,
        service: str,
        start: datetime,
        end: datetime,
        ranking: RankingContext | None = None,
    ) -> ChangeResult:
        """`Tools.change_history`, unchanged, **marked truncated when an answer was cut**.

        SREGym's kubectl server cuts every answer at 10,000 characters. The change log keeps the
        lines a cut answer holds and names it (`KubernetesChangeLog.cut`), and the result says
        so with the flag every other tool uses for a partial read (adapter registration,
        Addendum 4, F2).
        """
        result = super().change_history(service, start, end, ranking)
        if result.error is None and getattr(self._changes, "cut", None):
            return result.model_copy(update={"truncated": True})
        return result

    # --- logs ----------------------------------------------------------------------

    def _lookback_minutes(self, start: datetime) -> int:
        """Whole minutes from `start` to now, plus one: the servers' windows end at their now."""
        return max(1, math.ceil((self._now() - start).total_seconds() / 60) + 1)

    def logql_query(
        self,
        service: str,
        start: datetime,
        end: datetime,
        limit: int | None = None,
        contains: str | None = None,
    ) -> LogResult:
        canonical = canonical_service(service)
        selector = (
            f'{{namespace="{self._namespace}",'
            f'pod=~"{pod_pattern(self._profile.deployment(canonical))}"}}'
        )
        contains = (contains or "").strip()[:CONTAINS_MAX_CHARS]
        if contains:
            selector = f"{selector} |= {logql_string(contains)}"
        window = Window(start=start, end=end)
        refusal = self._check_window("logql_query", selector, start, end)
        if refusal is not None:
            return LogResult(
                selector=selector, contains=contains, window=window, error=refusal, empty=True
            )

        def fetch() -> str:
            text = self._client.call(
                "loki",
                "get_logs",
                {"query": selector, "last_n_minutes": self._lookback_minutes(start)},
            )
            error = backend_error(text)
            if error is not None:
                raise RuntimeError(error)
            return text

        try:
            text = self._backend("loki", fetch)
        except Exception as exc:
            return LogResult(
                selector=selector, contains=contains, window=window, error=str(exc), empty=True
            )

        parsed = parse_log_lines(text, start.tzinfo or UTC)
        # Whole seconds: a line stamped in the window's last second belongs to it.
        last = end + timedelta(seconds=1)
        kept = sorted(
            (line for line in parsed if start - timedelta(seconds=1) < line.at < last),
            key=lambda line: line.at,
        )
        cap = limit or self._settings.max_log_lines
        capped = len(parsed) >= LOKI_LINE_CAP
        return LogResult(
            selector=selector,
            contains=contains,
            window=window,
            lines=kept[-cap:],
            empty=not kept,
            truncated=capped or len(kept) > cap,
        )

    # --- traces --------------------------------------------------------------------

    def trace_query(
        self, service: str, start: datetime, end: datetime, only_errors: bool = False
    ) -> TraceResult:
        canonical = canonical_service(service)
        window = Window(start=start, end=end)
        refusal = self._check_window("trace_query", canonical, start, end)
        if refusal is not None:
            return TraceResult(service=canonical, window=window, error=refusal, empty=True)

        def fetch() -> Any:
            text = self._client.call(
                "jaeger",
                "get_traces",
                {"service": canonical, "last_n_minutes": self._lookback_minutes(start)},
            )
            error = backend_error(text)
            if error is not None:
                raise RuntimeError(error)
            return python_literal(text)

        try:
            found = self._backend("tempo", fetch)
        except Exception as exc:
            return TraceResult(service=canonical, window=window, error=str(exc), empty=True)

        traces = [t for t in (found or []) if isinstance(t, dict)]
        spans: list[TraceSpan] = []
        for trace in traces:
            members = spans_of_jaeger(trace, start.tzinfo or UTC)
            if not any(start <= m.started_at <= end for m in members):
                continue
            if only_errors and not any(m.error for m in members):
                continue
            spans.extend(members)
        spans.sort(key=lambda span: span.started_at)
        cap = self._settings.max_spans
        return TraceResult(
            service=canonical,
            window=window,
            spans=spans[:cap],
            traces=len(traces),
            max_depth=max_depth_for(self._settings.world),
            empty=not spans,
            truncated=len(traces) >= JAEGER_TRACE_CAP or len(spans) > cap,
        )


def parse_log_lines(text: str, tz: Any) -> list[LogLine]:
    """`get_logs`' text back into lines. Its timestamps are the MCP server's local time, which
    on the deployment is UTC; `tz` is the window's zone, used as given."""
    if text.strip() in {"No logs found matching the query.", "No log entries found."}:
        return []
    lines: list[LogLine] = []
    for raw in text.split("\n"):
        match = LOKI_LINE.match(raw)
        if match is None:
            if lines and raw:
                # A log line with an embedded newline continues the previous entry.
                lines[-1] = LogLine(at=lines[-1].at, line=f"{lines[-1].line}\n{raw}")
            continue
        at = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        lines.append(LogLine(at=at, line=match.group(3)))
    return lines


def _tag(tags: list[dict[str, Any]], key: str) -> Any:
    for tag in tags or []:
        if isinstance(tag, dict) and tag.get("key") == key:
            return tag.get("value")
    return None


def spans_of_jaeger(trace: dict[str, Any], tz: Any) -> list[TraceSpan]:
    """Jaeger's `/api/traces` shape → the span model `faultline.tools.spantree` reads.

    The parent is the first `CHILD_OF` reference; `FOLLOWS_FROM` is a link, not a parent, as OTLP's
    `parentSpanId` is. Status comes from `otel.status_code` where an OTLP-instrumented service
    set it (Astronomy Shop), and otherwise from OpenTracing's `error` tag (DeathStarBench), which
    is the status-tag question the harness read left open for those applications.
    """
    processes = trace.get("processes") or {}
    trace_id = str(trace.get("traceID") or "")
    spans: list[TraceSpan] = []
    for span in trace.get("spans") or []:
        if not isinstance(span, dict):
            continue
        process = processes.get(span.get("processID")) or {}
        service = str(process.get("serviceName") or "")
        tags = span.get("tags") or []
        otel_status = str(_tag(tags, "otel.status_code") or "").upper()
        error_tag = _tag(tags, "error")
        errored = otel_status == "ERROR" or error_tag is True or str(error_tag).lower() == "true"
        status = otel_status or ("ERROR" if errored else "UNSET")
        parent = next(
            (
                str(ref.get("spanID") or "")
                for ref in span.get("references") or []
                if isinstance(ref, dict) and ref.get("refType") == "CHILD_OF"
            ),
            "",
        )
        started_us = int(span.get("startTime") or 0)
        spans.append(
            TraceSpan(
                trace_id=str(span.get("traceID") or trace_id),
                service=canonical_service(service) if service else "",
                operation=str(span.get("operationName") or ""),
                started_at=datetime.fromtimestamp(started_us / 1e6, tz=tz),
                duration_ms=max(0, int(span.get("duration") or 0)) / 1000,
                error=errored,
                span_id=str(span.get("spanID") or ""),
                parent_span_id=parent,
                status=status,
                status_message=str(_tag(tags, "otel.status_description") or ""),
            )
        )
    return spans


SESSION_VAR = "FAULTLINE_SREGYM_SESSION"
NAMESPACE_VAR = "FAULTLINE_SREGYM_NAMESPACE"


def from_environment(settings: ToolSettings | None = None) -> McpToolSet:
    """The tool set `faultline-investigate` builds when `FAULTLINE_TOOLS_BACKEND=sregym`.

    Everything comes from the environment the adapter's driver sets for the investigation:
    SREGym's own `MCP_SERVER_URL`, the namespace `/get_app` named, and the application whose
    snapshot the catalog loads (`FAULTLINE_CONTEXT_APPLICATION`, Q125 and Q128).
    """
    import os

    from faultline.sregym.kube import KubernetesChangeLog
    from faultline.sregym.profiles import profile_by_application

    missing = [
        name
        for name in ("MCP_SERVER_URL", NAMESPACE_VAR, "FAULTLINE_CONTEXT_APPLICATION")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(f"the SREGym tool set needs {', '.join(missing)} in the environment")
    profile = profile_by_application(os.environ["FAULTLINE_CONTEXT_APPLICATION"])
    namespace = os.environ[NAMESPACE_VAR]
    client = McpClient(os.environ["MCP_SERVER_URL"], session_id=os.environ.get(SESSION_VAR, ""))
    return McpToolSet(
        client,
        profile,
        namespace,
        settings,
        changes=KubernetesChangeLog(client, profile, namespace),
    )
