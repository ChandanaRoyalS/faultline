"""Progressive disclosure: the briefing assembler, under budget, measured (T3.2c).

The plan's T3.2c: *"Agents start from a minimal briefing — the alert, scoped topology, top-3
similar past incidents — and pull further context via tools on demand, rather than receiving
everything push-style; briefing size is token-budgeted per role and measured."* Method: *"A
briefing assembler builds the per-role pack under budget; everything else is tool-reachable;
briefing size and pull-rate are logged per run so T7.3's ablation has data to compare against."*
Deliverable: *"Budgeted briefing assembler + pull-rate metrics."*

## What was already true, and what was not

**Half of this was built and never called that.** The specialists have held one modality each
since T3.3 and the synthesizer has never held a tool - so context does arrive on demand, through
a planner that dispatches rather than through a role that asks. Retrieval has been `k=3` since
T3.4.

**This docstring used to end that sentence with "which is the plan's *top-3 similar past
incidents* exactly", and the Phase 3 audit (2026-09-03) found that claim too strong.** The count
is exact; the consumer is not. T3.2 gives the *planner* the top similar past incidents and T3.2c
puts them in the *minimal briefing*, and in this code they reach the **synthesizer** - the
planner's brief is `incident` plus `round-one-findings`, and no single role receives the alert,
the scoped topology and the top-3 together. Whether the synthesizer is the better consumer is a
real question and may well be answered yes; **what was wrong was asserting the clause was met
while the wiring differed.** The decision is queued as Q23.

**What did not exist was any bound, and any number.** Each role assembled its own brief inline,
appending until it ran out of things to append: the evidence board grows with the dispatch count,
the allowlist and the runbooks grow with the catalog, and nothing anywhere said how large a brief
was or refused to make it larger. A pipeline whose context discipline is *"we did not add much"*
has no defence against the day someone does, and T7.3's ablation - does progressive disclosure
beat prompt stuffing? - has nothing to compare against without the numbers.

## Priority, not truncation

A brief is a list of `Section`s with priorities, and the assembler keeps whole sections in
priority order until the budget is spent. **A dropped section is named in the brief itself**, so
a model is told what it is not being shown rather than left to infer it from a gap - the same
principle as the tool layer's `truncated`, where a capped result that looks complete is the
failure mode.

Sections marked `essential` are never dropped. If the essential sections alone exceed the
budget, the assembler says so in `over_budget` and delivers them anyway: refusing to brief a
role at all would fail the investigation to protect a number, and the number exists to describe
the investigation.

## Tokens are estimated, and the estimate is named

`estimated_tokens` divides characters by `CHARS_PER_TOKEN`. It is not a tokenizer count and
must never be reported as one: the boundary this bound enforces is *approximately* four
characters, and the alternative - importing a tokenizer into the product to enforce a budget on
itself - is a dependency ADR-0004 would not accept for a figure nobody scores. What the harness
records is the estimate under its own name, beside the real token counts the API returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CHARS_PER_TOKEN = 4
"""The estimator. Roughly right for English prose and for the log lines this system quotes, and
wrong in the same direction for every role, which is what a comparison needs."""


def estimate_tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class Section:
    """One block of a briefing, with what it costs and whether it may be dropped."""

    name: str
    lines: list[str]
    priority: int = 50
    """Lower is kept first. The convention: 0-19 what the role is being asked, 20-49 the
    evidence it must reason over, 50+ context that improves an answer without being required
    for one."""

    essential: bool = False
    """Never dropped. A role that lost this section would be answering a different question."""

    def render(self) -> str:
        return "\n".join(self.lines)

    def cost(self) -> int:
        return estimate_tokens(self.render()) + 1


@dataclass(frozen=True, slots=True)
class Briefing:
    """What a role was actually given, and what it was not."""

    role: str
    text: str
    estimated_tokens: int
    budget: int
    kept: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    content_tokens: int = 0
    """The kept sections, without the withheld notice. **This is what the budget bounds.**"""

    over_budget: bool = False
    """The kept sections alone exceeded the budget, which can only happen through `essential`.
    Recorded rather than enforced: refusing to brief a role would fail an investigation to
    protect a number, and the number exists to describe the investigation.

    **Deliberately not set by the withheld notice.** When a section is dropped, the line naming
    it is appended *after* packing and is not charged to the budget - so `estimated_tokens` can
    exceed `budget` by that line while `over_budget` stays false. Charging it would mean a brief
    that drops one section might have to drop a second to afford saying so, which is the one
    trade this design will not make."""

    def as_row(self) -> dict[str, object]:
        """The shape written onto a trajectory step, so T7.3 reads it without re-deriving it."""
        return {
            "role": self.role,
            "estimated_tokens": self.estimated_tokens,
            "content_tokens": self.content_tokens,
            "budget": self.budget,
            "kept": list(self.kept),
            "dropped": list(self.dropped),
            "over_budget": self.over_budget,
        }


def assemble(role: str, sections: list[Section], budget: int) -> Briefing:
    """Pack the highest-priority sections that fit, and say which did not.

    Order is by `priority` then by the order given, so two sections of equal priority keep the
    order the role wrote them in - a brief whose sections reshuffle between runs would make two
    runs of one configuration differ for a reason that has nothing to do with the model.
    """
    ordered = sorted(enumerate(sections), key=lambda pair: (pair[1].priority, pair[0]))
    kept: list[tuple[int, Section]] = []
    dropped: list[str] = []
    spent = 0
    for index, section in ordered:
        if not section.lines:
            continue
        cost = section.cost()
        if section.essential or spent + cost <= budget:
            kept.append((index, section))
            spent += cost
            continue
        dropped.append(section.name)

    body = [section.render() for _, section in sorted(kept, key=lambda pair: pair[0])]
    if dropped:
        # **Told, not hidden.** A role that does not know what it was denied cannot say its
        # answer was limited by it, and "the evidence did not settle this" is a thing every
        # role here is required to be able to say.
        body.append(
            "Withheld from this briefing to stay inside its context budget, and reachable only "
            f"by asking: {', '.join(dropped)}."
        )
    text = "\n".join(part for part in body if part)
    return Briefing(
        role=role,
        text=text,
        estimated_tokens=estimate_tokens(text),
        content_tokens=spent,
        budget=budget,
        kept=[section.name for _, section in sorted(kept, key=lambda pair: pair[0])],
        dropped=dropped,
        over_budget=spent > budget,
    )


@dataclass(frozen=True, slots=True)
class Disclosure:
    """One investigation's context accounting: what was pushed, what was pulled (T3.2c).

    **The pull rate is the number T7.3's ablation compares**, and it is defined here rather than
    computed at read time so two runs cannot be measured by two definitions. *Pushed* is what a
    briefing handed a role without being asked. *Pulled* is what arrived because the pipeline
    went and got it: a tool envelope, a retrieval. Both are estimated in the same unit by the
    same estimator, so their ratio is meaningful even though neither is a token count.

    **What this number is not.** It is not a quality measure and nothing should optimise it: a
    pipeline that pushed nothing and pulled everything would score 1.0 and might be worse. It
    describes *how* an investigation got its context, which is what an ablation against
    prompt-stuffing needs to hold constant or vary on purpose.
    """

    pushed_tokens: int = 0
    pulled_tokens: int = 0
    briefings: list[dict[str, object]] = field(default_factory=list)
    dropped_sections: int = 0

    @property
    def pull_rate(self) -> float:
        total = self.pushed_tokens + self.pulled_tokens
        return 0.0 if total == 0 else self.pulled_tokens / total

    def as_row(self) -> dict[str, object]:
        return {
            "pushed_tokens": self.pushed_tokens,
            "pulled_tokens": self.pulled_tokens,
            "pull_rate": round(self.pull_rate, 4),
            "dropped_sections": self.dropped_sections,
            "briefings": list(self.briefings),
        }


class DisclosureMeter:
    """Accumulates a `Disclosure` as the investigation runs."""

    def __init__(self) -> None:
        self._pushed = 0
        self._pulled = 0
        self._dropped = 0
        self._briefings: list[dict[str, object]] = []

    def pushed(self, briefing: Briefing | None) -> None:
        if briefing is None:
            return
        self._pushed += briefing.estimated_tokens
        self._dropped += len(briefing.dropped)
        self._briefings.append(briefing.as_row())

    def pulled(self, text: str) -> None:
        self._pulled += estimate_tokens(text)

    def snapshot(self) -> Disclosure:
        return Disclosure(
            pushed_tokens=self._pushed,
            pulled_tokens=self._pulled,
            briefings=list(self._briefings),
            dropped_sections=self._dropped,
        )
