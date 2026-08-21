"""Scenario catalog schema (T1.5) with the dev/holdout split assigned at authoring (T1.6).

This model is the contract between the injector, the eval harness, and the contamination
rules. Every YAML file under evals/scenarios/ must validate against it.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class FaultClass(StrEnum):
    """Fault classes the injector supports. T1.4 builds these four; T7.0 adds four more."""

    BAD_DEPLOY = "bad_deploy"
    DEPENDENCY_LATENCY = "dependency_latency"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    BAD_CONFIG = "bad_config"


class Split(StrEnum):
    """Contamination split (T1.6): assigned at authoring, before any rehearsal artifact exists."""

    DEV = "dev"
    HOLDOUT = "holdout"


class RemediationClass(StrEnum):
    """What kind of fix resolves the fault - scored as remediation-class correctness (T4.2)."""

    ROLLBACK = "rollback"
    RESTART = "restart"
    CONFIG_REVERT = "config_revert"
    SCALE = "scale"


class Injection(BaseModel):
    """The concrete, reversible operation the injector performs."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(description="Service in the target environment to break")
    method: str = Field(description="Named injector operation, e.g. shrink_db_pool")
    params: dict[str, int | float | str] = Field(default_factory=dict)


class GroundTruth(BaseModel):
    """The answer key. Exists because we injected the fault ourselves."""

    model_config = ConfigDict(extra="forbid")

    root_cause: str
    category: FaultClass


class Scenario(BaseModel):
    """One labeled failure scenario - simultaneously eval case, regression test, and demo script."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    title: str
    fault_class: FaultClass
    split: Split
    injection: Injection
    ground_truth: GroundTruth
    expected_evidence: list[dict[str, str]] = Field(min_length=1)
    expected_remediation_class: RemediationClass
    rehearsed: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> Scenario:
        """Load and validate one scenario file."""
        raw = yaml.safe_load(path.read_text())
        return cls.model_validate(raw)


def load_catalog(directory: Path) -> list[Scenario]:
    """Load every scenario YAML under a directory tree, validated."""
    return [Scenario.from_yaml(p) for p in sorted(directory.rglob("*.yaml"))]
