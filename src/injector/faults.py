"""The four fault classes T1.4 covers, each with an inject and a restore (T7.0 adds more).

Two rules hold across all of them:

* Restore never guesses. Whatever the world looked like before is captured at
  inject time and written to the state file, because by stop time the evidence
  is gone.
* Restore is idempotent. Stopping an inactive fault, or one whose container has
  already gone away, is a no-op that succeeds - a demo that cannot be reset is
  worse than a demo that never ran.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, ConfigDict

from evalharness.scenario import FaultClass
from injector.docker import CommandError, ComposeCli, DockerCli
from injector.models import (
    ComposeServiceRestore,
    FaultDefinition,
    MemoryLimitRestore,
    PumbaRestore,
    RestoreState,
)
from injector.settings import InjectorSettings


class InjectionOutcome(BaseModel):
    """What a fault did, and what it will take to undo it."""

    model_config = ConfigDict(extra="forbid")

    restore: RestoreState
    changes: list[str]
    """Human-readable lines, printed by `start`: an operator must see what moved."""


class FaultUsageError(RuntimeError):
    """The fault definition asks for something this handler cannot do."""


def _str_param(definition: FaultDefinition, name: str, default: str) -> str:
    value = definition.params.get(name, default)
    if not isinstance(value, str):
        raise FaultUsageError(f"{definition.id}: param {name!r} must be a string, got {value!r}")
    return value


def _int_param(definition: FaultDefinition, name: str, default: int) -> int:
    value = definition.params.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FaultUsageError(f"{definition.id}: param {name!r} must be an integer, got {value!r}")
    return value


class Fault(ABC):
    """One fault class: how to break the world this way, and how to put it back."""

    fault_class: ClassVar[FaultClass]

    @abstractmethod
    def inject(self, definition: FaultDefinition) -> InjectionOutcome: ...

    @abstractmethod
    def restore(self, state: RestoreState) -> list[str]:
        """Undo the injection. Must succeed when there is nothing left to undo."""


class ResourceExhaustionFault(Fault):
    """Shrink a container's memory limit until the workload cannot fit in it."""

    fault_class = FaultClass.RESOURCE_EXHAUSTION

    def __init__(self, docker: DockerCli) -> None:
        self._docker = docker

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        container = definition.target
        memory = _str_param(definition, "memory", "64m")
        original_memory, original_swap = self._docker.memory_limits(container)
        # Swap ceiling pinned to the memory limit: with swap left open the workload
        # escapes the squeeze into swap and the fault produces latency rather than
        # the memory pressure the scenario claims to be about.
        self._docker.set_memory_limits(container, memory, memory)
        return InjectionOutcome(
            restore=MemoryLimitRestore(
                container=container,
                memory_bytes=original_memory,
                memory_swap_bytes=original_swap,
            ),
            changes=[
                f"docker update: {container} memory limit "
                f"{_human_bytes(original_memory)} -> {memory} (swap capped at the same value)",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, MemoryLimitRestore):
            raise FaultUsageError(f"resource_exhaustion cannot restore {state.kind}")
        if not self._docker.container_exists(state.container):
            return [f"{state.container} is gone; nothing to restore"]
        swap = str(state.memory_swap_bytes) if state.memory_swap_bytes != 0 else None
        self._docker.set_memory_limits(state.container, str(state.memory_bytes), swap)
        return [
            f"docker update: {state.container} memory limit restored to "
            f"{_human_bytes(state.memory_bytes)}"
        ]


class _ComposeOverrideFault(Fault):
    """Shared machinery for faults that recreate a service under a generated override.

    The override is a file on disk rather than an in-memory edit, so the exact
    change is inspectable while the incident is live, and removing the file plus
    recreating the service is a complete, auditable rollback.
    """

    def __init__(self, compose: ComposeCli, settings: InjectorSettings) -> None:
        self._compose = compose
        self._settings = settings

    def _apply_override(self, definition: FaultDefinition, service_body: dict[str, object]) -> Path:
        path = self._settings.override_dir / f"{definition.id}.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "# generated by faultline-inject": f"fault {definition.id}; delete via stop",
            "services": {definition.target: service_body},
        }
        path.write_text(yaml.safe_dump(document, sort_keys=False))
        try:
            self._compose.recreate(definition.target, overrides=[path])
        except Exception:
            # A failed recreate returns no restore record, so nothing would ever
            # clean this up. Put the service back on the world's own definition
            # and take the override with us - best effort, since the caller needs
            # to see the original failure, not a second one from the cleanup.
            with contextlib.suppress(CommandError):
                self._compose.recreate(definition.target)
            path.unlink(missing_ok=True)
            raise
        return path

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, ComposeServiceRestore):
            raise FaultUsageError(f"{self.fault_class} cannot restore {state.kind}")
        override = Path(state.override_file)
        # Recreate from the base compose files alone: whatever the override was
        # saying, the service comes back as the world defines it.
        self._compose.recreate(state.service)
        override.unlink(missing_ok=True)
        return [
            f"compose: {state.service} recreated from the base world definition",
            f"removed override {override}",
        ]


class BadDeployFault(_ComposeOverrideFault):
    """Ship a build that starts, serves, and fails on the hot path."""

    fault_class = FaultClass.BAD_DEPLOY

    def __init__(self, docker: DockerCli, compose: ComposeCli, settings: InjectorSettings) -> None:
        super().__init__(compose, settings)
        self._docker = docker

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        image = _str_param(definition, "image", "faultline/ffs-stub:broken")
        server = _str_param(definition, "server", "server_broken.py")
        # Built here rather than assumed present: a scenario must be reproducible
        # from a clean clone, where this tag does not exist yet.
        self._docker.build(image, self._settings.ffs_stub_context, {"SERVER": server})
        path = self._apply_override(definition, {"image": image})
        return InjectionOutcome(
            restore=ComposeServiceRestore(service=definition.target, override_file=str(path)),
            changes=[
                f"docker build: {image} from {self._settings.ffs_stub_context} (SERVER={server})",
                f"compose: {definition.target} recreated on {image}",
                f"override written to {path}",
            ],
        )


class BadConfigFault(_ComposeOverrideFault):
    """Recreate a service with one environment variable set wrong."""

    fault_class = FaultClass.BAD_CONFIG

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        variable = _str_param(definition, "env_var", "")
        value = _str_param(definition, "value", "")
        if not variable:
            raise FaultUsageError(f"{definition.id}: bad_config needs an env_var param")
        path = self._apply_override(definition, {"environment": {variable: value}})
        return InjectionOutcome(
            restore=ComposeServiceRestore(service=definition.target, override_file=str(path)),
            changes=[
                f"compose: {definition.target} recreated with {variable}={value}",
                f"override written to {path}",
            ],
        )


class DependencyLatencyFault(Fault):
    """Delay a container's network traffic with tc netem, driven by pumba."""

    fault_class = FaultClass.DEPENDENCY_LATENCY

    def __init__(self, docker: DockerCli, settings: InjectorSettings) -> None:
        self._docker = docker
        self._settings = settings

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        delay_ms = _int_param(definition, "delay_ms", 300)
        jitter_ms = _int_param(definition, "jitter_ms", 0)
        duration = _str_param(definition, "duration", "1h")
        interface = _str_param(definition, "interface", "eth0")
        helper = f"faultline-pumba-{definition.id}"

        # A leftover sidecar from a killed run would hold a stale netem rule and
        # make the next injection's delay unexplainable. Clear it first.
        self._docker.remove(helper)
        self._docker.run_detached(
            name=helper,
            image=self._settings.pumba_image,
            volumes=["/var/run/docker.sock:/var/run/docker.sock"],
            command=[
                "--log-level",
                "info",
                "netem",
                "--duration",
                duration,
                "--interface",
                interface,
                # tc runs from a sidecar image, so the target container needs no
                # network tooling of its own - and stays the image the world pins.
                "--tc-image",
                self._settings.tc_image,
                "delay",
                "--time",
                str(delay_ms),
                "--jitter",
                str(jitter_ms),
                definition.target,
            ],
        )
        return InjectionOutcome(
            restore=PumbaRestore(helper_container=helper),
            changes=[
                f"pumba {self._settings.pumba_image}: {delay_ms}ms (+/-{jitter_ms}ms) delay on "
                f"{definition.target} {interface}",
                f"sidecar {helper} holds the rule; it self-reverts after {duration}",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, PumbaRestore):
            raise FaultUsageError(f"dependency_latency cannot restore {state.kind}")
        if not self._docker.container_exists(state.helper_container):
            return [f"{state.helper_container} already gone; netem rule expired with it"]
        # Pumba reverts its own netem rules on SIGTERM, so stop before removing.
        self._docker.stop(state.helper_container)
        self._docker.remove(state.helper_container)
        return [f"pumba sidecar {state.helper_container} stopped; netem delay reverted"]


def _human_bytes(value: int) -> str:
    if value == 0:
        return "unlimited"
    if value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)}M"
    return f"{value}B"


def build_handlers(
    docker: DockerCli, compose: ComposeCli, settings: InjectorSettings
) -> dict[FaultClass, Fault]:
    """Every fault class T1.4 supports, wired to one docker layer."""
    handlers: list[Fault] = [
        ResourceExhaustionFault(docker),
        BadDeployFault(docker, compose, settings),
        DependencyLatencyFault(docker, settings),
        BadConfigFault(compose, settings),
    ]
    return {handler.fault_class: handler for handler in handlers}
