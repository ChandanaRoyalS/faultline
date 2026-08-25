"""The nine agent roles: triage, planner, four specialists, synthesizer, proposer, scribe (T3.x).

Triage is built (T3.1, ADR-0020 §6). The other eight are not.
"""

from faultline.agents.triage import (
    BlastRadiusMember,
    EntryReason,
    Triage,
    TriageResult,
)

__all__ = ["BlastRadiusMember", "EntryReason", "Triage", "TriageResult"]
