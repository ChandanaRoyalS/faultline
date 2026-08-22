"""Persisted record of what is currently broken (T1.4).

`status` and `stop --all` run in different processes from `start`, so the
restore data has to outlive the invocation that produced it. The file is
written atomically: a half-written state file is a world nobody can un-break.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from injector.models import ActiveInjection, InjectorState


class StateError(RuntimeError):
    """The state file exists but cannot be trusted."""


class StateStore:
    """Loads and saves the injector's active-injection record."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> InjectorState:
        if not self.path.exists():
            return InjectorState()
        try:
            return InjectorState.model_validate_json(self.path.read_text())
        except (ValidationError, json.JSONDecodeError) as exc:
            raise StateError(
                f"{self.path} is not readable injector state; inspect it by hand rather than "
                f"deleting it - it is the only record of what is still injected: {exc}"
            ) from exc

    def save(self, state: InjectorState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        tmp.write_text(state.model_dump_json(indent=2) + "\n")
        os.replace(tmp, self.path)

    def add(self, injection: ActiveInjection) -> None:
        state = self.load()
        state.active[injection.definition.id] = injection
        self.save(state)

    def remove(self, fault_id: str) -> None:
        state = self.load()
        state.active.pop(fault_id, None)
        self.save(state)
