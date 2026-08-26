"""The dispatch loop: planner, specialists, budget, trajectory (T3.3, ADR-0020).

Everything the roles do lands in the trajectory as it happens, because the record is T4.2's
scoring input and T5.3's replay source and both need the run rather than a summary of it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from faultline.agents.budget import Budget, BudgetState
from faultline.agents.contracts import DispatchPlan, SpecialistFindings, SpecialistName
from faultline.agents.model import LanguageModel
from faultline.agents.roles import Planner, Specialist, SpecialistRun, default_window
from faultline.agents.trajectory import (
    RetrievalRecord,
    StepKind,
    ToolCallRecord,
    Trajectory,
    TrajectoryStep,
    TrajectoryStore,
)
from faultline.agents.triage import TriageResult
from faultline.tools import envelope as envelope_renderer


@dataclass(slots=True)
class InvestigationResult:
    trajectory: Trajectory
    plans: list[DispatchPlan] = field(default_factory=list)
    runs: list[SpecialistRun] = field(default_factory=list)
    budget_exhausted: bool = False
    exhausted_reason: str | None = None

    @property
    def findings(self) -> dict[str, SpecialistFindings]:
        return {run.specialist: run.findings for run in self.runs}

    def summary(self) -> str:
        flag = f" BUDGET EXHAUSTED ({self.exhausted_reason})" if self.budget_exhausted else ""
        return (
            f"{len(self.plans)} round(s), {len(self.runs)} dispatch(es), "
            f"{self.trajectory.steps[-1].seq if self.trajectory.steps else 0} step(s){flag}"
        )


class Investigation:
    """One incident, one trajectory, at most two dispatch rounds."""

    def __init__(
        self,
        planner: Planner,
        specialists: dict[SpecialistName, Specialist],
        store: TrajectoryStore,
        model: LanguageModel,
        budget: Budget,
        role_models: dict[str, str] | None = None,
        effort: str = "medium",
    ) -> None:
        self._planner = planner
        self._specialists = specialists
        self._store = store
        self._model = model
        self._budget = budget
        self._role_models = role_models or {}
        self._effort = effort

    def run(self, incident_id: str, triage: TriageResult, anchor: datetime) -> InvestigationResult:
        trajectory = Trajectory(
            incident_id=incident_id,
            model=self._model.name,
            effort=self._effort,
            started_at=datetime.now(UTC),
            role_models=dict(self._role_models),
            runtime_version="t3.3",
        )
        state = BudgetState(self._budget)
        result = InvestigationResult(trajectory=trajectory)
        seq = 0

        while state.start_round():
            findings = result.findings if result.runs else None
            completion = self._planner.plan(triage, findings)
            state.spend_tokens(completion.response.input_tokens, completion.response.output_tokens)
            seq += 1
            trajectory.add(
                TrajectoryStep(
                    seq=seq,
                    role=Planner.ROLE,
                    kind=StepKind.COMPLETION,
                    at=datetime.now(UTC),
                    tokens_in=completion.response.input_tokens,
                    tokens_out=completion.response.output_tokens,
                    payload={
                        "round": state.rounds,
                        "attempts": completion.attempts,
                        "plan": completion.value.model_dump(),
                    },
                )
            )
            plan: DispatchPlan = completion.value
            result.plans.append(plan)

            for dispatch in plan.dispatches:
                if not state.may_call_tool(dispatch.specialist):
                    break
                seq += 1
                self._dispatch(trajectory, state, result, dispatch, anchor, seq)
                seq += 1

            if state.exhausted or len(result.plans) >= self._budget.max_dispatch_rounds:
                break

        result.budget_exhausted = state.exhausted
        result.exhausted_reason = state.exhausted_reason
        trajectory.ended_at = datetime.now(UTC)
        trajectory.outcome = "budget_exhausted" if state.exhausted else "dispatched"
        trajectory.budget_exhausted = state.exhausted
        self._store.save(trajectory)
        return result

    def _dispatch(
        self,
        trajectory: Trajectory,
        state: BudgetState,
        result: InvestigationResult,
        dispatch: object,
        anchor: datetime,
        seq: int,
    ) -> None:
        name: SpecialistName = dispatch.specialist  # type: ignore[attr-defined]
        service: str = dispatch.service  # type: ignore[attr-defined]
        question: str = dispatch.question  # type: ignore[attr-defined]
        specialist = self._specialists[name]
        start, end = default_window(anchor)

        began = time.monotonic()
        tool_result = specialist.query(service, start, end)
        rendered = envelope_renderer.render(tool_result)
        state.record_tool_call(name)

        # The envelope goes into the trajectory verbatim, before anything reads it: a replay
        # that re-renders from the typed result is replaying a different prompt (ADR-0020 §3).
        trajectory.add(
            TrajectoryStep(
                seq=seq,
                role=name,
                kind=StepKind.TOOL_CALL,
                at=datetime.now(UTC),
                latency_ms=int((time.monotonic() - began) * 1000),
                payload={"question": question, "service": service},
                tool_call=ToolCallRecord(
                    tool=tool_result.tool,
                    request={"service": service, "window": [start.isoformat(), end.isoformat()]},
                    result_id=tool_result.id,
                    envelope=rendered,
                ),
            )
        )

        findings, response, attempts = specialist.run(service, question, start, end, rendered)
        state.spend_tokens(response.input_tokens, response.output_tokens)
        trajectory.add(
            TrajectoryStep(
                seq=seq + 1,
                role=name,
                kind=StepKind.COMPLETION,
                at=datetime.now(UTC),
                tokens_in=response.input_tokens,
                tokens_out=response.output_tokens,
                payload={
                    "attempts": attempts,
                    "result_id": tool_result.id,
                    "findings": findings.model_dump(),
                },
            )
        )
        result.runs.append(
            SpecialistRun(
                specialist=name,
                service=service,
                question=question,
                result=tool_result,
                envelope=rendered,
                findings=findings,
                response=response,
                attempts=attempts,
            )
        )


def record_retrieval(
    trajectory: Trajectory, seq: int, role: str, record: RetrievalRecord
) -> TrajectoryStep:
    """Attach a retrieval to the trajectory. `exclude_origin` is on the record, and T4.1b reads
    it from the column rather than from a log line (ADR-0008)."""
    return trajectory.add(
        TrajectoryStep(
            seq=seq,
            role=role,
            kind=StepKind.RETRIEVAL,
            at=datetime.now(UTC),
            retrieval=record,
        )
    )
