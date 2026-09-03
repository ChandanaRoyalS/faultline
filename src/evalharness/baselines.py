"""B0 — the no-LLM heuristic baseline (T4.7).

The plan's T4.7 names three permanent baselines *"scored by the same judge, at the same R, on the
same catalog, appearing in every headline table"*. **B0** is the first: *"a no-LLM heuristic
(alert-label attribution + most-recent deploy in window + largest error-rate delta → top-1)"*.

Its purpose is not to be good. It is to answer the sharpest question a reader can ask about an
agent system - *how much of this accuracy needed an agent?* - and to answer it with a number
rather than an assurance. A pipeline that beats B0 by a little has a much weaker claim than one
that beats it by a lot, and a pipeline that loses to it has an answer nobody wants and everybody
should want to know.

## The three signals, in the plan's own order

1. **Alert-label attribution.** Which services alerted, earliest first. It scopes which services
   are looked at at all - a change on a service that never alerted is not this incident.
2. **Most-recent change in the window.** The most recent pre-onset change on any alerting
   service, from the same change log the change analyst reads. **This is the primary signal**: it
   names the culprit and the class together.
3. **Largest error-rate delta.** Which alerting service moved furthest from its baseline. Used
   when there is no change to point at, and to break ties between simultaneous changes.

## The rules, stated so they can be argued with

**The most recent pre-onset change in the window names the culprit**, whatever service it is on.
Where there is no such change, the culprit is the alerting service with the largest error-rate
delta, and where no error ratio is available - which is common, `cartservice` has no `calls_total`
series at all - the earliest alerting service.

**This ordering is the correction of a v1 defect, and it is recorded rather than quietly fixed.**
v1 chose the culprit *first*, from alerts alone, and then looked for changes **on that service**.
The plan says *"most-recent deploy **in window**"*, not *on the suspect*, and the narrowing was
mine. Its first live run showed what the narrowing costs: on `ad-memory-squeeze` v1 picked
`frontend` - the earliest alerting service, which is the **propagator** - found no change on it,
fell to the residual, and answered `dependency_latency` against a truth of `resource_exhaustion`.
The `adservice` memory-limit change that caused the incident was in the window and was never
looked at.

**Two further v1 defects, found while making that correction**, both in `signals_from_tools` and
both invisible in the only run v1 ever made:

- it read `ChangeResult.records` rows as objects (`record.service`, `record.at`), and they are
  dicts carrying no `service` key at all. That raises `AttributeError` the first time a change is
  found - which never happened, because v1 asked only `frontend` and `frontend` had no changes.
  See `changes_in`.
- it read `result.points` from a `MetricResult`, which has `series`, each with its own `points`.
  So `error_deltas` was **always empty** and B0 always took the no-error-series fallback. The live
  run's *"no error-ratio series available"* was not a fact about `frontend`; it was that line.
  See `error_delta`.

Signal 3 therefore never ran in v1 at all, and signal 2 could not have. What was measured on
`ad-memory-squeeze` was signal 1 alone.

**On the propriety of changing a baseline after seeing it fail.** The misreading is visible in the
plan's own words without any run, and the correction makes B0 more faithful rather than more
accurate-on-this-catalog - but it was **noticed** because of a failure, and pretending otherwise
would be the exact dishonesty a baseline exists to prevent. So: the v1 run stays in the record,
wrong; the version marker moves so v1 and v2 can never be pooled; and this paragraph is why.

**Fault class** comes from that change, by resource:

| resource that changed | class |
|---|---|
| `image` | `bad_deploy` |
| `resource_limits` | `resource_exhaustion` |
| `environment`, `config` | `bad_config` |
| *nothing changed* | `dependency_latency` |

The last row is the residual and is the whole trick: `dependency_latency` is the one class in
this catalog with **no change signature**, because a network delay injected with `pumba` touches
no configuration. So "nothing changed" is a positive prediction rather than an absence, and a
reader should notice that this is a fact about the injector rather than about incidents.

**Remediation class** is a table lookup from the fault class, and this is the finding B0 exists
to surface:

| fault class | remediation | scenarios |
|---|---|---|
| `bad_config` | `config_revert` | 5 |
| `bad_deploy` | `rollback` | 5 |
| `dependency_latency` | `restart` | 4 |
| `resource_exhaustion` | `config_revert` | 4 |

**Across all eighteen catalog scenarios that mapping is one-to-one.** So the remediation axis
carries no information independent of the fault class: any predictor that gets the class right
gets remediation free, and B0 demonstrates that with a `dict`. That is a measurement about the
benchmark, not about B0 - it means the two scored axes are not two measurements, and a headline
reporting both as if they were is double-counting one result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

BASELINE_ID = "B0"

BASELINE_VERSION = "2"
"""**A baseline that changes silently is not a baseline.**

v1 is every run stamped `faultline/0.0.1+baseline:B0` with no version - one run,
`20260903T031137Z-ad-memory-squeeze`, which answered `dependency_latency` against a truth of
`resource_exhaustion`. It is kept, wrong, and must never be pooled with a v2 run. The version is
in the runtime string, so the eval database separates them without anyone remembering to.
"""

DESCRIPTION = "no-LLM heuristic: alert attribution + most-recent change + largest error delta"

RESOURCE_TO_CLASS: dict[str, str] = {
    "image": "bad_deploy",
    "resource_limits": "resource_exhaustion",
    "environment": "bad_config",
    "config": "bad_config",
    "container": "bad_deploy",
}
"""What a changed resource implies about the fault class. Operational vocabulary in, fault
vocabulary out - the mapping the change analyst's prompt asks a model to make, made by a table."""

NO_CHANGE_CLASS = "dependency_latency"
"""The residual, and the rule that makes B0 more than a coin flip.

`dependency_latency` is the one class in this catalog injected without touching configuration -
`pumba` adds delay to an interface and leaves no change record. So an incident with alerts and no
recent change is, in this world, a latency fault. **This is a fact about the injector**, and a
baseline that exploits it is showing the reader something true about the benchmark rather than
something true about incident response."""

CLASS_TO_REMEDIATION: dict[str, str] = {
    "bad_config": "config_revert",
    "bad_deploy": "rollback",
    "dependency_latency": "restart",
    "resource_exhaustion": "config_revert",
}
"""One-to-one across all eighteen scenarios. See the module docstring: the remediation axis adds
no information the fault class does not already carry."""


@dataclass(frozen=True, slots=True)
class Change:
    """One change record, as B0 needs it."""

    service: str
    at: datetime
    resource: str


@dataclass(frozen=True, slots=True)
class Signals:
    """Everything B0 is allowed to see. **No model, no narrative, no evidence board.**"""

    alerting: list[str] = field(default_factory=list)
    """Services that alerted, earliest first."""

    changes: list[Change] = field(default_factory=list)
    error_deltas: dict[str, float] = field(default_factory=dict)
    """Service to its error-ratio delta against baseline. Frequently empty, and that is real:
    several services in this world publish no `calls_total` series."""


@dataclass(frozen=True, slots=True)
class Prediction:
    """B0's top-1, and the reasoning that produced it."""

    service: str | None
    fault_class: str | None
    fix_class: str | None
    why: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, object]:
        return {
            "baseline": BASELINE_ID,
            "service": self.service,
            "fault_class": self.fault_class,
            "fix_class": self.fix_class,
            "why": list(self.why),
        }


def latest_change(signals: Signals, onset: datetime) -> Change | None:
    """The most recent pre-onset change on any **alerting** service. The primary signal.

    Alert-label attribution scopes it: a change on a service that never alerted is not this
    incident, however recent. Ties on timestamp break on the larger error-rate delta, which is
    the only use signal 3 has when a change is present.
    """
    alerting = set(signals.alerting)
    candidates = [c for c in signals.changes if c.service in alerting and c.at <= onset]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c.at, signals.error_deltas.get(c.service, 0.0)))


def fallback_culprit(signals: Signals) -> tuple[str | None, str]:
    """The suspect when no change points at one. Signal 3, then signal 1."""
    scored = {
        service: delta
        for service, delta in signals.error_deltas.items()
        if service in set(signals.alerting)
    }
    if scored:
        best = max(scored, key=lambda service: scored[service])
        return best, f"largest error-rate delta among alerting services ({scored[best]:+.3f})"
    if signals.alerting:
        return signals.alerting[0], "earliest alerting service (no error-ratio series available)"
    return None, "nothing alerted"


def predict(signals: Signals, onset: datetime) -> Prediction:
    """B0's whole investigation. No model call, no tool budget, no context window.

    **The change comes first.** v1 chose a suspect from alerts and then looked for changes on it,
    which is not what the plan says and cost it the first scenario it ever ran - see the module
    docstring. Here the most recent pre-onset change in the window names the culprit and the
    class together, and the alert signals are the fallback for when there is no change to point
    at, which in this catalog means `dependency_latency`.
    """
    change = latest_change(signals, onset)
    fault_class: str | None
    service: str | None
    if change is not None:
        fault_class = RESOURCE_TO_CLASS.get(change.resource)
        service_why = (
            f"service of the most recent pre-onset change in the window ({change.at:%H:%M:%S})"
        )
        class_why = (
            f"that change was to {change.resource}"
            if fault_class
            else f"that change was to {change.resource!r}, which maps to no class"
        )
        service = change.service
    else:
        service, service_why = fallback_culprit(signals)
        # Deliberately a prediction rather than an abstention. See NO_CHANGE_CLASS.
        fault_class = NO_CHANGE_CLASS if service else None
        class_why = (
            "no change on any alerting service before onset"
            if service
            else "no suspect, so no class"
        )

    fix_class = CLASS_TO_REMEDIATION.get(fault_class) if fault_class else None
    return Prediction(
        service=service,
        fault_class=fault_class,
        fix_class=fix_class,
        why=[
            f"suspect: {service_why}",
            f"class: {class_why}",
            (
                f"remediation: table lookup from {fault_class}"
                if fix_class
                else "remediation: no class, so none"
            ),
        ],
    )


# --- B0 as a run under the standard harness ------------------------------------------------

BASELINE_RUNTIME = f"faultline/0.0.1+baseline:B0.{BASELINE_VERSION}"
"""**Deliberately not the agent's stamp.**

`runtime_version` is a digest over every role system prompt and every contract schema, and B0
uses none of them - so stamping it with the agent's digest would put B0's runs in the same
comparability generation as the pipeline it is a control for, which is precisely the comparison
it exists to make possible. A distinct runtime keeps them separable in `eval_runs` and makes the
config fingerprint differ for the right reason.

It also never moves. B0 is a fixed rule: if it changes, it is a different baseline and gets a
different name, because a baseline that drifts is not a baseline.
"""


class Window(Protocol):
    """The scoped window B0 reads, derived by the same `WindowPolicy` the agent's tools enforce.

    Read-only members, because the window B0 is handed is a frozen `ScopedWindow` and a protocol
    declaring them settable would refuse the very type this is meant to accept.
    """

    @property
    def start(self) -> datetime: ...

    @property
    def end(self) -> datetime: ...


class ToolLayer(Protocol):
    """The two tools B0 is allowed. **Narrower than the agent's by design** - a baseline with the
    same reach as the system it controls for measures nothing."""

    def change_history(self, service: str, start: datetime, end: datetime) -> Any: ...

    def promql_query(self, query: str, start: datetime, end: datetime) -> Any: ...


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One read B0 made, in the shape the trajectory records.

    **Recorded as a real tool call, with its envelope.** v1 wrote `TOOL_CALL` steps carrying no
    `ToolCallRecord`, so nothing reached `trajectory_tool_calls` and the metric panel reported
    *0 tool calls* beside *2 steps* - two true statements that together read as a defect. B0 does
    make tool calls; they belong in the table the panel reads.
    """

    tool: str
    request: dict[str, Any]
    envelope: str
    result_id: str


def changes_in(history: Any, service: str) -> list[Change]:
    """Read `ChangeResult.records` as what it is: **a list of rows, not of objects.**

    v1 wrote `record.service` / `record.at` / `record.resource` against dicts whose keys are
    `at`, `actor`, `resource`, `action`, `summary` - and which carry no `service` at all, because
    the service is a property of the query rather than of the row. That code raises
    `AttributeError` the first time a change is found, and it never was: v1's only live run asked
    `frontend`, which had no changes in the window. A defect that only fires on the path v2 makes
    primary.

    `at` arrives as an ISO string from `ChangeRecord.as_row`. A naive one is read as UTC, which is
    what the injector writes; guessing local time here would silently shift a change across onset.
    """
    rows = getattr(history, "records", []) or []
    canonical = str(getattr(history, "service", service) or service)
    changes: list[Change] = []
    for row in rows:
        raw = row.get("at") if isinstance(row, dict) else None
        if raw is None:
            continue
        at = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        changes.append(Change(service=canonical, at=at, resource=str(row.get("resource", ""))))
    return changes


def error_delta(result: Any) -> float | None:
    """The largest within-window rise in error ratio across the returned series.

    v1 read `result.points`, which `MetricResult` does not have - it has `series`, each with its
    own `points`. So `error_deltas` was **always empty** and B0 always took the
    no-error-series fallback. The live run's *"no error-ratio series available"* was therefore not
    a fact about `frontend`; it was this line.

    The delta is the window's peak against its own first sample. B0 has no baseline window of its
    own, and inventing one would hand it a signal the plan did not give it.
    """
    best: float | None = None
    for series in getattr(result, "series", []) or []:
        values = [value for _, value in getattr(series, "points", []) if value == value]
        if not values:
            continue
        rise = max(values) - values[0]
        best = rise if best is None else max(best, rise)
    return best


def signals_from_tools(
    tools: ToolLayer, alerting: list[str], onset: datetime, window: Window
) -> tuple[Signals, list[ToolCall]]:
    """Read B0's three signals through the same tool layer the agent uses.

    **The same tools, deliberately.** A baseline reading the database directly would be measuring
    a different world than the agent sees - different windows, different caps, different
    refusals - and the comparison would silently be between two observation regimes rather than
    between two methods.
    """
    from faultline.tools.envelope import render
    from faultline.tools.metrics import MetricTemplate, render_query

    changes: list[Change] = []
    deltas: dict[str, float] = {}
    calls: list[ToolCall] = []
    window_row = {"window": [window.start.isoformat(), window.end.isoformat()]}
    for service in alerting:
        history = tools.change_history(service, window.start, window.end)
        changes += changes_in(history, service)
        calls.append(
            ToolCall(
                tool="change_history",
                request={"service": service, **window_row},
                envelope=render(history),
                result_id=history.id,
            )
        )

        query = render_query(MetricTemplate.ERROR_RATIO, service)
        result = tools.promql_query(query, window.start, window.end)
        delta = error_delta(result)
        if delta is not None:
            deltas[service] = delta
        calls.append(
            ToolCall(
                tool="promql_query",
                request={"service": service, "query": query, **window_row},
                envelope=render(result),
                result_id=result.id,
            )
        )
    return Signals(alerting=list(alerting), changes=changes, error_deltas=deltas), calls


def artifact(
    incident_id: str,
    trajectory_id: str,
    blast_radius: list[str],
    unmeasured_edges: int,
    exclude_origin: str | None,
    prediction: Prediction,
) -> dict[str, object]:
    """The verdict artifact, in exactly the shape `evalharness.run.score` reads.

    B0 is scored by the same code path as the agent - not by a parallel scorer - because a
    baseline scored differently is not a baseline. The fields the agent fills and B0 cannot
    (`retrieved`, `disclosure`, `proposal`) are empty rather than absent, so a reader diffing two
    artifacts sees which parts of the pipeline B0 does not have.
    """
    return {
        "incident_id": incident_id,
        "trajectory_id": trajectory_id,
        "states": ["triaging"],
        "blast_radius": list(blast_radius),
        "unmeasured_edges": unmeasured_edges,
        "exclude_origin": exclude_origin,
        "verdict": {
            "fault_class": prediction.fault_class,
            "remediation_class": prediction.fix_class,
            "summary": "; ".join(prediction.why),
            "confidence": "n/a - B0 is a rule, not an estimate",
        },
        "flags": [],
        "retrieved": [],
        "failed_dispatches": [],
        "narrative_error": None,
        "disclosure": {},
        "proposal": None,
        "triage_judgement": None,
        "baseline": prediction.as_row(),
    }
