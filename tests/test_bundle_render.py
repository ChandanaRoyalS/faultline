"""T5.3b: rendering recorded bundles for a human reader.

No model calls and no live services - the renderer reads committed files and writes Markdown,
so the autouse guards in conftest have nothing to intercept. What is pinned here is the shape
of a page, the determinism the whole thing rests on, and the two cases that would otherwise be
found by a reader rather than by a test: a bundle where nothing fired, and output the
pre-commit hooks would rewrite.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from evalharness import bundle_render

FIXTURE_MANIFEST = {
    "scenario_id": "fixture-scenario",
    "title": "A fixture, not a rehearsal",
    "split": "dev",
    "fault_class": "bad_config",
    "expected_remediation_class": "config_revert",
    "injection": {"target": "cartservice", "method": "fixture-method"},
    "seconds_to_alert": 165,
    "seconds_of_steady_state": 300,
    "window": {"start": "2026-08-24T04:39:27+00:00", "end": "2026-08-24T04:57:13+00:00"},
    "t_inject": "2026-08-24T04:44:27+00:00",
    "t_alert_firing": "2026-08-24T04:47:12+00:00",
    "t_revert": "2026-08-24T04:52:12+00:00",
    "t_clear": "2026-08-24T04:55:13+00:00",
    "alerts_at_fire": ["ServiceHighErrorRate/frontend"],
    "alerts_over_window": [
        {
            "alert": "ServiceHighErrorRate",
            "service": "frontend",
            "first_seen": "2026-08-24T04:47:12+00:00",
            "last_seen": "2026-08-24T04:54:27+00:00",
            "minutes_firing": 7.5,
            "began_after_revert": False,
        },
        {
            "alert": "ServiceNoTraffic",
            "service": "emailservice",
            "first_seen": "2026-08-24T04:50:27+00:00",
            "last_seen": "2026-08-24T04:52:27+00:00",
            "minutes_firing": 2.2,
            "began_after_revert": True,
        },
    ],
}


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """One bundle with every part a page can show, so the fixture exercises each branch."""
    root = tmp_path / "dev" / "fixture-scenario"
    (root / "metrics").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "manifest.json").write_text(json.dumps(FIXTURE_MANIFEST))
    (root / "metrics" / "error-ratio.json").write_text('{"status": "success"}')
    (root / "queries.md").write_text("# Queries\n\n## error-ratio\n\n```promql\nup\n```\n")
    # An ANSI escape and a trailing space, both of which must be gone from the page.
    (root / "logs" / "cart-service.txt").write_text(
        "# target container: cart-service\n\x1b[31mred line\x1b[0m   \nplain line\n"
    )
    (root / "incident.md").write_text(
        "---\norigin: scenario:fixture-scenario\nfault_class: bad_config\n---\n\n"
        "# A fixture, not a rehearsal\n\n## What was observed\n\nSomething broke.\n"
    )
    return root


def test_a_page_carries_the_scenario_the_timeline_and_the_narrative(bundle: Path) -> None:
    page = bundle_render.render(bundle)

    assert page.startswith("# A fixture, not a rehearsal\n")
    assert "| fault class | **`bad_config`** |" in page
    assert "| split | `dev` |" in page
    # Times are offsets from the injection, never local clock times.
    assert "| first alert firing | T+2m45s |" in page
    assert "| T+2m45s | `frontend` | ServiceHighErrorRate | 7.5 min | **paged** |" in page
    # The two labels that carry meaning a reader cannot reconstruct from a timestamp.
    assert "began after the revert" in page
    assert "`metrics/error-ratio.json`" in page and "`up`" in page
    assert "## The incident record" in page and "Something broke." in page
    # The narrative's own H1 is the page title and must not appear twice.
    assert page.count("A fixture, not a rehearsal") == 1
    # Its headings are demoted so they nest under the page's sections.
    assert "### What was observed" in page


def test_the_same_bundle_renders_to_the_same_bytes(bundle: Path) -> None:
    """The property everything else depends on. A page that moved between renders would put
    an unreviewable diff in front of anyone who regenerated the docs."""
    assert bundle_render.render(bundle) == bundle_render.render(bundle)


def test_rendering_never_reads_the_clock(bundle: Path) -> None:
    """Determinism has one obvious way to fail, so it is pinned at the source rather than by
    grepping the output for today's date - the bundle's own timestamps contain the current
    year, so that check passes or fails for the wrong reason."""

    class NoClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            raise AssertionError("render() read the clock; its output is not reproducible")

        @classmethod
        def utcnow(cls) -> datetime:  # type: ignore[override]
            raise AssertionError("render() read the clock; its output is not reproducible")

    monkeypatched = bundle_render.datetime
    bundle_render.datetime = NoClock  # type: ignore[misc]
    try:
        assert bundle_render.render(bundle)
    finally:
        bundle_render.datetime = monkeypatched  # type: ignore[misc]


def test_a_page_survives_the_pre_commit_hooks_unchanged(bundle: Path) -> None:
    """`docs/bundles/` is not in the captured-evidence exclusion, so `trailing-whitespace`
    and `end-of-file-fixer` rewrite whatever is left there. A renderer whose output those
    hooks corrected would disagree with its own files after every commit."""
    page = bundle_render.render(bundle)

    assert not any(line != line.rstrip() for line in page.split("\n")), "hook would rewrite"
    assert page.endswith("\n") and not page.endswith("\n\n"), "exactly one final newline"


def test_hostile_log_content_does_not_reach_the_page(bundle: Path) -> None:
    """Captured logs are attacker-shaped by construction and two committed captures carry
    ANSI escapes (ADR-0019 measured them). They are stripped before rendering."""
    page = bundle_render.render(bundle)

    assert "\x1b" not in page
    assert "red line" in page, "the text survives; only the escape is removed"


def test_a_bundle_where_nothing_fired_says_so(bundle: Path) -> None:
    """The two INVALID bundles carry `null` for the alert time and an empty alert list. A page
    that rendered those as `T+0m00s` would claim an instant page for a fault that never paged."""
    manifest = dict(FIXTURE_MANIFEST)
    manifest["seconds_to_alert"] = None
    manifest["t_alert_firing"] = None
    manifest["alerts_at_fire"] = []
    manifest["alerts_over_window"] = []
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (bundle / "INVALID.md").write_text("# not evidence\n")

    page = bundle_render.render(bundle)

    assert "⚠ This bundle is not evidence of anything" in page
    assert "| time to page | — never paged |" in page
    assert "| first alert firing | — |" in page
    assert "_No alert fired over the capture window._" in page
    assert "T+0m00s" in page, "t_inject is still a real moment"


def test_a_directory_without_a_manifest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(bundle_render.BundleError, match="not a bundle"):
        bundle_render.render(tmp_path)


def test_the_committed_pages_match_the_committed_bundles() -> None:
    """The renderer and `docs/bundles/` are checked in together; this is what catches a bundle
    that changed without its page being regenerated."""
    assert bundle_render.main(["--all", "--check"]) == 0, "run `faultline-render --all`"


def test_every_link_on_a_generated_page_resolves() -> None:
    """A generated page can ship a dead link silently - this one shipped
    `0008-contamination-and-splits.md`, which has been `0008-contamination-model.md` since it
    was written. Generated docs get the check that hand-written ones get from being read."""
    import re

    pages = sorted(bundle_render.DEFAULT_OUT.glob("*.md"))
    assert pages, "run `faultline-render --all`"

    broken: list[str] = []
    for page in pages:
        for target in re.findall(r"\]\((?!https?:)([^)#]+)", page.read_text()):
            if not (page.parent / target).exists():
                broken.append(f"{page.name} -> {target}")
    assert not broken, f"dead links on generated pages: {broken}"
