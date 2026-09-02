"""Trajectory persistence: what the model saw, kept so it can be scored and replayed (T3.2).

ADR-0003 promised "full trajectory persistence to Postgres" without saying what a trajectory
is; ADR-0020 §3 designed it. Two consumers, and the harder one sets the shape: **T4.2 scores it
and T5.3 replays it.** Reconstructing what the model saw means storing the *rendered* text, not
the object it was rendered from - a replay that re-renders from a typed result is replaying a
different prompt, and the difference is invisible in a diff of the two objects.

So `trajectory_tool_calls.envelope` holds the exact string the agent read, byte for byte, and
the smoke asserts it round-trips that way: encoding and escaping are exactly where a store
corrupts something quietly. The ANSI escapes in `cart-bad-image-tag`'s committed log capture and
the per-call nonce in the closing delimiter are both things a helpful normaliser would eat.

And `trajectory_retrievals.exclude_origin` is where T4.1b reads ADR-0008's assertion: the
harness "sets it to the scenario under test on every scored run and then asserts the filter
actually fired; a scored run where the filter did not fire is marked **invalid**, not
annotated". A column, not a log line.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from faultline.archive import Archive, archive_trajectory


class StepKind(StrEnum):
    """What one step in a trajectory was."""

    PROMPT = "prompt"
    COMPLETION = "completion"
    TOOL_CALL = "tool_call"
    RETRIEVAL = "retrieval"
    MESSAGE = "message"
    """An inter-agent message. ADR-0020 §3: fan-out means a specialist's conclusion becomes the
    synthesizer's input, and scoring the synthesizer without seeing what it was given scores the
    wrong thing."""

    VERDICT = "verdict"


@dataclass(slots=True)
class ToolCallRecord:
    """One tool call and the envelope it produced."""

    tool: str
    request: dict[str, Any]
    result_id: str
    """The envelope's own id. **The key everything else hangs off**: the synthesizer cites it,
    the citation validator resolves it, and the envelope row is stored under it."""

    envelope: str
    """The rendered text, verbatim. Never re-rendered on read."""

    @property
    def envelope_sha256(self) -> str:
        """Stored beside the text so corruption is detectable without a second copy to diff.

        ADR-0020 marked envelope storage as inline-versus-content-addressed and this is neither
        wholly: stored inline, keyed by `result_id`, with a hash that makes the byte-identity
        claim checkable at read time rather than only in a smoke.
        """
        return hashlib.sha256(self.envelope.encode()).hexdigest()


@dataclass(slots=True)
class RetrievalRecord:
    """One retrieval, with the exclusion that was actually passed."""

    query: str
    k: int
    exclude_origin: str | None
    """`None` is the product case and is legal. Every **benchmark** retrieval passes one
    (ADR-0008, axis 2), and this column is how T4.1b tells the two apart after the fact."""

    returned: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)

    rendered: list[str] = field(default_factory=list)
    """The retrieved lines **as the model read them**, verbatim (T7.9).

    `returned` holds chunk ids, which is what ADR-0008's contamination assertion needs. It is
    not what the agent saw, and it does not stay pointing at the same text: the corpus is
    rewritten whenever a narrative is corrected, and **60 of 62 stored trajectories name chunks
    whose prose has since changed**.

    ADR-0020 already settled the principle for the other kind of evidence - *"reconstructing
    what the model saw means storing the rendered text, not the object it was rendered from"* -
    and applied it to tool envelopes only, because retrieval rows were specified for
    contamination auditing rather than for replay. This carries it across.

    **Rendered, not the chunk body.** The synthesizer is handed
    `f"{scenario_id} / {section}: {text[:280]}"`, so the body is the object and this is the
    text; storing bodies would replay a different prompt, which is the failure the ADR names.
    """

    @property
    def rendered_sha256(self) -> str:
        """Beside the text, never instead of it - the same choice as `envelope_sha256`.

        A hash alone would detect that the corpus had drifted and still not let anyone read
        what was retrieved, and ADR-0020 rejected content-addressing on the ground that a hash
        *as key* is "a place for a hash to disagree with its content".
        """
        return hashlib.sha256("\n".join(self.rendered).encode()).hexdigest()


@dataclass(slots=True)
class TrajectoryStep:
    seq: int
    role: str
    kind: StepKind
    at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    tool_call: ToolCallRecord | None = None
    retrieval: RetrievalRecord | None = None


@dataclass(slots=True)
class Trajectory:
    """One investigation, end to end."""

    incident_id: str
    model: str
    """The **effective** model. Two trajectories from different models are not comparable and
    nothing else in the record would say so (ADR-0020 §3)."""

    effort: str
    started_at: datetime
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role_models: dict[str, str] = field(default_factory=dict)
    """The effective per-role map, empty when every role ran the default. Recorded because a
    published figure reports the map rather than the default (ADR-0020 §1)."""

    runtime_version: str = ""
    ended_at: datetime | None = None
    outcome: str | None = None
    budget_exhausted: bool = False
    """ADR-0020 §5: exhaustion finishes the investigation early with a flagged verdict rather
    than failing it, and T4.2 must report those separately rather than pooling them."""

    steps: list[TrajectoryStep] = field(default_factory=list)

    def add(self, step: TrajectoryStep) -> TrajectoryStep:
        self.steps.append(step)
        return step

    @property
    def tool_calls(self) -> list[ToolCallRecord]:
        return [s.tool_call for s in self.steps if s.tool_call is not None]

    @property
    def retrievals(self) -> list[RetrievalRecord]:
        return [s.retrieval for s in self.steps if s.retrieval is not None]


class TrajectoryStore(Protocol):
    """Where trajectories live. The seam the tests substitute at."""

    def save(self, trajectory: Trajectory) -> None: ...

    def get(self, trajectory_id: str) -> Trajectory | None: ...

    def envelope(self, result_id: str) -> str | None:
        """The rendered envelope for one tool result, byte for byte as it was stored."""


class InMemoryTrajectoryStore:
    """A dict. For tests, and for a dry run."""

    def __init__(self) -> None:
        self.trajectories: dict[str, Trajectory] = {}

    def save(self, trajectory: Trajectory) -> None:
        self.trajectories[trajectory.id] = trajectory

    def get(self, trajectory_id: str) -> Trajectory | None:
        return self.trajectories.get(trajectory_id)

    def envelope(self, result_id: str) -> str | None:
        for trajectory in self.trajectories.values():
            for call in trajectory.tool_calls:
                if call.result_id == result_id:
                    return call.envelope
        return None


class PostgresTrajectoryStore:
    """The real one, plus the archive copy that outlives it (T2.3).

    `archive` is optional and defaults to none: a deployment without object storage keeps
    working exactly as before, and every envelope is still stored inline in Postgres under
    its `result_id`. What the archive adds is a copy with a different failure mode - the
    database holds the only one otherwise, so resetting it destroys the evidence behind every
    citation ever made, and the reports become unfalsifiable rather than wrong.
    """

    def __init__(self, connection: Any, archive: Archive | None = None) -> None:
        self._conn = connection
        self._archive = archive

    def save(self, trajectory: Trajectory) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trajectories (id, incident_id, model, role_models, effort, "
                "runtime_version, started_at, ended_at, outcome, budget_exhausted) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET "
                "ended_at = EXCLUDED.ended_at, outcome = EXCLUDED.outcome, "
                "budget_exhausted = EXCLUDED.budget_exhausted",
                (
                    trajectory.id,
                    trajectory.incident_id,
                    trajectory.model,
                    json.dumps(trajectory.role_models),
                    trajectory.effort,
                    trajectory.runtime_version,
                    trajectory.started_at,
                    trajectory.ended_at,
                    trajectory.outcome,
                    trajectory.budget_exhausted,
                ),
            )
            for step in trajectory.steps:
                cur.execute(
                    "INSERT INTO trajectory_steps (trajectory_id, seq, role, kind, at, "
                    "tokens_in, tokens_out, latency_ms, payload) VALUES (%s,%s,%s,%s,%s,%s,%s,"
                    "%s,%s) ON CONFLICT (trajectory_id, seq) DO NOTHING",
                    (
                        trajectory.id,
                        step.seq,
                        step.role,
                        step.kind.value,
                        step.at,
                        step.tokens_in,
                        step.tokens_out,
                        step.latency_ms,
                        json.dumps(step.payload),
                    ),
                )
                if step.tool_call is not None:
                    call = step.tool_call
                    cur.execute(
                        "INSERT INTO trajectory_tool_calls (trajectory_id, seq, tool, request, "
                        "result_id, envelope, envelope_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (trajectory_id, seq) DO NOTHING",
                        (
                            trajectory.id,
                            step.seq,
                            call.tool,
                            json.dumps(call.request),
                            call.result_id,
                            call.envelope,
                            call.envelope_sha256,
                        ),
                    )
                if step.retrieval is not None:
                    r = step.retrieval
                    cur.execute(
                        "INSERT INTO trajectory_retrievals (trajectory_id, seq, query, k, "
                        "exclude_origin, returned, scores, rendered, rendered_sha256) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (trajectory_id, seq) DO NOTHING",
                        (
                            trajectory.id,
                            step.seq,
                            r.query,
                            r.k,
                            r.exclude_origin,
                            json.dumps(r.returned),
                            json.dumps(r.scores),
                            json.dumps(r.rendered),
                            r.rendered_sha256 if r.rendered else None,
                        ),
                    )
        self._conn.commit()
        self._archive_envelopes(trajectory)

    def _archive_envelopes(self, trajectory: Trajectory) -> None:
        """After the commit, never before, and never fatal.

        The trajectory row is the record; the archive is the copy. Losing a finished
        investigation because object storage was unreachable would trade the thing being
        protected for the protection. A failure is logged loudly and the run continues -
        logged rather than swallowed, because a silently empty archive is exactly the kind of
        claim this project keeps finding was true when written and false later.
        """
        if self._archive is None:
            return
        try:
            archive_trajectory(trajectory, self._archive)
        except Exception:
            logging.getLogger(__name__).warning(
                "trajectory %s was saved but its envelopes were not archived; the inline "
                "copies in Postgres are still authoritative",
                trajectory.id,
                exc_info=True,
            )

    def get(self, trajectory_id: str) -> Trajectory | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, incident_id, model, role_models, effort, runtime_version, "
                "started_at, ended_at, outcome, budget_exhausted FROM trajectories "
                "WHERE id = %s",
                (trajectory_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            trajectory = Trajectory(
                id=row[0],
                incident_id=row[1],
                model=row[2],
                role_models=row[3] or {},
                effort=row[4],
                runtime_version=row[5],
                started_at=row[6],
                ended_at=row[7],
                outcome=row[8],
                budget_exhausted=row[9],
            )
            cur.execute(
                "SELECT seq, role, kind, at, tokens_in, tokens_out, latency_ms, payload "
                "FROM trajectory_steps WHERE trajectory_id = %s ORDER BY seq",
                (trajectory_id,),
            )
            steps = {
                r[0]: TrajectoryStep(
                    seq=r[0],
                    role=r[1],
                    kind=StepKind(r[2]),
                    at=r[3],
                    tokens_in=r[4],
                    tokens_out=r[5],
                    latency_ms=r[6],
                    payload=r[7] or {},
                )
                for r in cur.fetchall()
            }
            cur.execute(
                "SELECT seq, tool, request, result_id, envelope FROM trajectory_tool_calls "
                "WHERE trajectory_id = %s",
                (trajectory_id,),
            )
            for seq, tool, request, result_id, envelope in cur.fetchall():
                steps[seq].tool_call = ToolCallRecord(
                    tool=tool, request=request or {}, result_id=result_id, envelope=envelope
                )
            cur.execute(
                "SELECT seq, query, k, exclude_origin, returned, scores, rendered "
                "FROM trajectory_retrievals WHERE trajectory_id = %s",
                (trajectory_id,),
            )
            for seq, query, k, exclude_origin, returned, scores, rendered in cur.fetchall():
                steps[seq].retrieval = RetrievalRecord(
                    query=query,
                    k=k,
                    exclude_origin=exclude_origin,
                    returned=returned or [],
                    scores=scores or [],
                    # Empty for anything recorded before T7.9. Read it as "the retrieved text
                    # was not kept", never as "nothing was retrieved" - `returned` says that.
                    rendered=rendered or [],
                )
        trajectory.steps = [steps[seq] for seq in sorted(steps)]
        return trajectory

    def envelope(self, result_id: str) -> str | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT envelope FROM trajectory_tool_calls WHERE result_id = %s LIMIT 1",
                (result_id,),
            )
            row = cur.fetchone()
            return None if row is None else str(row[0])
