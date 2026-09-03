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

1. **Alert-label attribution.** Which services alerted, earliest first. The cheapest signal
   there is, and the one a human on-call reads before anything else.
2. **Most-recent change in the window.** What changed on the suspect, most recent first, from the
   same change log the change analyst reads.
3. **Largest error-rate delta.** Which alerting service moved furthest from its baseline.

## The rules, stated so they can be argued with

**Culprit** is the alerting service with the largest error-rate delta; where no error ratio is
available - which is common, `cartservice` has no `calls_total` series at all - it falls back to
the earliest alerting service. That fallback is doing more work than it looks like it should, and
it is exactly the kind of thing a baseline is for: if B0 is competitive, the reason is worth
knowing.

**Fault class** comes from the most recent change on the culprit before onset, by resource:

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
from datetime import datetime
from typing import Any, Protocol

BASELINE_ID = "B0"
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


def culprit(signals: Signals) -> tuple[str | None, str]:
    """The suspect service, and which signal chose it."""
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


def classify(signals: Signals, service: str | None, onset: datetime) -> tuple[str | None, str]:
    """The fault class, from the most recent pre-onset change on the suspect."""
    if service is None:
        return None, "no suspect, so no class"
    candidates = [c for c in signals.changes if c.service == service and c.at <= onset]
    if not candidates:
        # Deliberately a prediction rather than an abstention. See NO_CHANGE_CLASS.
        return NO_CHANGE_CLASS, "no change on the suspect before onset"
    latest = max(candidates, key=lambda c: c.at)
    predicted = RESOURCE_TO_CLASS.get(latest.resource)
    if predicted is None:
        return None, f"most recent change was {latest.resource!r}, which maps to no class"
    return predicted, f"most recent change on {service} was to {latest.resource}"


def predict(signals: Signals, onset: datetime) -> Prediction:
    """B0's whole investigation. No model call, no tool budget, no context window."""
    service, service_why = culprit(signals)
    fault_class, class_why = classify(signals, service, onset)
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

BASELINE_RUNTIME = "faultline/0.0.1+baseline:B0"
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


def signals_from_tools(
    tools: ToolLayer, alerting: list[str], onset: datetime, window: Window
) -> Signals:
    """Read B0's three signals through the same tool layer the agent uses.

    **The same tools, deliberately.** A baseline reading the database directly would be measuring
    a different world than the agent sees - different windows, different caps, different
    refusals - and the comparison would silently be between two observation regimes rather than
    between two methods.
    """
    from faultline.tools.metrics import MetricTemplate, render_query

    changes: list[Change] = []
    deltas: dict[str, float] = {}
    for service in alerting:
        history = tools.change_history(service, window.start, window.end)
        changes += [
            Change(service=record.service, at=record.at, resource=str(record.resource))
            for record in getattr(history, "records", [])
        ]
        result = tools.promql_query(
            render_query(MetricTemplate.ERROR_RATIO, service), window.start, window.end
        )
        points = [value for _, value in getattr(result, "points", []) if value == value]
        if points:
            # The delta is the window's peak against its own first sample: B0 has no baseline
            # window of its own, and inventing one would give it a signal the plan did not.
            deltas[service] = max(points) - points[0]
    return Signals(alerting=list(alerting), changes=changes, error_deltas=deltas)


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
