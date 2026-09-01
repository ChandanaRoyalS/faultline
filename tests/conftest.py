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

T2.1 and T2.2 added two more ways out of the process - Redis and Postgres - and the same
trap with them: both run locally on a development machine, so a test that reaches one would
pass here and fail in CI. Guarded the same way and for the same reason, below. Substitute at
the seams the code already has (`EpisodeLog`, `EventStream`, `IncidentStore`, `EventSource`),
never at the client.

T3.2 adds the fourth and worst: **the model**. A test that reached it would not merely be
non-hermetic - it would be slow, non-deterministic, and billed, and it would fail on a machine
with no key in a way that looks like the test being wrong. `DeterministicModel` is the only
model the suite ever touches, and the guard below makes that true by construction rather than
by discipline.

T2.3's integration tests are the one exemption, and it is narrow: a test carrying the
`integration` marker may reach a real Redis and a real Postgres, because reaching them is the
entire point - they are containers testcontainers started, not a daemon that happened to be
running. The marker is deselected from `make check` by `addopts`, so the hermetic contract is
unchanged for every test that has not asked. **The new way to get this wrong is to mark a test
`integration` to quiet the guard and then never run it**, which is why CI runs the marked
selection as its own job rather than leaving it to whoever remembers `make test-integration`.
"""

from __future__ import annotations

from typing import Any, NoReturn

import psycopg
import pytest
import redis

from evalharness import rehearse
from faultline.agents import model


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


def _reaches_real_services_on_purpose(request: pytest.FixtureRequest) -> bool:
    """A test marked `integration` owns a container it started, not a daemon it stumbled on."""
    return request.node.get_closest_marker("integration") is not None


def _refuse(test_id: str, what: str, seams: str) -> NoReturn:
    raise AssertionError(
        f"{test_id} tried to reach {what}.\n\n"
        "The suite is hermetic by contract, so this is an unmocked collaborator rather than "
        f"a missing service - and both Redis and Postgres often run on a development "
        f"machine, so this would have passed here and failed in CI. Substitute at the seam "
        f"instead: {seams}."
    )


@pytest.fixture(autouse=True)
def _no_live_redis(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any command sent to a real Redis.

    Patched at `execute_command`, which every redis-py call funnels through, so constructing
    a client stays free - `redis.from_url` connects lazily and module import must not need a
    server.
    """
    if _reaches_real_services_on_purpose(request):
        return

    def refuse(self: Any, *args: Any, **kwargs: Any) -> NoReturn:
        command = " ".join(str(a) for a in args[:2])
        _refuse(
            request.node.nodeid,
            f"a real Redis ({command})",
            "faultline.ingest.dedupe.InMemoryEpisodeLog, "
            "faultline.ingest.stream.RecordingEventStream, "
            "faultline.orchestrator.consumer.ReplayEventSource",
        )

    monkeypatch.setattr(redis.Redis, "execute_command", refuse)


@pytest.fixture(autouse=True)
def _no_live_postgres(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any attempt to open a Postgres connection."""
    if _reaches_real_services_on_purpose(request):
        return

    def refuse(*args: Any, **kwargs: Any) -> NoReturn:
        _refuse(
            request.node.nodeid,
            "a real Postgres (psycopg.connect)",
            "faultline.orchestrator.store.InMemoryIncidentStore",
        )

    monkeypatch.setattr(psycopg, "connect", refuse)


@pytest.fixture(autouse=True)
def _no_live_model(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any attempt to construct or call a real model client.

    Patched on the boundary rather than on the SDK, so it holds whether or not the optional
    `faultline[agents]` extra is installed - a guard that only fires when a dependency happens
    to be present is a guard that passes for the wrong reason on a clean machine.
    """

    def refuse(*args: Any, **kwargs: Any) -> NoReturn:
        _refuse(
            request.node.nodeid,
            "a real language model (faultline.agents.model.AnthropicModel)",
            "faultline.agents.model.DeterministicModel",
        )

    monkeypatch.setattr(model, "AnthropicModel", refuse)

    # The judge brings its own client (T4.4), so the guard has to cover it too - otherwise a
    # test could reach a real provider through the one boundary nobody thought to patch.
    from evalharness import judge as judge_module

    monkeypatch.setattr(judge_module, "JudgeModel", refuse)
