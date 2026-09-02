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
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Budget:
    """The bounds an investigation is held to. **Placeholders, named as such** - reasons rather
    than measurements (ADR-0020), except `per_specialist_tool_calls`, which T4.7 measured.

    **Six now, and the two additions are Batch B's** (T3.2c and Q16). Both were queued behind
    the same fact: `freeze.budget_bounds()` is a frozen key, so a new bound costs a comparability
    generation, and two bounds cost the same one generation as one.
    """

    max_tool_calls_per_specialist: int = 12
    """The default bound, applied to any specialist without an override below."""

    per_specialist_tool_calls: Mapping[str, int] = field(default_factory=dict)
    """Per-specialist overrides. **Added at T4.7, and the reason is a measurement.**

    One bound for all four specialists was right when a dispatch could name several services at
    once. T3.4c made a dispatch name exactly one service - correctly, because a comma-separated
    list produced a selector that could not match - and that multiplied the planner's
    change-history needs by the size of the blast radius without anyone moving the bound.

    Read out of the stored trajectories: every budget-exhausted run in the record exhausted the
    *same* bound, `changes`, and in three of the four the target service's change record was
    dispatch five or six of a plan the bound cut off at four. The planner was not being
    profligate; it was being charged per service for a question it used to ask once.

    A mapping rather than four fields because the specialists are `SpecialistName` values and a
    bound that has to be measured is a bound that will move again.
    """

    max_tokens: int = 150_000
    wall_clock_seconds: int = 600
    max_dispatch_rounds: int = 2
    """The plan and at most one follow-up. **Structural, not prose**: unbounded re-dispatch is
    the non-termination risk this budget exists to remove, arriving through the planner instead
    of through a specialist."""

    briefing_tokens: int = 4_000
    """How large a briefing any one role may be handed, estimated (T3.2c).

    **A placeholder with a derivation rather than a measurement.** The largest brief this
    pipeline builds is the synthesizer's: an evidence board of one entry per claim, with a
    400-character sample per dispatch. Six dispatches averaging three claims each, plus triage,
    retrieval and flags, estimates near 2,500 tokens; 4,000 leaves room for a wider fan-out
    before anything is dropped, and drops the *lowest-priority* section first when it is not
    enough. The number should move when a sweep measures what dropping actually costs, and
    moving it moves the stamp's budget block, which is what makes the move visible.
    """

    per_role_briefing_tokens: Mapping[str, int] = field(default_factory=dict)
    """Per-role overrides. Empty by default, for the reason `role_models` is empty by default:
    a table of six numbers would make six decisions where the evidence supports one."""

    usd_per_mtok: tuple[float, float] = (5.0, 25.0)
    """The price table the dollar cap is computed at, in and out, per million tokens.

    **Recorded in the freeze beside the cap, because the cap is meaningless without it**: a $2
    bound at $5/$25 stops an investigation in a different place than a $2 bound at $15/$75, and
    a manifest that recorded only the bound would call those two runs the same experiment. The
    same reasoning as Q14's, arriving one field earlier.
    """

    max_usd: float = 2.0
    """The per-incident dollar cap (**Q16**), enforced at the choke point that already halts on
    tokens.

    T2.5's description names *"per-incident token/dollar budgets"* and the proposal's runaway-cost
    row promises *"hard per-incident cap halts agents"*. What halted was a token cap, and a token
    cap is not a dollar cap: **the price of a model can change without the token bound moving**,
    and the bound is then enforcing a different amount of money than it was set to enforce.
    Gate 4's threshold is `cost ≤ $2 per incident`, which is where this default comes from - the
    cap is the gate's own number, so a run that would fail the gate stops instead of finishing
    and failing it.

    Cost computation is **not** new instrumentation: T4.3 owns the scored figure and computes it
    from persisted trajectories. What is new is a bound the *runtime* can stop on, which needs
    the runtime to hold prices - `AgentSettings.usd_per_mtok_in` / `_out`, defaulting to the same
    numbers `evalharness.run` applies after the fact. **The two must be kept equal by hand**, and
    a test asserts they are: a runtime that halts at a different price than the harness scores
    would produce a run that stopped for a reason no figure could explain.
    """

    def tool_calls_for(self, specialist: str) -> int:
        """The bound this specialist is held to: its override, or the default."""
        return self.per_specialist_tool_calls.get(specialist, self.max_tool_calls_per_specialist)

    def briefing_tokens_for(self, role: str) -> int:
        return self.per_role_briefing_tokens.get(role, self.briefing_tokens)


@dataclass(slots=True)
class BudgetState:
    """Live from the first dispatch. Every bound is checked before spending, not after."""

    budget: Budget
    started_at: float = field(default_factory=time.monotonic)
    tokens: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    """Split as well as summed, because money is priced per direction and a cap denominated in
    money cannot be computed from the total (Q16)."""

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
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def usd_spent(self) -> float:
        """What this investigation has cost, at the runtime's own price table (Q16)."""
        usd_in, usd_out = self.budget.usd_per_mtok
        return self.tokens_in / 1e6 * usd_in + self.tokens_out / 1e6 * usd_out

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
        allowed = self.budget.tool_calls_for(specialist)
        if used >= allowed:
            self._exhaust(f"{specialist} tool calls: {used} of {allowed} used")
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
        spent = self.usd_spent()
        if spent >= self.budget.max_usd:
            # **The same choke point, a different denomination** (Q16). Checked after tokens
            # because a run that breaches both should report the bound it was set by, and the
            # token bound is the one every recorded figure was measured under.
            self._exhaust(f"cost: ${spent:.2f} of ${self.budget.max_usd:.2f} used")
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
