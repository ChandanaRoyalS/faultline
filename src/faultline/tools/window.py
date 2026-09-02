"""Temporal scoping: the window policy the tool layer enforces (T3.2b).

The plan's words, which this module implements and nothing else in the codebase may override:
*every tool derives its default window from alert onset (onset - 30 min -> now), the change
analyst alone widens its lookback (onset - 24 h, because causes precede symptoms), and the
planner may widen a window per hypothesis - all enforced at the tool layer, never left to agent
discretion.* Deliverable: *tool-enforced window policy + per-query window logging.*

**What "enforced at the tool layer" means here.** Two things, in one object. The policy
*derives* the window a specialist is given - `for_specialist` - and it *checks* every window a
tool is asked to read - `refusal` - so a window that arrives from anywhere else (a planner
widening, a test, a future caller) is measured against the same ceiling. The agent code asks
the policy for a window; it does not compute one. No model ever sees a window it could change.

**The measured finding this supersedes and keeps.** Until T3.2b the default was
`onset - 10 min -> onset + 5 min`, and the ten minutes were justified by measurement: three of
the ten rehearsed investigations read logs from before onset, and `shipping-wrong-image` says the
pre-onset stream "is where it breaks open" - a JVM banner in a service whose logs had never
contained one. Thirty minutes is wider on the side that finding cares about and the forward end
now reaches the moment of investigation, so the finding is honoured, not discarded: ten minutes
was the least that finding required, and the plan's thirty is the policy. The lookbacks are
configuration
(`FAULTLINE_TOOLS_DEFAULT_LOOKBACK_SECONDS`, `..._CHANGE_LOOKBACK_SECONDS`), never prompt text,
so moving them does not move the frozen `prompts` key.

**Clipping, because "-> now" can be later than the ceiling allows.** An investigation that starts
hours after onset asks for a window the ceiling would refuse, and a policy whose own default is
refused by its own check is a contradiction. So the derived window is clipped at
`start + ceiling` and says so - `clipped=True` travels into the per-query log and onto the
trajectory step - rather than silently shortened. Live investigations start minutes after onset
and never clip; the replayed and rehearsed ones with historical anchors do, and should say so.

**The planner's per-hypothesis widening arrived at Q17** and is `planner_widened`. A dispatch
may carry `lookback_minutes`, which moves the window's *start* further back and nothing else:
not the forward end, not narrower than the default, and never past the ceiling this module would
refuse from any other caller. The rule stays "enforced at the tool layer, never left to agent
discretion" because what the planner supplies is a request that this policy either honours or
clips - the same treatment a historical anchor gets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from faultline.tools.settings import ToolSettings

log = logging.getLogger("faultline.tools.window")
"""Per-query window logging. One record per tool call, whatever the outcome."""

WindowRule = Literal["default", "change_lookback", "planner_widened"]
"""Which clause of the policy produced a window. `planner_widened` is reserved for Q17."""

CHANGE_TOOL = "change_history"
"""The tool whose ceiling is the change lookback, not the telemetry bound."""

BASELINE_TOOL = "metric_baseline"
"""The tool that reads **two** windows: the incident's and the one before it (T3.3b)."""


@dataclass(frozen=True, slots=True)
class ScopedWindow:
    """A window with its provenance: which rule produced it and whether it was clipped."""

    start: datetime
    end: datetime
    rule: WindowRule
    lookback_seconds: int
    clipped: bool

    def as_request(self) -> dict[str, Any]:
        """The shape written onto a trajectory step's `tool_call.request`."""
        return {
            "window": [self.start.isoformat(), self.end.isoformat()],
            "window_rule": self.rule,
            "lookback_seconds": self.lookback_seconds,
            "clipped": self.clipped,
        }


class WindowPolicy:
    """Derives windows from onset and refuses the ones no tool may read. One per `Tools`."""

    def __init__(self, settings: ToolSettings | None = None) -> None:
        self._settings = settings or ToolSettings()

    # --- derivation -------------------------------------------------------------

    def lookback_for(self, specialist: str) -> int:
        """Seconds before onset a specialist's window opens. Only `changes` differs."""
        if specialist == "changes":
            return self._settings.change_lookback_seconds
        return self._settings.default_lookback_seconds

    def rule_for(self, specialist: str) -> WindowRule:
        return "change_lookback" if specialist == "changes" else "default"

    def for_specialist(
        self,
        specialist: str,
        anchor: datetime,
        now: datetime,
        widen_minutes: int | None = None,
    ) -> ScopedWindow:
        """`onset - lookback -> now`, clipped at the tool's ceiling and labelled if so.

        `now` is the moment the investigation began, passed in rather than read from the clock
        so every dispatch of one investigation shares one end and a replay can reproduce it.

        `widen_minutes` is the planner's per-hypothesis request (Q17). **It can only widen**: a
        value at or below the specialist's own lookback is ignored rather than honoured, because
        a planner narrowing a window would be overriding a policy the plan says is not its to
        set. A request that would exceed the ceiling is clipped like any other.
        """
        lookback = self.lookback_for(specialist)
        rule = self.rule_for(specialist)
        if widen_minutes is not None and widen_minutes * 60 > lookback:
            lookback = widen_minutes * 60
            rule = "planner_widened"
        start = anchor - timedelta(seconds=lookback)
        end = max(now, anchor)
        ceiling = self.ceiling_for(CHANGE_TOOL if specialist == "changes" else "telemetry")
        limit = start + timedelta(seconds=ceiling)
        clipped = end > limit
        if clipped:
            end = limit
        return ScopedWindow(
            start=start,
            end=end,
            rule=rule,
            lookback_seconds=lookback,
            clipped=clipped,
        )

    # --- enforcement ------------------------------------------------------------

    def ceiling_for(self, tool: str) -> int:
        """The widest span a tool will read, in seconds.

        Telemetry tools share `max_window_seconds`. Two tools are derived from it rather than
        given a second invented number:

        **`change_history`** - the change lookback plus the telemetry bound, because the policy
        deliberately hands it a 24-hour window and a ceiling that refused the policy's own
        default would be a contradiction.

        **`metric_baseline`** - twice the telemetry bound, because the tool reads two windows of
        equal length and the span it is checked against covers both (T3.3b). Found by a test: a
        clipped window sitting exactly at the ceiling made the pair twice the ceiling, and every
        historical-anchor run was refused. The alternative - shortening the baseline to fit -
        was rejected, because two summaries with different `n` are not a comparison.
        """
        if tool == CHANGE_TOOL:
            return self._settings.change_lookback_seconds + self._settings.max_window_seconds
        if tool == BASELINE_TOOL:
            return 2 * self._settings.max_window_seconds
        return self._settings.max_window_seconds

    def refusal(self, tool: str, start: datetime, end: datetime) -> str | None:
        """Why a window may not be read, with a narrowing hint - or `None` when it may."""
        if end <= start:
            return "window end is not after its start"
        span = (end - start).total_seconds()
        ceiling = self.ceiling_for(tool)
        if span > ceiling:
            lookback = (
                self._settings.change_lookback_seconds
                if tool == CHANGE_TOOL
                else self._settings.default_lookback_seconds
            )
            return (
                f"window is {span / 3600:.1f}h and the ceiling for {tool} is "
                f"{ceiling / 3600:.0f}h, so the read is refused rather than answered in part; "
                f"narrow it - the policy's default is onset - {_span(lookback)} to now"
            )
        return None

    # --- logging ----------------------------------------------------------------

    def record(
        self, tool: str, subject: str, start: datetime, end: datetime, refusal: str | None
    ) -> None:
        """Per-query window logging: every read, its span, and whether it was refused."""
        log.info(
            "window tool=%s subject=%s start=%s end=%s span_s=%d refused=%s",
            tool,
            subject,
            start.isoformat(),
            end.isoformat(),
            int((end - start).total_seconds()),
            refusal is not None,
        )


def _span(seconds: int) -> str:
    return f"{seconds // 3600} h" if seconds % 3600 == 0 else f"{seconds // 60} min"
