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
from injector.settings import InjectorSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
FFS_STUB_DIR = REPO_ROOT / "compose" / "ffs-stub"

BUNDLE_SCHEMA_VERSION = 2
"""Bumped only by a change to the manifest's shape. A bump obsoletes every bundle recorded
before it, because the consistency guards compare like against like. v1 -> v2 added
`world.compose_digest` and `world.ffs_stub_source_digest`; see ADR-0014 for why that was
worth breaking ADR-0009's freeze."""

CAPTURE_SET = 2
"""Which set of captures a bundle holds. Absent means set 1: the original four metric files.

Deliberately **not** a `bundle_schema_version` bump. ADR-0014's bar for a bump is a change
that makes existing bundles false, and this is not one: the manifest gains an optional
field, every v2 manifest without it stays valid and correctly describes what it holds, and
no guard that passed before starts failing. A bump would instead obsolete all ten recorded
bundles for evidence that cannot be backfilled into them - Prometheus retention is 6h and
their windows are long gone.

Set 2 adds `metrics/runtime.json`, the target service's own runtime series. See
`evals/scenarios/ARTIFACTS.md` for why the existing ten are not being re-recorded, and
`evalharness.prom.runtime_query` for what the capture contains."""


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


def _digest_of(paths: list[Path]) -> str | None:
    """sha256 over the concatenated bytes of `paths`, in the order given."""
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            return None
        digest.update(path.read_bytes())
    return digest.hexdigest()


def compose_digest(settings: InjectorSettings | None = None) -> str | None:
    """sha256 over the three layered compose files, in the order compose loads them.

    This is what makes a change to the world visible from inside a bundle. Raising kafka's
    memory limit altered every container's environment and no manifest could show it: the
    demo image tag was unchanged, the stub image was unchanged, and the only field that
    moved was a build artifact that moves on its own. A bundle recorded before that edit
    and one recorded after describe different worlds and said they described the same one.

    Taken from `InjectorSettings.compose_files` rather than a hardcoded list, so the digest
    covers exactly the files the injector and the Makefile actually layer.
    """
    settings = settings or InjectorSettings()
    return _digest_of([(settings.world_dir / name).resolve() for name in settings.compose_files])


def ffs_stub_source_digest(directory: Path = FFS_STUB_DIR) -> str | None:
    """sha256 over everything in the stub build context, sorted by filename.

    The source, not the image. `ffs_stub_image_id` changed overnight with no source change
    at all, because `make world-up` rebuilt the image and re-resolved a pip layer. An image
    ID answers "was this byte-identical", which is not the question; this answers "was the
    stub built from the same code", which is.
    """
    if not directory.is_dir():
        return None
    return _digest_of(sorted((p for p in directory.iterdir() if p.is_file()), key=lambda p: p.name))


OBSERVABILITY_FILES: tuple[tuple[str, str], ...] = (
    (
        "compose/prometheus/alert-rules.yml",
        "the three alert rules, their thresholds and their `for:` clauses - so this file "
        "decides alerts_at_fire, alerts_over_window, seconds_to_alert, the blast radius, and "
        "whether an incident opens at all",
    ),
    (
        "compose/prometheus/prometheus-config.yaml",
        "scrape_interval (5s), evaluation_interval and rule_files - the sampling resolution "
        "of every capture. `evalharness.run.SCRAPE_INTERVAL_SECONDS` is pinned against it",
    ),
    (
        "compose/prometheus/alertmanager.yml",
        "routing, grouping and repeat to the ingest webhook - whether a firing alert reaches "
        "the orchestrator at all, and how it is deduped (ADR-0015)",
    ),
    (
        "compose/promtail-config.yml",
        "which containers ship logs and under what `service` label - so it decides every "
        "logql_query result, and T7.4's log-reachability census with it",
    ),
    (
        "compose/otelcol-extras.yml",
        "the collector's second `--config`, mounted over the demo's own extras path by "
        "`telemetry.yml` (T7.28). It carries the `memory_limiter`, so it decides what the "
        "collector does under memory pressure - refuse and drop, or grow until it is killed. "
        "Covered here rather than the clone's stub file, because this is the one in effect",
    ),
    (
        "world/src/otelcollector/otelcol-config.yml",
        "the spanmetrics connector: whether calls_total and latency_bucket exist, and (by not "
        "overriding them) the histogram bucket boundaries T7.14's whole analysis turned on",
    ),
    (
        "world/src/otelcollector/otelcol-config-extras.yml",
        "the demo's own extras stub. **Mounted over by `compose/otelcol-extras.yml` since T7.28**, "
        "so it no longer reaches the collector - kept under cover because a change here would "
        "mean the mount had been removed, which is worth catching",
    ),
)
"""Every file whose *content* decides what a bundle records, with why (T7.15).

**None of these were under any digest until T7.15.** `compose_digest` covers the three layered
compose files, which name these as mounts but say nothing about what is inside them - so editing
a threshold changed every future bundle's alert set and no manifest field moved. That is the
failure ADR-0014 was written to prevent, on files outside its cover.

Deliberately excluded, and named so the exclusions are decisions rather than oversights:

* `compose/grafana-loki-datasource.yml` and `world/src/grafana/**` - Grafana provisioning. A
  human reads those; no capture, tool or score does.
* `world/src/prometheus/prometheus-config.yaml` - **dead.** `compose/telemetry.yml` points
  Prometheus at `--config.file=/etc/prometheus/faultline-prometheus.yaml`, so the demo's own
  config is mounted by the demo's compose file and never read.
* The world's service source and images - already identified by `otel_demo_image` and the
  upstream tag the clone is pinned to.
"""


def observability_digests() -> dict[str, str | None]:
    """sha256 per file, so a mismatch can say *which* file changed rather than that one did."""
    return {name: _digest_of([REPO_ROOT / name]) for name, _ in OBSERVABILITY_FILES}


def observability_digest() -> str | None:
    """One value over every file in `OBSERVABILITY_FILES`, in the order declared.

    A sibling of `compose_digest`, **not an extension of it**, and that is the whole decision -
    see ADR-0014's T7.15 addendum. Adding these paths to `compose_digest` would change the value
    it computes, and the twelve recorded bundles would stop being reproducible from the
    repository - which is the one property the guard on them relies on.

    `None` when any file is absent (an uncloned `world/`), matching `compose_digest`'s behaviour
    rather than inventing a second convention.
    """
    paths = [REPO_ROOT / name for name, _ in OBSERVABILITY_FILES]
    return _digest_of(paths)


def image_content_digest(container: str) -> str | None:
    """The registry content digest of the image a container is actually running (T7.16).

    **`otel_demo_image` records a tag, and a tag is mutable.** Every demo image is *pulled* -
    `make world-up` passes `--no-build` - so what runs is whatever `ghcr.io/open-telemetry/demo:
    v1.2.1-cartservice` resolved to on the day it was pulled. If upstream ever republished that
    tag, every bundle would go on claiming the same world while running different code, and no
    recorded field would move. The `sha256:` digest is the immutable half of that reference.

    Deliberately unlike `ffs_stub_image_id`, which ADR-0014 records but refuses to compare: the
    stub is **built here**, so a rebuild churns its id from unchanged source. These are pulled,
    never built, so their digest is stable and *is* a content identifier. Same principle - prefer
    content over build artifact - reaching the opposite conclusion because the situation is
    opposite.

    One image, matching `otel_demo_image`'s existing choice of a single reference container. The
    limitation is real and worth stating: the demo publishes its sixteen service images from one
    release, so this is a proxy for that release rather than proof of the other fifteen.
    """
    image = _run(["docker", "inspect", container, "--format", "{{.Config.Image}}"])
    if not image:
        return None
    raw = _run(["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"])
    if not raw:
        return None
    try:
        digests = json.loads(raw)
    except json.JSONDecodeError:
        return None
    # Empty for an image that was never pulled from a registry, which is not an error here -
    # it is the honest answer that this image has no content digest to record.
    return str(digests[0]) if isinstance(digests, list) and digests else None


def world_provenance(reference_container: str, stub_image: str) -> dict[str, Any]:
    """What world this was recorded against.

    Two content digests and three observations. The digests are the load-bearing part - they
    are reproducible from the repository and change only when the world's definition does.
    """
    return {
        "compose_digest": compose_digest(),
        # T7.15. Absent on every bundle recorded before it, and absence means unknown
        # rather than unchanged: these digests are not derivable from a capture, so they
        # could not be backfilled honestly. ADR-0014 T7.15 addendum.
        "observability_digest": observability_digest(),
        "observability_files": observability_digests(),
        "ffs_stub_source_digest": ffs_stub_source_digest(),
        "otel_demo_image": _run(
            ["docker", "inspect", reference_container, "--format", "{{.Config.Image}}"]
        ),
        # T7.16. The immutable half of the line above. Absent on bundles recorded before it,
        # and absence means unknown rather than unchanged - the digest is not derivable from a
        # capture, so it could not be backfilled honestly. ADR-0026.
        "otel_demo_image_digest": image_content_digest(reference_container),
        # Informational only, and deliberately not compared between bundles: a rebuild
        # produces a new id from unchanged source, so disagreement here means nothing.
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
