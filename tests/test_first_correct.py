"""Time to first correct hypothesis (T4.2).

The metric that answers what no accuracy figure can: **when did the pipeline first hold the right
idea?** A run that reaches it in its second dispatch and one that reaches it only in the
synthesizer score identically on every other axis, and they are not the same run - the second is
one dropped step away from being wrong.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from evalharness import first_correct as fc
from faultline.agents.model import ModelRequest, ModelResponse

START = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def step(seq: int, role: str, seconds: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "role": role,
        "at": START + timedelta(seconds=seconds),
        "payload": payload,
    }


def plan_step(seq: int, seconds: int, *questions: tuple[str, str, str]) -> dict[str, Any]:
    return step(
        seq,
        "planner",
        seconds,
        {
            "plan": {
                "dispatches": [
                    {"specialist": s, "service": svc, "question": q} for s, svc, q in questions
                ]
            }
        },
    )


def finding_step(seq: int, role: str, seconds: int, *statements: str) -> dict[str, Any]:
    return step(
        seq,
        role,
        seconds,
        {"findings": {"found": [{"statement": s, "result_id": "tr_x"} for s in statements]}},
    )


def verdict_step(seq: int, seconds: int, root_cause: str) -> dict[str, Any]:
    return step(seq, "synthesizer", seconds, {"verdict": {"root_cause": root_cause}})


TRAJECTORY = [
    plan_step(1, 0, ("changes", "adservice", "What changed on adservice?")),
    finding_step(2, "changes", 30, "adservice resource_limits was lowered before onset"),
    verdict_step(3, 90, "adservice was OOM-killed after its memory limit was cut"),
]


class ScriptedJudge:
    name = "scripted-judge"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(text=self._reply, model=self.name, input_tokens=800, output_tokens=40)


class Settings:
    model = "judge-model-x"


# --- extraction is deterministic and free ----------------------------------------------------


def test_every_kind_of_claim_is_collected_in_the_order_it_was_made() -> None:
    """Three payload shapes carry a hypothesis: a plan's dispatch questions, a specialist's
    `found` statements, and the verdict. Everything else is evidence, or prose about claims made
    elsewhere, and including it would put the same idea in the list twice at two times."""
    items = fc.hypotheses(TRAJECTORY)

    assert [h.kind for h in items] == ["plan", "finding", "verdict"]
    assert [h.seq for h in items] == [1, 2, 3]


def test_steps_out_of_order_in_the_row_set_are_sorted_by_seq() -> None:
    """*First* is the whole metric. A row set that arrives unordered - which any SQL without an
    ORDER BY can produce - must not silently change which entry is position 0."""
    items = fc.hypotheses(list(reversed(TRAJECTORY)))

    assert [h.kind for h in items] == ["plan", "finding", "verdict"]


def test_tool_calls_and_disclosure_are_not_hypotheses() -> None:
    """A tool call is evidence, not a claim; disclosure is accounting. Counting either would put
    a position in the list that nobody argued for."""
    noise = [
        step(1, "changes", 0, {"tool": "change_history", "service": "adservice"}),
        step(2, "orchestrator", 5, {"disclosure": {"pull_rate": 0.5}}),
    ]

    assert fc.hypotheses(noise) == []


def test_a_step_with_no_timestamp_is_skipped_rather_than_dated_now() -> None:
    """The metric is a duration. Substituting the current time for a missing one would produce a
    number that changes every time the trajectory is re-read."""
    broken = [
        {"seq": 1, "role": "planner", "at": None, "payload": {"verdict": {"root_cause": "x"}}}
    ]

    assert fc.hypotheses(broken) == []


def test_blank_statements_are_dropped_rather_than_ranked() -> None:
    items = fc.hypotheses([finding_step(1, "logs", 0, "", "   ", "a real statement")])

    assert [h.text for h in items] == ["a real statement"]


def test_a_dispatch_question_carries_its_specialist_and_service() -> None:
    """A question is a hypothesis in interrogative form and the earliest one the record holds -
    but *which* service it was asked about is what decides whether it commits to anything."""
    items = fc.hypotheses(TRAJECTORY)

    assert "[changes @ adservice]" in items[0].text


# --- one judged call, not one per step -------------------------------------------------------


def test_the_judge_is_asked_once_for_the_whole_ordered_list() -> None:
    """**The decision that makes this metric affordable.** The answer is a single position;
    judging each entry separately would multiply the judge's cost by the trajectory length to
    compute the same number, and would hide the ordering that "first" depends on."""
    judge = ScriptedJudge(json.dumps({"index": 1, "reason": "names the limit cut"}))

    result = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    assert len(judge.calls) == 1
    assert result.index == 1
    assert result.hypothesis is not None and result.hypothesis.kind == "finding"


def test_the_claims_reach_the_judge_numbered_and_framed_as_untrusted() -> None:
    """Reuses `judge.wrap`, so the delimiter discipline is the one `judge_run` already has. The
    claims are a document the system under test wrote from tool output it did not control."""
    judge = ScriptedJudge(json.dumps({"index": 0, "reason": "r"}))

    fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    sent = str(judge.calls[0].messages[0]["content"])
    assert 'trust="untrusted"' in sent
    assert "0. [planner/plan]" in sent
    assert "recorded_narrative" in sent, "graded against the human-written reference"


def test_elapsed_runs_from_the_first_hypothesis_not_from_the_run_start() -> None:
    """Triage and the baseline gate are the same work for every arm. Including them would add a
    constant to every figure and make a short investigation look proportionally slower."""
    judge = ScriptedJudge(json.dumps({"index": 2, "reason": "the verdict"}))

    result = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    assert result.elapsed_ms == 90_000, "90s from the plan, not from whenever the run began"


# --- never reaching it is not slowness --------------------------------------------------------


def test_minus_one_is_a_normal_answer_and_leaves_no_time() -> None:
    """**Returning -1 is not a judge failure.** Plenty of investigations never get there, and
    guessing at an entry that is merely close would make this number shortest for the runs that
    deserve it least."""
    judge = ScriptedJudge(json.dumps({"index": -1, "reason": "no entry states the mechanism"}))

    result = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    assert result.reached is False
    assert result.elapsed_ms is None
    assert "no entry" in result.reason


def test_an_out_of_range_index_is_read_as_not_found_rather_than_clamped() -> None:
    """A clamp would invent a position the judge did not choose, and this metric *is* a
    position."""
    judge = ScriptedJudge(json.dumps({"index": 99, "reason": "r"}))

    result = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    assert result.index is None


def test_an_unparseable_reply_is_recorded_rather_than_raised() -> None:
    result = fc.judge_first_correct(
        ScriptedJudge("not json at all"),
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    assert result.index is None
    assert "did not parse" in result.reason


def test_a_trajectory_with_no_claims_is_distinguished_from_never_being_right() -> None:
    """ADR-0019's distinction, one layer up: nothing was claimed, so there was nothing to be
    correct about. The judge is not called at all."""
    judge = ScriptedJudge(json.dumps({"index": 0, "reason": "r"}))

    result = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=[],
    )

    assert judge.calls == [], "no model call when there is nothing to judge"
    assert result.reached is False
    assert "no hypothesis-bearing step" in result.reason


def test_a_very_long_trajectory_says_the_judge_saw_a_prefix() -> None:
    """A judgement over a prefix is a judgement about a prefix, and the cap exists so a
    pathological run cannot put an unbounded document in front of the judge."""
    many = [finding_step(n, "logs", n, f"statement {n}") for n in range(fc.MAX_HYPOTHESES + 5)]
    judge = ScriptedJudge(json.dumps({"index": 0, "reason": "r"}))

    result = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(many),
    )

    assert result.truncated is True
    assert result.depth == fc.MAX_HYPOTHESES + 5, "depth reports what existed, not what was shown"


# --- the deterministic near-neighbour, and why it is not this metric -------------------------


def test_naming_the_suspect_is_reported_separately_and_is_not_this_metric() -> None:
    """**The cheap alternative measures something else.** The planner dispatches at the alerting
    service on nearly every run - that is where the alerts are - so a string match scores the
    correct suspect at position 0 on a run that did not understand the incident until much later.
    The gap between the two is the interesting part, and it is why both are computed.
    """
    items = fc.hypotheses(TRAJECTORY)

    assert fc.suspect_first_named(items, "adservice") == 0, "named in the very first question"

    judge = ScriptedJudge(json.dumps({"index": 2, "reason": "only the verdict commits"}))
    judged = fc.judge_first_correct(
        judge,
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=items,
    )

    assert judged.index == 2
    assert judged.index != fc.suspect_first_named(items, "adservice"), (
        "pointed at the right service from the start while believing the wrong thing until the end"
    )


def test_an_unnamed_suspect_yields_none_rather_than_zero() -> None:
    assert fc.suspect_first_named(fc.hypotheses(TRAJECTORY), "") is None
    assert fc.suspect_first_named(fc.hypotheses(TRAJECTORY), "paymentservice") is None


# --- the panel, and the two ways this metric reads as better than it is ----------------------


def reached(ms: int) -> fc.FirstCorrect:
    items = (
        fc.Hypothesis(seq=1, role="planner", at=START, text="a", kind="plan"),
        fc.Hypothesis(
            seq=2, role="logs", at=START + timedelta(milliseconds=ms), text="b", kind="finding"
        ),
    )
    return fc.FirstCorrect(run_id="r", scenario_id="s", hypotheses=items, index=1)


def never() -> fc.FirstCorrect:
    items = (fc.Hypothesis(seq=1, role="planner", at=START, text="a", kind="plan"),)
    return fc.FirstCorrect(run_id="r", scenario_id="s", hypotheses=items)


def test_a_run_that_never_reached_it_is_excluded_rather_than_scored_as_slow() -> None:
    """**Averaging a failure in as a large number invents a duration nobody measured.** But
    excluding it silently would let a pipeline that is right once and fast post the best time in
    the table, so the reach rate is reported beside the mean, always."""
    panel = fc.Panel(runs=(reached(1000), reached(3000), never()))

    assert panel.mean_elapsed_ms == 2000
    assert panel.reach_rate is not None and abs(panel.reach_rate - 2 / 3) < 1e-9
    assert "2 of 3" in "\n".join(panel.render())


def test_a_panel_where_nothing_reached_it_says_so_rather_than_printing_a_mean() -> None:
    panel = fc.Panel(runs=(never(), never()))

    assert panel.mean_elapsed_ms is None
    assert "No run reached it" in "\n".join(panel.render())


def test_depth_of_one_is_reported_because_ordering_was_not_measured() -> None:
    """The same reason `RankedScore.depth` exists: a figure computed over a list of length one is
    not a measurement of ordering."""
    single = fc.FirstCorrect(
        run_id="r",
        scenario_id="s",
        hypotheses=(fc.Hypothesis(seq=1, role="synthesizer", at=START, text="a", kind="verdict"),),
        index=0,
    )

    assert single.depth == 1
    assert single.elapsed_ms == 0
    assert single.as_dict()["depth"] == 1


def test_the_lineage_note_travels_with_the_figure() -> None:
    """ADR-0020 §1: the lineage rule is *checked at eval time, not assumed*, so the check's own
    reasoning has to reach the row. A judged number whose lineage caveat is dropped is
    half-reported."""
    result = fc.judge_first_correct(
        ScriptedJudge(json.dumps({"index": 0, "reason": "r"})),
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )

    assert "lineage_note" in result.as_dict()
    assert result.as_dict()["lineage_note"], "the check said something; it must not be discarded"


def test_the_row_carries_both_model_ids() -> None:
    """ADR-0020 §1: a judged number is a function of two models, and reporting one of them is
    reporting half the experiment."""
    result = fc.judge_first_correct(
        ScriptedJudge(json.dumps({"index": 0, "reason": "r"})),
        Settings(),
        scenario_id="ad-memory-squeeze",
        run_id="r1",
        agent_model="claude-opus-5",
        items=fc.hypotheses(TRAJECTORY),
    )
    row = result.as_dict()

    assert row["judge_model"] == "judge-model-x"
    assert row["agent_model"] == "claude-opus-5"
