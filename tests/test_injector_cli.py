"""The CLI contract: what an operator sees, and what exit code a script gets.

Every test drives the real engine over a fake docker, so `make check` needs no
world - and the state file is a real file, because the point of these tests is
that separate invocations agree about what is broken.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from injector.cli import main
from injector.engine import Engine
from injector.models import MemoryLimitRestore
from injector.settings import InjectorSettings
from tests.fakes import FakeRunner


@pytest.fixture
def settings(tmp_path: Path) -> InjectorSettings:
    return InjectorSettings(
        world_dir=tmp_path / "world",
        state_dir=tmp_path / ".faultline",
        ffs_stub_context=tmp_path / "compose" / "ffs-stub",
    )


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner(stdout={"inspect": "838860800 -1\n"})


def make_engine(settings: InjectorSettings, runner: FakeRunner, minute: int = 0) -> Engine:
    """A fresh engine over the same state file - i.e. a separate CLI invocation."""
    return Engine(
        settings, runner=runner, clock=lambda: datetime(2026, 8, 22, 12, minute, tzinfo=UTC)
    )


def test_list_shows_every_fault_with_its_metadata(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["list"], engine=make_engine(settings, runner)) == 0

    out = capsys.readouterr().out
    for definition in make_engine(settings, runner).catalog:
        assert definition.id in out
    assert "memory=48m" in out
    assert "cpus=0.05" in out
    assert "[ACTIVE]" not in out


def test_start_prints_what_changed_and_how_to_undo_it(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["start", "recommendation-memory-squeeze"], engine=make_engine(settings, runner)) == 0
    )

    out = capsys.readouterr().out
    assert "injected recommendation-memory-squeeze (resource_exhaustion)" in out
    assert "800M -> 48m" in out
    assert "faultline-inject stop recommendation-memory-squeeze" in out


def test_status_reads_state_written_by_an_earlier_invocation(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["start", "cart-dependency-latency"], engine=make_engine(settings, runner))
    capsys.readouterr()

    assert main(["status"], engine=make_engine(settings, runner)) == 0
    out = capsys.readouterr().out
    assert "1 active injection(s)" in out
    assert "cart-dependency-latency" in out
    assert "faultline-pumba-cart-dependency-latency" in out


def test_status_is_quiet_on_a_healthy_world(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["status"], engine=make_engine(settings, runner)) == 0
    assert capsys.readouterr().out.strip() == "no active injections"


def test_list_marks_what_is_currently_injected(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["start", "cart-redis-misconfig"], engine=make_engine(settings, runner))
    capsys.readouterr()

    main(["list"], engine=make_engine(settings, runner))
    out = capsys.readouterr().out
    assert "cart-redis-misconfig  [ACTIVE]" in out


def test_stop_reverts_and_clears_the_state(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["start", "recommendation-memory-squeeze"], engine=make_engine(settings, runner))
    runner.calls.clear()
    capsys.readouterr()

    assert (
        main(["stop", "recommendation-memory-squeeze"], engine=make_engine(settings, runner)) == 0
    )
    assert runner.argv("update")[3] == "838860800", "the pre-fault limit, not a guess"
    assert make_engine(settings, runner).active() == {}


def test_stopping_an_inactive_fault_is_a_successful_no_op(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["stop", "recommendation-memory-squeeze"], engine=make_engine(settings, runner))

    assert code == 0, "reset must be safe to repeat; an unbroken world is not an error"
    assert "not active" in capsys.readouterr().out
    assert not runner.called("update")


def test_stop_all_reverts_everything_newest_first(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["start", "recommendation-memory-squeeze"], engine=make_engine(settings, runner, minute=0))
    main(["start", "cart-dependency-latency"], engine=make_engine(settings, runner, minute=5))
    runner.calls.clear()
    capsys.readouterr()

    assert main(["stop", "--all"], engine=make_engine(settings, runner)) == 0

    out = capsys.readouterr().out
    assert out.index("cart-dependency-latency") < out.index("recommendation-memory-squeeze")
    assert make_engine(settings, runner).active() == {}


def test_stop_all_on_a_clean_world_is_a_no_op(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["stop", "--all"], engine=make_engine(settings, runner)) == 0
    assert "no active injections" in capsys.readouterr().out


def test_a_failed_revert_keeps_the_fault_in_state_for_a_retry(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["start", "recommendation-memory-squeeze"], engine=make_engine(settings, runner))
    capsys.readouterr()
    runner.returncodes["update"] = 1

    assert (
        main(["stop", "recommendation-memory-squeeze"], engine=make_engine(settings, runner)) == 1
    )
    assert "FAILED to revert" in capsys.readouterr().err
    assert "recommendation-memory-squeeze" in make_engine(settings, runner).active()

    del runner.returncodes["update"]
    assert (
        main(["stop", "recommendation-memory-squeeze"], engine=make_engine(settings, runner)) == 0
    )
    assert make_engine(settings, runner).active() == {}


def test_starting_an_active_fault_is_refused(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["start", "recommendation-memory-squeeze"], engine=make_engine(settings, runner))
    capsys.readouterr()
    runner.stdout["inspect"] = "67108864 67108864\n"  # what a second inspect would now see

    code = main(["start", "recommendation-memory-squeeze"], engine=make_engine(settings, runner))

    assert code == 1, "re-injecting would overwrite the restore record with post-fault values"
    assert "already active" in capsys.readouterr().err
    restore = make_engine(settings, runner).active()["recommendation-memory-squeeze"].restore
    assert isinstance(restore, MemoryLimitRestore)
    assert restore.memory_bytes == 838860800, "the original limit is still the one on record"


def test_unknown_fault_id_is_an_error_not_a_traceback(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["start", "no-such-fault"], engine=make_engine(settings, runner)) == 1
    assert "unknown fault" in capsys.readouterr().err


def test_stop_without_a_target_is_an_error(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["stop"], engine=make_engine(settings, runner)) == 1
    assert "--all" in capsys.readouterr().err


def test_docker_failure_during_start_is_reported_cleanly(
    settings: InjectorSettings, runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    runner.returncodes["docker build"] = 1

    code = main(["start", "flag-service-bad-deploy"], engine=make_engine(settings, runner))

    assert code == 1
    assert "error:" in capsys.readouterr().err
    assert make_engine(settings, runner).active() == {}, "a fault that failed is not active"
