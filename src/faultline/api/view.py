"""The incident view: what T5.1's UI reads (T5.1).

T5.1: *"A focused web view per incident: live-updating timeline, evidence cards per specialist,
the ranked RCA report, and citations that deep-link into Grafana queries."* Its reason:
***"The clickable citation is the demo's most convincing moment — a claim that lands you in the
actual data."***

The plan says the frontend goes *"over the platform API"*. **There is no platform API.** The
service's entire HTTP surface is `POST /api/v1/alerts` and `GET /healthz` — a write path and a
health check. This module is the read half, and it is the half that can be built and tested
without a browser.

## A citation that does not resolve is shown, not dropped

The verdict cites `result_id`s. Some may not resolve — a trajectory pruned, a run whose envelopes
were never persisted, or **a fabricated id**, which is what an unresolvable citation looks like
when a model invents one (ADR-0028 §2 lists it among the executor's refusals, and B2 produces them
by construction).

**The obvious implementation drops them and shows the rest.** That would make a verdict resting on
three real citations and one invented one indistinguishable from one resting on four. So
`Citation.resolved` is false and the card says so, in the surface where a reader is most likely to
be persuaded by the *appearance* of evidence.

## The deep link is built from the stored query, never reconstructed

The link goes to what the tool actually asked, read out of `trajectory_tool_calls.request` — not
re-derived from the service and the window. A reconstructed query is a *plausible* query, and a
link that lands a reader in data the agent did not look at is worse than no link: it manufactures
corroboration.

Where the stored request has no query — a change-history call, which reads Postgres and not a
datasource — there is no link, and `deep_link` is `None`. **No link is better than a link to
something else.**

## Everything the world produced is labelled untrusted, in the payload

THREAT-MODEL thesis 1: *"Logs, traces, and commit messages are attacker-influenced text that flows
into agent context. A malicious log line is a prompt-injection vector."*

**The incident view is the first place that text reaches a browser**, which the threat model does
not yet cover — thesis 1 is about text reaching a *model*. The same text reaching a *renderer* is
an injection surface of a different kind, and a frontend that interpolates it into the DOM has an
XSS hole fed by the monitored system's own logs.

Nothing here can force a frontend to escape. What it can do is refuse to hand over untrusted text
unlabelled: every field carrying world-produced content sits under `untrusted`, so a renderer that
treats it as markup has ignored a label rather than missed a subtlety. `docs/THREAT-MODEL.md`
gains a thesis when T5.1's frontend exists; this is the seam it will attach to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from faultline.tools.settings import ToolSettings

GRAFANA_EXPLORE = "/explore"
"""Grafana's explore path, appended to `ToolSettings.grafana_url`.

**This was a bare relative path and every citation link 404'd.** The reasoning recorded here was
*"relative, so the deep link works against whatever host serves Grafana in the reader's
environment - the platform does not know its own public URL"*. The first half does not follow from
the second: the host serving the incident page is `faultline-ingest`, which has exactly two static
routes and no `/explore`, so a relative link resolved to the one host guaranteed not to answer it.

The platform does not know its own public URL and still does not. It is *told* Grafana's, beside
Prometheus's and Loki's, which is what a deep link actually needs."""


@lru_cache(maxsize=1)
def _grafana_base() -> str:
    """Read once, not per citation.

    `ToolSettings` parses the environment and `.env` on construction and a verdict cites several
    times per page. Tests that change the setting call `_grafana_base.cache_clear()`.
    """
    return ToolSettings().grafana_url.rstrip("/")


DATASOURCE_BY_TOOL = {
    "promql_query": "webstore-metrics",
    "metric_baseline": "webstore-metrics",
    "logql_query": "loki",
    "trace_query": "webstore-traces",
}
"""Which Grafana datasource a tool's query belongs to, **by the uid each is provisioned under**.

The first version said `prometheus`, `loki` and `tempo`. Two of those were wrong for this world and
nothing could tell: Grafana resolves `left.datasource` by uid, the demo provisions Prometheus as
`webstore-metrics` and Jaeger as `webstore-traces` (`world/src/grafana/provisioning/datasources/`),
and there is no Tempo here at all. Only `loki` was right, because this repository provisions it
(`compose/grafana-loki-datasource.yml`). `tests/test_incident_view.py` now reads the uids from those
files rather than trusting this table.

`change_history` is absent deliberately: it reads the platform's own Postgres, has no datasource,
and gets no link."""


@dataclass(frozen=True, slots=True)
class Citation:
    """One `result_id` a verdict rests on, resolved or visibly not."""

    result_id: str
    resolved: bool
    tool: str = ""
    service: str = ""
    query: str = ""
    deep_link: str | None = None
    window: tuple[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "resolved": self.resolved,
            "tool": self.tool,
            "service": self.service,
            "deep_link": self.deep_link,
            "window": list(self.window) if self.window else None,
            # Under `untrusted` because a PromQL selector can carry a service name that came from
            # the monitored world. Small surface, same rule.
            "untrusted": {"query": self.query},
        }


def deep_link(tool: str, request: dict[str, Any], grafana_url: str | None = None) -> str | None:
    """A Grafana explore URL for one stored tool call, or `None` when there is nothing to link to.

    Built from `request` as it was recorded. A query re-derived from the service and window would
    be a *plausible* query rather than the one that ran, and a link landing a reader in data the
    agent never saw manufactures corroboration - the opposite of what a citation is for.

    **Which is why, until T5.4c, no real incident had ever had a link.** This function read
    `request["query"]` and `request["selector"]`, and the investigation recorded neither: it wrote
    the service and the window onto the request and the tool kept the query to itself. Every test
    passed, because every test built its own `request` with the key in it. The first citation
    clicked on a machine other than the author's was plain text, and so was every other one. The
    investigation now records what the tool reports it asked (`Investigation._asked`), and this
    reads exactly that: PromQL under `query`, LogQL under `selector`, and for traces the canonical
    service Jaeger was searched for under `traced_service`.

    `grafana_url` overrides the configured base; `None` reads `ToolSettings.grafana_url`. The
    parameter exists so a test can state the base it expects instead of inheriting the ambient
    environment - which is how this function's own defect survived a test suite.
    """
    datasource = DATASOURCE_BY_TOOL.get(tool)
    if not datasource:
        return None
    if tool == "trace_query":
        # Jaeger has no query language. What was asked was a search: this service, this window.
        traced = str(request.get("traced_service") or "").strip()
        if not traced:
            return None
        queries: list[dict[str, Any]] = [{"queryType": "search", "service": traced}]
    else:
        query = str(request.get("query") or request.get("selector") or "").strip()
        if not query:
            return None
        queries = [{"expr": query}]
    window = request.get("window") or []
    left: dict[str, Any] = {"datasource": datasource, "queries": queries}
    if len(window) == 2:
        left["range"] = {"from": window[0], "to": window[1]}
    base = _grafana_base() if grafana_url is None else grafana_url.rstrip("/")
    return f"{base}{GRAFANA_EXPLORE}?left={quote(json.dumps(left, separators=(',', ':')))}"


def citations(cited: list[str], calls: list[Any]) -> list[Citation]:
    """Resolve every cited id against the trajectory's tool calls.

    **Order follows the verdict, not the trajectory.** The verdict cites in the order it argues,
    and a reader following an argument should meet the evidence in the order it is offered.

    An id that resolves to nothing becomes a `Citation` with `resolved=False` rather than being
    omitted - see the module docstring. Dropping it would make a verdict resting on three real
    citations and one invented one look identical to one resting on four.
    """
    by_id = {getattr(call, "result_id", None): call for call in calls}
    found: list[Citation] = []
    for result_id in cited:
        call = by_id.get(result_id)
        if call is None:
            found.append(Citation(result_id=result_id, resolved=False))
            continue
        request = dict(getattr(call, "request", {}) or {})
        window = request.get("window") or []
        found.append(
            Citation(
                result_id=result_id,
                resolved=True,
                tool=str(getattr(call, "tool", "")),
                service=str(request.get("service") or ""),
                query=str(
                    request.get("query")
                    or request.get("selector")
                    or request.get("traced_service")
                    or ""
                ),
                deep_link=deep_link(str(getattr(call, "tool", "")), request),
                window=(str(window[0]), str(window[1])) if len(window) == 2 else None,
            )
        )
    return found


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One step, as the timeline shows it."""

    seq: int
    role: str
    kind: str
    at: datetime
    summary: str
    """**Structural text only** - the role, the tool, the service. Never a log line: a summary
    built from world-produced content would put untrusted text outside the `untrusted` block."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "role": self.role,
            "kind": self.kind,
            "at": self.at.isoformat(),
            "summary": self.summary,
        }


def timeline(steps: list[Any]) -> list[TimelineEntry]:
    """The steps in order, described without quoting anything the world produced."""
    entries: list[TimelineEntry] = []
    for step in sorted(steps, key=lambda s: int(getattr(s, "seq", 0))):
        payload = dict(getattr(step, "payload", {}) or {})
        kind = getattr(getattr(step, "kind", None), "value", str(getattr(step, "kind", "")))
        call = getattr(step, "tool_call", None)
        if call is not None:
            summary = f"{getattr(call, 'tool', 'tool')} on {payload.get('service', 'a service')}"
        elif payload.get("verdict"):
            summary = "verdict returned"
        elif payload.get("proposal"):
            body = payload.get("proposal") or {}
            action = body.get("action_id") or "abstained"
            target = body.get("target") or ""
            summary = f"proposed {action}" + (f" on {target}" if target else "")
        elif payload.get("plan"):
            dispatches = (payload.get("plan") or {}).get("dispatches") or []
            summary = f"planned {len(dispatches)} dispatch(es)"
        else:
            summary = f"{getattr(step, 'role', 'role')} step"
        entries.append(
            TimelineEntry(
                seq=int(getattr(step, "seq", 0)),
                role=str(getattr(step, "role", "")),
                kind=str(kind),
                at=step.at,
                summary=summary,
            )
        )
    return entries


@dataclass(frozen=True, slots=True)
class EvidenceCard:
    """One specialist's findings, with the citations behind them."""

    role: str
    statements: list[str] = field(default_factory=list)
    ruled_out: list[str] = field(default_factory=list)
    cites: list[Citation] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "cites": [c.as_dict() for c in self.cites],
            # **Every statement is a model's prose about attacker-influenced text.** Labelled, so
            # a renderer that interpolates it into the DOM has ignored a label rather than missed
            # a subtlety. See the module docstring on thesis 1 reaching a browser.
            "untrusted": {"statements": list(self.statements), "ruled_out": list(self.ruled_out)},
        }


def evidence(steps: list[Any], calls: list[Any]) -> list[EvidenceCard]:
    """One card per specialist step that reported findings."""
    cards: list[EvidenceCard] = []
    for step in sorted(steps, key=lambda s: int(getattr(s, "seq", 0))):
        findings = (dict(getattr(step, "payload", {}) or {})).get("findings") or {}
        found = findings.get("found") or []
        if not found:
            continue
        cited = [str(f.get("result_id")) for f in found if f.get("result_id")]
        cards.append(
            EvidenceCard(
                role=str(getattr(step, "role", "")),
                statements=[str(f.get("statement", "")) for f in found],
                ruled_out=[str(r.get("hypothesis", "")) for r in findings.get("ruled_out") or []],
                cites=citations(cited, calls),
            )
        )
    return cards


def incident_view(incident: Any, trajectory: Any | None) -> dict[str, Any]:
    """Everything one incident view needs, in one payload.

    One payload rather than several endpoints: the view is a single screen, and T5.1 asks for
    *"one great screen"*. Assembling it server-side also means the untrusted/structural split is
    decided in one place rather than in each of a frontend's fetches.
    """
    steps = list(getattr(trajectory, "steps", []) or []) if trajectory else []
    calls = [step.tool_call for step in steps if getattr(step, "tool_call", None) is not None]
    verdict = next(
        (
            (dict(getattr(s, "payload", {}) or {})).get("verdict")
            for s in reversed(steps)
            if (dict(getattr(s, "payload", {}) or {})).get("verdict")
        ),
        None,
    )

    report: dict[str, Any] | None = None
    if verdict:
        report = {
            "fault_class": verdict.get("fault_class"),
            "remediation_class": verdict.get("remediation_class"),
            "service": verdict.get("service") or None,
            "confidence": verdict.get("confidence"),
            "cites": [c.as_dict() for c in citations(list(verdict.get("evidence") or []), calls)],
            # T4.2's ranked runners-up, shown as ranked rather than as a flat list - a reader who
            # cannot see the order cannot see that the verdict *chose*.
            "alternatives": [
                {
                    "rank": position,
                    "service": alt.get("service"),
                    "fault_class": alt.get("fault_class"),
                    "untrusted": {
                        "root_cause": alt.get("root_cause", ""),
                        "why_not": alt.get("why_not", ""),
                    },
                }
                for position, alt in enumerate(verdict.get("alternatives") or [], start=2)
            ],
            "untrusted": {
                "root_cause": verdict.get("root_cause", ""),
                "reasoning": verdict.get("reasoning", ""),
                "open_questions": list(verdict.get("open_questions") or []),
            },
        }

    proposal = _proposal(steps, calls)
    return {
        "incident_id": getattr(incident, "id", ""),
        "state": getattr(getattr(incident, "state", None), "value", ""),
        "severity": getattr(getattr(incident, "severity", None), "value", ""),
        "opened_at": (
            incident.opened_at.isoformat() if getattr(incident, "opened_at", None) else None
        ),
        "episodes": [
            {
                "service": episode.service,
                "alertname": episode.alertname,
                "severity": getattr(episode.severity, "value", str(episode.severity)),
                "starts_at": episode.starts_at.isoformat(),
            }
            for episode in sorted(
                getattr(incident, "episodes", {}).values(), key=lambda e: e.starts_at
            )
        ],
        "trajectory_id": getattr(trajectory, "id", None) if trajectory else None,
        "timeline": [entry.as_dict() for entry in timeline(steps)],
        "evidence": [card.as_dict() for card in evidence(steps, calls)],
        "report": report,
        "proposal": proposal,
    }


EXECUTION_NOTE = "not executed - no executor exists; a proposal is a claim, never the change"
"""What the screen says where an action plane would report execution status. ADR-0028 §4 leaves
execution success as a reported-not-measured axis until T6.2 builds the plane; the MVP-cut bullets
say *"remediation as proposals with risk notes"*, and a screen that showed the proposal without
saying it was not run would be claiming the second half of a sentence the project only owns the
first half of."""


def _proposal(steps: list[Any], calls: list[Any]) -> dict[str, Any] | None:
    """The remediation proposal, from the newest `PROPOSAL` step - or `None` before one exists.

    **The screen showed a fix class and called it the remediation (T5.6's audit).** The proposer
    had been producing a full proposal since T3.9 - action, target, expected effect, how long to
    wait, what would falsify it, the risk, the blast radius - and the trajectory stored it, and
    nothing rendered it. The specification's video beat is *"remediation as proposal"*; the MVP-cut
    bullets promise *"proposals with risk notes"*. A risk note nobody can read is not a deliverable.

    Structural fields (`action_id`, `target`, `remediation_class`, the seconds, the flags) are
    drawn from catalogs or validated by contract. The four prose fields are the proposer's words
    about attacker-influenced telemetry and sit under `untrusted`, like every other model sentence
    on this screen.
    """
    step = next(
        (
            s
            for s in reversed(steps)
            if getattr(getattr(s, "kind", None), "value", str(getattr(s, "kind", ""))) == "proposal"
        ),
        None,
    )
    if step is None:
        return None
    payload = dict(getattr(step, "payload", {}) or {})
    body = dict(payload.get("proposal") or {})
    if not body:
        return None
    return {
        "action_id": str(body.get("action_id") or ""),
        "target": str(body.get("target") or ""),
        "remediation_class": str(body.get("remediation_class") or ""),
        "confirm_within_seconds": body.get("confirm_within_seconds"),
        "accepted": bool(payload.get("accepted", False)),
        "violations": [str(v) for v in payload.get("violations") or []],
        "escalated": bool(payload.get("escalated", False)),
        "execution": EXECUTION_NOTE,
        "cites": [c.as_dict() for c in citations(list(body.get("rests_on") or []), calls)],
        "untrusted": {
            "expected_effect": str(body.get("expected_effect") or ""),
            "if_wrong": str(body.get("if_wrong") or ""),
            "risk": str(body.get("risk") or ""),
            "blast_radius": str(body.get("blast_radius") or ""),
        },
    }
