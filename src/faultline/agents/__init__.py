"""The nine agent roles, the model boundary, and trajectory persistence (T3.x).

Triage is built (T3.1); the model boundary and trajectory store are built (T3.2). The other
eight roles are not.
"""

from faultline.agents.budget import Budget, BudgetState
from faultline.agents.contracts import (
    Dispatch,
    DispatchPlan,
    Finding,
    NarrativeDraft,
    NarrativeSection,
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
from faultline.agents.roles import Planner, Scribe, Specialist, Synthesizer, build_specialists
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
