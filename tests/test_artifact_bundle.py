"""The rehearsal bundle format, enforced (ADR-0009).

Incremental, like the contamination guards: these pass on an empty artifacts tree and
tighten as bundles land. Nothing here checks the honesty of the narrative - no test can -
but everything that is mechanically checkable is checked.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalharness.prom import alert_intervals
from evalharness.provenance import BUNDLE_SCHEMA_VERSION, scenario_fingerprint
from evalharness.scenario import Scenario, Split
from injector.world import SERVICE_CONTAINERS

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "evals" / "scenarios"
ARTIFACT_ROOT = SCENARIO_DIR / "artifacts"

REQUIRED_MANIFEST_KEYS = {
    "bundle_schema_version",
    "origin",
    "title",
    "scenario_fingerprint",
    "recorder",
    "world",
    "seconds_to_settle",
    "scenario_id",
    "split",
    "fault_class",
    "injection",
    "baseline_clear_at",
    "t_inject",
    "t_revert",
    "alerts_at_fire",
    "alerts_over_window",
    "seconds_of_steady_state",
    "window",
}

REQUIRED_METRICS = {
    "error-ratio.json",
    "call-rate.json",
    "latency-p95.json",
    "alerts-firing.json",
}


def scenarios() -> list[Scenario]:
    out: list[Scenario] = []
    for path in sorted(SCENARIO_DIR.rglob("*.yaml")):
        if "examples" in path.parts or "artifacts" in path.parts:
            continue
        out.append(Scenario.from_yaml(path))
    return out


def bundles() -> list[Path]:
    """Every directory under artifacts/ that has something in it."""
    if not ARTIFACT_ROOT.exists():
        return []
    found: list[Path] = []
    for split in (Split.DEV, Split.HOLDOUT):
        tree = ARTIFACT_ROOT / split.value
        if not tree.exists():
            continue
        found += [d for d in sorted(tree.iterdir()) if d.is_dir() and any(d.iterdir())]
    return found


def manifest_of(bundle: Path) -> dict[str, Any]:
    raw: Any = json.loads((bundle / "manifest.json").read_text())
    assert isinstance(raw, dict), f"{bundle.name}: manifest.json is not an object"
    return raw


def test_every_bundle_has_a_manifest() -> None:
    for bundle in bundles():
        assert (bundle / "manifest.json").is_file(), (
            f"{bundle.name}: no manifest.json. A bundle without one cannot be traced back "
            "to the run that produced it."
        )


def test_manifest_carries_provenance() -> None:
    """T4.1b's exclusion filter has nothing to filter on without this stamp."""
    for bundle in bundles():
        manifest = manifest_of(bundle)
        assert manifest.get("origin") == f"scenario:{bundle.name}", (
            f"{bundle.name}: origin must be 'scenario:{bundle.name}', "
            f"got {manifest.get('origin')!r}"
        )


def test_manifest_has_required_keys() -> None:
    for bundle in bundles():
        missing = REQUIRED_MANIFEST_KEYS - set(manifest_of(bundle))
        assert not missing, f"{bundle.name}: manifest missing {sorted(missing)}"


def test_manifest_split_matches_its_directory() -> None:
    for bundle in bundles():
        expected = bundle.parent.name
        assert manifest_of(bundle).get("split") == expected, (
            f"{bundle.name}: manifest says split="
            f"{manifest_of(bundle).get('split')!r} but it is filed under {expected}/"
        )


def test_bundles_carry_the_metric_captures() -> None:
    for bundle in bundles():
        present = {p.name for p in (bundle / "metrics").glob("*.json")}
        missing = REQUIRED_METRICS - present
        assert not missing, f"{bundle.name}: metrics/ missing {sorted(missing)}"


def test_rehearsed_scenarios_have_a_finished_narrative() -> None:
    """`rehearsed: true` claims a complete bundle. Template comments mean it isn't."""
    by_id = {b.name: b for b in bundles()}
    for scenario in scenarios():
        if not scenario.rehearsed:
            continue
        bundle = by_id.get(scenario.id)
        assert bundle is not None, f"{scenario.id} is marked rehearsed but has no artifact bundle."
        incident = bundle / "incident.md"
        assert incident.is_file(), f"{scenario.id}: no incident.md"
        text = incident.read_text()
        assert "<!--" not in text, (
            f"{scenario.id}: incident.md still has template comments in it. "
            "Finish the narrative before marking the scenario rehearsed."
        )
        assert len(text.split()) > 120, (
            f"{scenario.id}: incident.md is too short to be a real narrative "
            f"({len(text.split())} words). This file seeds the retrieval corpus."
        )


def test_narratives_do_not_leak_the_answer_key() -> None:
    """A responder did not know the fault class or the scenario id. Neither should the prose."""
    banned = ("faultline-inject", "injector", "injected", "fault_class", "scenario id")
    for bundle in bundles():
        incident = bundle / "incident.md"
        if not incident.is_file():
            continue
        # HTML comments are the template's instructions to the author, and they say
        # things like "no mention of the injector" - guidance, not narrative, and gone
        # by the time the scenario is marked rehearsed. Scanning them would fail every
        # freshly recorded bundle for quoting the rule it exists to enforce.
        body = re.sub(r"<!--.*?-->", "", incident.read_text(), flags=re.DOTALL)
        body = body.split("---", 2)[-1].lower()
        leaked = [word for word in banned if word in body]
        assert not leaked, (
            f"{bundle.name}: incident.md mentions {leaked} in its prose. Write it from the "
            "responder's chair - this text is retrieved later as a past incident."
        )


def test_bundles_record_a_usable_steady_state_window() -> None:
    """A bundle that caught only the transient is not worth seeding a corpus from.

    Recorded rather than inferred, because the first live rehearsal spent 180s of a 300s
    dwell waiting for the alert and the thinness was invisible in the manifest.
    """
    for bundle in bundles():
        seconds = manifest_of(bundle).get("seconds_of_steady_state")
        assert isinstance(seconds, int), (
            f"{bundle.name}: seconds_of_steady_state is {seconds!r}, not an integer"
        )
        assert seconds >= 60, (
            f"{bundle.name}: only {seconds}s of steady state after the alert fired. "
            "Re-record with a longer --dwell before trusting this bundle."
        )


# --- consistency guards ------------------------------------------------------
#
# The checks above ask whether a file is present. These ask whether the bundle agrees
# with itself. Three defects shipped tonight that presence guards could not see: a
# manifest recording 2 alerts when 11 fired, a log capture under a wrong selector that
# reported "no lines matched", and that same stale capture surviving a re-record beside
# its replacement. Each was present, well-formed, and wrong. See ADR-0009.


def metric_files(bundle: Path) -> list[Path]:
    return sorted((bundle / "metrics").glob("*.json"))


def load_metric(path: Path) -> dict[str, Any]:
    raw: Any = json.loads(path.read_text())
    assert isinstance(raw, dict), f"{path.name}: not a JSON object"
    return raw


def sample_times(payload: dict[str, Any]) -> list[float]:
    data = payload.get("data")
    results = data.get("result", []) if isinstance(data, dict) else []
    return [
        float(pair[0])
        for item in results
        if isinstance(item, dict)
        for pair in item.get("values", [])
        if isinstance(pair, list) and len(pair) == 2
    ]


def test_manifest_alerts_agree_with_the_captured_alert_series() -> None:
    """A manifest that disagrees with its own evidence is the 2-vs-11 defect."""
    for bundle in bundles():
        manifest = manifest_of(bundle)
        if "alerts_over_window" not in manifest or "t_inject" not in manifest:
            continue
        series = bundle / "metrics" / "alerts-firing.json"
        if not series.is_file():
            continue

        rederived = alert_intervals(
            load_metric(series),
            step=15,
            since=datetime.fromisoformat(manifest["t_inject"]),
            revert=datetime.fromisoformat(manifest["t_revert"]),
        )

        assert manifest["alerts_over_window"] == rederived, (
            f"{bundle.name}: manifest alerts_over_window does not match what "
            "metrics/alerts-firing.json re-derives to. The manifest and its own evidence "
            "disagree; one of them was written by a different version of the recorder."
        )


def test_seconds_to_alert_matches_the_timestamps_it_summarises() -> None:
    for bundle in bundles():
        manifest = manifest_of(bundle)
        if "seconds_to_alert" not in manifest:
            continue
        fired, injected = manifest.get("t_alert_firing"), manifest.get("t_inject")

        if fired is None:
            assert manifest["seconds_to_alert"] is None, (
                f"{bundle.name}: seconds_to_alert is set but no alert ever fired"
            )
            continue

        expected = int(
            (datetime.fromisoformat(fired) - datetime.fromisoformat(injected)).total_seconds()
        )
        assert manifest["seconds_to_alert"] == expected, (
            f"{bundle.name}: seconds_to_alert is {manifest['seconds_to_alert']}s but "
            f"t_alert_firing - t_inject is {expected}s"
        )


def test_the_declared_window_contains_every_captured_sample() -> None:
    """Timings and captures must describe the same incident, not two overlapping ones."""
    for bundle in bundles():
        window = manifest_of(bundle).get("window") or {}
        if not window.get("start") or not window.get("end"):
            continue
        start = datetime.fromisoformat(window["start"]).timestamp()
        end = datetime.fromisoformat(window["end"]).timestamp()

        for path in metric_files(bundle):
            times = sample_times(load_metric(path))
            if not times:
                continue  # emptiness is the next test's business
            slack = 15  # one query step; Prometheus aligns samples to step boundaries
            assert start - slack <= min(times) and max(times) <= end + slack, (
                f"{bundle.name}/{path.name}: samples span "
                f"{datetime.fromtimestamp(min(times), tz=UTC):%H:%M:%S}-"
                f"{datetime.fromtimestamp(max(times), tz=UTC):%H:%M:%S} but the manifest "
                f"declares {window['start']} to {window['end']}"
            )


def test_exactly_one_log_capture_named_for_the_target_container() -> None:
    """Two captures, or one named after the compose service, is the stale-artifact defect."""
    for bundle in bundles():
        target = manifest_of(bundle)["injection"]["target"]
        expected = SERVICE_CONTAINERS.get(target, target)
        captured = sorted(p.name for p in (bundle / "logs").glob("*.txt"))

        assert captured == [f"{expected}.txt"], (
            f"{bundle.name}: expected exactly one log capture, logs/{expected}.txt, for "
            f"target {target!r} - found {captured}. More than one means a re-record left "
            "a stale capture behind; a differently-named one means the selector was built "
            "from the compose service name instead of the container name."
        )


def test_no_metric_capture_is_silently_empty() -> None:
    """An empty result set is a capture failure wearing the shape of a successful one."""
    for bundle in bundles():
        manifest = manifest_of(bundle)
        for path in metric_files(bundle):
            payload = load_metric(path)
            data = payload.get("data")
            results = data.get("result", []) if isinstance(data, dict) else []
            populated = [r for r in results if isinstance(r, dict) and r.get("values")]

            if path.name == "alerts-firing.json":
                # The only capture that is legitimately empty sometimes: a fault may fire
                # nothing at all. The manifest is what disambiguates it.
                fired = manifest.get("t_alert_firing") or manifest.get("alerts_at_fire")
                if not fired:
                    continue
                assert populated, (
                    f"{bundle.name}: the manifest says alerts fired "
                    f"({manifest.get('alerts_at_fire')}) but alerts-firing.json is empty. "
                    "The capture failed - this is not a quiet world."
                )
                continue

            assert populated, (
                f"{bundle.name}/{path.name} contains no series with samples. This is "
                "AMBIGUOUS and needs a human: either the capture failed, or the world "
                "genuinely produced no data for this query over the window. Check whether "
                "the other metric files have data - if they do, the capture failed."
            )


def test_every_bundle_declares_the_current_schema_version() -> None:
    """A mixed-version catalog cannot be compared against itself. See ADR-0009."""
    for bundle in bundles():
        found = manifest_of(bundle).get("bundle_schema_version")
        assert found == BUNDLE_SCHEMA_VERSION, (
            f"{bundle.name}: bundle_schema_version is {found!r}, current is "
            f"{BUNDLE_SCHEMA_VERSION}. Re-record it - the guards compare bundles against "
            "each other, and a catalog recorded by two recorders is not one measurement."
        )


def test_every_bundle_records_what_produced_it_and_against_what() -> None:
    """Provenance nulls are allowed; missing provenance is not."""
    for bundle in bundles():
        manifest = manifest_of(bundle)
        recorder, world = manifest.get("recorder", {}), manifest.get("world", {})

        assert recorder.get("git_sha"), (
            f"{bundle.name}: no recorder git_sha. Without it, 'which version wrote this' "
            "is an inference from which keys happen to be missing."
        )
        for field in ("otel_demo_image", "ffs_stub_image_id", "docker_arch"):
            assert field in world, f"{bundle.name}: world provenance is missing {field}"


def test_bundles_agree_about_the_world_they_were_recorded_against() -> None:
    """The catalog's claim is ten scenarios measured under the same conditions."""
    seen: dict[str, list[str]] = {}
    for bundle in bundles():
        world = manifest_of(bundle).get("world", {})
        key = f"{world.get('otel_demo_image')} | {world.get('ffs_stub_image_id')}"
        seen.setdefault(key, []).append(bundle.name)

    assert len(seen) <= 1, (
        "bundles were recorded against different worlds, so their numbers are not "
        f"comparable: {json.dumps(seen, indent=2)}"
    )


def test_bundles_match_the_label_they_were_recorded_against() -> None:
    """A scenario's scored fields changing turns its bundle into evidence for another question."""
    by_id = {s.id: s for s in scenarios()}
    for bundle in bundles():
        scenario = by_id.get(bundle.name)
        if scenario is None:
            continue
        recorded = manifest_of(bundle).get("scenario_fingerprint")
        assert recorded == scenario_fingerprint(scenario), (
            f"{bundle.name}: recorded against a different version of the scenario. Its "
            "injection, fault class, split, ground truth or remediation class has changed "
            "since. Re-record it, or revert the change. Editing the title or the evidence "
            "list does not trip this."
        )
