"""The pipeline as one callable unit (T3.5).

Everything T3.1-T3.4c built runs as a hand-assembled script in the evidence directories: build
a triage, build a model, build four specialists, build a corpus, run, print. That is fine for a
smoke and useless to T4, which needs to invoke an investigation the way T2's smokes invoke
ingest - as one command, over a store, with an exit code.

**This module owns the sequence and the state, not the reasoning.** `Investigation` still does
the reasoning; what is here is the part every evidence README kept doing by hand and the part
they kept noting was missing: refuse an incident the machine says is not investigable, drive the
agent-driven states as the phases complete, attach the trajectory to the incident row, and be
honest in the exit code about what the run actually produced.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from functools import partial
from pathlib import Path

from faultline.agents.contracts import TriageJudgement
from faultline.agents.investigation import (
    Investigation,
    InvestigationFailedError,
    InvestigationResult,
)
from faultline.agents.roles import SchemaValidationError, Triager
from faultline.agents.triage import TriageResult
from faultline.archive import Archive, report_key
from faultline.orchestrator import machine
from faultline.orchestrator.models import Incident, IncidentState
from faultline.orchestrator.store import IncidentStore


class Exit(IntEnum):
    """What the shell learns. **Four outcomes, because they are four different things.**

    A harness that cannot tell "diagnosed" from "diagnosed with half its budget missing" from
    "never got a verdict" will pool them, and ADR-0020 §5 exists to stop exactly that pooling.
    """

    CLEAN = 0
    """A verdict, with nothing flagged."""

    FLAGGED = 2
    """A verdict, flagged: budget exhausted, a specialist that failed alone, a contradiction.
    **Not an error.** The investigation ran and produced something scoreable; the flag is the
    finding. Distinct from 0 so a sweep can count them without parsing prose."""

    REFUSED = 3
    """Nothing ran. No such incident, or one in a state the machine does not investigate."""

    NO_VERDICT = 4
    """It ran and produced no verdict - the synthesizer failed, or the run raised. The
    trajectory is persisted up to the failure; the incident is `FAILED`."""

    GATED = 5
    """Triage declined it before any specialist ran (T3.1): noise, or a duplicate of an incident
    already open. **Not a failure and not a refusal.** The pipeline worked - the deliverable's
    second half is *"noise gated before fan-out"*, and a gate that never fires is not a gate.
    Distinct from `REFUSED` because something did run and made a judgement, and distinct from
    `NO_VERDICT` because no verdict was *owed*."""


class NotInvestigableError(RuntimeError):
    """Refused before any model call. Carries why, for the operator and the exit code."""


@dataclass(frozen=True, slots=True)
class RunReport:
    """What one CLI invocation did. Everything the transcript and the exit code need."""

    incident_id: str
    trajectory_id: str | None
    states: tuple[str, ...]
    """Every state the incident passed through, in order, starting from the one it was in."""

    result: InvestigationResult | None
    error: str | None = None
    judgement: TriageJudgement | None = None
    """What triage decided (T3.1). `None` when no `Triager` was configured, which is still a
    supported way to run: the gate is a role, not a requirement of the pipeline."""

    blast_radius: tuple[str, ...] = ()
    """Triage's predicted set, carried onto the artifact so the harness can score it without
    importing the product's triage (T4.1). ADR-0009 specifies the harness works through public
    interfaces, and a file the CLI wrote is one."""

    unmeasured_edges: int = 0

    @property
    def gated(self) -> bool:
        return self.judgement is not None and self.judgement.disposition != "investigate"

    @property
    def exit_code(self) -> Exit:
        if self.gated:
            return Exit.GATED
        if self.result is None or self.result.verdict is None:
            return Exit.NO_VERDICT
        return Exit.FLAGGED if self.result.flags else Exit.CLEAN


def investigable(store: IncidentStore, incident_id: str) -> Incident:
    """The incident, or a refusal naming the reason. **Checked before anything is spent.**"""
    incident = store.get(incident_id)
    if incident is None:
        raise NotInvestigableError(f"no incident {incident_id} in the store")
    if incident.state not in machine.INVESTIGABLE:
        legal = ", ".join(sorted(s.value for s in machine.INVESTIGABLE))
        terminal = (
            "A failed or resolved incident is terminal in ADR-0016's table. "
            if incident.is_terminal
            else ""
        )
        raise NotInvestigableError(
            f"incident {incident_id} is in state {incident.state.value}; the machine "
            f"investigates from {legal} only. {terminal}"
            "See ADR-0016 and faultline.orchestrator.machine.INVESTIGABLE."
        )
    return incident


def run_investigation(
    store: IncidentStore,
    incident: Incident,
    engine: Investigation,
    triage: TriageResult,
    anchor: datetime,
    triager: Triager | None = None,
) -> RunReport:
    """One investigation, with the incident's state moved to match what happened.

    The incident is saved after every transition rather than once at the end: a crash between
    two phases should leave the state it had actually reached, not the state it started in.

    With a `triager`, the judgement runs **first and alone** (T3.1): a `noise` or `duplicate`
    disposition ends the run before a planner is asked for anything, which is what the
    deliverable's *"noise gated before fan-out"* means and where the saving is. Without one,
    every incident handed here is investigated, which is what happened until T3.1.
    """
    states = [incident.state.value]
    radius = tuple(sorted(member.service for member in triage.blast_radius))
    edges = len(triage.unmeasured_edges)

    judgement: TriageJudgement | None = None
    if triager is not None:
        judgement = _judge(store, incident, triage, triager)
        if judgement is not None and judgement.disposition != "investigate":
            # **Nothing else runs.** The state the incident lands in is the one the machine
            # already had a transition for and no writer: `TRIAGING -> DUPLICATE_MERGED`, or
            # `TRIAGING -> RESOLVED` for noise.
            target = (
                IncidentState.DUPLICATE_MERGED
                if judgement.disposition == "duplicate"
                else IncidentState.RESOLVED
            )
            trigger = f"triage declined: {judgement.disposition} - {judgement.reasoning}"
            advance_gate(store, incident, states, target, trigger)
            return RunReport(incident.id, None, tuple(states), None, None, judgement, radius, edges)

    def advance(step: Callable[[], None]) -> None:
        step()
        states.append(incident.state.value)
        # **Narrow write.** `save` upserts episodes from this in-memory copy, which was loaded
        # before the investigation started - so writing it back overwrote `resolved_at` on
        # episodes the orchestrator had resolved meanwhile. T4.5's sweep found it the hard way.
        store.save_investigation_state(incident)

    try:
        result = engine.run(incident.id, triage, anchor)
    except InvestigationFailedError as failure:
        why = str(failure)
        if not failure.started:
            # **Nothing ran, so nothing about the incident changed.** A missing dependency or an
            # unreachable database is a failed start, not a failed investigation, and marking it
            # `FAILED` would retire a live incident permanently - ADR-0016 makes `FAILED`
            # terminal and `INVESTIGABLE` is `{TRIAGING}`. T3.5's own smoke did exactly this,
            # once, with a `ModuleNotFoundError`.
            return RunReport(
                incident.id,
                None,
                tuple(states),
                None,
                f"did not start - {why}",
                judgement,
                radius,
                edges,
            )
        advance(
            partial(
                machine.record_investigation_failure, incident, failure.cause.__class__.__name__
            )
        )
        return RunReport(
            incident.id, failure.trajectory.id, tuple(states), None, why, judgement, radius, edges
        )

    incident.investigation_id = result.trajectory.id
    # **What the result evidences, decided in one place** (`machine.phases_for`) and walked
    # here so the incident is persisted after each transition rather than once at the end.
    for state, trigger in machine.phases_for(result):
        advance(partial(machine.transition, incident, state, trigger=trigger))
    if result.verdict is None:
        advance(lambda: machine.record_investigation_failure(incident, "no verdict was produced"))

    return RunReport(
        incident.id, result.trajectory.id, tuple(states), result, None, judgement, radius, edges
    )


def write_outputs(report: RunReport, out: Path, archive: Archive | None = None) -> list[Path]:
    """The verdict and the narrative, as files. **Machine-readable and human-readable both.**

    T4.2 reads the JSON; a responder reads the markdown. Writing only one of them would make
    the other a parsing exercise.

    With an `archive`, the rendered narrative also goes to object storage - the *rendered
    reports* half of T2.3's deliverable, beside the evidence envelopes the trajectory store
    writes. The file and the object are the same bytes; the file is where a person looks
    today and the object is what survives the directory being cleaned up.
    """
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    result = report.result
    if result is None:
        return written

    verdict = out / f"{report.incident_id}-verdict.json"
    verdict.write_text(
        json.dumps(
            {
                "incident_id": report.incident_id,
                "trajectory_id": report.trajectory_id,
                "states": list(report.states),
                "blast_radius": list(report.blast_radius),
                "unmeasured_edges": report.unmeasured_edges,
                "exclude_origin": result.exclude_origin,
                "verdict": None if result.verdict is None else result.verdict.model_dump(),
                "flags": result.flags,
                "retrieved": result.retrieved,
                "failed_dispatches": [list(pair) for pair in result.failed_dispatches],
                "narrative_error": result.narrative_error,
            },
            indent=2,
        )
        + "\n"
    )
    written.append(verdict)

    if result.narrative is not None:
        narrative = out / f"{report.incident_id}-narrative.md"
        body = result.narrative + "\n"
        narrative.write_text(body)
        written.append(narrative)
        if archive is not None:
            # Keyed by the trajectory rather than the incident: an incident can be
            # investigated more than once, and keying by incident would have the second
            # report silently overwrite the first. The incident id is the fallback for a run
            # that failed before it had a trajectory to name.
            archive.put(
                report_key(report.trajectory_id or report.incident_id),
                body.encode(),
                content_type="text/markdown; charset=utf-8",
            )
    return written


def advance_gate(
    store: IncidentStore,
    incident: Incident,
    states: list[str],
    target: IncidentState,
    trigger: str,
) -> None:
    """Move a gated incident and persist it, recording the state it reached (T3.1)."""
    machine.transition(incident, target, trigger=trigger)
    states.append(incident.state.value)
    store.save_investigation_state(incident)


def _judge(
    store: IncidentStore, incident: Incident, triage: TriageResult, triager: Triager
) -> TriageJudgement | None:
    """Triage's judgement, or `None` if it would not validate twice.

    **A triage that fails is not a gate that closes.** A schema failure here means the model
    could not answer, and declining an incident because the cheapest role in the pipeline
    malfunctioned would turn a model outage into silent under-investigation - the failure mode
    ADR-0031 built the fallback for. So the investigation proceeds, and the absent judgement is
    visible in the report rather than being read as a decision.
    """
    open_incidents = [
        (
            other.id,
            f"{other.opened_at:%H:%M:%S}" if other.opened_at else "unknown",
            ", ".join(sorted({e.service for e in other.episodes.values() if e.service})),
        )
        for other in store.correlation_candidates(datetime.now(UTC))
        if other.id != incident.id and not other.is_terminal
    ]
    try:
        judgement: TriageJudgement = triager.judge(triage, open_incidents).value
    except SchemaValidationError:
        return None
    return judgement
