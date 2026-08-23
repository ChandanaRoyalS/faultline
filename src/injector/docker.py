"""Argument-list wrappers around the docker and docker-compose CLIs (T1.4).

Every command is a list of arguments and never a shell string. Fault parameters
(container names, env values, delays) are data that reaches this layer from
files and argv; interpolating them into a shell would make them code.

The whole layer is behind CommandRunner so tests can drive the injector with a
recorded fake and assert on the exact argv - no daemon, no containers, no
network in `make check`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from injector.settings import InjectorSettings


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    """A command exited non-zero and the caller asked to be told."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        detail = result.stderr.strip() or result.stdout.strip()
        super().__init__(f"exit {result.returncode}: {' '.join(result.args)}\n{detail}")


class CommandRunner(Protocol):
    """Runs a command and reports what happened."""

    def run(
        self, args: Sequence[str], *, cwd: Path | None = None, check: bool = True
    ) -> CommandResult: ...


class SubprocessRunner:
    """The real thing: subprocess with an argv list and no shell."""

    def run(
        self, args: Sequence[str], *, cwd: Path | None = None, check: bool = True
    ) -> CommandResult:
        # An argument list with shell=False by construction: a fault parameter is
        # data, and must never get a chance to be read as shell code.
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        result = CommandResult(
            args=tuple(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            raise CommandError(result)
        return result


class DockerCli:
    """The docker verbs the four fault classes need."""

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def memory_limits(self, container: str) -> tuple[int, int]:
        """Current (memory, memory-swap) limits in bytes; 0 means unlimited, -1 unbounded swap."""
        result = self._runner.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}",
                container,
            ]
        )
        memory, swap = result.stdout.split()
        return int(memory), int(swap)

    def set_memory_limits(self, container: str, memory: str, memory_swap: str | None) -> None:
        """Set the memory limit, and the swap ceiling when the container had one.

        memory_swap is omitted when it was 0 (unset): docker rejects a swap limit
        below the memory limit, so passing a literal 0 back would fail the restore
        that matters most.
        """
        args = ["docker", "update", "--memory", memory]
        if memory_swap is not None:
            args += ["--memory-swap", memory_swap]
        args.append(container)
        self._runner.run(args)

    def nano_cpus(self, container: str) -> int:
        """Current CPU quota in nano-CPUs; 0 means no quota, i.e. all the cores."""
        result = self._runner.run(
            ["docker", "inspect", "--format", "{{.HostConfig.NanoCpus}}", container]
        )
        return int(result.stdout.strip())

    def build(self, tag: str, context: Path, build_args: Mapping[str, str]) -> None:
        args = ["docker", "build", "--tag", tag]
        for name, value in build_args.items():
            args += ["--build-arg", f"{name}={value}"]
        args.append(str(context))
        self._runner.run(args)

    def run_detached(
        self,
        *,
        name: str,
        image: str,
        command: Sequence[str],
        volumes: Sequence[str] = (),
    ) -> None:
        args = ["docker", "run", "--detach", "--name", name]
        for volume in volumes:
            args += ["--volume", volume]
        args.append(image)
        args += list(command)
        self._runner.run(args)

    def container_exists(self, name: str) -> bool:
        result = self._runner.run(
            ["docker", "inspect", "--type", "container", "--format", "{{.Id}}", name],
            check=False,
        )
        return result.returncode == 0

    def stop(self, name: str, *, timeout_seconds: int = 30) -> None:
        self._runner.run(["docker", "stop", "--time", str(timeout_seconds), name], check=False)

    def remove(self, name: str) -> None:
        self._runner.run(["docker", "rm", "--force", name], check=False)


class ComposeCli:
    """Compose, invoked exactly as the Makefile invokes it, so it targets the same project."""

    def __init__(self, runner: CommandRunner, settings: InjectorSettings) -> None:
        self._runner = runner
        self._settings = settings

    def _base_args(self) -> list[str]:
        args = ["docker", "compose"]
        for compose_file in self._settings.compose_files:
            args += ["-f", compose_file]
        return args

    def recreate(self, service: str, *, overrides: Sequence[Path] = ()) -> None:
        """Recreate one service, optionally with extra override files layered on top.

        --no-build because the world runs with --no-build (ADR-0006): the demo's own
        build definitions are inert and must stay that way. --no-deps because a fault
        is aimed at one service; restarting its dependencies would inject a second,
        unlabelled incident.
        """
        args = self._base_args()
        for override in overrides:
            args += ["-f", str(override)]
        args += ["up", "-d", "--no-build", "--no-deps", "--force-recreate", service]
        self._runner.run(args, cwd=self._settings.world_dir)

    def stop(self, service: str) -> None:
        """Stop a service's container without removing it.

        An explicitly stopped container is not brought back by its `restart: always`
        policy, which is what makes a service stay down for the duration of a fault.
        """
        self._runner.run([*self._base_args(), "stop", service], cwd=self._settings.world_dir)

    def container_id(self, service: str) -> str | None:
        """The running container behind a compose service, or None if it is not up.

        Compose services and container names are not the same string in this world
        (service `cartservice`, container `cart-service`), so a fault that targets a
        service and needs to inspect its container has to ask compose which one it is
        rather than guessing at the naming convention.
        """
        result = self._runner.run(
            [*self._base_args(), "ps", "--quiet", service], cwd=self._settings.world_dir
        )
        ids = result.stdout.split()
        return ids[0] if ids else None
