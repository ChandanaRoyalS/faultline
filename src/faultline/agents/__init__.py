"""The nine agent roles, the model boundary, and trajectory persistence.

**All nine are built as of T3.9.** Triage is deterministic rather than model-driven and says why
in its own module; the proposer is the last to arrive and proposes only - the executor it
proposes to is a separate system outside this runtime, and ADR-0028 §3 is the argument for why
that is a boundary rather than a later commit.
"""

from faultline.agents.budget import Budget, BudgetState
from faultline.agents.contracts import (
    Dispatch,
    DispatchPlan,
    Finding,
    NarrativeDraft,
    NarrativeSection,
    Proposal,
    RuledOut,
    SpecialistFindings,
    Verdict,
)
from faultline.agents.investigation import Investigation, InvestigationResult
from faultline.agents.model import (
    AnthropicModel,
    DeterministicModel,
    LanguageModel,
    ModelRequest,
    ModelResponse,
)
from faultline.agents.narrative import NarrativeLeakError, UnknownCitationError
from faultline.agents.roles import (
    Planner,
    Proposer,
    Scribe,
    Specialist,
    Synthesizer,
    build_specialists,
)
from faultline.agents.settings import AgentSettings
from faultline.agents.trajectory import (
    InMemoryTrajectoryStore,
    PostgresTrajectoryStore,
    RetrievalRecord,
    StepKind,
    ToolCallRecord,
    Trajectory,
    TrajectoryStep,
    TrajectoryStore,
)
from faultline.agents.triage import BlastRadiusMember, EntryReason, Triage, TriageResult

__all__ = [
    "AgentSettings",
    "AnthropicModel",
    "BlastRadiusMember",
    "Budget",
    "BudgetState",
    "DeterministicModel",
    "Dispatch",
    "DispatchPlan",
    "EntryReason",
    "Finding",
    "InMemoryTrajectoryStore",
    "Investigation",
    "InvestigationResult",
    "LanguageModel",
    "ModelRequest",
    "ModelResponse",
    "NarrativeDraft",
    "NarrativeLeakError",
    "NarrativeSection",
    "Planner",
    "PostgresTrajectoryStore",
    "Proposal",
    "Proposer",
    "RetrievalRecord",
    "RuledOut",
    "Scribe",
    "Specialist",
    "SpecialistFindings",
    "StepKind",
    "Synthesizer",
    "ToolCallRecord",
    "Trajectory",
    "TrajectoryStep",
    "TrajectoryStore",
    "Triage",
    "TriageResult",
    "UnknownCitationError",
    "Verdict",
    "build_specialists",
]
