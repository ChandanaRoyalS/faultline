"""What a tool returns, and the three states it can be in (T2.6, ADR-0019).

**Empty and error are different results, and that is a contract term rather than an
implementation detail.** The requirements list for this layer is the nine rehearsed
narratives' *What was checked* sections, and in eight of the nine the load-bearing finding is
a negative: five turn on nothing having changed on a service, three on logs that say nothing,
and `shipping-wrong-image` on a memory limit having *not* changed while the image did. A tool
that returns the same thing for "I looked and there was nothing" and "I could not look"
destroys the evidence those investigations rest on.

So every result carries `empty` and `error` separately, and `window` alongside them - a
negative that cannot name the window it is negative over is not evidence either.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Trust(StrEnum):
    """Always `UNTRUSTED` for anything a tool returns.

    Not "usually", not "for logs". Metric labels are service-supplied, change records
    describe attacker-influenceable configuration, and trace operation names are strings a
    service chose. A rule with exceptions is a rule an agent has to reason about, and
    THREAT-MODEL thesis 1 is that this text is a prompt-injection vector.
    """

    UNTRUSTED = "untrusted"


class Window(BaseModel):
    """The interval a result covers. Present even when the result is empty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime

    def render(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"


def new_result_id() -> str:
    """A per-call id, random rather than sequential.

    It is also the envelope's closing delimiter (`envelope.render`), so content cannot close
    a frame it cannot name. Sequential ids would be guessable from inside a log line.
    """
    return f"tr_{secrets.token_hex(6)}"


class ToolResult(BaseModel):
    """The base every tool result shares. **The T3.x contract.**"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_result_id)
    """Stable handle. `ARCHITECTURE.md` requires the synthesizer produce a cited,
    citation-validated RCA, so every claim needs something a validator can resolve."""

    tool: str
    source: str
    trust: Trust = Trust.UNTRUSTED
    window: Window | None = None
    empty: bool = False
    truncated: bool = False
    """A capped result that looks complete is the logs failure mode - the committed captures
    hit a 500-line cap and one narrative's argument depends on knowing that."""

    error: str | None = None
    """Failure is a value, not an exception. An agent has to be able to reason about a failed
    query, and an exception unwinds past the point where that reasoning would happen."""

    def attributes(self) -> dict[str, str]:
        """What the envelope renders in the opening tag."""
        attributes = {
            "id": self.id,
            "tool": self.tool,
            "trust": self.trust.value,
            "source": self.source,
            "empty": str(self.empty).lower(),
            "truncated": str(self.truncated).lower(),
        }
        if self.window is not None:
            attributes["window"] = self.window.render()
        if self.error is not None:
            attributes["error"] = self.error
        return attributes

    def body(self) -> str:
        """The human-readable payload the agent reads inside the envelope."""
        return ""


class MetricSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    labels: dict[str, str]
    points: list[tuple[float, float]]


class MetricResult(ToolResult):
    tool: Literal["promql_query"] = "promql_query"
    source: Literal["prometheus"] = "prometheus"
    query: str = ""
    series: list[MetricSeries] = Field(default_factory=list)

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        if not self.series:
            return f"no series matched {self.query!r} over this window"
        lines = [f"query: {self.query}", f"{len(self.series)} series"]
        for entry in self.series:
            labels = ", ".join(f"{k}={v}" for k, v in sorted(entry.labels.items()))
            values = [value for _, value in entry.points]
            summary = (
                f"min={min(values):.4g} max={max(values):.4g} n={len(values)}"
                if values
                else "no points"
            )
            lines.append(f"  {{{labels}}} {summary}")
        return "\n".join(lines)


class LogLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    line: str


class LogResult(ToolResult):
    tool: Literal["logql_query"] = "logql_query"
    source: Literal["loki"] = "loki"
    selector: str = ""
    lines: list[LogLine] = Field(default_factory=list)

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        if not self.lines:
            return f"no log lines matched {self.selector} over this window"
        rendered = [f"{entry.at.isoformat()}  {entry.line}" for entry in self.lines]
        return "\n".join([f"selector: {self.selector}", *rendered])


class TraceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    service: str
    operation: str
    started_at: datetime
    duration_ms: float
    error: bool = False


class TraceResult(ToolResult):
    tool: Literal["trace_query"] = "trace_query"
    source: Literal["jaeger"] = "jaeger"
    service: str = ""
    spans: list[TraceSpan] = Field(default_factory=list)

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        if not self.spans:
            return f"no traces for {self.service} over this window"
        lines = [f"service: {self.service}", f"{len(self.spans)} spans"]
        for span in self.spans:
            flag = " ERROR" if span.error else ""
            lines.append(
                f"  {span.trace_id[:16]} {span.service}/{span.operation} "
                f"{span.duration_ms:.1f}ms{flag}"
            )
        return "\n".join(lines)


class ChangeResult(ToolResult):
    tool: Literal["change_history"] = "change_history"
    source: Literal["change-log"] = "change-log"
    service: str = ""
    records: list[dict[str, Any]] = Field(default_factory=list)

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        if not self.records:
            # The single most common load-bearing result in the requirements list: five of
            # nine investigations turn on this sentence being true and being trustworthy.
            return f"no changes recorded for {self.service} over this window"
        lines = [f"service: {self.service}", f"{len(self.records)} changes"]
        for record in self.records:
            lines.append(
                f"  {record['at']}  {record['actor']}  {record['resource']} "
                f"{record['action']}: {record['summary']}"
            )
            before, after = record.get("before"), record.get("after")
            if before is not None or after is not None:
                lines.append(f"      {before}  ->  {after}")
        return "\n".join(lines)
