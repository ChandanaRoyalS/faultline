"""The rehearsal bundle format, enforced (ADR-0009).

Incremental, like the contamination guards: these pass on an empty artifacts tree and
tighten as bundles land. Nothing here checks the honesty of the narrative - no test can -
but everything that is mechanically checkable is checked.
"""

from __future__ import annotations

import inspect
import json
import re
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalharness import reachability
from evalharness.prom import PROMETHEUS, RUNTIME_CAPTURE, alert_intervals, get_json
from evalharness.provenance import (
    BUNDLE_SCHEMA_VERSION,
    OBSERVABILITY_FILES,
    observability_digest,
    observability_digests,
    scenario_fingerprint,
)
from evalharness.rehearse import SUPERSEDED, duration, superseded_name
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

RUNTIME_CAPTURE_FILE = f"{RUNTIME_CAPTURE}.json"

NO_RUNTIME_METRICS = frozenset(
    {
        "currency-cpu-throttle",
        "email-wrong-image",
        "flag-service-crashloop",
        "product-catalog-flag-failure",
        "productcatalog-dependency-latency",
        "shipping-quote-misconfig",
        "shipping-wrong-image",
    }
)
"""Bundles whose target exports no runtime metrics, so an empty `runtime.json` is the world
speaking rather than a capture failing.

**Measured at T7.1's uniform re-record, and invisible before it.** `runtime.json` arrived with
capture set 2, so only the two bundles recorded after it carried the file at all; re-recording
all twelve put the question to every target at once and six came back empty.

The query is not at fault, which was the other hypothesis this guard names. Asking Prometheus
directly, `process_runtime_*` exists for exactly four services - `adservice` 48 series,
`frauddetectionservice` 38, `checkoutservice` 25, `cartservice` 20 - and `runtime_*` /
`system_memory_*` adds `recommendationservice`. For the six below, `{exported_job="<target>"}`
matches **nothing at all**, not merely no runtime family, so the label is right and the services
are silent.

Pinned rather than skipped, and asserted in both directions: an entry here whose capture is
populated fails too, because the interesting direction is the world gaining instrumentation.
"""

CAPTURE_SETS: dict[int, set[str]] = {
    1: REQUIRED_METRICS,
    2: REQUIRED_METRICS | {RUNTIME_CAPTURE_FILE},
}
"""What each capture set holds. A bundle with no `capture_set` is set 1.

The catalog is deliberately mixed: the ten bundles recorded before the fifth capture keep
set 1 and are not being re-recorded, because their windows predate Prometheus's 6h
retention and cannot be backfilled. `evals/scenarios/ARTIFACTS.md` records that decision.
`capture_set` is what makes the mix legible instead of silently inconsistent.
"""


def capture_set_of(bundle: Path) -> int:
    """Which capture set this bundle claims. Absent means the original four files."""
    declared = manifest_of(bundle).get("capture_set", 1)
    assert isinstance(declared, int) and declared in CAPTURE_SETS, (
        f"{bundle.name}: capture_set is {declared!r}, which names no known capture set "
        f"{sorted(CAPTURE_SETS)}. Add it to CAPTURE_SETS or fix the manifest."
    )
    return declared


def capture_discrepancy(declared: int, present: set[str]) -> tuple[set[str], set[str]]:
    """(missing, unaccounted-for) between a declared capture set and what is on disk."""
    expected = CAPTURE_SETS[declared]
    return expected - present, present - expected


def is_invalidated(bundle: Path) -> bool:
    """Whether this bundle carries an INVALID.md."""
    return (bundle / "INVALID.md").is_file()


def valid_bundles() -> list[Path]:
    """Bundles that make a claim about the world. **Iterate this, not `bundles()`.**

    An invalidated bundle is the record of a failed attempt. It claims nothing, it never
    enters a corpus, and no number is ever read out of it, so holding it to the standards
    that make measurements comparable asks the wrong question - and satisfying that
    question would mean deleting the evidence of why the attempt failed. Two of the
    invalidated bundles cannot be re-recorded at all: `currency-cpu-throttle`'s mechanism
    was retired by ADR-0013, and `flag-service-crashloop` targets a service that emits no
    span metrics.

    Use `bundles()` only for checks that are *about* the record itself rather than about
    the measurement - whether a manifest exists, or whether a capture with no alerts has
    been invalidated at all.

    The scoping was originally applied to one guard and omitted from two others. Keeping
    it in one place is what stops that recurring.
    """
    return [b for b in bundles() if not is_invalidated(b)]


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
    """Every bundle holds the captures its declared set promises - no more, no fewer.

    Checked in both directions. A missing file is a failed capture; an extra one means a
    bundle holds evidence its `capture_set` does not account for, which is the silent
    inconsistency the field exists to prevent.
    """
    for bundle in bundles():
        declared = capture_set_of(bundle)
        present = {p.name for p in (bundle / "metrics").glob("*.json")}
        missing, extra = capture_discrepancy(declared, present)
        assert not missing and not extra, (
            f"{bundle.name}: capture_set {declared} means metrics/ holds "
            f"{sorted(CAPTURE_SETS[declared])}; missing {sorted(missing)}, "
            f"unaccounted for {sorted(extra)}."
        )


def test_the_capture_set_rule_holds_in_both_directions() -> None:
    """The rule itself, checked without a bundle - no set-2 bundle exists to exercise it yet.

    A guard that has never been seen to fail is an assumption. `capture_set` will not have
    a real bundle behind it until the next rehearsal, so the mapping is tested directly.
    """
    four = set(REQUIRED_METRICS)
    assert capture_discrepancy(1, four) == (set(), set())
    assert capture_discrepancy(2, four | {RUNTIME_CAPTURE_FILE}) == (set(), set())

    # Set 2 without the fifth capture: the file it promises is missing.
    assert capture_discrepancy(2, four) == ({RUNTIME_CAPTURE_FILE}, set())
    # Set 1 carrying it anyway: evidence the manifest does not account for.
    assert capture_discrepancy(1, four | {RUNTIME_CAPTURE_FILE}) == (set(), {RUNTIME_CAPTURE_FILE})


def test_the_existing_bundles_declare_no_capture_set_and_that_means_set_one() -> None:
    """The mixed catalog, asserted rather than assumed.

    The ten bundles recorded before the fifth capture are staying as they are (see
    `ARTIFACTS.md`), so they carry no `capture_set` and must keep passing untouched. If one
    of them ever grows the field, that was a backfill - which is exactly what the decision
    ruled out, since their windows are past Prometheus's retention and cannot be recaptured.
    """
    for bundle in bundles():
        if "capture_set" in manifest_of(bundle):
            continue  # a bundle recorded after the change - fine, and checked above
        present = {p.name for p in (bundle / "metrics").glob("*.json")}
        assert capture_set_of(bundle) == 1 and present == REQUIRED_METRICS, (
            f"{bundle.name} declares no capture_set, so it must hold exactly the original "
            f"four captures - found {sorted(present)}."
        )


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


ERROR_RATIO = "error-ratio.json"

CONTINUOUS_CAPTURES = ("call-rate.json", "latency-p95.json")
"""Captures that have samples whenever collection is running at all.

Both are sums over every service's spans, so they go quiet only when the pipeline does -
which is what makes them usable as the reference for whether a gap elsewhere was an
outage. `error-ratio` is not one of them: it can be empty in a perfectly healthy world.
"""


def collection_sample_times(bundle: Path) -> list[float]:
    """Every instant this bundle proves telemetry was still arriving."""
    return sorted(
        {
            t
            for name in CONTINUOUS_CAPTURES
            for t in sample_times(load_metric(bundle / "metrics" / name))
        }
    )


def collection_was_live(live: list[float], gap: tuple[float, float, float]) -> bool:
    """Whether anything was still being sampled strictly inside this gap."""
    _, start, end = gap
    return any(start < t < end for t in live)


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

            if path.name == RUNTIME_CAPTURE_FILE and bundle.name in NO_RUNTIME_METRICS:
                assert not populated, (
                    f"{bundle.name}: its target is recorded as exporting no runtime metrics, "
                    "but this capture has series. If the world gained instrumentation that is "
                    "good news - take the entry out of NO_RUNTIME_METRICS."
                )
                continue

            if path.name == RUNTIME_CAPTURE_FILE:
                # Same rule, different diagnosis. This capture covers one service, so the
                # other files having data says nothing about whether this one failed - the
                # target can legitimately export no runtime series at all. It is still not
                # allowed to be silently empty: an empty file cannot distinguish "this
                # service is not instrumented" from "the query matched nothing", and the
                # whole point of the capture is that its *absence during the fault* means
                # something. The window opens five minutes before injection, so a healthy
                # instrumented service always has samples there.
                assert populated, (
                    f"{bundle.name}/{path.name} contains no series over the whole window, "
                    "including the five healthy minutes before injection. Either "
                    f"{manifest.get('injection', {}).get('target')!r} exports no runtime "
                    "metrics, or the query is wrong - note the label is `exported_job`, "
                    "not `service_name`. Needs a human either way."
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
    for bundle in valid_bundles():
        found = manifest_of(bundle).get("bundle_schema_version")
        assert found == BUNDLE_SCHEMA_VERSION, (
            f"{bundle.name}: bundle_schema_version is {found!r}, current is "
            f"{BUNDLE_SCHEMA_VERSION}. This bundle predates the v1 -> v2 bump (ADR-0014) "
            "and must be re-recorded. Do not backfill the new fields into it: v1 bundles "
            "were recorded under the old container memory limits, so they describe a "
            "genuinely different world and a backfilled digest would be a false claim."
        )


def test_every_bundle_records_what_produced_it_and_against_what() -> None:
    """Provenance nulls are allowed; missing provenance is not."""
    for bundle in valid_bundles():
        manifest = manifest_of(bundle)
        recorder, world = manifest.get("recorder", {}), manifest.get("world", {})

        assert recorder.get("git_sha"), (
            f"{bundle.name}: no recorder git_sha. Without it, 'which version wrote this' "
            "is an inference from which keys happen to be missing."
        )
        for field in ("otel_demo_image", "ffs_stub_image_id", "docker_arch"):
            assert field in world, f"{bundle.name}: world provenance is missing {field}"
        # v2: the two content digests are what actually identify a world, so unlike the
        # observations above they may not be null.
        for field in ("compose_digest", "ffs_stub_source_digest"):
            assert world.get(field), (
                f"{bundle.name}: world provenance has no {field}. Without it there is no "
                "way to tell whether this bundle was recorded against the same world as "
                "any other."
            )


def test_bundles_agree_about_the_world_they_were_recorded_against() -> None:
    """The catalog's claim is that its scenarios were measured under the same conditions.

    Invalidated bundles are skipped via `valid_bundles()`, which carries the reasoning and
    is shared with the schema-version and provenance guards. It is a scoping decision
    rather than a loophole.

    The guard's actual claim is unweakened: **any two VALID bundles that disagree still
    fail.** If a valid bundle is ever recorded against a different world image, this
    catches it, which is the case that would corrupt a comparison.
    """
    seen: dict[str, list[str]] = {}
    skipped = [b.name for b in bundles() if is_invalidated(b)]
    for bundle in valid_bundles():
        world = manifest_of(bundle).get("world", {})
        # Content digests, not the image id. An image id is a build artifact: it changed
        # overnight from identical source when a rebuild re-resolved a pip layer, so
        # comparing it reports differences that are not differences. compose_digest and
        # ffs_stub_source_digest are reproducible from the repository and move only when
        # the world's definition moves.
        key = (
            f"compose={world.get('compose_digest')} | "
            f"stub_source={world.get('ffs_stub_source_digest')}"
        )
        seen.setdefault(key, []).append(bundle.name)

    assert len(seen) <= 1, (
        "valid bundles were recorded against different worlds, so their numbers are not "
        f"comparable: {json.dumps(seen, indent=2)}"
        + (f"\n(invalidated bundles skipped: {sorted(skipped)})" if skipped else "")
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


# --- a bundle cannot alert faster than its own rule permits ------------------

RULES_FILE = REPO_ROOT / "compose" / "prometheus" / "alert-rules.yml"


def parse_for_duration(value: str) -> int:
    """Prometheus duration to seconds. Only the units the rules actually use."""
    units = {"s": 1, "m": 60, "h": 3600}
    match = re.fullmatch(r"(\d+)([smh])", value.strip())
    assert match, f"unparsable `for` duration {value!r}"
    return int(match.group(1)) * units[match.group(2)]


def alert_for_durations() -> tuple[dict[str, int], str]:
    """alertname -> `for` seconds, from the live rules if reachable, else the committed file.

    Prometheus is authoritative about what was actually evaluating, so it is preferred. The
    file is the fallback rather than the primary because a rule can be edited without being
    reloaded - but the fallback matters: CI has no world, and a guard that only runs on a
    developer's laptop is half a guard.
    """
    try:
        payload = get_json(PROMETHEUS, "/api/v1/rules", {})
        data = payload.get("data")
        groups = data.get("groups", []) if isinstance(data, dict) else []
        live = {
            str(rule["name"]): int(float(rule["duration"]))
            for group in groups
            for rule in group.get("rules", [])
            if "name" in rule and rule.get("duration") is not None
        }
        if live:
            return live, "Prometheus /api/v1/rules"
    except Exception:  # any failure to reach Prometheus falls back to the file
        pass

    doc = yaml.safe_load(RULES_FILE.read_text())
    return {
        str(rule["alert"]): parse_for_duration(str(rule["for"]))
        for group in doc.get("groups", [])
        for rule in group.get("rules", [])
        if "alert" in rule and "for" in rule
    }, str(RULES_FILE.relative_to(REPO_ROOT))


def test_no_bundle_alerts_faster_than_its_own_rule_permits() -> None:
    """A page that arrives sooner than the rule's `for` clause is not this fault's page.

    Independent of the recorder's solo gate, and catches the same corruption from the other
    side: the gate prevents two faults sharing a world, this detects the result if
    prevention is ever bypassed - a stranded state file, an injection made outside the CLI,
    a rule changed mid-batch.

    The bound is deliberately loose. The true floor is the `for` clause plus the rule's rate
    window plus an evaluation interval; only the `for` clause is asserted, because it is
    exact and needs no assumption about which window a rule uses. Anything below it is
    physically impossible rather than merely suspicious.
    """
    durations, source = alert_for_durations()

    for bundle in bundles():
        manifest = manifest_of(bundle)
        at_fire = manifest.get("alerts_at_fire") or []
        seconds = manifest.get("seconds_to_alert")
        if not at_fire or seconds is None:
            continue

        name = str(at_fire[0]).split("/")[0]
        required = durations.get(name)
        assert required is not None, (
            f"{bundle.name}: paged on {name!r}, which is not a rule in {source}. Either the "
            "rules changed since this was recorded, or the bundle names an alert that does "
            "not exist."
        )
        assert seconds >= required, (
            f"{bundle.name}: paged on {name} {seconds}s after injection, but that rule has "
            f"`for: {required}s` ({source}). The alert cannot have been caused by this "
            "fault - its condition was already true before the injection, so this bundle "
            "was timed against an incident already in progress. Re-record it on a world "
            "that is genuinely quiet."
        )


# --- a narrative must belong to the recording it sits beside -----------------


def front_matter(bundle: Path) -> dict[str, Any] | None:
    """The YAML block at the top of incident.md, or None if there is no narrative."""
    incident = bundle / "incident.md"
    if not incident.is_file():
        return None
    parts = incident.read_text().split("---", 2)
    if len(parts) < 3:
        return None
    try:
        loaded = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise AssertionError(
            f"{bundle.name}: incident.md front matter is not valid YAML, so nothing can "
            f"read it - including the corpus seeder at T2.4b.\n{exc}"
        ) from exc
    return loaded if isinstance(loaded, dict) else None


def as_instant(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def test_every_narrative_names_the_recording_it_describes() -> None:
    """`recorded_from` pins prose to one recording, and a re-record moves t_inject.

    Deliberately the one absolute timestamp allowed near a narrative. The prose is written
    in relative time so a re-record cannot orphan it; this field is written in absolute
    time so a re-record *does* break it. Without it a stale narrative sits green over
    facts that stopped describing it - which happened, and was caught by eye rather than
    by a test.
    """
    for bundle in bundles():
        matter = front_matter(bundle)
        if matter is None:
            continue
        recorded = matter.get("recorded_from")
        assert recorded is not None, (
            f"{bundle.name}: incident.md front matter has no `recorded_from`, so nothing "
            "ties this narrative to a recording."
        )
        expected = manifest_of(bundle)["t_inject"]
        # Compared as instants, not strings: YAML turns an unquoted ISO timestamp into a
        # datetime, so the two sides spell the same moment differently. The question is
        # whether the narrative belongs to this recording, not how the date was written.
        assert as_instant(recorded) == as_instant(expected), (
            f"{bundle.name}: incident.md says it was written from a recording at "
            f"{recorded}, but the bundle beside it was recorded at {expected}. The "
            "narrative describes an incident this bundle no longer contains - rewrite it "
            "against the current recording, or restore the recording it was written from."
        )


def test_narrative_front_matter_durations_match_the_manifest() -> None:
    """Same formatter on both sides (evalharness.rehearse.duration), so they cannot drift."""
    for bundle in bundles():
        matter = front_matter(bundle)
        if matter is None:
            continue
        recorded = matter.get("onset_to_page")
        expected = duration(manifest_of(bundle).get("seconds_to_alert"))
        assert str(recorded) == expected, (
            f"{bundle.name}: front matter says onset_to_page={recorded}, but the manifest's "
            f"seconds_to_alert formats to {expected}."
        )


def test_a_bundle_that_captured_no_alert_is_marked_invalid() -> None:
    """A capture with no alert is a healthy world, and must not look like a rehearsal.

    Some faults are legitimately quiet, so an empty `alerts_at_fire` is not automatically
    an error - but it is never self-evidently fine either, and the recorder only says so on
    stdout, which nothing keeps. Requiring an INVALID.md forces the judgement to be written
    down where the next reader finds it, next to the capture it applies to.

    The real case: currency-cpu-throttle set a quota ~60x above the service's demand. It
    could not bind, the world stayed healthy, and the bundle sat in the tree complete and
    well-formed with nothing in it.
    """
    for bundle in bundles():
        manifest = manifest_of(bundle)
        if manifest.get("alerts_at_fire"):
            continue
        # An empty alerts_at_fire with a populated alerts_over_window is a *timeout*, not
        # silence: the recorder stopped waiting before the alert arrived. Measured on
        # frauddetection-memory-squeeze, which alerted at +675s against a 420s wait.
        # Requiring an INVALID.md there would invalidate a working scenario.
        if manifest.get("alerts_over_window"):
            continue
        marker = bundle / "INVALID.md"
        assert marker.is_file(), (
            f"{bundle.name}: no alert fired at any point in the captured window "
            f"({manifest.get('seconds_to_alert')=}, alerts_over_window empty) and there "
            f"is no INVALID.md beside the capture. Either the fault did not fire - write "
            "INVALID.md saying why - or the scenario is deliberately quiet, in which case "
            "say that there instead. A bundle that captured nothing must not look complete."
        )
        assert marker.stat().st_size > 200, (
            f"{bundle.name}: INVALID.md is too short to explain anything. It is the only "
            "record of why this capture is not evidence."
        )


# --- archived manifests keep old numbers checkable ---------------------------


def test_superseded_manifests_are_parseable_and_correctly_named() -> None:
    """A re-record replaces manifest.json, so every number cited from it becomes
    unverifiable unless the outgoing copy is kept.

    Not required to exist: most bundles have never been re-recorded, and several predate
    the archive entirely. But an archive that is present must be usable - a malformed or
    misnamed file there is worse than none, because prose will be checked against it.
    """
    for bundle in bundles():
        archive = bundle / SUPERSEDED
        if not archive.is_dir():
            continue
        live = manifest_of(bundle)["t_inject"]
        # Two layouts. Predecessors recovered from git history are flat `<stamp>.json`
        # manifests - that is all git had. Anything the recorder archives itself is
        # `<stamp>/manifest.json` with compressed metric captures beside it.
        entries = [*archive.glob("*.json"), *archive.glob("*/manifest.json")]
        for path in sorted(entries):
            try:
                old = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{bundle.name}/{path.name} is not valid JSON: {exc}") from exc

            recorded = old.get("t_inject")
            assert recorded, f"{bundle.name}/{path.name} has no t_inject"
            stamp = (
                path.name
                if path.name.endswith(".json") and path.parent == archive
                else path.parent.name + ".json"
            )
            assert stamp == superseded_name(recorded), (
                f"{bundle.name}/{stamp} is named for a different run than it contains "
                f"(t_inject {recorded} would be {superseded_name(recorded)}). The filename "
                "is how a citation is looked up, so it has to match."
            )
            assert as_instant(recorded) != as_instant(live), (
                f"{bundle.name}/{path.name} has the same t_inject as the live manifest. An "
                "archive entry is a *previous* recording; this one is a duplicate of the "
                "current bundle and would make two files claim to be the same run."
            )


# --- a capture must be continuous, not merely present ------------------------

MAX_SAMPLE_GAP_SECONDS = 120
"""Eight scrape intervals. Healthy captures top out at 30s; this catches holes, not jitter."""


def test_the_error_ratio_cross_check_still_reports_a_real_outage() -> None:
    """The cross-check must narrow the guard, not disable it for the file.

    Both directions, because the failure mode of a fix like this is that it quietly
    accepts everything: a quiet world is forgiven only because something else kept
    sampling, and an actual collection stop is still a hole.
    """
    gap = (225.0, 1000.0, 1225.0)

    # Something was still being sampled throughout: the world had no errors.
    assert collection_was_live([990.0, 1015.0, 1100.0, 1215.0, 1240.0], gap)

    # Nothing was sampled inside it: collection stopped, and this is a hole.
    assert not collection_was_live([990.0, 1000.0, 1225.0, 1240.0], gap)
    assert not collection_was_live([], gap)


def test_metric_captures_have_no_holes() -> None:
    """A gap of hours mid-window is a stopped scraper, not a slow one.

    Measured: a rehearsal ran while the machine suspended. Docker stopped, Prometheus
    stopped scraping, and all three continuous captures share a 2250-second hole. Every
    existing guard passed - the manifest is self-consistent, the files are present and
    well-formed, the window contains every sample. Nothing looked at whether the samples
    were *continuous*.

    `alerts-firing.json` is excluded: an ALERTS series exists only while something is
    firing, so gaps between episodes are the normal shape of that capture and mean nothing.
    Gaps in a single service's series are also fine - a service that dies stops emitting,
    which is often the fault itself. This looks at the union of sample times across every
    series in a file, which only goes quiet when collection does.

    `runtime.json` is excluded for that same reason, one step further on. Every series in
    it belongs to **one** service, so the union argument does not hold: when that process
    stops, the whole file goes quiet, and nothing else in the capture disagrees. Measured
    on `ad-memory-squeeze` and `recommendation-memory-squeeze` - the series vanish for the
    length of the fault. That silence is the evidence this capture exists to record, so a
    hole here is a finding rather than a defect (CATALOG.md, "Runtime metrics reach
    Prometheus, and their absence is the signal").

    **`error-ratio.json` is cross-checked rather than excluded.** Its numerator selects
    only `STATUS_CODE_ERROR` series, so a stretch during which nothing anywhere is failing
    produces no samples at all - a healthy world, not a stopped one. Measured on the
    `ad-memory-squeeze` re-record of 2026-08-24: a 225s gap from 10:01:43Z, running from
    90 seconds into the window to 15 seconds after injection, which is exactly the quiet
    stretch before the fault bit. `call-rate` and `latency-p95` are continuous across the
    same window, so collection plainly never stopped.

    Excluding the file outright would be the easy fix and would blind the guard to a real
    outage in it. Instead a gap here counts only when the continuous captures gap there
    too: if anything was still being sampled while error-ratio was silent, the silence was
    the world having no errors. This is the same union argument the rest of the guard
    rests on, applied across files instead of across series - which is what it takes for a
    capture whose emptiness is meaningful.
    """
    exempt = {"alerts-firing.json", f"{RUNTIME_CAPTURE}.json"}
    for bundle in bundles():
        live = collection_sample_times(bundle)
        for path in metric_files(bundle):
            if path.name in exempt:
                continue
            times = sorted(set(sample_times(load_metric(path))))
            if len(times) < 2:
                continue
            gaps = [(b - a, a, b) for a, b in pairwise(times)]
            if path.name == ERROR_RATIO:
                gaps = [g for g in gaps if not collection_was_live(live, g)]
            if not gaps:
                continue
            worst, at, _ = max(gaps)
            assert worst <= MAX_SAMPLE_GAP_SECONDS, (
                f"{bundle.name}/{path.name}: {worst:.0f}s with no samples from any series, "
                f"starting {datetime.fromtimestamp(at, tz=UTC):%H:%M:%S}Z. That is a hole in "
                "the capture, not a slow scrape - the whole collection stopped. The usual "
                "cause is the machine suspending mid-rehearsal: Docker stops, Prometheus "
                "stops scraping, and the recorded window keeps advancing. Re-record it."
            )


def test_a_re_record_cannot_delete_the_files_a_person_wrote(tmp_path: Path) -> None:
    """T7.1's uniform re-record deleted both `INVALID.md` files: the marker was not on the
    preserve list, so `--force` removed the only thing explaining why those two bundles are
    empty. The guards caught it immediately, which is them working - but an alert-free bundle
    whose marker has been deleted looks exactly like a capture failure nobody has explained,
    and the file that says otherwise is the one the re-record just removed.
    """
    from evalharness.rehearse import clear_bundle

    bundle = tmp_path / "a-bundle"
    (bundle / "metrics").mkdir(parents=True)
    (bundle / "superseded").mkdir()
    for name in ("incident.md", "INVALID.md", "queries.md", "manifest.json"):
        (bundle / name).write_text(name)
    (bundle / "metrics" / "error-ratio.json").write_text("{}")
    (bundle / "superseded" / "old.json").write_text("{}")

    removed = clear_bundle(bundle)

    assert (bundle / "incident.md").is_file(), "the narrative survives a re-record"
    assert (bundle / "INVALID.md").is_file(), "so does the reason a bundle is not evidence"
    assert (bundle / "superseded" / "old.json").is_file(), "and so does the archive"
    assert sorted(removed) == ["manifest.json", "metrics", "queries.md"]


# --- the capability guard (T7.8) ----------------------------------------------


def test_every_narrative_was_reviewed_against_the_current_capability_set() -> None:
    """**A narrative is only as current as the last capability change.**

    Discipline failed at this twice. T2.6 built a change log and four narratives went on
    asserting "what changed: nothing" for weeks. T7.1 re-recorded every bundle, *did* force a
    narrative rewrite, and the rewrite still missed sixteen restart lines in
    `ad-memory-squeeze` because the review compared front matter against the manifest and never
    opened `logs/`.

    `recorded_from` already breaks when the recording changes. This breaks when the capability
    set changes, which is the other way a true claim goes false.

    **It checks a stamp, not the prose.** A passing run means somebody reviewed the narrative,
    never that its claims were verified - and the failure message says so, because a guard whose
    green is mistaken for a proof is worse than no guard.
    """
    from evalharness.capability import (
        STALE_NARRATIVE_MESSAGE,
        capability_inputs,
        capability_version,
    )

    current = capability_version()
    stale: list[str] = []
    for bundle in bundles():
        incident = bundle / "incident.md"
        if not incident.is_file():
            continue
        front = re.match(r"\A---\n(.*?)\n---\n", incident.read_text(), re.DOTALL)
        found = None
        if front:
            for line in front.group(1).split("\n"):
                if line.startswith("capability:"):
                    found = line.split(":", 1)[1].strip()
        if found != current:
            stale.append(
                STALE_NARRATIVE_MESSAGE.format(
                    name=bundle.name,
                    found=found or "no capability stamp",
                    current=current,
                    changes="\n".join(f"  {k}: {v}" for k, v in capability_inputs().items()),
                )
            )

    assert not stale, "\n\n".join(stale)


def test_the_capability_version_moves_only_on_a_capability_change() -> None:
    """Two of its three inputs are derived so they cannot drift; the third is deliberate.

    The failure this guards against is a version that moves when nothing a narrative could cite
    has moved - which is the `ffs_stub_image_id` mistake ADR-0014 names, a field producing
    differences nobody can act on until nobody looks at it.
    """
    from unittest.mock import patch

    from evalharness import capability

    baseline = capability.capability_version()
    assert baseline.startswith("cap:")
    assert capability.capability_version() == baseline, "stable across calls"

    with patch.object(capability, "tool_surface", return_value=["promql_query"]):
        assert capability.capability_version() != baseline, "losing a tool is a capability change"

    with patch.object(capability, "CAPTURE_SET", 99):
        assert capability.capability_version() != baseline, "a new capture set is new evidence"


def test_the_capability_inputs_are_read_from_the_code_not_written_down() -> None:
    """`tool_surface` reads the class. A hand-maintained list is the thing that drifts."""
    from evalharness.capability import tool_surface

    assert tool_surface() == ["change_history", "logql_query", "promql_query", "trace_query"]


# --- T7.15: the observability config is under cover -----------------------------------------


WORLD_CLONE = REPO_ROOT / "world"
needs_world_clone = pytest.mark.skipif(
    not (WORLD_CLONE / "docker-compose.yml").is_file(),
    reason=(
        "world/ is not cloned. It is gitignored (ADR-0026 - a pinned clone of somebody else's "
        "repository), so CI does not have it, and every digest that reads a file inside it is "
        "`None` there by design. Skipping is correct: these guards compare digests, and a digest "
        "nobody can compute is not a disagreement. Run them locally after `make world-up`."
    ),
)


@needs_world_clone
def test_bundles_that_record_an_observability_digest_agree_with_the_repository() -> None:
    """**The guard T7.14's hole needed, and the one that fires where a person will see it.**

    Editing a threshold in `alert-rules.yml` changes what every future bundle records - which
    alerts fire, how fast, how wide the blast radius is - and until T7.15 no manifest field
    moved when it happened. `compose_digest` covers the compose files, which *name* these as
    mounts and say nothing about what is inside them.

    The check is against the repository as it stands now, not bundle-against-bundle, because
    the drift to catch happens at the moment somebody edits a rule, not months later when the
    next bundle is finally recorded.

    **Bundles recorded before T7.15 have no such field and are skipped.** That is not a
    loophole: the digest is not derivable from a capture, so it could not be backfilled
    honestly, and absence means unknown rather than agreed.
    """
    current = observability_digest()
    assert current, "the observability files are missing - is world/ cloned?"

    recorded: dict[str, list[str]] = {}
    for bundle in valid_bundles():
        world = manifest_of(bundle).get("world", {})
        digest = world.get("observability_digest")
        if digest:
            recorded.setdefault(digest, []).append(bundle.name)

    stale = {d: names for d, names in recorded.items() if d != current}
    assert not stale, observability_drift_message(stale)


def observability_drift_message(stale: dict[str, list[str]]) -> str:
    """Say what changed and what it means for bundles recorded before it."""
    per_file = observability_digests()
    lines = [
        "the observability config changed since these bundles were recorded, so what they "
        "record is no longer what this repository would record.",
        "",
        "Files under cover, and their digests now:",
    ]
    for name, why in OBSERVABILITY_FILES:
        digest = per_file.get(name)
        lines.append(f"  {(digest or 'MISSING')[:12]}  {name}")
        lines.append(f"                {why}")
    lines += [
        "",
        f"current combined digest: {observability_digest()}",
        "recorded by these bundles:",
    ]
    for digest, names in sorted(stale.items()):
        lines.append(f"  {digest[:12]}  {', '.join(sorted(names))}")
    lines += [
        "",
        "What this means for them: their alert timings, blast radius and log evidence were "
        "measured against a different observability pipeline than the one in the tree now. "
        "They are not wrong about what happened; they are no longer comparable with anything "
        "recorded after the change.",
        "",
        "Resolve it the way ADR-0014 resolves a world change - re-record, or mark the bundles "
        "invalid with the reason. Do NOT edit the recorded digest to match: it is a claim "
        "about the pipeline that produced the capture, and rewriting it makes the bundle lie.",
    ]
    return "\n".join(lines)


@needs_world_clone
def test_the_guard_reproduces_the_shape_a_rule_edit_makes() -> None:
    """A rule is edited, the digest moves, and the mismatch surfaces naming the file.

    The whole failure T7.14 described, walked end to end against the real files rather than a
    fixture - so the test fails if the digest ever stops covering `alert-rules.yml`.
    """
    rules = REPO_ROOT / "compose" / "prometheus" / "alert-rules.yml"
    before, before_files = observability_digest(), observability_digests()
    original = rules.read_bytes()
    try:
        # The edit T7.14 argued against: move ServiceHighLatency's threshold.
        rules.write_bytes(original.replace(b") > 250", b") > 500"))
        after, after_files = observability_digest(), observability_digests()

        assert after != before, "editing a threshold must move the digest"
        moved = [n for n in after_files if after_files[n] != before_files[n]]
        assert moved == ["compose/prometheus/alert-rules.yml"], (
            "only the edited file's digest may move, so a mismatch names what changed"
        )

        # And the message a person actually reads names the file and says what it means.
        message = observability_drift_message({before: ["some-recorded-bundle"]})
        assert "compose/prometheus/alert-rules.yml" in message
        assert "no longer comparable" in message
        assert "makes the bundle lie" in message
    finally:
        rules.write_bytes(original)

    assert observability_digest() == before, "the test must leave the rules file untouched"


@needs_world_clone
def test_every_file_under_cover_exists_and_is_actually_mounted() -> None:
    """A digest over a path that no longer exists silently degrades to None and covers nothing.

    Also pins the mount: each file is named in a compose file that mounts it into the running
    world, so the set cannot drift into covering something the world never reads - which is
    exactly what `world/src/prometheus/prometheus-config.yaml` turned out to be.
    """
    mounts = "\n".join(
        (REPO_ROOT / f).read_text() for f in ("compose/telemetry.yml", "world/docker-compose.yml")
    )
    for name, why in OBSERVABILITY_FILES:
        assert (REPO_ROOT / name).is_file(), f"{name} is under digest cover but does not exist"
        assert why.strip(), f"{name} must say what it decides"
        assert Path(name).name in mounts, (
            f"{name} is under digest cover but no compose file mounts it - a digest over a "
            "file the world never reads records nothing"
        )


# --- T7.16: the world is somebody else's repository -----------------------------------------


def test_bundles_agree_about_the_image_they_ran() -> None:
    """**The mutable half of `otel_demo_image`, guarded (T7.16).**

    Every demo image is pulled rather than built (`--no-build`), so a bundle's
    `otel_demo_image` names a tag that upstream can republish. Two bundles could then claim the
    same world, byte-for-byte identical in every other provenance field, while having run
    different code. The content digest is what makes that visible.

    Bundle-against-bundle rather than against the live daemon, so this runs without Docker.
    Bundles recorded before T7.16 carry no digest and are skipped: absence means unknown.
    """
    seen: dict[str, list[str]] = {}
    for bundle in valid_bundles():
        world = manifest_of(bundle).get("world", {})
        digest = world.get("otel_demo_image_digest")
        if digest:
            seen.setdefault(digest, []).append(bundle.name)

    assert len(seen) <= 1, image_digest_drift_message(seen)


def image_digest_drift_message(seen: dict[str, list[str]]) -> str:
    """Say what moved, and what it means for the bundles on either side of it."""
    lines = [
        "valid bundles ran different images while claiming the same world.",
        "",
        "The demo's images are pulled, never built here, so `otel_demo_image` records a tag "
        "and a tag can be republished upstream. These bundles disagree about what that tag "
        "actually resolved to:",
        "",
    ]
    for digest, names in sorted(seen.items()):
        lines.append(f"  {digest}")
        lines.append(f"      {', '.join(sorted(names))}")
    lines += [
        "",
        "What this means: their numbers are not comparable, and the fields that would normally "
        "show a world change - compose_digest, ffs_stub_source_digest, observability_digest - "
        "will all agree, because none of them describes the image contents.",
        "",
        "Resolve it as ADR-0014 resolves a world change: re-record, or mark the older bundles "
        "invalid with the reason. Do NOT edit the recorded digest to match.",
    ]
    return "\n".join(lines)


def test_the_guard_reproduces_the_shape_a_republished_tag_makes() -> None:
    """A tag republished upstream: same tag string, different content, every other field equal.

    The failure this field exists for, walked through - and the message has to say the thing a
    reader would otherwise get wrong, which is that the other digests agreeing proves nothing.
    """
    before = "ghcr.io/open-telemetry/demo@sha256:" + "a" * 64
    after = "ghcr.io/open-telemetry/demo@sha256:" + "b" * 64

    message = image_digest_drift_message(
        {before: ["cart-redis-misconfig"], after: ["ad-memory-squeeze"]}
    )

    assert before in message and after in message
    assert "cart-redis-misconfig" in message and "ad-memory-squeeze" in message
    assert "a tag can be republished upstream" in message
    assert "will all agree, because none of them describes the image contents" in message
    assert "Do NOT edit the recorded digest to match" in message


def test_a_recorded_image_digest_is_a_content_digest_not_a_tag() -> None:
    """The field is only worth anything if it is the immutable form."""
    for bundle in valid_bundles():
        digest = manifest_of(bundle).get("world", {}).get("otel_demo_image_digest")
        if digest:
            assert "@sha256:" in digest, (
                f"{bundle.name}: otel_demo_image_digest is {digest!r}, which is a tag. The "
                "field exists because tags are mutable; recording one defeats it."
            )


def test_the_clone_is_recorded_by_nothing_and_that_is_the_decision() -> None:
    """**T7.16 decided to record nothing about the world clone.** This pins the decision.

    The clone is not the source of what runs: images are pulled, and the only three clone files
    that shape a bundle are already covered by content digests - `world/docker-compose.yml` by
    `compose_digest`, and both collector configs by `observability_digest`. A commit SHA, a
    dirty flag or an untracked-file digest would each catch nothing those digests miss, and the
    last would churn on a Docker mount artifact that reappears on every `world-up`. See ADR-0026.

    If a later task adds a clone field, this test fails and sends the reader to the argument
    rather than letting it in by habit.
    """
    from evalharness.provenance import world_provenance

    source = inspect.getsource(world_provenance)
    for banned in ("world_git_sha", "world_dirty", "world_untracked", "clone_sha"):
        assert banned not in source, (
            f"{banned} was added to world provenance. T7.16 argued the clone should be "
            "recorded by nothing - if that has changed, change ADR-0026 with it."
        )


def test_the_covered_clone_files_are_the_only_ones_that_can_reach_a_bundle() -> None:
    """The premise the decision rests on, made checkable.

    Three files inside the clone shape what a bundle records, and all three are already
    digested. Everything else in the clone is build context for images that are never built.
    """
    from injector.settings import InjectorSettings

    from_clone_in_compose = [
        f for f in InjectorSettings().compose_files if not str(f).startswith("..")
    ]
    assert [str(f) for f in from_clone_in_compose] == ["docker-compose.yml"], (
        "compose_digest's clone-resident inputs changed; ADR-0026's argument counts them"
    )
    from_clone_in_observability = [n for n, _ in OBSERVABILITY_FILES if n.startswith("world/")]
    assert from_clone_in_observability == [
        "world/src/otelcollector/otelcol-config.yml",
        "world/src/otelcollector/otelcol-config-extras.yml",
    ]

    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "--no-build" in makefile, (
        "the world is now built from the clone rather than pulled, which invalidates ADR-0026: "
        "the clone's source would then be the source of what runs"
    )


def test_recorded_reachability_matches_the_captures_beside_it() -> None:
    """**The manifest's `reachability` is derived, so it must agree with a re-derivation (T7.22).**

    It did not. `write_bundle` derives the field from the bundle directory, and the recorder
    called it *before* writing the metrics and logs — so it read an empty directory and stamped
    `target_log_lines: 0, none_can_answer: true` onto a bundle holding 126 log lines.

    It went unnoticed because no bundle had been recorded since T7.5 introduced the field: every
    existing value was derived over an already-finished bundle rather than produced by this path.

    **A false `none_can_answer` is the worst direction for this field to be wrong in.** T7.5 added
    it so a scorer could tell an abstention nothing could have answered from one caused by
    reasoning, and this would have marked a scenario unanswerable when its evidence was sitting
    in the same directory.
    """
    for bundle in valid_bundles():
        recorded = manifest_of(bundle).get("reachability")
        if recorded is None:
            continue  # predates the field, which is permitted
        assert recorded == reachability.derive(bundle), (
            f"{bundle.name}: manifest reachability disagrees with a re-derivation from its own "
            f"captures.\n  recorded:   {recorded}\n  re-derived: {reachability.derive(bundle)}\n"
            "The field is derived, not asserted, so a disagreement means it was computed against "
            "a different set of files than the ones stored here - check the recorder's write "
            "order (T7.22)."
        )
