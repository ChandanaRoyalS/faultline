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
    """Log lines for one service, **kept from both ends of the window** (T3.4b).

    `lines` is chronological throughout. When `oldest_kept` is non-zero the first that many
    entries are the *start* of the window and the rest are its *end*, with everything between
    them dropped - so the two groups must be labelled, or the agent reads a contiguous stream
    that never existed. `docs/adr/0021` argues why both ends; this class is where the reader
    is told which is which.
    """

    tool: Literal["logql_query"] = "logql_query"
    source: Literal["loki"] = "loki"
    selector: str = ""
    lines: list[LogLine] = Field(default_factory=list)

    oldest_kept: int = 0
    """How many of `lines` come from the start of the window. Zero when nothing was elided."""

    newest_kept: int = 0
    """How many come from the end of it. Equals `len(lines)` when nothing was elided."""

    def attributes(self) -> dict[str, str]:
        attributes = super().attributes()
        if self.oldest_kept:
            attributes["oldest_kept"] = str(self.oldest_kept)
            attributes["newest_kept"] = str(self.newest_kept)
        return attributes

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        if not self.lines:
            return f"no log lines matched {self.selector} over this window"
        head = [f"{e.at.isoformat()}  {e.line}" for e in self.lines[: self.oldest_kept]]
        rest = [f"{e.at.isoformat()}  {e.line}" for e in self.lines[self.oldest_kept :]]
        if not self.oldest_kept:
            return "\n".join([f"selector: {self.selector}", *rest])
        marker = (
            f"  ... lines between here and the next timestamp were not returned: "
            f"this result keeps the OLDEST {self.oldest_kept} and the NEWEST "
            f"{self.newest_kept} lines of the window, and nothing in between ..."
        )
        return "\n".join([f"selector: {self.selector}", *head, marker, *rest])


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


class BaselineResult(ToolResult):
    """One metric, in the incident window and in a comparable quiet one (T3.3b).

    **Two windows, one result**, because the finding is the comparison: *"p95 is 15s"* is a
    number and *"p95 is 15s against a baseline of 38ms measured over the preceding half hour"*
    is evidence. A responder reading only the first has to know this world's healthy values by
    heart, and the rehearsed narratives show that is exactly where wrong turns start - T7.13's
    starved histogram read as degradation, T3.4 reading the same 15s as a fault.
    """

    tool: Literal["metric_baseline"] = "metric_baseline"
    source: Literal["prometheus"] = "prometheus"
    service: str = ""
    template: str = ""
    query: str = ""
    baseline_window: Window | None = None
    incident: dict[str, float] = Field(default_factory=dict)
    baseline: dict[str, float] = Field(default_factory=dict)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    """Change points, oldest first, each with the timestamp the departure *started*."""

    incident_undefined: int = 0
    baseline_undefined: int = 0
    """Samples the series had no value for - `NaN`, which is what a ratio over no traffic is.
    Dropped from the arithmetic and counted here, because a service with no traffic is a
    finding and a service with a zero error ratio is its opposite."""

    def attributes(self) -> dict[str, str]:
        attributes = super().attributes()
        attributes["template"] = self.template
        if self.baseline_window is not None:
            attributes["baseline"] = self.baseline_window.render()
        return attributes

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        lines = [f"service: {self.service}", f"metric: {self.template}", f"query: {self.query}"]
        if not self.baseline:
            # **Not "unchanged".** A comparison with no baseline is a comparison that was not
            # made, and ADR-0019's whole distinction is that an unobserved window is not an
            # observed-empty one.
            lines.append("NO BASELINE: the comparison window returned nothing, so nothing here")
            lines.append("says whether the incident window is unusual.")
        else:
            lines.append(f"  incident window: {_stats(self.incident)}")
            lines.append(f"  baseline window: {_stats(self.baseline)}")
            lines.append(f"  mean moved {_delta(self.baseline, self.incident)}")
        if self.incident_undefined or self.baseline_undefined:
            lines.append(
                f"  {self.incident_undefined} sample(s) in the incident window and "
                f"{self.baseline_undefined} in the baseline had NO DEFINED VALUE - for a ratio "
                "that means no traffic in the interval, which is a finding rather than a zero"
            )
        if self.changes:
            lines.append(f"{len(self.changes)} change point(s), earliest first:")
            for change in self.changes:
                lines.append(
                    f"  {change['at']}  value {change['value']:.4g} "
                    f"crossed {change['threshold']:.4g}"
                )
        elif self.baseline:
            lines.append("no sustained departure from the baseline in this window")
        return "\n".join(lines)


def _stats(stats: dict[str, float]) -> str:
    if not stats or not stats.get("samples"):
        return "no samples"
    return (
        f"n={int(stats['samples'])} mean={stats['mean']:.4g} min={stats['minimum']:.4g} "
        f"max={stats['maximum']:.4g} sd={stats['stdev']:.4g}"
    )


def _delta(baseline: dict[str, float], incident: dict[str, float]) -> str:
    before, after = baseline.get("mean", 0.0), incident.get("mean", 0.0)
    if not incident.get("samples"):
        return "nowhere - the incident window returned no samples"
    if before == 0:
        return f"from 0 to {after:.4g} (no ratio: the baseline was exactly zero)"
    return f"from {before:.4g} to {after:.4g}, x{after / before:.3g}"


def describe_lead(lead: int) -> str:
    """`lead_seconds` as a responder reads it: `2m before onset`, `40s after onset` (T3.4)."""
    magnitude = abs(lead)
    if magnitude < 60:
        span = f"{magnitude}s"
    elif magnitude < 3600:
        span = f"{magnitude // 60}m"
    else:
        span = f"{magnitude / 3600:.1f}h"
    return f"{span} {'before' if lead >= 0 else 'after'} onset"


class ChangeResult(ToolResult):
    tool: Literal["change_history"] = "change_history"
    source: Literal["change-log"] = "change-log"
    service: str = ""
    records: list[dict[str, Any]] = Field(default_factory=list)
    """In rank order when `standing` is set (T3.4); oldest first otherwise."""

    standing: dict[str, Any] | None = None
    """The queried service's place in triage's blast radius - `direction`, `hops`, `reason` -
    when the call was ranked (T3.4). `None` means the caller supplied no ranking context and
    the records are in time order, unranked."""

    def attributes(self) -> dict[str, str]:
        attributes = super().attributes()
        if self.standing is not None:
            attributes["radius"] = str(self.standing["direction"])
            if self.standing.get("hops") is not None:
                attributes["hops"] = str(self.standing["hops"])
        return attributes

    def body(self) -> str:
        if self.error is not None:
            return f"query failed: {self.error}"
        if not self.records:
            # The single most common load-bearing result in the requirements list: five of
            # nine investigations turn on this sentence being true and being trustworthy.
            return f"no changes recorded for {self.service} over this window"
        ranked = self.standing is not None
        header = (
            f"{len(self.records)} changes, ranked by suspicion"
            if ranked
            else (f"{len(self.records)} changes")
        )
        lines = [f"service: {self.service}", header]
        for record in self.records:
            prefix = (
                f"  #{record['rank']}  {describe_lead(record['lead_seconds'])}  "
                if ranked
                else "  "
            )
            lines.append(
                f"{prefix}{record['at']}  {record['actor']}  {record['resource']} "
                f"{record['action']}: {record['summary']}"
            )
            before, after = record.get("before"), record.get("after")
            if before is not None or after is not None:
                lines.append(f"      {before}  ->  {after}")
        return "\n".join(lines)
