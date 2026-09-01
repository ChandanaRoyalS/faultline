"""The allowlist action catalog: what the action plane is permitted to do (T2.4b).

Read-only by construction. This module loads and validates; it has no writer, and
`tests/test_allowlist.py` fails if one appears. The reasoning is ADR-0032's: a catalog the
investigation runtime can edit is not a control, and the runtime is the part of this system
that reads untrusted telemetry.

The catalog names *classes* of action against a *selector*, never a service. Which service an
action may touch is the incident's scoped topology to decide, checked by the executor at
approval time - the proposal's failure table calls a mismatch there a hard reject before the
approval is even requested, and a catalog that pinned services would move that check here,
where the incident is not in scope.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

CATALOG_NAME = "allowlist.yaml"


class ActionStatus(StrEnum):
    AVAILABLE = "available"
    UNPERFORMABLE = "unperformable"
    """The world cannot perform it. Listed so the gap is recorded rather than missing."""


class TargetSelector(StrEnum):
    INCIDENT_SCOPED_SERVICE = "incident_scoped_service"
    """Any service inside the incident's scoped topology, and no other."""


class AllowlistAction(BaseModel):
    """One permitted action. Not a `_CONTRACTS` member - no role prompt promises it yet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    remediation_class: str
    summary: str
    target_selector: TargetSelector
    preconditions: list[str] = Field(default_factory=list)
    blast_radius: str
    reversible: bool
    approval: str
    status: ActionStatus
    unperformable_reason: str | None = None
    excluded_targets: list[str] = Field(default_factory=list)


class ActionCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: int = Field(ge=1)
    origin: str
    actions: list[AllowlistAction]

    def by_id(self, action_id: str) -> AllowlistAction | None:
        return next((a for a in self.actions if a.id == action_id), None)

    @property
    def performable(self) -> list[AllowlistAction]:
        return [a for a in self.actions if a.status is ActionStatus.AVAILABLE]


def catalog_path() -> Path:
    """Walk up from this module for the `knowledge/` directory.

    Not a package-relative constant: the catalog is repository data rather than package data,
    and it must resolve the same from an editable install and from a clean clone.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "knowledge" / CATALOG_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no knowledge/{CATALOG_NAME} above {__file__}")


@cache
def load_allowlist() -> ActionCatalog:
    raw: Any = yaml.safe_load(catalog_path().read_text())
    return ActionCatalog.model_validate(raw)
