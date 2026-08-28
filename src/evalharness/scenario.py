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
    alert_timeout_seconds: int | None = None
    """How long the recorder should wait for this scenario's first alert. None = the default.

    A **rehearsal hint**, not a fault parameter. It describes how long the world takes to
    notice this fault, not what the fault does, so it stays out of `injection` - which
    keeps it out of `scenario_fingerprint` and out of the YAML/catalog params gate. Two
    scenarios differing only here are the same experiment.

    Needed because detection time scales with the target's traffic rate: a service at
    0.099 req/s takes four minutes longer to trip a rule than one at 5 req/s, and a global
    timeout tuned on the busy ones reports the sparse one as undetectable."""
    answers_idle_or_absent: list[str] | None = None
    """Which evidence classes the author expects to answer "was the target idle or absent"
    (T7.5). `[]` declares that none will.

    **Authored before recording; checked against the bundle afterwards.** The recorded value is
    derived from the captures (`bundle.reachability`), and this field is the claim the author
    made in advance. The gate exists because six of twelve existing bundles were recorded before
    anyone asked whether their target could produce the evidence their narrative would go on to
    cite, and two of them cannot answer this question at all - a fact discovered at T7.4, long
    after the narratives were written.

    Only `runtime` and `logs` can answer it. Span metrics and traces cannot: their absence *is*
    the ambiguity. Change history cannot: it says what changed, not what is running.

    `None` means undeclared, which is permitted for the scenarios that predate the gate and
    refused for new ones - see `CATALOG.md`. **A scenario declaring `[]` is recordable**, but
    only deliberately: its narrative must not rest on a question its target cannot answer."""

    blocked: bool = False
    """This scenario cannot be rehearsed and does not occupy its slot.

    Set when a scenario's fault turns out not to be injectable or observable on this world
    - a retired mechanism, or a target that emits no telemetry. The file is kept so the
    slot's history is visible, but the allocation guards skip it: a scenario that can never
    be rehearsed is not filling a slot, and its replacement must be allowed in without
    widening the table in SPLIT.md.

    A machine-readable field rather than a comment, because the guards have to act on it.
    The reason belongs in a comment at the top of the file, next to this."""

    @classmethod
    def from_yaml(cls, path: Path) -> Scenario:
        """Load and validate one scenario file."""
        raw = yaml.safe_load(path.read_text())
        return cls.model_validate(raw)


def load_catalog(directory: Path) -> list[Scenario]:
    """Load every scenario YAML under a directory tree, validated."""
    return [Scenario.from_yaml(p) for p in sorted(directory.rglob("*.yaml"))]
