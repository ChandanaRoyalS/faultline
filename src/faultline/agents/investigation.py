"""The dispatch loop: planner, specialists, budget, trajectory (T3.3, ADR-0020).

Everything the roles do lands in the trajectory as it happens, because the record is T4.2's
scoring input and T5.3's replay source and both need the run rather than a summary of it.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

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
)
from faultline.agents.stamp import runtime_version
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


class InvestigationFailedError(RuntimeError):
    """A run that raised, carrying what it had got to. **The distinction the runner needs.**

    A failure with steps behind it is a partial investigation: evidence exists, it is persisted,
    and the incident should record that an attempt happened. A failure with none is a failed
    *start* - a missing dependency, an unreachable database - and nothing about the incident has
    changed. Found at T3.5's smoke, where `ModuleNotFoundError` raised before the first model
    call and moved the incident to `FAILED`, which ADR-0016 makes terminal: one missing optional
    extra permanently retired a live incident that nothing had actually investigated.
    """

    def __init__(self, trajectory: Trajectory, cause: Exception) -> None:
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.trajectory = trajectory
        self.cause = cause

    @property
    def started(self) -> bool:
        """Whether any step was recorded before the failure."""
        return bool(self.trajectory.steps)


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
    citation_violations: list[str] = field(default_factory=list)
    """Every refusal the publication boundary issued for this run, in order (T3.8's
    violation metrics). Zero, one, or two: one means the regeneration succeeded, two means it
    did not and the narrative was escalated."""
    narrative_regenerated: bool = False
    narrative_escalated: bool = False
    """Refused twice. The plan's "then page a human": this system has no pager, so the
    escalation is a flag on the verdict, a warning in the log, and a field in the trajectory -
    all three of which T4.2 and T4.3 read."""
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
        if self.narrative_escalated:
            flags.append(
                f"narrative escalated to human review after {len(self.citation_violations)} "
                "refused render(s)"
            )
        return flags + self.contradictions

    contradictions: list[str] = field(default_factory=list)
    """**Always empty since T4.3.** The contradiction checker is retired; see
    `faultline.agents.grounding` and ADR-0021's addendum.

    The field stays so runs recorded before the retirement still load, and so the category keeps
    printing at zero in a scored report rather than vanishing - a category that disappears takes
    its history with it."""

    def summary(self) -> str:
        flag = f" BUDGET EXHAUSTED ({self.exhausted_reason})" if self.budget_exhausted else ""
        if self.failed_dispatches:
            flag += f" {len(self.failed_dispatches)} failed dispatch(es)"
        return (
            f"{len(self.plans)} round(s), {len(self.runs)} dispatch(es), "
            f"{self.trajectory.steps[-1].seq if self.trajectory.steps else 0} step(s){flag}"
        )


@dataclass(slots=True)
class DispatchOutcome:
    """What one dispatch produced, before anything shared is touched (T3.5)."""

    steps: list[TrajectoryStep]
    run: SpecialistRun | None
    failure: tuple[str, str] | None
    tokens_in: int
    tokens_out: int


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

    def run(
        self,
        incident_id: str,
        triage: TriageResult,
        anchor: datetime,
        now: datetime | None = None,
    ) -> InvestigationResult:
        """Investigate one incident. `anchor` is alert onset; `now` is when the investigation
        began, defaulting to the clock. Every specialist window ends at `now` (T3.2b), so it is
        fixed once here and recorded as the trajectory's `started_at` rather than read per
        dispatch - a replay with the same two instants asks the same windows."""
        trajectory = Trajectory(
            incident_id=incident_id,
            model=self._model.name,
            effort=self._effort,
            started_at=now or datetime.now(UTC),
            role_models=dict(self._role_models),
            runtime_version=runtime_version(),
        )
        state = BudgetState(self._budget)
        result = InvestigationResult(trajectory=trajectory)
        try:
            return self._run(trajectory, state, result, incident_id, triage, anchor)
        except Exception as exc:
            # **The partial record survives the failure.** Found at T3.5: a run that died in the
            # synthesizer left nothing in the store at all, because the only saves were at the
            # end - so three specialists' worth of evidence went with the exception. The
            # trajectory is what T4.2 scores and T5.3 replays, and a crashed run is exactly the
            # one worth reading.
            #
            # A trajectory with no steps is not saved. Nothing ran, so there is nothing to
            # score, and an empty row would be indistinguishable from an investigation that
            # produced no evidence.
            if trajectory.steps:
                trajectory.ended_at = datetime.now(UTC)
                trajectory.outcome = "failed"
                self._store.save(trajectory)
            raise InvestigationFailedError(trajectory, exc) from exc

    def _run(
        self,
        trajectory: Trajectory,
        state: BudgetState,
        result: InvestigationResult,
        incident_id: str,
        triage: TriageResult,
        anchor: datetime,
    ) -> InvestigationResult:
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
            # Dispatches the planner named illegally and did not correct on its one re-ask.
            # Recorded as failures rather than dropped quietly, so they reach the verdict's
            # flags and T4.2's scoring alongside every other kind of incompleteness (T3.4c).
            result.failed_dispatches += [(Planner.ROLE, why) for why in completion.rejected]

            seq = self._fan_out(trajectory, state, result, plan.dispatches, anchor, seq)

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
                    # The same list handed to the synthesizer below, not a re-render of it
                    # (T7.9). Rebuilding this at read time is what ADR-0020 calls replaying a
                    # different prompt.
                    rendered=list(result.retrieved),
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
        # The contradiction cross-check ran here until T4.3. Retired on its own evidence:
        # 0 true positives and 4 false positives across every live firing (ADR-0021 addendum).
        # `grounding` is kept, unwired, with the bar for re-admission written down.
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
        """Draft, render, and - if the boundary refuses - regenerate once, then escalate (T3.8).

        The renderer is the grounding gate: a citation the store cannot resolve raises, and so
        does a narrative that leaks harness vocabulary. The plan's method is *"failures feed back
        for one regeneration, then page a human"*. The second attempt receives the refusal in its
        user message; a second refusal sets `narrative_escalated`, which flags the verdict.

        Every refusal is kept in `citation_violations` and written to the step, so T4.3 can
        compute a violation rate from persisted trajectories with no new instrumentation.
        """
        if self._scribe is None or result.verdict is None:
            return seq
        completion: Any = None
        tokens_in = tokens_out = 0
        violation: str | None = None
        for attempt in (1, 2):
            try:
                completion = self._scribe.draft(
                    triage, result.runs, result.verdict, violation=violation
                )
            except SchemaValidationError as failure:
                state.spend_tokens(failure.response.input_tokens, failure.response.output_tokens)
                result.failed_dispatches.append((Scribe.ROLE, str(failure)))
                if attempt == 2:
                    result.narrative_escalated = True
                break
            state.spend_tokens(completion.response.input_tokens, completion.response.output_tokens)
            tokens_in += completion.response.input_tokens
            tokens_out += completion.response.output_tokens
            result.draft = completion.value
            try:
                result.narrative = narrative_renderer.render(completion.value, self._store)
                result.narrative_error = None
                break
            except (
                narrative_renderer.UnknownCitationError,
                narrative_renderer.NarrativeLeakError,
            ) as exc:
                # A refused render is a finding, not a crash: the draft is kept so the failure
                # can be read, and the investigation still has its verdict.
                violation = str(exc)
                result.citation_violations.append(violation)
                result.narrative_error = violation
                if attempt == 1:
                    result.narrative_regenerated = True
                else:
                    result.narrative_escalated = True

        if result.narrative_escalated:
            logging.getLogger(__name__).warning(
                "narrative for incident %s was refused at the publication boundary twice and "
                "needs a human: %s",
                trajectory.incident_id,
                result.narrative_error,
            )
        if completion is None:
            return seq

        seq += 1
        trajectory.add(
            TrajectoryStep(
                seq=seq,
                role=Scribe.ROLE,
                kind=StepKind.MESSAGE,
                at=datetime.now(UTC),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                payload={
                    "attempts": completion.attempts,
                    "draft": completion.value.model_dump(),
                    "rendered": result.narrative is not None,
                    "render_error": result.narrative_error,
                    "violations": list(result.citation_violations),
                    "regenerated": result.narrative_regenerated,
                    "escalated": result.narrative_escalated,
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

    def _fan_out(
        self,
        trajectory: Trajectory,
        state: BudgetState,
        result: InvestigationResult,
        dispatches: list[Any],
        anchor: datetime,
        seq: int,
    ) -> int:
        """One round's dispatches, run at once and merged in plan order (T3.5).

        Three phases, and the separation is the design. **Admission** is sequential and reserves
        the tool call at admission, so a specialist with one call left cannot be dispatched twice
        by two entries admitted together. **Execution** is parallel - each dispatch runs on its
        own thread and touches nothing shared. **Merging** is in plan order, so `seq`, the
        trajectory and the synthesizer's input are byte-identical to what a sequential run would
        have produced. Concurrency changes the wall clock and nothing else that is recorded.

        The token check therefore moves from between dispatches to between rounds: a round can
        overshoot `max_tokens` by at most its own spend. That is the price of running a round at
        once, and the per-specialist tool budgets still bound every specialist individually.

        A dispatch that outlives the remaining wall clock is recorded as a failed dispatch with a
        step of its own, so it reaches the synthesizer and T4.2's scoring the same way a schema
        failure does - the plan's "modality unavailable", as typed evidence rather than silence.
        Its thread cannot be interrupted and is abandoned, not awaited.
        """
        admitted: list[tuple[Any, int]] = []
        for dispatch in dispatches:
            if not state.may_call_tool(dispatch.specialist):
                break
            state.record_tool_call(dispatch.specialist)
            seq += 1
            admitted.append((dispatch, seq))
            seq += 1
        if not admitted:
            return seq

        outcomes: list[DispatchOutcome | None]
        if len(admitted) == 1:
            dispatch, at = admitted[0]
            outcomes = [self._run_dispatch(dispatch, anchor, trajectory.started_at, at)]
        else:
            pool = ThreadPoolExecutor(max_workers=len(admitted), thread_name_prefix="specialist")
            futures = [
                pool.submit(self._run_dispatch, d, anchor, trajectory.started_at, at)
                for d, at in admitted
            ]
            outcomes = []
            for future in futures:
                remaining = max(1.0, state.budget.wall_clock_seconds - state.elapsed_seconds())
                try:
                    outcomes.append(future.result(timeout=remaining))
                except FuturesTimeout:
                    outcomes.append(None)
            pool.shutdown(wait=False, cancel_futures=True)

        for (dispatch, at), outcome in zip(admitted, outcomes, strict=True):
            name: SpecialistName = dispatch.specialist
            if outcome is None:
                reason = (
                    f"timed out: the investigation's {state.budget.wall_clock_seconds}s wall "
                    "clock ran out before this specialist answered"
                )
                result.failed_dispatches.append((name, reason))
                trajectory.add(
                    TrajectoryStep(
                        seq=at,
                        role=name,
                        kind=StepKind.COMPLETION,
                        at=datetime.now(UTC),
                        payload={"timed_out": True, "service": dispatch.service},
                    )
                )
                state.check()
                continue
            for step in outcome.steps:
                trajectory.add(step)
            state.spend_tokens(outcome.tokens_in, outcome.tokens_out)
            if outcome.failure is not None:
                result.failed_dispatches.append(outcome.failure)
            if outcome.run is not None:
                result.runs.append(outcome.run)
        # The round's spend landed all at once, so the check that used to run between
        # dispatches runs here instead. An overshoot is permitted by the concurrency and must
        # still be *recorded* as exhaustion - ADR-0020 §5 flags it, and a flag nobody set is a
        # partial diagnosis presented as a complete one.
        state.check()
        return seq

    def _run_dispatch(
        self, dispatch: Any, anchor: datetime, now: datetime, seq: int
    ) -> DispatchOutcome:
        """One specialist, start to finish, **touching nothing shared.**

        Runs on a worker thread whenever a round has more than one dispatch, which is why it
        returns what happened rather than recording it: `_fan_out` merges outcomes in plan
        order, so the record never depends on which thread finished first.
        """
        name: SpecialistName = dispatch.specialist
        service: str = dispatch.service
        question: str = dispatch.question
        specialist = self._specialists[name]
        # The window comes from the tool layer's policy, never from here and never from a model
        # (T3.2b): onset - 30 min to now for three specialists, onset - 24 h for `changes`.
        scoped = specialist.window(anchor, now)
        start, end = scoped.start, scoped.end
        steps: list[TrajectoryStep] = []

        began = time.monotonic()
        tool_result = specialist.query(service, start, end)
        rendered = envelope_renderer.render(tool_result)

        # The envelope goes into the trajectory verbatim, before anything reads it: a replay
        # that re-renders from the typed result is replaying a different prompt (ADR-0020 §3).
        steps.append(
            TrajectoryStep(
                seq=seq,
                role=name,
                kind=StepKind.TOOL_CALL,
                at=datetime.now(UTC),
                latency_ms=int((time.monotonic() - began) * 1000),
                payload={"question": question, "service": service},
                tool_call=ToolCallRecord(
                    tool=tool_result.tool,
                    # Per-query window logging on the record itself: which rule produced the
                    # window and whether the ceiling clipped it, beside the window (T3.2b).
                    request={"service": service, **scoped.as_request()},
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
            steps.append(
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
            return DispatchOutcome(
                steps=steps,
                run=None,
                failure=(name, str(failure)),
                tokens_in=failure.response.input_tokens,
                tokens_out=failure.response.output_tokens,
            )

        steps.append(
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
        return DispatchOutcome(
            steps=steps,
            run=SpecialistRun(
                specialist=name,
                service=service,
                question=question,
                result=tool_result,
                envelope=rendered,
                findings=findings,
                response=response,
                attempts=attempts,
            ),
            failure=None,
            tokens_in=response.input_tokens,
            tokens_out=response.output_tokens,
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
