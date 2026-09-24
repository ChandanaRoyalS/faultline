"""The nine fault classes: T1.4's four and T7.0's five, each with an inject and a restore.

**Nine, measured.** The four are T1.4's. The five were each attempted live on the v2 world under
`evals/runs/PREREGISTRATION-T7.0.md` and admitted on the registered criteria (ADR-0043 addendum,
2026-09-24); each handler below does what its attempt did, with the parameters the attempt found
to matter carried as params rather than assumed. What a class *may* still gain is another
mechanism, which costs nothing: ADR-0010 draws that line and `resource_exhaustion` owns two.

**Five of the nine leave no change record, on purpose.** ADR-0019 has the injector write the
record an operator would have written; nobody records a pause, a cable pull, a bad key or a full
disk, and A1 measured that a flag flip leaves nothing either. Each handler says so with
`records_change`, and the engine reads it. The registered distinctness of every one of the five
rests in part on that emptiness - *no change recorded but the world broke* is the signal.

A class may own more than one mechanism - resource_exhaustion squeezes either
memory or CPU, bad_deploy ships either a bad build or a tag that resolves
nowhere - because the class is what a scenario is scored against, not how the
injector happens to produce it. Which mechanism runs is decided by the
definition's params, so the choice is visible in the catalog.

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
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, ConfigDict

from evalharness.scenario import FaultClass
from injector.docker import CommandError, ComposeCli, DockerCli
from injector.models import (
    ComposeServiceRestore,
    CorruptionRestore,
    CpuQuotaRestore,
    DiskFillRestore,
    FaultDefinition,
    FlagRestore,
    MemoryLimitRestore,
    NetworkRestore,
    PauseRestore,
    PumbaRestore,
    RestoreState,
    TargetKind,
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


def _is_cpu_quota(definition: FaultDefinition) -> bool:
    """Whether a resource_exhaustion definition squeezes CPU rather than memory.

    One predicate, called by both the mechanism dispatch and the target-name check
    in the catalog. Two copies would drift, and the drift would be silent: a
    definition validated against one mechanism and injected by the other.
    """
    return "cpus" in definition.params


class Fault(ABC):
    """One fault class: how to break the world this way, and how to put it back."""

    fault_class: ClassVar[FaultClass]
    records_change: ClassVar[bool] = True
    """Whether an operator would have written a change record for this mechanism (ADR-0019).

    True for every compose- and sidecar-mechanism class T1.4 built. False for T7.0's five: a
    pause, a disconnect, a bad key, a full disk and a flag flip leave nothing in this world's
    change history, and A1-A8b measured their distinctness on that emptiness.
    """

    @classmethod
    @abstractmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        """Whether this definition's mechanism addresses a container or a compose service."""

    @abstractmethod
    def inject(self, definition: FaultDefinition) -> InjectionOutcome: ...

    @abstractmethod
    def restore(self, state: RestoreState) -> list[str]:
        """Undo the injection. Must succeed when there is nothing left to undo."""


class _ComposeOverrideFault(Fault):
    """Shared machinery for faults that recreate a service under a generated override.

    The override is a file on disk rather than an in-memory edit, so the exact
    change is inspectable while the incident is live, and removing the file plus
    recreating the service is a complete, auditable rollback.
    """

    def __init__(self, compose: ComposeCli, settings: InjectorSettings) -> None:
        self._compose = compose
        self._settings = settings

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        return TargetKind.SERVICE

    def _write_override(self, definition: FaultDefinition, service_body: dict[str, object]) -> Path:
        path = self._settings.override_dir / f"{definition.id}.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Provenance goes in a comment, not a key: compose validates its schema and
        # rejects unknown top-level properties.
        header = (
            f"# generated by faultline-inject for fault {definition.id}\n"
            f"# reverted by: faultline-inject stop {definition.id}\n"
        )
        document = {"services": {definition.target: service_body}}
        path.write_text(header + yaml.safe_dump(document, sort_keys=False))
        return path

    def _apply_override(self, definition: FaultDefinition, service_body: dict[str, object]) -> Path:
        """Write the override and bring the service back under it. All or nothing."""
        path = self._write_override(definition, service_body)
        try:
            self._compose.recreate(definition.target, overrides=[path])
        except Exception:
            self._abandon_override(definition.target, path)
            raise
        return path

    def _abandon_override(self, service: str, path: Path) -> None:
        """Undo a half-applied override: no restore record will exist to do it later.

        Best effort - the caller needs to see the failure that got us here, not a
        second one raised out of the cleanup.
        """
        with contextlib.suppress(CommandError):
            self._compose.recreate(service)
        path.unlink(missing_ok=True)

    def _revert_override(self, service: str, override_file: str) -> list[str]:
        override = Path(override_file)
        # Recreate from the base compose files alone: whatever the override was
        # saying, the service comes back as the world defines it.
        self._compose.recreate(service)
        override.unlink(missing_ok=True)
        return [
            f"compose: {service} recreated from the base world definition",
            f"removed override {override}",
        ]

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, ComposeServiceRestore):
            raise FaultUsageError(f"{self.fault_class} cannot restore {state.kind}")
        return self._revert_override(state.service, state.override_file)


class ResourceExhaustionFault(_ComposeOverrideFault):
    """Starve a workload of a resource it needs: memory ceiling, or CPU quota.

    Two mechanisms, because the two resources are held in different places. A
    memory limit is a live property of a running container and `docker update`
    changes it in place. A CPU quota under compose is `deploy.resources.limits.
    cpus`, which compose only reads when it creates the container - so that one
    goes through a generated override and a recreate, like the other config faults.
    """

    fault_class = FaultClass.RESOURCE_EXHAUSTION

    def __init__(self, docker: DockerCli, compose: ComposeCli, settings: InjectorSettings) -> None:
        super().__init__(compose, settings)
        self._docker = docker

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        # The only class whose answer depends on the definition: the CPU quota goes
        # through compose, the memory limit goes straight at the container.
        return TargetKind.SERVICE if _is_cpu_quota(definition) else TargetKind.CONTAINER

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        if _is_cpu_quota(definition) and "memory" in definition.params:
            # Two resources squeezed at once is two incidents, and the scenario
            # would have no single answer to be scored against.
            raise FaultUsageError(
                f"{definition.id}: resource_exhaustion squeezes one resource at a time; "
                "drop either 'memory' or 'cpus'"
            )
        if _is_cpu_quota(definition):
            return self._inject_cpu_quota(definition)
        return self._inject_memory_limit(definition)

    def _inject_memory_limit(self, definition: FaultDefinition) -> InjectionOutcome:
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

    def _inject_cpu_quota(self, definition: FaultDefinition) -> InjectionOutcome:
        cpus = _str_param(definition, "cpus", "")
        if not cpus:
            raise FaultUsageError(f"{definition.id}: a cpu quota needs a non-empty cpus param")
        # Inspected before the override goes on, and through compose, because this
        # fault targets a service name and the container behind it is called
        # something else entirely.
        container = self._compose.container_id(definition.target)
        if container is None:
            raise FaultUsageError(
                f"{definition.id}: {definition.target} is not running, so there is no CPU quota "
                "to capture; bring the world up first"
            )
        original = self._docker.nano_cpus(container)
        path = self._apply_override(
            definition, {"deploy": {"resources": {"limits": {"cpus": cpus}}}}
        )
        return InjectionOutcome(
            restore=CpuQuotaRestore(
                service=definition.target, override_file=str(path), nano_cpus=original
            ),
            changes=[
                f"compose: {definition.target} cpu quota "
                f"{_human_cpus(original)} -> {cpus} (recreated to pick it up)",
                f"override written to {path}",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        match state:
            case MemoryLimitRestore():
                if not self._docker.container_exists(state.container):
                    return [f"{state.container} is gone; nothing to restore"]
                swap = str(state.memory_swap_bytes) if state.memory_swap_bytes != 0 else None
                self._docker.set_memory_limits(state.container, str(state.memory_bytes), swap)
                return [
                    f"docker update: {state.container} memory limit restored to "
                    f"{_human_bytes(state.memory_bytes)}"
                ]
            case CpuQuotaRestore():
                return [
                    *self._revert_override(state.service, state.override_file),
                    f"cpu quota back to the world's own value "
                    f"({_human_cpus(state.nano_cpus)} at inject time)",
                ]
            case _:
                raise FaultUsageError(f"resource_exhaustion cannot restore {state.kind}")


class BadDeployFault(_ComposeOverrideFault):
    """Ship a bad release: one that starts and fails on the hot path, or one that never starts.

    Both are the same image swap. A `server` param names a file in the stub build
    context, which means the image is one of ours and gets built here; without it
    the tag is deployed exactly as written, and a tag that resolves nowhere is the
    fault. Nothing else distinguishes them, so a definition cannot claim both to
    build an image and to point at one that does not exist.
    """

    fault_class = FaultClass.BAD_DEPLOY

    def __init__(self, docker: DockerCli, compose: ComposeCli, settings: InjectorSettings) -> None:
        super().__init__(compose, settings)
        self._docker = docker

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        image = _str_param(definition, "image", "")
        if not image:
            raise FaultUsageError(f"{definition.id}: bad_deploy needs an image param")
        server = _str_param(definition, "server", "")
        if server:
            return self._deploy_built_image(definition, image, server)

        # Declared, not inferred. A bare image swap has two opposite outcomes - the tag
        # resolves and the container starts (then misbehaves), or it resolves nowhere and
        # nothing starts - and the injector has to know which to treat as success.
        # Inferring it from the absence of a `server` param worked while only the second
        # kind existed and silently mislabels the first.
        expect_start = _str_param(definition, "expect_start", "")
        if expect_start not in ("yes", "no"):
            raise FaultUsageError(
                f"{definition.id}: a bad_deploy without a `server` param must declare "
                "expect_start: 'yes' (the image exists, so the container starts and then "
                "misbehaves) or 'no' (the tag resolves nowhere, so nothing starts)."
            )
        if expect_start == "no":
            return self._deploy_unresolvable_image(definition, image)
        return self._deploy_existing_image(definition, image)

    def _deploy_built_image(
        self, definition: FaultDefinition, image: str, server: str
    ) -> InjectionOutcome:
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

    def _deploy_existing_image(self, definition: FaultDefinition, image: str) -> InjectionOutcome:
        """Swap to an image that exists. The container starts; what it does then is the fault.

        No stop-first and no tolerated failure: this deploy is expected to succeed at the
        compose level, exactly as a real bad release does. Whatever goes wrong afterwards -
        wrong protocol, wrong resource profile, a crash loop - is the incident.
        """
        path = self._apply_override(definition, {"image": image})
        return InjectionOutcome(
            restore=ComposeServiceRestore(service=definition.target, override_file=str(path)),
            changes=[
                f"compose: {definition.target} recreated on {image}",
                "the image resolves, so the deploy itself succeeds - the fault is what the "
                "container does next",
                f"override written to {path}",
            ],
        )

    def _deploy_unresolvable_image(
        self, definition: FaultDefinition, image: str
    ) -> InjectionOutcome:
        # The old container comes down first, on purpose. Compose resolves every
        # image before it touches any container, so an unresolvable tag fails the
        # `up` with the healthy container still running - the deploy breaks and the
        # world does not, which is no fault at all. Stopping first is also what a
        # real rolling deploy does, and it makes the outage independent of how a
        # given compose version happens to order pull and recreate.
        self._compose.stop(definition.target)
        path = self._write_override(definition, {"image": image})
        try:
            self._compose.recreate(definition.target, overrides=[path])
        except CommandError:
            # This failure is the fault, not an error to roll back from. The
            # override stays: it is the evidence of why the service is down, and
            # the thing `stop` has to remove.
            return InjectionOutcome(
                restore=ComposeServiceRestore(service=definition.target, override_file=str(path)),
                changes=[
                    f"compose: {definition.target} stopped, then pointed at {image}",
                    f"the tag does not resolve, so nothing came back up - "
                    f"{definition.target} is dark",
                    f"override written to {path}",
                ],
            )
        # The tag resolved, so the service is up and healthy on it and no fault was
        # injected. Silence here would be worse than a failure: a scenario would be
        # scored against a world nothing is wrong with.
        self._abandon_override(definition.target, path)
        raise FaultUsageError(
            f"{definition.id}: {image} resolved and {definition.target} started on it, so no "
            "fault was injected; the tag has been published since this definition was written - "
            "pick one that does not exist"
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


SIDECAR_SETTLE_SECONDS = 4
"""How long to let a detached sidecar live before believing it started."""


class DependencyLatencyFault(Fault):
    """Delay a container's network traffic with tc netem, driven by pumba."""

    fault_class = FaultClass.DEPENDENCY_LATENCY

    def __init__(self, docker: DockerCli, settings: InjectorSettings) -> None:
        self._docker = docker
        self._settings = settings

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        return TargetKind.CONTAINER

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
        self._require_sidecar_alive(helper)
        return InjectionOutcome(
            restore=PumbaRestore(helper_container=helper),
            changes=[
                f"pumba {self._settings.pumba_image}: {delay_ms}ms (+/-{jitter_ms}ms) delay on "
                f"{definition.target} {interface}",
                f"sidecar {helper} holds the rule; it self-reverts after {duration}",
            ],
        )

    def _require_sidecar_alive(self, helper: str) -> None:
        """`docker run --detach` returns as soon as the container is created, not when it works.

        Pumba enumerates every container on the host to find its target and exits if any of
        them references an image that is no longer present locally (ADR-0007). That happens
        at startup, before it touches the target, so the sidecar is created, dies within a
        second, and the injection reports success. Measured: a latency fault ran for
        thirteen minutes with no netem rule applied, `faultline-inject status` showing it
        active throughout, and the recorder wrote a bundle of a perfectly healthy world.

        A fault that failed to apply has to fail the injection. Silence here is the most
        expensive failure the injector can produce, because everything downstream of it
        looks correct.
        """
        time.sleep(SIDECAR_SETTLE_SECONDS)
        if self._docker.is_running(helper):
            return
        logs = self._docker.logs(helper) or "(the sidecar produced no output)"
        # Take the corpse with us: leaving it would make the next injection's cleanup
        # look like it removed a working sidecar.
        self._docker.remove(helper)
        raise FaultUsageError(
            f"the pumba sidecar {helper} exited within {SIDECAR_SETTLE_SECONDS}s, so no "
            "netem rule was applied and no delay exists. The fault has NOT been injected.\n"
            f"--- {helper} logs ---\n{logs}\n"
            "Pumba dies at startup if any running container references an image that is no "
            "longer present locally - check for orphaned image references and recreate the "
            "affected services."
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


# --- T7.0's five ----------------------------------------------------------------------------


class FeatureFlagFault(Fault):
    """Flip a flag in the flag daemon's file; it reloads and the flagged path fails (A1).

    The file is bind-mounted from the world into flagd, so a write here is the whole injection.
    Nothing is recreated and nothing is recorded. The flag and the variant are params; the
    file is a path relative to the world directory, defaulting to where the demo keeps it.
    """

    fault_class = FaultClass.FEATURE_FLAG
    records_change = False

    def __init__(self, settings: InjectorSettings) -> None:
        self._settings = settings

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        # The target names the service the flag breaks - the culprit the scenario is scored
        # against - and it is a compose service name, not the flag daemon's.
        return TargetKind.SERVICE

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        flag = _str_param(definition, "flag", "")
        variant = _str_param(definition, "variant", "on")
        if not flag:
            raise FaultUsageError(f"{definition.id}: feature_flag needs a flag param")
        path = self._settings.world_dir / _str_param(
            definition, "flag_file", "src/flagd/demo.flagd.json"
        )
        previous = _set_default_variant(path, flag, variant)
        if previous is None:
            raise FaultUsageError(f"{definition.id}: {path} defines no flag {flag!r}")
        if variant == previous:
            raise FaultUsageError(
                f"{definition.id}: {flag} is already {variant!r}; flipping it would inject nothing"
            )
        return InjectionOutcome(
            restore=FlagRestore(flag_file=str(path), flag=flag, previous_variant=previous),
            changes=[
                f"flagd: {flag} defaultVariant {previous!r} -> {variant!r} in {path}",
                "no compose change and no change record: the flag daemon reloads its own file",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, FlagRestore):
            raise FaultUsageError(f"feature_flag cannot restore {state.kind}")
        path = Path(state.flag_file)
        if not path.is_file():
            return [f"{path} is gone; nothing to restore"]
        previous = _set_default_variant(path, state.flag, state.previous_variant)
        if previous == state.previous_variant:
            return [f"flagd: {state.flag} already {state.previous_variant!r}"]
        return [f"flagd: {state.flag} defaultVariant restored to {state.previous_variant!r}"]


def _set_default_variant(path: Path, flag: str, variant: str) -> str | None:
    """Set one flag's `defaultVariant`, returning what it was; None if the flag is not there.

    A whole-document rewrite with the two-space indentation the demo's file uses, so a diff of
    the file shows exactly one line moved.
    """
    document = json.loads(path.read_text())
    entry = (document.get("flags") or {}).get(flag)
    if not isinstance(entry, dict):
        return None
    previous = str(entry.get("defaultVariant", ""))
    if variant not in (entry.get("variants") or {}):
        raise FaultUsageError(f"{flag} has no variant {variant!r} in {path}")
    entry["defaultVariant"] = variant
    path.write_text(json.dumps(document, indent=2) + "\n")
    return previous


class ProcessFreezeFault(Fault):
    """`docker pause` the target: its socket stays open and nothing answers (A2).

    Callers hang to their deadlines rather than fail; everything behind them goes silent. The
    unpause is instantaneous and the recovery is not - every hung request wakes at once and the
    world takes about six minutes to go quiet - which is a property of the class and is said in
    the changes so a scenario's recovery clock allows for it.
    """

    fault_class = FaultClass.PROCESS_FREEZE
    records_change = False

    def __init__(self, docker: DockerCli) -> None:
        self._docker = docker

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        return TargetKind.CONTAINER

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        container = definition.target
        if not self._docker.is_running(container):
            raise FaultUsageError(f"{definition.id}: {container} is not running; nothing to freeze")
        self._docker.pause(container)
        if not self._docker.is_paused(container):
            raise FaultUsageError(
                f"{definition.id}: docker pause returned but {container} is not paused. "
                "The fault has NOT been injected."
            )
        return InjectionOutcome(
            restore=PauseRestore(container=container),
            changes=[
                f"docker pause: {container} frozen; its socket accepts and nothing answers",
                "callers will hang to their deadlines; expect ~6 min from unpause to quiet",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, PauseRestore):
            raise FaultUsageError(f"process_freeze cannot restore {state.kind}")
        if not self._docker.container_exists(state.container):
            return [f"{state.container} is gone; nothing to unpause"]
        if not self._docker.is_paused(state.container):
            return [f"{state.container} is not paused; nothing to restore"]
        self._docker.unpause(state.container)
        return [
            f"docker unpause: {state.container} resumed",
            "the requests that hung will wake together; a second error wave is the recovery",
        ]


class NetworkPartitionFault(Fault):
    """Cut the target from its network; its process runs and reaches nothing (A3).

    Callers hang exactly as for a freeze - packets on established connections are dropped, not
    reset. What is captured before the cut is the container's aliases on the network, because
    `docker network connect` does not restore them on its own, and a container reachable only
    by its container name is a second fault on a world where service and container names
    differ. The network is a param: this handler assumes nothing about what a world calls it.
    """

    fault_class = FaultClass.NETWORK_PARTITION
    records_change = False

    def __init__(self, docker: DockerCli) -> None:
        self._docker = docker

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        return TargetKind.CONTAINER

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        container = definition.target
        network = _str_param(definition, "network", "")
        if not network:
            raise FaultUsageError(f"{definition.id}: network_partition needs a network param")
        attached = self._docker.network_aliases(container)
        if network not in attached:
            raise FaultUsageError(
                f"{definition.id}: {container} is not on network {network!r} "
                f"(it is on {sorted(attached) or 'nothing'})"
            )
        aliases = attached[network]
        self._docker.network_disconnect(network, container)
        if network in self._docker.network_aliases(container):
            raise FaultUsageError(
                f"{definition.id}: docker network disconnect returned but {container} is still "
                f"on {network}. The fault has NOT been injected."
            )
        return InjectionOutcome(
            restore=NetworkRestore(container=container, network=network, aliases=aliases),
            changes=[
                f"docker network disconnect: {container} cut from {network} "
                f"(aliases captured: {', '.join(aliases) or 'none'})",
                "callers will hang, not fail; the target keeps running and logs that it cannot "
                "reach anything; expect ~6 min from reconnect to quiet",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, NetworkRestore):
            raise FaultUsageError(f"network_partition cannot restore {state.kind}")
        if not self._docker.container_exists(state.container):
            return [f"{state.container} is gone; nothing to reconnect"]
        if state.network in self._docker.network_aliases(state.container):
            return [f"{state.container} is already on {state.network}; nothing to restore"]
        self._docker.network_connect(state.network, state.container, state.aliases)
        return [
            f"docker network connect: {state.container} back on {state.network} as "
            f"{', '.join(state.aliases) or state.container}",
            "the requests that hung will wake together; a second error wave is the recovery",
        ]


CORRUPTION_SWEEP = (
    'local c="0" local n=0 '
    'repeat local r=redis.call("SCAN",c,"COUNT",1000) c=r[1] '
    "for _,k in ipairs(r[2]) do "
    'if redis.call("TYPE",k).ok=="hash" then redis.call("HSET",k,ARGV[1],ARGV[2]) n=n+1 end '
    'end until c=="0" return n'
)
"""One atomic sweep: set every hash's `ARGV[1]` field to `ARGV[2]`, returning the count.

A4 measured that a store's live values are written and read within milliseconds and then
abandoned, so a sweep has to repeat faster than the store's clients cycle a key or it corrupts
only dead ones (A4 at 5s paged nothing; A4b at 50ms paged). The loop below runs this on an
interval inside the container, so the corruption is continuous rather than a single pass.
"""

CORRUPTION_LOOP = (
    'i=0; while [ ! -f "$STOP" ]; do '
    '{cli} EVAL "$SCRIPT" 0 "$FIELD" "$BYTES" >/dev/null 2>&1; '
    'i=$((i+1)); sleep {interval}; done; echo "swept $i times"'
)
"""The shell that carries the sweep. Fed to `sh -c` as one argument via docker exec, so no
quoting crosses a shell of ours - the failure that voided an attempt on 2026-09-23. It exits
when the stop file appears, which restore touches."""


class DatastoreCorruptionFault(Fault):
    """Make the target datastore's contents unparseable while the store stays healthy (A4b).

    The store answers, and what it returns cannot be decoded. A background loop inside the
    container overwrites a chosen hash field of every key with bytes the client cannot parse,
    on an interval, because the store's live values turn over in milliseconds. Restore stops the
    loop and flushes the store; its clients make fresh values.
    """

    fault_class = FaultClass.DATASTORE_CORRUPTION
    records_change = False

    def __init__(self, docker: DockerCli) -> None:
        self._docker = docker

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        return TargetKind.CONTAINER

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        container = definition.target
        cli = _str_param(definition, "cli", "valkey-cli")
        field = _str_param(definition, "field", "cart")
        payload = _str_param(definition, "payload", r"\xff\xff\xff\xff")
        interval = _str_param(definition, "interval", "0.05")
        stop_file = f"/tmp/faultline-{definition.id}.stop"
        if not self._docker.is_running(container):
            raise FaultUsageError(
                f"{definition.id}: {container} is not running; nothing to corrupt"
            )
        # Verify one sweep runs and takes before starting the loop: A4's first run corrupted
        # nothing and reported success because its command never ran (2026-09-23).
        probe = self._docker.exec(
            container,
            [cli, "EVAL", CORRUPTION_SWEEP, "0", field, payload],
            check=False,
        )
        if probe.returncode != 0:
            raise FaultUsageError(
                f"{definition.id}: the corrupting EVAL failed on {container}, so nothing was "
                f"corrupted. The fault has NOT been injected.\n{probe.stdout}{probe.stderr}"
            )
        script = CORRUPTION_LOOP.format(cli=cli, interval=interval)
        self._docker.exec(
            container,
            [
                "sh",
                "-c",
                script,
                "faultline",
                CORRUPTION_SWEEP,
                field,
                payload,
                stop_file,
            ],
            detach=True,
        )
        return InjectionOutcome(
            restore=CorruptionRestore(
                container=container, stop_file=stop_file, cli=cli, flush=True
            ),
            changes=[
                f"{cli} on {container}: every hash's {field!r} field set to unparseable bytes, "
                f"swept every {interval}s (first sweep verified: {probe.stdout.strip()} keys)",
                "no change record: the store is healthy and its contents are wrong",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, CorruptionRestore):
            raise FaultUsageError(f"datastore_corruption cannot restore {state.kind}")
        if not self._docker.container_exists(state.container):
            return [f"{state.container} is gone; the corruption went with it"]
        # Stop the loop first, or the flush races it and fresh keys get re-corrupted.
        self._docker.exec(state.container, ["touch", state.stop_file], check=False)
        changes = [f"{state.container}: stop file placed; the corruption loop will end"]
        if state.flush:
            self._docker.exec(state.container, [state.cli, "FLUSHALL"], check=False)
            changes.append(f"{state.cli} FLUSHALL: every corrupted value discarded")
        return changes


class DiskFillFault(Fault):
    """Fill the target's only writable data directory to capacity (A8b).

    A broker whose log directory cannot be written halts and crashloops against it. The
    directory is read off the running container - A8 filled a path the target never used, to
    the byte, because the path was assumed - and the fill is a single `dd` that stops at *no
    space left*. Restore removes the file; if the container is crashlooping too fast for exec
    to land, the fallback recreates the service (discarding the fill), then restarts whatever
    stopped consuming, because this world's consumers do not reconnect on their own (T7.27).
    """

    fault_class = FaultClass.DISK_FILL
    records_change = False

    def __init__(self, docker: DockerCli, compose: ComposeCli) -> None:
        self._docker = docker
        self._compose = compose

    @classmethod
    def target_kind(cls, definition: FaultDefinition) -> TargetKind:
        return TargetKind.CONTAINER

    def inject(self, definition: FaultDefinition) -> InjectionOutcome:
        container = definition.target
        service = _str_param(definition, "service", "")
        if not service:
            raise FaultUsageError(f"{definition.id}: disk_fill needs a service param for recovery")
        directory = _str_param(definition, "directory", "")
        if not directory:
            raise FaultUsageError(
                f"{definition.id}: disk_fill needs a directory param, read off the running broker "
                "(e.g. its log.dirs), not assumed"
            )
        restart_after = [r for r in _str_param(definition, "restart_after", "").split(",") if r]
        if not self._docker.is_running(container):
            raise FaultUsageError(f"{definition.id}: {container} is not running; nothing to fill")
        size_kib, used_kib, mount = self._docker.disk_usage(container, directory)
        # The directory must be the mount point, or dd fills a filesystem the broker shares with
        # the host and the safety argument (a size-capped tmpfs) does not hold.
        if mount != directory:
            raise FaultUsageError(
                f"{definition.id}: {directory} is not a mount point inside {container} "
                f"(it sits on {mount}); aim the fill at the capped filesystem, not a dir on it"
            )
        fill_file = f"{directory.rstrip('/')}/faultline-{definition.id}.fill"
        count = max(1, (size_kib // 1024) + 8)  # MiB, comfortably over capacity
        result = self._docker.exec(
            container,
            ["dd", "if=/dev/zero", f"of={fill_file}", "bs=1M", f"count={count}"],
            check=False,
        )
        no_space = "no space left" in (result.stdout + result.stderr).lower()
        if not no_space:
            self._docker.exec(container, ["rm", "-f", fill_file], check=False)
            raise FaultUsageError(
                f"{definition.id}: dd did not run the filesystem out of space "
                f"({mount} is {size_kib // 1024}MiB, {used_kib // 1024}MiB used). "
                "The directory is not the capped one, or it has more room than expected. "
                "The fault has NOT been injected."
            )
        return InjectionOutcome(
            restore=DiskFillRestore(
                container=container,
                service=service,
                fill_file=fill_file,
                restart_after=restart_after,
            ),
            changes=[
                f"dd on {container}: {mount} filled to capacity (no space left on device)",
                "the broker will halt and crashloop against the full directory; no change record",
            ],
        )

    def restore(self, state: RestoreState) -> list[str]:
        if not isinstance(state, DiskFillRestore):
            raise FaultUsageError(f"disk_fill cannot restore {state.kind}")
        if not self._docker.container_exists(state.container):
            return [f"{state.container} is gone; the fill went with it"]
        changes: list[str] = []
        removed = self._docker.exec(state.container, ["rm", "-f", state.fill_file], check=False)
        if removed.returncode == 0:
            changes.append(f"{state.container}: removed {state.fill_file}")
        else:
            # Crashlooping too fast for exec to land: recreate the service, discarding the fill.
            self._compose.recreate(state.service)
            changes.append(
                f"could not reach {state.container} to delete the fill; recreated {state.service}, "
                "which discards the filled directory"
            )
        for consumer in state.restart_after:
            self._docker.restart(consumer)
        if state.restart_after:
            changes.append(
                f"restarted {', '.join(state.restart_after)} (they do not reconnect on their own); "
                "expect ~4 min of duplicate-key errors on any that kept uncommitted offsets"
            )
        return changes


def _human_bytes(value: int) -> str:
    if value == 0:
        return "unlimited"
    if value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)}M"
    return f"{value}B"


def _human_cpus(nano_cpus: int) -> str:
    if nano_cpus == 0:
        return "unlimited"
    return f"{nano_cpus / 1_000_000_000:g}"


FAULT_TYPES: tuple[type[Fault], ...] = (
    ResourceExhaustionFault,
    BadDeployFault,
    DependencyLatencyFault,
    BadConfigFault,
    FeatureFlagFault,
    ProcessFreezeFault,
    NetworkPartitionFault,
    DatastoreCorruptionFault,
    DiskFillFault,
)
"""Every handler class, for the questions that can be answered without a docker layer."""


def target_kind(definition: FaultDefinition) -> TargetKind:
    """Which of the world's two names this definition's mechanism will address."""
    for fault_type in FAULT_TYPES:
        if fault_type.fault_class is definition.fault_class:
            return fault_type.target_kind(definition)
    raise FaultUsageError(f"{definition.id}: no handler for fault class {definition.fault_class}")


def build_handlers(
    docker: DockerCli, compose: ComposeCli, settings: InjectorSettings
) -> dict[FaultClass, Fault]:
    """Every fault class, T1.4's four and T7.0's five, wired to one docker layer."""
    handlers: list[Fault] = [
        ResourceExhaustionFault(docker, compose, settings),
        BadDeployFault(docker, compose, settings),
        DependencyLatencyFault(docker, settings),
        BadConfigFault(compose, settings),
        FeatureFlagFault(settings),
        ProcessFreezeFault(docker),
        NetworkPartitionFault(docker),
        DatastoreCorruptionFault(docker),
        DiskFillFault(docker, compose),
    ]
    return {handler.fault_class: handler for handler in handlers}
