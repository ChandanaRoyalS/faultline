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
    """Fault classes the injector supports: T1.4's four, and the five T7.0 measured.

    A class is individuated by the injector mechanism that produces it (ADR-0043). The first four
    are T1.4's. The five below were each **attempted live on the v2 world, pre-registered, and
    admitted only on the registered criteria** - pages within twelve minutes on the target or a
    direct caller, distinct from a named comparator in a dimension the agent's tools expose,
    reverts within ten (`evals/runs/PREREGISTRATION-T7.0.md`; results under `evals/attempts/`,
    2026-09-22/24). Two candidates the plan named did not make it: a flood flag (A5) produced no
    signal but request rate, and a wrong credential (A6) and an N+1 image (A7) are `bad_config`'s
    and `bad_deploy`'s own mechanisms. Nine is the ceiling the registration set.

    A member here must also be in the `FaultClass` `Literal` in `faultline.agents.contracts` -
    `tests/test_freeze.py` binds the two - and adding one moves `prompt_digest`. The five were
    added together, once, so it moved once: `06f24e827915` -> the digest `tests/test_harness_run.py`
    records as `T70_DIGEST`. Every figure published before it stands at the old stamp.
    """

    BAD_DEPLOY = "bad_deploy"
    DEPENDENCY_LATENCY = "dependency_latency"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    BAD_CONFIG = "bad_config"
    FEATURE_FLAG = "feature_flag"
    """A flag flipped in the world's flag store (flagd). A1: pages as errors on the caller; leaves
    no compose change, so `change_history` is empty while the world is broken."""
    PROCESS_FREEZE = "process_freeze"
    """The target's process stopped (`docker pause`) while its socket stays open. A2: callers hang
    rather than fail; thirteen alerts on ten services; the target's log is silent."""
    NETWORK_PARTITION = "network_partition"
    """The target cut from the network (`docker network disconnect`). A3: the same hang as a
    freeze, separable only by the target's own export failures in its log."""
    DATASTORE_CORRUPTION = "datastore_corruption"
    """The target's datastore reachable and its contents unparseable. A4b: pages on the caller
    that reads the store once per request; parse failures in the culprit's log."""
    DISK_FILL = "disk_fill"
    """The target's only writable data directory filled to capacity. A8b: the broker halts in
    seconds, its producer hangs then fails, its consumers starve; the broker's log names it."""


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
    RECONNECT = "reconnect"
    """Restore the target's connectivity (T7.0: `network_partition`'s fix)."""
    RESTORE_DATA = "restore_data"
    """Flush or restore the target's stored data (T7.0: `datastore_corruption`'s fix)."""
    FREE_STORAGE = "free_storage"
    """Free or grow the target's storage (T7.0: `disk_fill`'s fix)."""


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

    also_correct_remediation: list[RemediationClass] = Field(default_factory=list)
    """Other remediations **measured** to fix this fault durably (T7.17, ADR-0027).

    `expected_remediation_class` stays the labelled fix and stays in `scenario_fingerprint`;
    this is additive and deliberately **not** fingerprinted, so recording that a second fix works
    invalidates no bundle. A bundle is a recording of what the fault did to the world, and it is
    not made wrong by a later discovery about how to undo it.

    **The bar is measurement, not plausibility.** An entry here means the remediation was applied
    to a live injection and the fault verifiably cleared and stayed cleared. For the two
    `dependency_latency` scenarios that is `config_revert`: deleting the netem qdisc from the
    target's interface clears the delay durably, without restarting the container and with the
    pumba sidecar still running - 3/3 attempts, evidence in `docs/evidence/t7.17-fix-class/`.
    """

    slot: str | None = None
    """The SPLIT.md slot this scenario occupies, e.g. `bad_deploy-3`. **Recorded, then frozen.**

    SPLIT.md's rule - "slots are filled alphabetically by injector fault id within each class" -
    was enforced by nothing until T7.35: no scenario recorded a slot and the contamination guard
    counted per class rather than checking identity. This field is what makes the rule executable.

    **It is recorded rather than recomputed, and that is a decision with a measured reason.**
    Re-deriving alphabetically on every read is stable under every operation this repository
    performs *except the one that matters* - adding a scenario. Slot k goes to the k-th id
    alphabetically, so a new id that sorts early shifts every later scenario down one slot and
    **changes splits that have already been spent**: adding an `a...` id to `bad_deploy` moves
    `email-wrong-image` from holdout to dev, after three holdout entries have used it, and
    `cart-bad-image-tag` from dev to holdout after it has been tuned against. An anti-contamination
    rule that recomputes would cause the contamination it exists to prevent.

    So the derivation runs **once**, as a backfill, and is asserted against the recorded splits it
    reproduces. Afterwards this field is authoritative and a new scenario takes the lowest-numbered
    free slot in its class.

    **Deliberately outside `scenario_fingerprint`**, for the same reason as
    `also_correct_remediation` (T7.17): a bundle is evidence for what the fault does, and which
    bookkeeping slot the scenario occupies changes nothing about that. Fingerprinting it would
    invalidate every recorded bundle to record an allocation fact.

    `None` on a `blocked` scenario, which releases its slot rather than consuming it.
    """

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
