"""The dispatch loop: planner, specialists, budget, trajectory (T3.3, ADR-0020).

Everything the roles do lands in the trajectory as it happens, because the record is T4.2's
scoring input and T5.3's replay source and both need the run rather than a summary of it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from faultline.agents import grounding
from faultline.agents import narrative as narrative_renderer
from faultline.agents.budget import Budget, BudgetState
from faultline.agents.contracts import (
    DispatchPlan,
    NarrativeDraft,
    SpecialistName,
    Verdict,
)
from faultline.agents.model import LanguageModel
from faultline.agents.roles import (
    Planner,
    SchemaValidationError,
    Scribe,
    Specialist,
    SpecialistRun,
    Synthesizer,
    default_window,
)
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
    failed_dispatches: list[tuple[str, str]] = field(default_factory=list)
    """Specialists whose output did not validate twice. Reported, never silent."""

    verdict: Verdict | None = None
    draft: NarrativeDraft | None = None
    narrative: str | None = None
    narrative_error: str | None = None
    retrieved: list[str] = field(default_factory=list)
    exclude_origin: str | None = None

    @property
    def flags(self) -> list[str]:
        """Everything that makes this investigation incomplete. **The verdict must carry these.**

        ADR-0020 §5: exhaustion produces a flagged verdict rather than silence, and T4.2 must
        report flagged runs separately rather than pooling them. A specialist that failed alone
        is the same kind of incompleteness arriving by a different route.
        """
        flags: list[str] = []
        if self.budget_exhausted and self.exhausted_reason:
            flags.append(f"budget exhausted: {self.exhausted_reason}")
        flags += [
            f"{name} produced no valid findings: {why}" for name, why in self.failed_dispatches
        ]
        return flags + self.contradictions

    contradictions: list[str] = field(default_factory=list)
    """Verdict claims the trajectory refutes. **Flagged, never stripped** - see `grounding`."""

    def summary(self) -> str:
        flag = f" BUDGET EXHAUSTED ({self.exhausted_reason})" if self.budget_exhausted else ""
        if self.failed_dispatches:
            flag += f" {len(self.failed_dispatches)} failed dispatch(es)"
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
        synthesizer: Synthesizer | None = None,
        scribe: Scribe | None = None,
        corpus: Any = None,
        retrieval_k: int = 3,
    ) -> None:
        self._synthesizer = synthesizer
        self._scribe = scribe
        self._corpus = corpus
        self._retrieval_k = retrieval_k
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
            findings = result.runs or None
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

        seq = self._synthesise(trajectory, state, result, triage, incident_id, seq)

        # Persist before the scribe runs. Found on the first end-to-end run: the scribe cites
        # `result_id`s and the renderer resolves them against the store, so a trajectory still
        # only in memory makes every citation unresolvable - the guard fires correctly on
        # evidence that genuinely exists. Saving here is idempotent with the save below.
        self._store.save(trajectory)
        seq = self._scribe_record(trajectory, state, result, triage, seq)

        trajectory.ended_at = datetime.now(UTC)
        trajectory.outcome = "budget_exhausted" if state.exhausted else "dispatched"
        trajectory.budget_exhausted = state.exhausted
        self._store.save(trajectory)
        return result

    def _synthesise(
        self,
        trajectory: Trajectory,
        state: BudgetState,
        result: InvestigationResult,
        triage: TriageResult,
        incident_id: str,
        seq: int,
    ) -> int:
        """Retrieve, then conclude. **The first live consumer of `exclude_origin`.**"""
        if self._synthesizer is None:
            return seq

        exclude = self._exclusion_for(incident_id)
        result.exclude_origin = exclude
        if self._corpus is not None:
            query = self._retrieval_query(triage, result)
            hits = self._corpus.search(query, k=self._retrieval_k, exclude_origin=exclude)
            result.retrieved = [
                f"{hit.chunk.scenario_id} / {hit.chunk.section}: {hit.chunk.text[:280]}"
                for hit in hits
            ]
            seq += 1
            record_retrieval(
                trajectory,
                seq,
                Synthesizer.ROLE,
                RetrievalRecord(
                    query=query,
                    k=self._retrieval_k,
                    exclude_origin=exclude,
                    returned=[hit.chunk.document_id for hit in hits],
                    scores=[hit.score for hit in hits],
                ),
            )

        try:
            completion = self._synthesizer.synthesise(
                triage, result.runs, result.retrieved, result.flags
            )
        except SchemaValidationError as failure:
            state.spend_tokens(failure.response.input_tokens, failure.response.output_tokens)
            result.failed_dispatches.append((Synthesizer.ROLE, str(failure)))
            return seq
        state.spend_tokens(completion.response.input_tokens, completion.response.output_tokens)
        result.verdict = completion.value
        # Before the step is written, so the recorded flags are the ones the verdict carries.
        result.contradictions = grounding.contradictions(
            [
                completion.value.root_cause,
                completion.value.reasoning,
                *completion.value.open_questions,
            ],
            result.runs,
        )
        seq += 1
        trajectory.add(
            TrajectoryStep(
                seq=seq,
                role=Synthesizer.ROLE,
                kind=StepKind.VERDICT,
                at=datetime.now(UTC),
                tokens_in=completion.response.input_tokens,
                tokens_out=completion.response.output_tokens,
                payload={
                    "attempts": completion.attempts,
                    "verdict": completion.value.model_dump(),
                    "flags": result.flags,
                    "exclude_origin": exclude,
                },
            )
        )
        return seq

    def _scribe_record(
        self,
        trajectory: Trajectory,
        state: BudgetState,
        result: InvestigationResult,
        triage: TriageResult,
        seq: int,
    ) -> int:
        if self._scribe is None or result.verdict is None:
            return seq
        try:
            completion = self._scribe.draft(triage, result.runs, result.verdict)
        except SchemaValidationError as failure:
            state.spend_tokens(failure.response.input_tokens, failure.response.output_tokens)
            result.failed_dispatches.append((Scribe.ROLE, str(failure)))
            return seq
        state.spend_tokens(completion.response.input_tokens, completion.response.output_tokens)
        result.draft = completion.value
        try:
            result.narrative = narrative_renderer.render(completion.value, self._store)
        except (
            narrative_renderer.UnknownCitationError,
            narrative_renderer.NarrativeLeakError,
        ) as exc:
            # A refused render is a finding, not a crash: the draft is kept so the failure can
            # be read, and the investigation still has its verdict.
            result.narrative_error = str(exc)
        seq += 1
        trajectory.add(
            TrajectoryStep(
                seq=seq,
                role=Scribe.ROLE,
                kind=StepKind.MESSAGE,
                at=datetime.now(UTC),
                tokens_in=completion.response.input_tokens,
                tokens_out=completion.response.output_tokens,
                payload={
                    "attempts": completion.attempts,
                    "draft": completion.value.model_dump(),
                    "rendered": result.narrative is not None,
                    "render_error": result.narrative_error,
                },
            )
        )
        return seq

    @staticmethod
    def _exclusion_for(incident_id: str) -> str | None:
        """`None` in production; the scenario under test on a scored run (ADR-0008, axis 2).

        **Marked decision.** ADR-0020 requires every benchmark retrieval to pass one and does not
        say who supplies it. Here the caller sets `FAULTLINE_EVAL_SCENARIO` when a run is scored,
        because the *harness* knows which scenario is under test and the product does not - an
        investigation cannot infer that it is being examined, and one that could would be a worse
        design than one that cannot.
        """
        import os

        origin = os.environ.get("FAULTLINE_EVAL_SCENARIO", "").strip()
        return f"scenario:{origin}" if origin else None

    @staticmethod
    def _retrieval_query(triage: TriageResult, result: InvestigationResult) -> str:
        found = [f.statement for run in result.runs for f in run.findings.found][:4]
        services = ", ".join(m.service for m in triage.alerting)
        return f"{services}. " + " ".join(found)

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

        try:
            findings, response, attempts = specialist.run(service, question, start, end, rendered)
        except SchemaValidationError as failure:
            # One specialist's failure, not the investigation's. Recorded as a step so it is
            # visible to scoring rather than merely absent, and the other dispatches continue.
            state.spend_tokens(failure.response.input_tokens, failure.response.output_tokens)
            result.failed_dispatches.append((name, str(failure)))
            trajectory.add(
                TrajectoryStep(
                    seq=seq + 1,
                    role=name,
                    kind=StepKind.COMPLETION,
                    at=datetime.now(UTC),
                    tokens_in=failure.response.input_tokens,
                    tokens_out=failure.response.output_tokens,
                    payload={
                        "attempts": 2,
                        "result_id": tool_result.id,
                        "schema_failure": str(failure),
                        "stop_reason": failure.response.stop_reason,
                    },
                )
            )
            return
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
