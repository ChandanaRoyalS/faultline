"""The fifth compose file on a GitHub-hosted runner, and what it may and may not be (T4.5).

`compose/actions-kafka-jvm.override.yml` exists because the demo's kafka JDK throws in its
cgroup-v2 parser on `ubuntu-latest` and never starts (2026-09-04). It is layered *outside*
`compose_digest` on two arguments its header makes: the flag moves nothing a bundle records, and a
run from a runner is a separate generation by construction (`host_platform`, T5.4c). Both hold
only while the file stays exactly as small as it is and while the freeze records that it was in
force. These tests are the hold - the same one `tests/test_linux_host_gateway.py` puts on the
fourth file.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

from evalharness import provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
OVERRIDE = REPO_ROOT / "compose" / provenance.ACTIONS_KAFKA_JVM_OVERRIDE
GATEWAY = REPO_ROOT / "compose" / provenance.LINUX_HOST_GATEWAY_OVERRIDE


def test_the_override_sets_one_flag_on_one_service_and_does_nothing_else() -> None:
    """**One service, one variable, this value.** A second flag, a second service or a memory
    limit here is a change to the world the digest would not see, and at that point the file is a
    way around ADR-0014 rather than a shim for one runner's JDK."""
    override = yaml.safe_load(OVERRIDE.read_text())

    assert set(override) == {"services"}
    assert set(override["services"]) == {"kafka"}
    assert override["services"]["kafka"] == {
        "environment": {"KAFKA_OPTS": "-XX:-UseContainerSupport"}
    }


def test_the_override_is_outside_the_digest() -> None:
    """If it ever joins `compose_files` the header's reasoning is void and every future run is a
    new generation - a re-record decision, not a CI convenience."""
    from injector.settings import InjectorSettings

    assert OVERRIDE.name not in {Path(n).name for n in InjectorSettings().compose_files}


def _files_for(tmp_path: Path, kernel: str, actions: bool) -> list[str]:
    """What `make` would layer, asked of `make -n` under a fake `uname` and a set or cleared
    `GITHUB_ACTIONS` - the two facts the Makefile consults. Only make evaluates its conditionals,
    so the Makefile is not read; it is run."""
    fake_bin = tmp_path / f"{kernel}-{actions}"
    fake_bin.mkdir()
    (fake_bin / "uname").write_text(f"#!/bin/sh\necho {kernel}\n")
    (fake_bin / "uname").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    if actions:
        env["GITHUB_ACTIONS"] = "true"
    out = subprocess.run(
        ["make", "-n", "world-ps"], cwd=REPO_ROOT, env=env, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    return re.findall(r"-f (\S+)", out.stdout)


def test_the_makefile_layers_it_fifth_and_only_on_a_runner(tmp_path: Path) -> None:
    """The digest inputs first, in `InjectorSettings.compose_files` order; the Linux shim fourth;
    this file fifth, and only when `GITHUB_ACTIONS` is `true`. On the reference platform the
    command is byte-for-byte what it was before either shim existed."""
    from injector.settings import InjectorSettings

    hashed = list(InjectorSettings().compose_files)

    on_a_runner = _files_for(tmp_path, "Linux", actions=True)
    assert on_a_runner == [*hashed, f"../compose/{GATEWAY.name}", f"../compose/{OVERRIDE.name}"]

    on_a_linux_host = _files_for(tmp_path, "Linux", actions=False)
    assert on_a_linux_host == [*hashed, f"../compose/{GATEWAY.name}"]

    on_the_mac = _files_for(tmp_path, "Darwin", actions=False)
    assert on_the_mac == hashed


def test_the_freeze_records_exactly_what_the_makefile_layers(tmp_path: Path) -> None:
    """**The mirror, held by running both sides.** `provenance.host_overrides` is what the freeze
    writes into `world.host_overrides`; the Makefile is what actually layers the files. If either
    grows a condition the other lacks, a manifest will say something about the world that is not
    so, which is the one thing a freeze must never do."""
    for kernel, actions in (("Linux", True), ("Linux", False), ("Darwin", False), ("Darwin", True)):
        made = [Path(f).name for f in _files_for(tmp_path, kernel, actions)]
        hashed = [Path(f).name for f in provenance.InjectorSettings().compose_files]
        recorded = provenance.host_overrides(kernel, {"GITHUB_ACTIONS": "true"} if actions else {})
        assert made == [*hashed, *recorded], (kernel, actions)


def test_host_overrides_reads_the_runner_variable_the_way_the_runner_sets_it() -> None:
    """GitHub sets `GITHUB_ACTIONS=true`, the string. Anything else - absent, `1`, `false` - is
    not a runner, and a developer who exported `GITHUB_ACTIONS=false` to silence a tool must not
    get a kafka flag for it."""
    assert provenance.host_overrides("Linux", {"GITHUB_ACTIONS": "true"}) == [
        provenance.LINUX_HOST_GATEWAY_OVERRIDE,
        provenance.ACTIONS_KAFKA_JVM_OVERRIDE,
    ]
    assert provenance.host_overrides("Darwin", {"GITHUB_ACTIONS": "true"}) == [
        provenance.ACTIONS_KAFKA_JVM_OVERRIDE
    ]
    assert provenance.host_overrides("Linux", {"GITHUB_ACTIONS": "false"}) == [
        provenance.LINUX_HOST_GATEWAY_OVERRIDE
    ]
    assert provenance.host_overrides("Linux", {"GITHUB_ACTIONS": "1"}) == [
        provenance.LINUX_HOST_GATEWAY_OVERRIDE
    ]
    assert provenance.host_overrides("Darwin", {}) == []


def test_every_override_the_freeze_can_name_exists() -> None:
    """A manifest naming a file that is not in the tree is a manifest nobody can act on."""
    for name in (provenance.LINUX_HOST_GATEWAY_OVERRIDE, provenance.ACTIONS_KAFKA_JVM_OVERRIDE):
        assert (REPO_ROOT / "compose" / name).is_file(), name


def test_the_header_says_what_the_flag_does_not_change() -> None:
    """The argument for staying outside the digest is that nothing measurable moves. A header
    that stops saying what the flag touches - heap, processor count, the memory limit - has
    stopped making the argument, and the file is then just a flag."""
    text = OVERRIDE.read_text()
    for phrase in (
        "KAFKA_HEAP_OPTS",
        "CPU limit",
        "host_platform",
        "host_overrides",
        "GITHUB_ACTIONS",
    ):
        assert phrase in text, phrase
