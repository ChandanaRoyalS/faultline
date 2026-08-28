"""The docker layer must issue precise argv and never build a shell string."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from injector.docker import CommandError, ComposeCli, DockerCli, SubprocessRunner
from injector.settings import InjectorSettings
from tests.fakes import FakeRunner


def test_memory_limits_are_parsed_from_inspect() -> None:
    runner = FakeRunner(stdout={"inspect": "838860800 -1\n"})
    memory, swap = DockerCli(runner).memory_limits("recommendation-service")

    assert (memory, swap) == (838860800, -1)
    assert runner.argv("inspect") == (
        "docker",
        "inspect",
        "--format",
        "{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}",
        "recommendation-service",
    )


def test_update_passes_limits_as_separate_arguments() -> None:
    runner = FakeRunner()
    DockerCli(runner).set_memory_limits("cart-service", "64m", "64m")

    assert runner.argv("update") == (
        "docker",
        "update",
        "--memory",
        "64m",
        "--memory-swap",
        "64m",
        "cart-service",
    )


def test_container_exists_is_false_without_raising() -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    assert DockerCli(runner).container_exists("faultline-pumba-nope") is False


def test_build_forwards_build_args() -> None:
    runner = FakeRunner()
    DockerCli(runner).build("ffs-stub:2", Path("/ctx"), {"SERVER": "s.py"})

    assert runner.argv("build") == (
        "docker",
        "build",
        "--tag",
        "ffs-stub:2",
        "--build-arg",
        "SERVER=s.py",
        "/ctx",
    )


def test_compose_recreate_layers_overrides_and_runs_in_the_world(tmp_path: Path) -> None:
    settings = InjectorSettings(world_dir=tmp_path / "world")
    runner = FakeRunner()
    ComposeCli(runner, settings).recreate("cartservice", overrides=[tmp_path / "o.yml"])

    call = runner.calls[0]
    assert call.cwd == tmp_path / "world"
    assert call.args[-6:] == (
        "up",
        "-d",
        "--no-build",
        "--no-deps",
        "--force-recreate",
        "cartservice",
    )
    # The base files come first, in Makefile order, with our override layered last.
    files = [call.args[i + 1] for i, a in enumerate(call.args) if a == "-f"]
    assert files == [*settings.compose_files, str(tmp_path / "o.yml")]
    assert "--no-build" in call.args, "the world runs --no-build; building demo images is a trap"
    assert "--no-deps" in call.args, "a fault targets one service, not its dependencies"


def test_subprocess_runner_does_not_use_a_shell() -> None:
    runner = SubprocessRunner()
    # If this were handed to a shell, the substitution would run and stdout would differ.
    result = runner.run([sys.executable, "-c", "print('$(echo pwned)')"])
    assert result.stdout.strip() == "$(echo pwned)"


def test_subprocess_runner_raises_with_the_command_in_the_message() -> None:
    with pytest.raises(CommandError, match="exit 3"):
        SubprocessRunner().run([sys.executable, "-c", "raise SystemExit(3)"])
