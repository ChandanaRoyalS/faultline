"""The evidence archive (T2.3), hermetically.

What is being protected: `narrative.py` refuses a citation it cannot resolve, and resolution
goes through the envelope stored under a `result_id`. Postgres holds that envelope inline, and
until now held the only copy - so a reset database does not corrupt the record, it removes the
evidence under every citation ever made and leaves the reports unfalsifiable.

The archive is the second copy. These tests pin what it writes and where; the round trip
against a real S3-compatible server is in `tests/test_integration_archive.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from faultline.agents.trajectory import PostgresTrajectoryStore
from faultline.archive import (
    ENVELOPE_PREFIX,
    REPORT_PREFIX,
    InMemoryArchive,
    archive_trajectory,
    envelope_key,
    report_key,
)


@dataclass
class Call:
    result_id: str
    envelope: str


@dataclass
class Step:
    tool_call: Call | None = None


@dataclass
class Trajectory:
    id: str = "traj-1"
    steps: list[Step] = field(default_factory=list)


class Exploding:
    """An archive that is down, which is the case the ordering exists for."""

    def put(self, key: str, body: bytes, *, content_type: str = "") -> None:
        raise RuntimeError("object storage is unreachable")

    def get(self, key: str) -> bytes | None:
        return None


class Connection:
    """Enough of psycopg for `save` to commit. The database half is tested for real."""

    def __init__(self) -> None:
        self.commits = 0

    def cursor(self) -> Any:
        return self

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, *args: object, **kwargs: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


def test_keys_are_namespaced_by_what_they_hold() -> None:
    assert envelope_key("r-1") == f"{ENVELOPE_PREFIX}/r-1"
    assert report_key("inv-1") == f"{REPORT_PREFIX}/inv-1.md"


def test_an_envelope_is_archived_under_the_id_a_citation_resolves() -> None:
    """`result_id` is the handle the synthesizer cites and the validator looks up.

    Keying the archive by anything else would mean holding the evidence and being unable to
    answer the only question anyone asks of it.
    """
    archive = InMemoryArchive()
    trajectory = Trajectory(steps=[Step(Call("r-abc", "PromQL result: up == 1"))])

    written = archive_trajectory(trajectory, archive)

    assert written == [envelope_key("r-abc")]
    assert archive.get(envelope_key("r-abc")) == b"PromQL result: up == 1"


def test_the_bytes_are_the_envelope_verbatim() -> None:
    """`ToolCallRecord.envelope` is documented as "never re-rendered on read"."""
    envelope = "line one\n  line two with trailing space \n"
    archive = InMemoryArchive()

    archive_trajectory(Trajectory(steps=[Step(Call("r-1", envelope))]), archive)

    assert archive.get(envelope_key("r-1")) == envelope.encode()


def test_steps_without_a_tool_call_archive_nothing() -> None:
    archive = InMemoryArchive()

    assert archive_trajectory(Trajectory(steps=[Step(), Step()]), archive) == []
    assert archive.objects == {}


def test_the_in_memory_archive_stores_rather_than_discards() -> None:
    """A no-op double would let a test assert archiving happened while nothing was kept."""
    archive = InMemoryArchive()
    archive.put("k", b"v")
    assert archive.get("k") == b"v"
    assert archive.get("absent") is None


def test_a_failing_archive_never_costs_a_trajectory(caplog: Any) -> None:
    """The ordering is the design: commit first, copy second, and the copy is never fatal."""
    store = PostgresTrajectoryStore(Connection(), Exploding())
    trajectory = Trajectory(steps=[Step(Call("r-1", "evidence"))])

    with caplog.at_level(logging.WARNING):
        store._archive_envelopes(trajectory)

    assert "were not archived" in caplog.text
    assert "still authoritative" in caplog.text
