"""The incident view T5.1's UI reads (T5.1).

*"The clickable citation is the demo's most convincing moment — a claim that lands you in the
actual data."* The plan says the frontend goes *"over the platform API"*, and the platform's whole
HTTP surface was `POST /api/v1/alerts` and `GET /healthz`. This is the read half.
"""

from __future__ import annotations

import json
import typing
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

from faultline.api import view

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
WINDOW = ["2026-09-03T11:30:00+00:00", "2026-09-03T12:00:00+00:00"]


class Call:
    def __init__(self, tool: str, result_id: str, **request: Any) -> None:
        self.tool = tool
        self.result_id = result_id
        self.request = request


class Step:
    def __init__(self, seq: int, role: str, payload: dict, tool_call: Any = None) -> None:
        self.seq = seq
        self.role = role
        self.kind = "COMPLETION"
        self.at = NOW
        self.payload = payload
        self.tool_call = tool_call


# --- an unresolvable citation is shown, not dropped -------------------------------------------


def test_a_citation_that_resolves_to_nothing_is_kept_and_marked() -> None:
    """**The obvious implementation drops it and shows the rest**, which would make a verdict
    resting on three real citations and one invented one indistinguishable from one resting on
    four. An unresolvable id is what a fabricated citation looks like — B2 produces them by
    construction, and ADR-0028 §2 lists it among the executor's refusals."""
    real = Call("promql_query", "tr_real", service="adservice", query="up", window=WINDOW)

    found = view.citations(["tr_real", "tr_invented"], [real])

    assert [c.resolved for c in found] == [True, False]
    assert found[1].result_id == "tr_invented"
    assert found[1].deep_link is None


def test_citations_keep_the_verdicts_order_not_the_trajectorys() -> None:
    """A verdict cites in the order it argues, and a reader following an argument should meet the
    evidence in the order it is offered."""
    calls = [
        Call("promql_query", "tr_a", query="up"),
        Call("logql_query", "tr_b", selector='{app="x"}'),
    ]

    assert [c.result_id for c in view.citations(["tr_b", "tr_a"], calls)] == ["tr_b", "tr_a"]


# --- the deep link is the stored query, or nothing ---------------------------------------------


def test_the_link_carries_the_query_that_actually_ran() -> None:
    """**Never reconstructed.** A query re-derived from the service and window is a *plausible*
    query, and a link landing a reader in data the agent never saw manufactures corroboration —
    the opposite of what a citation is for."""
    call = Call(
        "promql_query", "tr_1", service="adservice", query="sum(rate(x[2m]))", window=WINDOW
    )

    link = view.citations(["tr_1"], [call])[0].deep_link

    assert link is not None
    left = json.loads(unquote(link.split("left=", 1)[1]))
    assert left["queries"][0]["expr"] == "sum(rate(x[2m]))"
    assert left["datasource"] == "prometheus"
    assert left["range"] == {"from": WINDOW[0], "to": WINDOW[1]}


def test_each_tool_links_to_its_own_datasource() -> None:
    logs = Call("logql_query", "tr_l", selector='{app="cart"}', window=WINDOW)
    traces = Call("trace_query", "tr_t", query="cartservice", window=WINDOW)

    for call, expected in ((logs, "loki"), (traces, "tempo")):
        link = view.citations([call.result_id], [call])[0].deep_link
        assert link is not None
        assert json.loads(unquote(link.split("left=", 1)[1]))["datasource"] == expected


def test_a_change_history_citation_gets_no_link_rather_than_a_wrong_one() -> None:
    """`change_history` reads the platform's own Postgres and has no datasource. **No link is
    better than a link to something else.**"""
    call = Call("change_history", "tr_c", service="adservice", window=WINDOW)

    citation = view.citations(["tr_c"], [call])[0]

    assert citation.resolved is True, "the citation resolves"
    assert citation.deep_link is None, "but there is nowhere to send a reader"


def test_the_link_is_relative_so_it_works_wherever_grafana_is_served() -> None:
    """The platform does not know its own public URL, and guessing one is how a demo link 404s on
    a stranger's machine — which is exactly what T5.4's clean-clone rehearsal exists to catch."""
    call = Call("promql_query", "tr_1", query="up")

    assert view.citations(["tr_1"], [call])[0].deep_link.startswith("/explore?")


def test_a_call_with_no_query_yields_no_link() -> None:
    assert view.deep_link("promql_query", {"service": "x"}) is None
    assert view.deep_link("promql_query", {"query": "   "}) is None


# --- untrusted content is labelled, everywhere it appears --------------------------------------


def test_every_world_produced_string_sits_under_untrusted() -> None:
    """**The incident view is the first place attacker-influenced telemetry reaches a browser.**

    THREAT-MODEL thesis 1 is about that text reaching a *model*; the same text reaching a
    *renderer* is an injection surface of a different kind, and a frontend interpolating it into
    the DOM has an XSS hole fed by the monitored system's own logs. Nothing here can force a
    frontend to escape — what it can do is refuse to hand the text over unlabelled.
    """
    card = view.EvidenceCard(role="logs", statements=["<script>alert(1)</script>"], cites=[])

    payload = card.as_dict()

    assert "statements" not in payload, "never at the top level"
    assert payload["untrusted"]["statements"] == ["<script>alert(1)</script>"]


def test_a_timeline_summary_never_quotes_the_world() -> None:
    """A summary built from world-produced content would put untrusted text outside the
    `untrusted` block, which is the one place the label cannot follow it."""
    steps = [
        Step(1, "planner", {"plan": {"dispatches": [{"specialist": "logs"}]}}),
        Step(2, "logs", {"service": "cartservice"}, tool_call=Call("logql_query", "tr_1")),
        Step(3, "synthesizer", {"verdict": {"root_cause": "<img onerror=x>"}}),
    ]

    summaries = [entry.summary for entry in view.timeline(steps)]

    assert summaries == ["planned 1 dispatch(es)", "logql_query on cartservice", "verdict returned"]
    assert not any("<" in s for s in summaries)


# --- the assembled view -------------------------------------------------------------------------


class Incident:
    id = "inc-1"
    opened_at = NOW

    class _State:
        value = "investigating"

    class _Sev:
        value = "critical"

    state = _State()
    severity = _Sev()
    episodes: typing.ClassVar[dict] = {}


class Trajectory:
    id = "traj-1"

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps


def test_the_view_carries_timeline_evidence_and_the_ranked_report() -> None:
    call = Call("promql_query", "tr_1", service="adservice", query="up", window=WINDOW)
    steps = [
        Step(1, "metrics", {"findings": {"found": [{"statement": "s", "result_id": "tr_1"}]}}),
        Step(
            2,
            "synthesizer",
            {
                "verdict": {
                    "root_cause": "r",
                    "service": "adservice",
                    "fault_class": "resource_exhaustion",
                    "remediation_class": "config_revert",
                    "confidence": "medium",
                    "evidence": ["tr_1"],
                    "reasoning": "because",
                    "open_questions": [],
                    "alternatives": [
                        {"service": "frontend", "fault_class": "bad_config", "why_not": "weaker"}
                    ],
                }
            },
        ),
    ]
    steps[0].tool_call = call

    payload = view.incident_view(Incident(), Trajectory(steps))

    assert payload["trajectory_id"] == "traj-1"
    assert len(payload["timeline"]) == 2
    assert payload["evidence"][0]["cites"][0]["deep_link"] is not None
    assert payload["report"]["service"] == "adservice"
    assert payload["report"]["untrusted"]["root_cause"] == "r"


def test_alternatives_are_ranked_from_two_because_the_verdict_is_rank_one() -> None:
    """A reader who cannot see the order cannot see that the verdict *chose*."""
    steps = [
        Step(
            1,
            "synthesizer",
            {
                "verdict": {
                    "evidence": [],
                    "alternatives": [
                        {"service": "a", "why_not": "w"},
                        {"service": "b", "why_not": "w"},
                    ],
                }
            },
        )
    ]

    ranks = [
        a["rank"]
        for a in view.incident_view(Incident(), Trajectory(steps))["report"]["alternatives"]
    ]

    assert ranks == [2, 3]


def test_an_incident_with_no_trajectory_still_renders() -> None:
    """An incident that has not been investigated yet is the state the live-updating view spends
    its first seconds in. It must not be an error."""
    payload = view.incident_view(Incident(), None)

    assert payload["report"] is None
    assert payload["timeline"] == [] and payload["evidence"] == []
    assert payload["incident_id"] == "inc-1"
