"""Test-suite invariants no individual test should have to remember.

`make check` is hermetic by contract: no docker daemon, no containers, no network.

That contract has now been broken twice, both times identically. A new pre-flight gate
landed in `evalharness.rehearse`; the tests exercising its neighbours did not mock it;
the suite kept passing because a daemon happened to be running on the machine. The first
fix mocked the new collaborator, which repaired the instance and left the class of bug
untouched - the next gate reintroduced it within hours, and one test spent that whole
window passing on an unrelated gate's abort message.

So the guard is structural rather than per-test. Every subprocess call made from
`evalharness.rehearse` raises, naming the test and the command it tried to run. A test
that needs docker behaviour says what docker returns; a test that reaches it by accident
fails immediately, whether or not a daemon is up.

Mock the wrapper, not the subprocess: `container_uptimes`, `container_memory_usage`,
`orphaned_image_references`, `injector` and friends. A test should state what the world
looks like, not how the code asks.
"""

from __future__ import annotations

from typing import Any, NoReturn

import pytest

from evalharness import rehearse


class _NoLiveSubprocess:
    """Stands in for the `subprocess` module as `evalharness.rehearse` sees it."""

    def __init__(self, test_id: str) -> None:
        self._test_id = test_id

    def run(self, args: Any = None, *rest: Any, **kwargs: Any) -> NoReturn:
        printable = " ".join(str(a) for a in args) if isinstance(args, (list, tuple)) else str(args)
        raise AssertionError(
            f"{self._test_id} reached a real subprocess from evalharness.rehearse:\n"
            f"    {printable}\n\n"
            "The suite is hermetic by contract, so this is an unmocked collaborator "
            "rather than a missing daemon. Mock the function wrapping this call - "
            "container_uptimes, container_memory_usage, orphaned_image_references, "
            "injector - so the test states what the world returns instead of how it "
            "is asked."
        )

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"{self._test_id} touched subprocess.{name} from evalharness.rehearse. "
            "The suite is hermetic by contract; mock the collaborator instead."
        )


@pytest.fixture(autouse=True)
def _no_live_subprocess(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any live subprocess from the rehearsal module."""
    monkeypatch.setattr(rehearse, "subprocess", _NoLiveSubprocess(request.node.nodeid))
