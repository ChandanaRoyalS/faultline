"""State survives across invocations, or `stop --all` cannot un-break the world."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from evalharness.scenario import FaultClass
from injector.models import ActiveInjection, FaultDefinition, MemoryLimitRestore
from injector.state import StateError, StateStore


def _injection(fault_id: str = "mem-squeeze-recommendation") -> ActiveInjection:
    return ActiveInjection(
        definition=FaultDefinition(
            id=fault_id,
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="recommendation-service",
            description="squeeze",
            params={"memory": "64m"},
        ),
        started_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        restore=MemoryLimitRestore(
            container="recommendation-service", memory_bytes=838860800, memory_swap_bytes=-1
        ),
    )


def test_missing_state_file_is_an_empty_world(tmp_path: Path) -> None:
    assert StateStore(tmp_path / "nope.json").load().active == {}


def test_roundtrip_preserves_restore_data(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state" / "injections.json")
    store.add(_injection())

    restored = StateStore(store.path).load().active["mem-squeeze-recommendation"]
    assert isinstance(restored.restore, MemoryLimitRestore)
    assert restored.restore.memory_bytes == 838860800
    assert restored.definition.params == {"memory": "64m"}


def test_remove_is_idempotent(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "injections.json")
    store.add(_injection())
    store.remove("mem-squeeze-recommendation")
    store.remove("mem-squeeze-recommendation")

    assert store.load().active == {}


def test_corrupt_state_is_refused_rather_than_silently_reset(tmp_path: Path) -> None:
    path = tmp_path / "injections.json"
    path.write_text("{not json")
    with pytest.raises(StateError):
        StateStore(path).load()


def test_save_leaves_no_partial_file_behind(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "injections.json")
    store.add(_injection())

    assert [p.name for p in tmp_path.iterdir()] == ["injections.json"]
