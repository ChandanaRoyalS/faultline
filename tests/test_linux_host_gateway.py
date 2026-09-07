"""The fourth compose file on a Linux development host, and what it may and may not be (T5.4c).

`compose/linux-host-gateway.override.yml` exists because Docker Engine has no `host.docker.internal`
and Alertmanager posts to it. It is layered *outside* `compose_digest` on the argument that it moves
nothing a bundle records - the same argument ADR-0030 made for the dashboard - and that argument
holds only while the file stays exactly as small as it is. These tests are the hold.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
OVERRIDE = REPO_ROOT / "compose" / "linux-host-gateway.override.yml"
MAKEFILE = REPO_ROOT / "Makefile"


def test_the_override_gives_one_name_to_one_service_and_does_nothing_else() -> None:
    """**One service, one key, one entry.** Anything more is a change to the world that the digest
    would not see, and at that point the file is a way around ADR-0014 rather than a platform shim.
    """
    override = yaml.safe_load(OVERRIDE.read_text())

    assert set(override) == {"services"}
    assert set(override["services"]) == {"alertmanager"}
    assert override["services"]["alertmanager"] == {
        "extra_hosts": ["host.docker.internal:host-gateway"]
    }


def test_the_override_is_outside_the_digest() -> None:
    """If it ever joins `compose_files` the reasoning in its header is void and the header must
    change with it - and every future run is a new generation, which is a re-record decision."""
    from injector.settings import InjectorSettings

    assert OVERRIDE.name not in {Path(n).name for n in InjectorSettings().compose_files}


def test_the_makefile_layers_it_fourth_and_only_on_linux(tmp_path: Path) -> None:
    """Asserted against `make -n` rather than by reading the Makefile, because the conditional is
    what is being checked and only make evaluates it. The digest inputs come first, in
    `InjectorSettings.compose_files` order; the shim is last; and on a non-Linux host it is absent,
    so the reference platform's command is byte-for-byte what it was before this file existed."""
    from injector.settings import InjectorSettings

    def files_for(kernel: str) -> list[str]:
        # `$(shell uname -s)` is what the Makefile consults; putting a fake `uname` first on PATH
        # is the only way to exercise both branches from one machine.
        fake_bin = tmp_path / kernel
        fake_bin.mkdir()
        (fake_bin / "uname").write_text(f"#!/bin/sh\necho {kernel}\n")
        (fake_bin / "uname").chmod(0o755)
        env = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
        out = subprocess.run(
            ["make", "-n", "world-ps"], cwd=REPO_ROOT, env=env, capture_output=True, text=True
        )
        assert out.returncode == 0, out.stderr
        return re.findall(r"-f (\S+)", out.stdout)

    hashed = list(InjectorSettings().compose_files)

    on_linux = files_for("Linux")
    assert on_linux == [*hashed, f"../compose/{OVERRIDE.name}"], on_linux

    elsewhere = files_for("Darwin")
    assert elsewhere == hashed, elsewhere


def test_the_release_checklist_and_readme_name_the_firewall_rule() -> None:
    """Resolving the name is half of it. On a hardened host a default-deny firewall drops the
    packet at the bridge, the symptom is a timeout instead of a lookup failure, and the operator
    following the checklist has to be told to open the port to the bridge - not to the world.

    **Fenced commands, not prose** - the first version of this test grepped the whole file and
    failed on the sentence that names `ufw allow 8000` in order to forbid it. Prose may name the
    command a reader must not run; a code block may not contain it.
    """
    for name in ("docs/RELEASE.md", "README.md"):
        text = (REPO_ROOT / name).read_text()
        fenced = "\n".join(block for i, block in enumerate(text.split("```")) if i % 2 == 1)

        assert "host.docker.internal" in text, name
        assert "ufw allow from" in fenced and "to any port 8000 proto tcp" in fenced, name
        assert "ufw allow 8000" not in fenced, (
            f"{name} opens the receiver to the world, not the bridge"
        )
