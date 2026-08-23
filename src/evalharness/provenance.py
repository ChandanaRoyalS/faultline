"""What produced a recorded artifact, and against what (T1.5).

A bundle is a measurement, and a measurement without provenance cannot be compared to
another one. Three questions have to be answerable from the manifest alone, months later,
without the machine that made it:

* Which recorder wrote this? Three schema changes in one evening meant three bundles that
  looked fine and disagreed with each other. "Written by a different version" should be a
  recorded fact, not an inference from a missing key.
* Which world was it recorded against? The catalog's central claim is that ten scenarios
  were measured under the same conditions. Without the demo tag, the stub image and the
  platform, that claim has nothing behind it.
* Which version of the label? A scenario's scored fields can change after a bundle is
  recorded, which silently turns the bundle into evidence for a different question.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from evalharness.scenario import Scenario

BUNDLE_SCHEMA_VERSION = 1
"""Bumped only by a change to the manifest's shape. See ADR-0009 - a bump obsoletes every
bundle recorded before it, because the consistency guards compare like against like."""


def _run(args: list[str], cwd: Path | None = None) -> str | None:
    """Best effort. Missing provenance is recorded as null, never as a wrong value."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False, cwd=cwd)
    except (OSError, ValueError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def recorder_provenance(tool: str, repo_root: Path) -> dict[str, Any]:
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    status = _run(["git", "status", "--porcelain"], cwd=repo_root)
    return {
        "tool": tool,
        "git_sha": sha,
        # A dirty tree means the SHA does not describe the code that ran. Recorded rather
        # than ignored: a bundle produced from uncommitted work is reproducible only by
        # whoever had that work, and the manifest should say so.
        "git_dirty": status is not None and status != "",
    }


def world_provenance(reference_container: str, stub_image: str) -> dict[str, Any]:
    """Read from the running world, not from config files, so it records what actually ran."""
    return {
        "otel_demo_image": _run(
            ["docker", "inspect", reference_container, "--format", "{{.Config.Image}}"]
        ),
        "ffs_stub_image_id": _run(
            ["docker", "image", "inspect", stub_image, "--format", "{{.Id}}"]
        ),
        "docker_arch": _run(["docker", "version", "--format", "{{.Server.Arch}}"]),
        "host_platform": f"{platform.system()}/{platform.machine()}",
    }


def scenario_fingerprint(scenario: Scenario) -> str:
    """A hash of the fields a bundle is evidence *for*, not of the whole file.

    Deliberately excludes `title`, `expected_evidence` and every comment: those are edited
    often - three were corrected the night the catalog was authored - and rewording an
    evidence item does not make an existing recording wrong. Changing an injection
    parameter, a fault class, a split or a remediation label does.
    """
    scored = {
        "fault_class": scenario.fault_class.value,
        "split": scenario.split.value,
        "injection": scenario.injection.model_dump(mode="json"),
        "ground_truth": scenario.ground_truth.model_dump(mode="json"),
        "expected_remediation_class": scenario.expected_remediation_class.value,
    }
    payload = json.dumps(scored, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
