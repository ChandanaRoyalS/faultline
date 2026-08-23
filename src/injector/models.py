"""Typed fault definitions and injector state (T1.4).

A fault is a value, not a function call: the definition carries everything a
scenario file (T1.5) needs to cite it, and an active injection carries
everything a *later, separate* CLI invocation needs to undo it. That is why
restore data is modelled explicitly rather than recomputed at stop time - the
original memory limit is gone from the world the moment we overwrite it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Fault classes live in the scenario schema (T1.5): it is the contract the eval
# harness, the catalog and the injector all validate against, and two copies of
# this enum would drift the first time T7.0 adds a class to one of them.
from evalharness.scenario import FaultClass

ParamValue = str | int | float


class FaultDefinition(BaseModel):
    """One injectable fault, in the shape a scenario file will reference it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    fault_class: FaultClass
    target: str = Field(description="Container or compose service the fault is aimed at")
    description: str
    params: dict[str, ParamValue] = Field(default_factory=dict)


class MemoryLimitRestore(BaseModel):
    """Put back the container's memory limit, in bytes, exactly as inspected."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["memory_limit"] = "memory_limit"
    container: str
    memory_bytes: int
    memory_swap_bytes: int


class ComposeServiceRestore(BaseModel):
    """Recreate a service without our override file, then delete the override."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["compose_service"] = "compose_service"
    service: str
    override_file: str


class PumbaRestore(BaseModel):
    """Stop the pumba sidecar; it reverts its own tc rules on SIGTERM."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pumba"] = "pumba"
    helper_container: str


RestoreState = Annotated[
    MemoryLimitRestore | ComposeServiceRestore | PumbaRestore,
    Field(discriminator="kind"),
]


class ActiveInjection(BaseModel):
    """A fault currently applied to the world, plus how to take it back off."""

    model_config = ConfigDict(extra="forbid")

    definition: FaultDefinition
    started_at: datetime
    restore: RestoreState


class InjectorState(BaseModel):
    """Everything the injector has broken and not yet fixed."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    active: dict[str, ActiveInjection] = Field(default_factory=dict)
