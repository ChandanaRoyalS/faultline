"""The budgeted briefing assembler and the pull-rate it measures (T3.2c)."""

from __future__ import annotations

from faultline.agents.briefing import (
    CHARS_PER_TOKEN,
    Briefing,
    Disclosure,
    DisclosureMeter,
    Section,
    assemble,
    estimate_tokens,
)


def block(name: str, size: int, priority: int = 50, essential: bool = False) -> Section:
    return Section(name=name, lines=["x" * size], priority=priority, essential=essential)


def test_sections_are_kept_in_priority_order_until_the_budget_is_spent() -> None:
    """Whole sections, not truncated text: half a section of evidence is worse than a named
    absence, because a model cannot tell which half it is missing."""
    briefing = assemble(
        "synthesizer",
        [
            block("context", 400, priority=60),
            block("evidence", 400, priority=20),
            block("question", 40, priority=0),
        ],
        budget=120,
    )

    # `kept` is in the order the brief reads, which is the order the role wrote - the priority
    # decided *what* survived, not where it appears.
    assert briefing.kept == ["evidence", "question"]
    assert briefing.dropped == ["context"]
    assert briefing.content_tokens <= 120 and not briefing.over_budget


def test_the_order_within_the_brief_is_the_order_the_role_wrote_it() -> None:
    """Priority decides what is kept; it does not reshuffle what survives. A brief whose
    sections reorder between runs makes two runs of one configuration differ for a reason that
    has nothing to do with the model."""
    briefing = assemble(
        "planner",
        [
            Section(name="first", lines=["AAA"], priority=90),
            Section(name="second", lines=["BBB"], priority=10),
        ],
        budget=1000,
    )

    assert briefing.kept == ["first", "second"]
    assert briefing.text.index("AAA") < briefing.text.index("BBB")


def test_a_dropped_section_is_named_in_the_brief_rather_than_silently_missing() -> None:
    """The same principle as the tool layer's `truncated`: a capped thing that looks complete is
    the failure mode. A role that does not know what it was denied cannot say so in its answer."""
    briefing = assemble("proposer", [block("runbooks", 4000, priority=60)], budget=100)

    assert briefing.dropped == ["runbooks"]
    assert "Withheld from this briefing" in briefing.text
    assert "runbooks" in briefing.text
    # The notice itself is not charged to the budget: a brief that drops one section must never
    # have to drop a second to afford saying so.
    assert not briefing.over_budget and briefing.estimated_tokens > briefing.content_tokens


def test_essential_sections_are_never_dropped_and_an_overrun_is_recorded() -> None:
    """Refusing to brief a role at all would fail an investigation to protect a number, and the
    number exists to describe the investigation."""
    briefing = assemble("scribe", [block("board", 4000, priority=10, essential=True)], budget=50)

    assert briefing.kept == ["board"] and briefing.dropped == []
    assert briefing.over_budget and briefing.content_tokens > 50


def test_empty_sections_are_not_kept_and_do_not_count_as_dropped() -> None:
    """A role with no flags and no retrieval should not be told either was withheld."""
    briefing = assemble("synthesizer", [Section(name="flags", lines=[]), block("board", 20)], 1000)

    assert briefing.kept == ["board"] and briefing.dropped == []
    assert "Withheld" not in briefing.text


def test_the_estimator_is_named_as_an_estimate() -> None:
    """Not a tokenizer count, and it must never be reported as one. Four characters per token,
    wrong in the same direction for every role - which is what a comparison needs."""
    assert estimate_tokens("x" * (CHARS_PER_TOKEN * 10)) == 10
    assert estimate_tokens("") == 0
    assert "estimated_tokens" in Briefing.__dataclass_fields__


# --- the pull rate ----------------------------------------------------------------


def test_the_pull_rate_is_what_arrived_by_asking() -> None:
    """*Pushed* is what a briefing handed a role. *Pulled* is what the pipeline went and got: a
    tool envelope, a retrieval. Both estimated by the same estimator, so the ratio means
    something even though neither is a token count."""
    meter = DisclosureMeter()
    meter.pushed(assemble("planner", [block("incident", 400)], 1000))
    meter.pulled("y" * 1200)

    disclosure = meter.snapshot()

    assert disclosure.pushed_tokens == 100 and disclosure.pulled_tokens == 300
    assert disclosure.pull_rate == 0.75
    assert disclosure.as_row()["pull_rate"] == round(disclosure.pull_rate, 4)


def test_an_investigation_that_pulled_nothing_reports_zero_rather_than_dividing_by_zero() -> None:
    assert Disclosure().pull_rate == 0.0
    assert DisclosureMeter().snapshot().pull_rate == 0.0


def test_every_briefing_is_recorded_with_what_it_dropped() -> None:
    """T7.3's ablation reads these rows off a stored run; a rate with no per-role detail cannot
    say which role's context the ablation actually changed."""
    meter = DisclosureMeter()
    meter.pushed(assemble("proposer", [block("runbooks", 4000, priority=60), block("a", 8)], 20))
    meter.pushed(None)

    disclosure = meter.snapshot()

    assert len(disclosure.briefings) == 1, "a role that never ran contributes nothing"
    assert disclosure.briefings[0]["role"] == "proposer"
    assert disclosure.briefings[0]["dropped"] == ["runbooks"]
    assert disclosure.dropped_sections == 1
