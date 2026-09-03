"""The non-headline metric panel, computed from what a run already recorded (T4.3).

The plan's T4.3: *"The non-headline metrics: citation validity (programmatic), tool-call validity
rate (steps, redundant calls), per-agent context-budget-overflow rate, latency, and dollar cost
per investigation."* Method: *"Computed from persisted trajectories and gateway logs; no new
instrumentation needed because P2 recorded everything."* Deliverable: *"Full metric panel computed
per run."*

## The method column's claim was checked and it holds

Every number here comes from rows that already existed before this module. **No column was added
and no call site was touched**, which is worth stating because the temptation in a task like this
is to instrument first and compute second, and instrumenting to produce a metric changes the
system the metric describes.

| metric | where it was already recorded |
|---|---|
| latency | `trajectories.started_at`/`ended_at`, and `trajectory_steps.latency_ms` per step |
| tool-call validity | the envelope's opening tag, stored verbatim in `trajectory_tool_calls` |
| redundant calls | `trajectory_tool_calls.request`, which carries service and window |
| context-budget overflow | the `disclosure` payload on the runtime step (T3.2c) |
| citation validity | the narrative step's `violations` payload (T3.8) |

**Validity is read out of the envelope rather than a status column, and that is deliberate.** The
envelope is the authoritative record of what the specialist actually saw - stored byte-for-byte
precisely so a replay reads the same prompt - and its opening tag already carries `empty`,
`truncated` and, when a query failed, `error`. Parsing it is not prose-scraping: `escape_attribute`
replaces every `"` with `'` before rendering, so within a rendered tag **every quote is a
delimiter**, and the parse is unambiguous by construction. A round-trip test pins that property so
the parse cannot drift from the renderer.

## What each number means, and what it must not be read as

**Validity rate is about the query, not the answer.** ADR-0019's distinction holds here and is the
whole reason this metric is worth having: *an empty result is evidence and an errored one is not*.
A window that was observed and held nothing is a **valid** call - the specialist learned something
- and only a call that failed to parse or execute is invalid. A pipeline optimising this number by
never asking hard questions would be worse and would score better, which is why it is reported
beside the accuracy figures and never folded into them.

**Redundancy is counted on the triple the tool was actually asked**, `(tool, service, window)`, not
on the tool name. Two `logql_query` calls against different services are two questions; two against
the same service and the same window are one question asked twice, and the second bought nothing.
It is a cost and context signal rather than a correctness one - a redundant call spends budget and
fills the synthesizer's board with a duplicate.

**Overflow rate is per briefing, not per role**, because a role briefed twice (the planner, across
two rounds) has two chances to overflow and both are facts about the run. `over_budget` can only
be true through `essential` sections, which the assembler never drops, so a non-zero rate says the
4,000-token cap is not binding on the roles that matter - which is the question T7.3's ablation
needs answered and this sweep could not answer.

**Latency is wall clock and includes every wait.** Not model time, not tool time: the number Gate 4
names is *time to report*, and a responder waiting on an investigation is waiting on all of it. The
component sums are reported beside it so a slow run can be attributed rather than merely observed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
"""One rendered envelope attribute. Unambiguous because `escape_attribute` removes every `"`
from values before rendering, so a quote inside a tag can only be a delimiter."""


def envelope_attributes(envelope: str) -> dict[str, str]:
    """The opening tag's attributes. The inverse of `envelope.render`'s first line.

    Reads the first line only. The body is neutralised untrusted content and may contain anything
    that looks like an attribute; the tag is the part this system wrote.
    """
    opening = envelope.split("\n", 1)[0]
    return {key: value for key, value in ATTRIBUTE.findall(opening)}


@dataclass(frozen=True, slots=True)
class ToolCalls:
    """Tool-call validity and redundancy for one investigation."""

    total: int = 0
    errored: int = 0
    empty: int = 0
    truncated: int = 0
    redundant: int = 0

    @property
    def valid(self) -> int:
        return self.total - self.errored

    @property
    def validity_rate(self) -> float | None:
        """`None` when no tool call was made. **Not 1.0** - a run that asked nothing has not
        achieved perfect validity, and averaging a fabricated 1.0 into a catalog figure would
        reward a pipeline for asking less."""
        return None if self.total == 0 else self.valid / self.total

    @property
    def redundancy_rate(self) -> float | None:
        return None if self.total == 0 else self.redundant / self.total

    def as_row(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "valid": self.valid,
            "errored": self.errored,
            "empty": self.empty,
            "truncated": self.truncated,
            "redundant": self.redundant,
            "validity_rate": _round(self.validity_rate),
            "redundancy_rate": _round(self.redundancy_rate),
        }


def tool_calls(rows: list[tuple[str, dict[str, Any], str]]) -> ToolCalls:
    """`(tool, request, envelope)` per call, in trajectory order.

    Redundancy is the count of calls whose `(tool, service, window)` triple has been seen earlier
    in the same trajectory - so the first of a repeated pair is not counted and the second is,
    which makes the number "calls that bought nothing" rather than "calls involved in a repeat".
    """
    seen: set[tuple[str, str, str]] = set()
    total = errored = empty = truncated = redundant = 0
    for tool, request, envelope in rows:
        total += 1
        attributes = envelope_attributes(envelope)
        if "error" in attributes:
            errored += 1
        if attributes.get("empty") == "true":
            empty += 1
        if attributes.get("truncated") == "true":
            truncated += 1
        window = request.get("window")
        key = (tool, str(request.get("service", "")), str(window))
        if key in seen:
            redundant += 1
        seen.add(key)
    return ToolCalls(
        total=total, errored=errored, empty=empty, truncated=truncated, redundant=redundant
    )


@dataclass(frozen=True, slots=True)
class Briefings:
    """Per-agent context budget, as the assembler recorded it (T3.2c)."""

    total: int = 0
    over_budget: int = 0
    dropped_sections: int = 0
    largest_estimated_tokens: int = 0
    budget: int = 0

    @property
    def overflow_rate(self) -> float | None:
        return None if self.total == 0 else self.over_budget / self.total

    def as_row(self) -> dict[str, Any]:
        return {
            "briefings": self.total,
            "over_budget": self.over_budget,
            "overflow_rate": _round(self.overflow_rate),
            "dropped_sections": self.dropped_sections,
            "largest_estimated_tokens": self.largest_estimated_tokens,
            "budget": self.budget,
        }


def briefings(disclosure: dict[str, Any] | None) -> Briefings:
    """Read from the runtime step's `disclosure` payload. Absent for runs before T3.2c."""
    if not disclosure:
        return Briefings()
    rows = list(disclosure.get("briefings", []))
    return Briefings(
        total=len(rows),
        over_budget=sum(1 for row in rows if row.get("over_budget")),
        dropped_sections=int(disclosure.get("dropped_sections", 0)),
        largest_estimated_tokens=max((int(r.get("estimated_tokens", 0)) for r in rows), default=0),
        budget=max((int(r.get("budget", 0)) for r in rows), default=0),
    )


@dataclass(frozen=True, slots=True)
class Latency:
    """Wall clock for one investigation, and where it went."""

    investigation_ms: int = 0
    tool_ms: int = 0
    model_ms: int = 0
    steps: int = 0

    @property
    def investigation_seconds(self) -> float:
        return self.investigation_ms / 1000

    @property
    def within_gate4(self) -> bool:
        """Gate 4 names **≤ 3 minutes** for the dev-set *median*, not for a single run. This is
        the per-run comparison against that threshold and is not the gate's condition: one run
        inside it proves nothing, and the median is computed over a catalog."""
        return self.investigation_ms <= GATE4_TIME_TO_REPORT_MS

    def as_row(self) -> dict[str, Any]:
        return {
            "investigation_ms": self.investigation_ms,
            "investigation_seconds": round(self.investigation_seconds, 1),
            "tool_ms": self.tool_ms,
            "model_ms": self.model_ms,
            "steps": self.steps,
            "within_gate4_threshold": self.within_gate4,
        }


GATE4_TIME_TO_REPORT_MS = 180_000
"""Gate 4's *"dev-set median time-to-report ≤ 3 minutes"*, in milliseconds. Named here so the
threshold has one definition, and applied to the **median of a catalog** rather than to a run."""


@dataclass(frozen=True, slots=True)
class MetricPanel:
    """T4.3's deliverable: the full panel for one run."""

    latency: Latency = field(default_factory=Latency)
    tools: ToolCalls = field(default_factory=ToolCalls)
    context: Briefings = field(default_factory=Briefings)
    citation_violations: int = 0
    narrative_regenerated: bool = False
    narrative_escalated: bool = False

    def as_row(self) -> dict[str, Any]:
        return {
            "latency": self.latency.as_row(),
            "tool_calls": self.tools.as_row(),
            "context": self.context.as_row(),
            "citations": {
                "violations": self.citation_violations,
                "regenerated": self.narrative_regenerated,
                "escalated": self.narrative_escalated,
            },
        }

    def render(self) -> list[str]:
        """The panel as `report.txt` prints it. Rates that are `None` print as `n/a`, never as a
        number - a run that made no tool call has no validity rate, and printing 1.00 there would
        be the report inventing a measurement."""
        t, c, x = self.tools, self.context, self.latency
        return [
            "METRIC PANEL (T4.3) - reported beside accuracy, never averaged into it",
            f"  latency        {x.investigation_seconds:.1f}s "
            f"({'within' if x.within_gate4 else 'OVER'} G4's 3-minute per-run comparison) "
            f"tools {x.tool_ms / 1000:.1f}s  models {x.model_ms / 1000:.1f}s  steps {x.steps}",
            f"  tool calls     {t.total} total, {t.valid} valid, {t.errored} errored, "
            f"{t.redundant} redundant  validity {_pct(t.validity_rate)}  "
            f"redundancy {_pct(t.redundancy_rate)}",
            "    a query that ran and found nothing is valid - an empty result is evidence "
            f"(ADR-0019); {t.empty} empty, {t.truncated} truncated",
            f"  context budget {c.total} briefing(s), {c.over_budget} over budget "
            f"({_pct(c.overflow_rate)}), {c.dropped_sections} section(s) dropped, "
            f"largest {c.largest_estimated_tokens} est. tokens against a {c.budget} cap",
            f"  citations      {self.citation_violations} violation(s), "
            f"regenerated {str(self.narrative_regenerated).lower()}, "
            f"escalated {str(self.narrative_escalated).lower()}",
        ]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
