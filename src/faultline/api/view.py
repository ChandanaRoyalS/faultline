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
from typing import Any
from urllib.parse import quote

GRAFANA_EXPLORE = "/explore"
"""Grafana's explore path. Relative, so the deep link works against whatever host serves Grafana
in the reader's environment - the platform does not know its own public URL and guessing one is
how a demo link 404s on a stranger's machine (T5.4's whole point)."""

DATASOURCE_BY_TOOL = {
    "promql_query": "prometheus",
    "metric_baseline": "prometheus",
    "logql_query": "loki",
    "trace_query": "tempo",
}
"""Which datasource a tool's query belongs to. `change_history` is absent deliberately: it reads
the platform's own Postgres, has no datasource, and gets no link."""


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


def deep_link(tool: str, request: dict[str, Any]) -> str | None:
    """A Grafana explore URL for one stored tool call, or `None` when there is nothing to link to.

    Built from `request` as it was recorded. A query re-derived from the service and window would
    be a *plausible* query rather than the one that ran, and a link landing a reader in data the
    agent never saw manufactures corroboration - the opposite of what a citation is for.
    """
    datasource = DATASOURCE_BY_TOOL.get(tool)
    query = str(request.get("query") or request.get("selector") or "").strip()
    if not datasource or not query:
        return None
    window = request.get("window") or []
    left: dict[str, Any] = {"datasource": datasource, "queries": [{"expr": query}]}
    if len(window) == 2:
        left["range"] = {"from": window[0], "to": window[1]}
    return f"{GRAFANA_EXPLORE}?left={quote(json.dumps(left, separators=(',', ':')))}"


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
                query=str(request.get("query") or request.get("selector") or ""),
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
    }
