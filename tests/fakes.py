"""A command runner that records argv instead of touching Docker.

The injector's whole job is issuing exactly the right commands, so the tests
assert on argv. Nothing here starts a container: `make check` passes on a
laptop with no world running, which is the point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from injector.docker import CommandError, CommandResult


@dataclass(frozen=True, slots=True)
class RecordedCall:
    args: tuple[str, ...]
    cwd: Path | None
    check: bool


@dataclass
class FakeRunner:
    """Answers commands from canned output, keyed by a substring of the joined argv."""

    stdout: dict[str, str] = field(default_factory=dict)
    returncodes: dict[str, int] = field(default_factory=dict)
    calls: list[RecordedCall] = field(default_factory=list)

    def run(
        self, args: Sequence[str], *, cwd: Path | None = None, check: bool = True
    ) -> CommandResult:
        joined = " ".join(args)
        self.calls.append(RecordedCall(args=tuple(args), cwd=cwd, check=check))
        stdout = next((v for k, v in self.stdout.items() if k in joined), "")
        returncode = next((v for k, v in self.returncodes.items() if k in joined), 0)
        result = CommandResult(args=tuple(args), returncode=returncode, stdout=stdout, stderr="")
        if check and returncode != 0:
            raise CommandError(result)
        return result

    def argv(self, *tokens: str) -> tuple[str, ...]:
        """The single recorded call containing all of `tokens`; fails loudly if not unique."""
        matches = [c.args for c in self.calls if all(t in c.args for t in tokens)]
        assert len(matches) == 1, f"expected one call with {tokens}, got {matches}"
        return matches[0]

    def called(self, *tokens: str) -> bool:
        return any(all(t in c.args for t in tokens) for c in self.calls)
