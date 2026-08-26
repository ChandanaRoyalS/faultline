"""What bounds an investigation, and what happens when it runs out (T3.3, ADR-0020 §5).

Four bounds, because they fail differently and one of them cannot substitute for another. The
eval harness needs every investigation to terminate or a sweep hangs on one scenario.

**Exhaustion is a value, never an exception.** ADR-0020 §5: the investigation finishes early
with a verdict flagged `budget_exhausted` and proceeds normally, because a partial diagnosis is
scoreable and a `FAILED` incident is not. An exception here would unwind past the point where
the partial answer exists, which is the answer T4.2 would have wanted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Budget:
    """The four bounds. **Placeholders, named as such** - reasons, no measurements (ADR-0020)."""

    max_tool_calls_per_specialist: int = 12
    max_tokens: int = 150_000
    wall_clock_seconds: int = 600
    max_dispatch_rounds: int = 2
    """The plan and at most one follow-up. **Structural, not prose**: unbounded re-dispatch is
    the non-termination risk this budget exists to remove, arriving through the planner instead
    of through a specialist."""


@dataclass(slots=True)
class BudgetState:
    """Live from the first dispatch. Every bound is checked before spending, not after."""

    budget: Budget
    started_at: float = field(default_factory=time.monotonic)
    tokens: int = 0
    rounds: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    exhausted_reason: str | None = None

    @property
    def exhausted(self) -> bool:
        return self.exhausted_reason is not None

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def spend_tokens(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens += tokens_in + tokens_out

    def start_round(self) -> bool:
        """Whether another dispatch round may begin. Records why not, if not."""
        if self.rounds >= self.budget.max_dispatch_rounds:
            self._exhaust(
                f"dispatch rounds: {self.rounds} of {self.budget.max_dispatch_rounds} used"
            )
            return False
        if not self.check():
            return False
        self.rounds += 1
        return True

    def may_call_tool(self, specialist: str) -> bool:
        used = self.tool_calls.get(specialist, 0)
        if used >= self.budget.max_tool_calls_per_specialist:
            self._exhaust(
                f"{specialist} tool calls: {used} of "
                f"{self.budget.max_tool_calls_per_specialist} used"
            )
            return False
        return self.check()

    def record_tool_call(self, specialist: str) -> None:
        self.tool_calls[specialist] = self.tool_calls.get(specialist, 0) + 1

    def check(self) -> bool:
        """Tokens and wall clock, which are per-investigation rather than per-specialist.

        Wall clock is not redundant with tokens: a tool call that hangs consumes none and makes
        no progress, and ADR-0019's tools do not retry internally past one attempt, so a stuck
        query is a stuck investigation with budget to spare.
        """
        if self.tokens >= self.budget.max_tokens:
            self._exhaust(f"tokens: {self.tokens} of {self.budget.max_tokens} used")
            return False
        if self.elapsed_seconds() >= self.budget.wall_clock_seconds:
            self._exhaust(
                f"wall clock: {self.elapsed_seconds():.0f}s of "
                f"{self.budget.wall_clock_seconds}s used"
            )
            return False
        return True

    def _exhaust(self, reason: str) -> None:
        if self.exhausted_reason is None:
            self.exhausted_reason = reason
