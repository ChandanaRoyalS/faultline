"""The incident view T5.1's UI reads (T5.1).

*"The clickable citation is the demo's most convincing moment — a claim that lands you in the
actual data."* The plan says the frontend goes *"over the platform API"*, and the platform's whole
HTTP surface was `POST /api/v1/alerts` and `GET /healthz`. This is the read half.
"""

from __future__ import annotations

import json
import typing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml

from faultline.api import view

REPO_ROOT = Path(__file__).resolve().parents[1]
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
    assert left["datasource"] == "webstore-metrics"
    assert left["range"] == {"from": WINDOW[0], "to": WINDOW[1]}


def test_each_tool_links_to_its_own_datasource() -> None:
    """**By uid, and the uids are read off the provisioning files rather than trusted here.**

    The first version of this test asserted `prometheus`, `loki` and `tempo` - what the table
    said, copied into the test. Grafana resolves `left.datasource` by uid; the demo provisions
    Prometheus as `webstore-metrics` and Jaeger as `webstore-traces`, and until T6.1 nothing here
    was Tempo. Two of three links would have opened Explore on no datasource. The Loki and Tempo
    uids are this repository's to provision and are read from their files; the demo's Prometheus
    lives in the pinned clone and is read from it when present, else pinned to what v1.2.1 ships.
    """
    logs = Call("logql_query", "tr_l", selector='{app="cart"}', window=WINDOW)
    traces = Call(
        "trace_query", "tr_t", service="cart", traced_service="cartservice", window=WINDOW
    )
    metrics = Call("metric_baseline", "tr_m", query="up", window=WINDOW)

    loki = yaml.safe_load((REPO_ROOT / "compose" / "grafana-loki-datasource.yml").read_text())
    tempo = yaml.safe_load((REPO_ROOT / "compose" / "grafana-tempo-datasource.yml").read_text())
    expected = {
        "logql_query": loki["datasources"][0]["uid"],
        "trace_query": tempo["datasources"][0]["uid"],
        **_world_grafana_uids(),
    }
    for call, key in ((logs, "logql_query"), (traces, "trace_query"), (metrics, "metric_baseline")):
        link = view.citations([call.result_id], [call])[0].deep_link
        assert link is not None, key
        assert json.loads(unquote(link.split("left=", 1)[1]))["datasource"] == expected[key], key


def _world_grafana_uids() -> dict[str, str]:
    """`{tool: uid}` for the datasource the demo provisions that a tool links to, read from the
    clone if present. Since T6.1 that is Prometheus alone; traces link to this repo's Tempo."""
    provisioned = REPO_ROOT / "world" / "src" / "grafana" / "provisioning" / "datasources"
    uids = {"metric_baseline": "webstore-metrics"}
    if not provisioned.is_dir():
        return uids
    by_type = {
        d["type"]: d["uid"]
        for f in provisioned.glob("*.yaml")
        for d in (yaml.safe_load(f.read_text()) or {}).get("datasources", [])
    }
    return {"metric_baseline": by_type["prometheus"]}


def test_a_trace_citation_links_to_the_traceql_tempo_was_asked() -> None:
    """The tool searched one canonical service over one window in TraceQL, and that is the whole of
    what was asked (T6.1). The link reproduces the search, not a guess at it - and it needs
    `traced_service`, the name the tool used, not `service`, the name the planner said, because the
    two differ (`cart` vs `cartservice`) and the trace store knows only one."""
    call = Call("trace_query", "tr_t", service="cart", traced_service="cartservice", window=WINDOW)

    left = json.loads(unquote(view.citations(["tr_t"], [call])[0].deep_link.split("left=", 1)[1]))

    assert left["queries"] == [
        {"queryType": "traceql", "query": '{resource.service.name="cartservice"}'}
    ]
    assert left["range"] == {"from": WINDOW[0], "to": WINDOW[1]}
    assert view.deep_link("trace_query", {"service": "cart", "window": WINDOW}) is None, (
        "the planner's name is not what Jaeger was asked; without the recorded one there is no link"
    )


def test_a_change_history_citation_gets_no_link_rather_than_a_wrong_one() -> None:
    """`change_history` reads the platform's own Postgres and has no datasource. **No link is
    better than a link to something else.**"""
    call = Call("change_history", "tr_c", service="adservice", window=WINDOW)

    citation = view.citations(["tr_c"], [call])[0]

    assert citation.resolved is True, "the citation resolves"
    assert citation.deep_link is None, "but there is nowhere to send a reader"


def test_the_link_carries_grafanas_host_and_not_the_page_s() -> None:
    """**The assertion this replaces was the defect.**

    It read `startswith("/explore?")` under the heading *"the link is relative so it works wherever
    Grafana is served"*, and a relative path does not resolve against wherever Grafana is served -
    it resolves against whatever served the page. That is `faultline-ingest`, which has two static
    routes and no `/explore`. Every citation on the incident screen 404'd, on the development
    machine and everywhere else, while this test passed.

    A link is only a link if it names a host that answers. Asserting the *shape* of a URL is what
    let a broken one through, so this asserts the base as well.
    """
    call = Call("promql_query", "tr_1", query="up")

    link = view.citations(["tr_1"], [call])[0].deep_link

    assert link is not None
    assert link.startswith("http://localhost:3000/explore?"), (
        "the configured Grafana, not the host serving the page"
    )


def test_the_grafana_base_is_configuration_not_a_constant() -> None:
    """A deployment serves Grafana somewhere else, and T5.5 puts one behind a single hostname.

    `deep_link` takes the base explicitly here rather than through the environment, because the
    ambient default is what the previous test asserts and a second test reading the same ambient
    value would prove nothing about whether the value is used.
    """
    link = view.deep_link("promql_query", {"query": "up"}, grafana_url="https://faultline.example")

    assert link is not None
    assert link.startswith("https://faultline.example/explore?")


def test_a_trailing_slash_on_the_configured_base_does_not_double() -> None:
    """`https://host//explore` is a different path to Grafana, and an operator writes the slash."""
    link = view.deep_link("promql_query", {"query": "up"}, grafana_url="https://faultline.example/")

    assert link is not None
    assert "//explore" not in link.removeprefix("https://")


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


# --- the proposal is shown, as a claim, with the line that says it did not run -----------------


class ProposalStep(Step):
    """A `PROPOSAL` step as `Investigation._run_proposer` records it (payload keys `proposal`,
    `accepted`, `violations`, `escalated`)."""

    def __init__(self, seq: int, proposal: dict, **flags: Any) -> None:
        super().__init__(seq, "proposer", {"proposal": proposal, **flags})
        self.kind = "proposal"


PROPOSAL = {
    "remediation_class": "config_revert",
    "action_id": "revert-image-tag",
    "target": "cartservice",
    "rests_on": ["tr_1", "tr_invented"],
    "expected_effect": "<b>5xx rate</b> returns to baseline",
    "confirm_within_seconds": 300,
    "if_wrong": "errors persist past the window",
    "risk": "a brief restart",
    "blast_radius": "cartservice only",
}


def test_the_view_carries_the_proposal_and_says_it_was_not_executed() -> None:
    """**The screen showed a fix class and called it the remediation (T5.6's audit).** The proposer
    has produced action, target, effect, window, falsifier, risk and blast radius since T3.9 and
    the trajectory stored all of it; nothing rendered it. MVP-CUT promises *"proposals with risk
    notes"* and a risk note nobody can read is not delivered. The execution line is the server's
    and says the plane does not exist (ADR-0028 §4): the page must not be able to imply otherwise.
    """
    call = Call("promql_query", "tr_1", service="cartservice", query="up", window=WINDOW)
    steps = [
        Step(1, "metrics", {"service": "cartservice"}, tool_call=call),
        ProposalStep(2, PROPOSAL, accepted=True, violations=[], escalated=False),
    ]

    proposal = view.incident_view(Incident(), Trajectory(steps))["proposal"]

    assert proposal["action_id"] == "revert-image-tag"
    assert proposal["target"] == "cartservice"
    assert proposal["remediation_class"] == "config_revert"
    assert proposal["confirm_within_seconds"] == 300
    assert proposal["accepted"] is True and proposal["escalated"] is False
    assert proposal["execution"] == view.EXECUTION_NOTE
    assert "not executed" in proposal["execution"]
    assert [c["result_id"] for c in proposal["cites"]] == ["tr_1", "tr_invented"]
    assert [c["resolved"] for c in proposal["cites"]] == [True, False]


def test_the_proposers_prose_sits_under_untrusted_and_its_ids_do_not() -> None:
    """`action_id` and `target` come from catalogs and the class is an enum - safe to put in a
    heading. The four sentences are the model's words about attacker-influenced telemetry and go
    where every other model sentence on this screen goes."""
    steps = [ProposalStep(1, PROPOSAL, accepted=True, violations=[], escalated=False)]

    proposal = view.incident_view(Incident(), Trajectory(steps))["proposal"]

    for key in ("expected_effect", "if_wrong", "risk", "blast_radius"):
        assert key not in proposal, key
        assert proposal["untrusted"][key] == PROPOSAL[key], key


def test_a_refused_proposal_is_shown_with_its_violations_not_hidden() -> None:
    """A proposal the validator refused is still what the model proposed. Hiding it would make a
    run that was stopped at the approval boundary look like a run that abstained."""
    steps = [
        ProposalStep(
            1,
            {**PROPOSAL, "target": "frontend"},
            accepted=False,
            violations=["target frontend is not in the allowlist for revert-image-tag"],
            escalated=True,
        )
    ]

    proposal = view.incident_view(Incident(), Trajectory(steps))["proposal"]

    assert proposal["accepted"] is False and proposal["escalated"] is True
    assert proposal["violations"] == [
        "target frontend is not in the allowlist for revert-image-tag"
    ]


def test_no_proposal_step_means_none_not_an_empty_card() -> None:
    """Before the proposer runs - and forever, for an investigation whose proposer produced nothing
    twice - there is no proposal, and the page says so rather than rendering empty fields."""
    steps = [Step(1, "synthesizer", {"verdict": {"evidence": [], "alternatives": []}})]

    assert view.incident_view(Incident(), Trajectory(steps))["proposal"] is None
    assert view.incident_view(Incident(), None)["proposal"] is None


def test_the_timeline_names_the_proposal_by_its_catalog_ids_only() -> None:
    """`action_id` and `target` are catalog entries; the summary may say them. Nothing else from the
    proposal - all of it prose - may reach a summary."""
    steps = [
        ProposalStep(1, PROPOSAL, accepted=True),
        ProposalStep(
            2,
            {**PROPOSAL, "remediation_class": "none", "action_id": "", "target": ""},
            accepted=True,
        ),
    ]

    summaries = [entry.summary for entry in view.timeline(steps)]

    assert summaries == ["proposed revert-image-tag on cartservice", "proposed abstained"]
    assert not any("<" in s for s in summaries)
