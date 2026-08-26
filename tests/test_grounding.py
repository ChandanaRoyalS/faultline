"""The verdict/trajectory cross-check, pinned against T3.4's actual run (T3.4b).

Both defects this file guards are recorded in `docs/evidence/t3.4-first-investigation/`:
the synthesizer asserted a dispatch had never happened while the dispatch sat in its own
trajectory, and the assembly that fed it had dropped that dispatch on the way in.
"""

from __future__ import annotations

from dataclasses import dataclass

from faultline.agents.grounding import contradictions

# Verbatim from trajectory e7739dec-8ad2-453d-9ab7-8fd1f039f435, the verdict's first open
# question. tr_f536225dc17d, dispatched at seq 9, is the query it says was never made.
T34_OPEN_QUESTION = (
    "No change history has been queried for shippingservice at all — the changes dispatch "
    "targeted quoteservice. A shippingservice deploy/config/flag query covering at least "
    "00:42–01:42 is the single highest-value missing check and would confirm or refute the "  # noqa: RUF001
    "bad_deploy classification."
)

# Verbatim from the same trajectory, seq 10 - what the changes specialist actually reported.
T34_CHANGES_FINDING = (
    "A single change to shippingservice is recorded in the queried window: an image reference "
    "update executed by platform-automation at 01:39:24Z, roughly three minutes before the "
    "01:42:15Z incident timestamp."
)


@dataclass(frozen=True)
class FakeResult:
    id: str


@dataclass(frozen=True)
class FakeRun:
    specialist: str
    service: str
    result: FakeResult


def t34_runs() -> list[FakeRun]:
    """T3.4's six dispatches, in the order the trajectory records them."""
    return [
        FakeRun("changes", "checkoutservice", FakeResult("tr_81afb255f44e")),
        FakeRun("metrics", "checkoutservice", FakeResult("tr_bf1ed807067d")),
        FakeRun("traces", "checkoutservice", FakeResult("tr_8657d00962e4")),
        FakeRun("changes", "shippingservice", FakeResult("tr_f536225dc17d")),
        FakeRun("changes", "quoteservice", FakeResult("tr_1c0655065fe4")),
        FakeRun("logs", "shippingservice", FakeResult("tr_2ccf8bd687ef")),
    ]


def test_the_t34_contradiction_is_caught_and_names_the_refuting_result_id() -> None:
    """The shape as it happened: the changes finding for shippingservice exists, the verdict
    says it does not, and the check has to notice - and say which result_id refutes it, because
    a flag a scorer cannot resolve is not evidence."""
    assert "shippingservice" in T34_CHANGES_FINDING, "the finding this claim denies"

    flags = contradictions([T34_OPEN_QUESTION], t34_runs())

    assert len(flags) == 1
    assert "tr_f536225dc17d" in flags[0]
    assert "changes" in flags[0] and "shippingservice" in flags[0]


def test_the_contradicting_claim_is_flagged_not_removed() -> None:
    """The verdict is evidence of what the model concluded. Editing it to agree with the record
    would erase the disagreement T4.2 needs to count, so the check returns a flag and touches
    nothing."""
    question = T34_OPEN_QUESTION
    contradictions([question], t34_runs())
    assert question == T34_OPEN_QUESTION


def test_an_empty_result_reported_as_empty_is_not_a_contradiction() -> None:
    """Eight of the nine rehearsed narratives turn on a negative finding. A tool that looked and
    found nothing must not be confused with a tool that never ran - that distinction is the
    whole reason `empty` and `error` are separate fields on every result (ADR-0019)."""
    findings = [
        "No change of any kind is recorded for checkoutservice in the window spanning onset.",
        "The change-history query for quoteservice returned no recorded changes.",
        "The metrics query found no errors for cartservice over the window.",
        "shippingservice logs contain no exceptions and no stack traces at all.",
    ]
    assert contradictions(findings, t34_runs()) == []


def test_a_claim_about_a_service_that_was_never_dispatched_is_not_a_contradiction() -> None:
    """ "paymentservice was never queried" is true and useful. Only a pair that matches an
    executed dispatch is a contradiction."""
    claim = "No change history has been queried for paymentservice at all."
    assert contradictions([claim], t34_runs()) == []


def test_the_wrong_evidence_type_for_a_dispatched_service_is_not_a_contradiction() -> None:
    """shippingservice had changes and logs dispatched, not traces. A verdict saying its traces
    were never pulled is correct, and flagging it would train a scorer to distrust the flag."""
    claim = "No traces were ever retrieved for shippingservice."
    assert contradictions([claim], t34_runs()) == []


def test_each_contradicted_pair_is_reported_once() -> None:
    """A verdict that repeats the claim in its root cause, its reasoning and an open question -
    which is what T3.4's did - is one contradiction, not three."""
    claims = [T34_OPEN_QUESTION, T34_OPEN_QUESTION, "No change record for shippingservice has "]
    assert len(contradictions(claims, t34_runs())) == 1


# Verbatim from trajectory 6b9715de-f684-4352-9739-bbdeeb3607df, T3.4b's own live re-run.
T34B_ROOT_CAUSE_TAIL = (
    "Why shippingservice/quoteservice is refusing these calls is unestablished: no dispatch "
    "examined either service, and the empty change results covered only checkoutservice plus "
    "five other dependencies over 02:17-02:32."
)


def test_a_comma_joined_clause_that_says_a_service_was_covered_is_not_a_contradiction() -> None:
    """**A false positive the T3.4b live run produced**, before the clause rule was tightened.

    The sentence has two halves: the first says shippingservice and quoteservice were never
    dispatched, the second says checkoutservice *was* covered. Read whole, it looks like a claim
    that checkoutservice's change history was never queried - and the check flagged it.

    A check that cries wolf is worse than no check: T4.2 has to be able to trust the flag.
    """
    runs = [FakeRun("changes", "checkoutservice", FakeResult("tr_8deedf529f24"))]
    assert contradictions([T34B_ROOT_CAUSE_TAIL], runs) == []


def test_the_first_half_of_that_sentence_still_flags_a_service_that_was_dispatched() -> None:
    """The tightening must not blunt the check. Same sentence shape, but with a dispatch that
    genuinely happened for the service the negation is about."""
    runs = [FakeRun("changes", "shippingservice", FakeResult("tr_f536225dc17d"))]
    claim = (
        "No change history was queried for shippingservice, and the results covered only "
        "checkoutservice."
    )
    flags = contradictions([claim], runs)
    assert len(flags) == 1 and "tr_f536225dc17d" in flags[0]
