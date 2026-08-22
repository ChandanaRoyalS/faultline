"""Start, stop and account for injections (T1.4).

The engine is the part that holds the invariants the CLI is judged on: never
lose the data needed to undo a fault, never inject the same fault twice over
its own restore record, and always be able to get back to a clean world.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from injector.catalog import CATALOG, by_id
from injector.docker import CommandError, CommandRunner, ComposeCli, DockerCli, SubprocessRunner
from injector.faults import Fault, build_handlers
from injector.models import ActiveInjection, FaultDefinition
from injector.settings import InjectorSettings
from injector.state import StateStore


class InjectorError(RuntimeError):
    """Something the operator can fix, reported without a traceback."""


class StartResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    injection: ActiveInjection
    changes: list[str]


class StopResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fault_id: str
    was_active: bool
    changes: list[str] = []
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


class Engine:
    """Applies faults to the world and remembers them across invocations."""

    def __init__(
        self,
        settings: InjectorSettings,
        runner: CommandRunner | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.settings = settings
        runner = runner if runner is not None else SubprocessRunner()
        docker = DockerCli(runner)
        compose = ComposeCli(runner, settings)
        self._handlers = build_handlers(docker, compose, settings)
        self._store = StateStore(settings.state_file)
        self._clock = clock

    @property
    def catalog(self) -> tuple[FaultDefinition, ...]:
        return CATALOG

    def active(self) -> dict[str, ActiveInjection]:
        return self._store.load().active

    def _handler_for(self, definition: FaultDefinition) -> Fault:
        handler = self._handlers.get(definition.fault_class)
        if handler is None:
            raise InjectorError(f"no handler for fault class {definition.fault_class}")
        return handler

    def start(self, fault_id: str) -> StartResult:
        definition = by_id(fault_id)
        if definition is None:
            raise InjectorError(f"unknown fault {fault_id!r}; `faultline-inject list` shows them")
        if fault_id in self.active():
            # Injecting twice would overwrite the restore record with post-fault
            # values and strand the world in the broken state permanently.
            raise InjectorError(f"{fault_id} is already active; stop it first")

        outcome = self._handler_for(definition).inject(definition)
        injection = ActiveInjection(
            definition=definition, started_at=self._clock(), restore=outcome.restore
        )
        self._store.add(injection)
        return StartResult(injection=injection, changes=outcome.changes)

    def stop(self, fault_id: str) -> StopResult:
        """Revert one fault. Stopping something inactive succeeds: reset must be safe to repeat."""
        injection = self.active().get(fault_id)
        if injection is None:
            return StopResult(fault_id=fault_id, was_active=False, changes=["not active"])

        try:
            changes = self._handler_for(injection.definition).restore(injection.restore)
        except (CommandError, InjectorError) as exc:
            # Keep the state entry: the fault is still applied, and the operator
            # needs the restore data to try again.
            return StopResult(fault_id=fault_id, was_active=True, error=str(exc))

        self._store.remove(fault_id)
        return StopResult(fault_id=fault_id, was_active=True, changes=changes)

    def stop_all(self) -> Sequence[StopResult]:
        """Revert everything, newest first, and keep going if one fails."""
        newest_first = sorted(self.active().values(), key=lambda i: i.started_at, reverse=True)
        return [self.stop(injection.definition.id) for injection in newest_first]
