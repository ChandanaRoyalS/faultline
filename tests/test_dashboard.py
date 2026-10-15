"""T7.4's eval dashboard: generated from the record, held to it, and honest about its counts."""

from __future__ import annotations

from pathlib import Path

from evalharness import dashboard
from evalharness.evaldb import read_runs, row_of

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "evals" / "dashboard" / "index.html"
NOTES = REPO / "evals" / "dashboard" / "versions.tsv"


def manifest(
    *,
    runtime: str = "faultline/0.0.1+prompts:aaaaaaaaaaaa",
    correct: bool = True,
    abstained: bool = False,
    truth: str = "bad_config",
    started: str = "2026-10-01T00:00:00+00:00",
    generation: str = "gen1",
    ablation_config: dict | None = None,
) -> dict:
    return {
        "run_id": f"r-{started}-{correct}-{runtime[-4:]}",
        "scenario_id": "s",
        "started_at": started,
        "comparability": {"generation": generation},
        "ablation_config": ablation_config or {},
        "score": {
            "runtime_version": runtime,
            "cost_usd": 0.5,
            "fault_class": {
                "truth": truth,
                "returned": truth if correct else "other",
                "correct": correct,
                "abstained": abstained,
            },
            "service": {"correct": correct, "abstained": False},
        },
        "metrics": {
            "latency": {"investigation_ms": 200_000},
            "citations": {"violations": 0, "regenerated": False},
            "tool_calls": {"validity_rate": 1.0},
        },
    }


def test_the_committed_page_is_the_record() -> None:
    """The rule README's generated blocks are held to: regenerate and compare, byte for byte."""
    page = dashboard.render(read_runs(REPO / "evals" / "runs"), dashboard.read_notes(NOTES))
    assert PAGE.read_text() == page, (
        "evals/dashboard/index.html does not match evals/runs/. Regenerate: make eval-dashboard"
    )


def test_a_rate_carries_its_n_and_an_interval() -> None:
    cell = dashboard.rate(3, 4)
    assert cell.startswith("3/4 = 75%")
    lo, hi = dashboard.wilson(3, 4)
    assert 0 < lo < 0.75 < hi < 1
    assert dashboard.rate(0, 0) == "-"


def test_abstentions_leave_the_denominator_and_gated_misses_stay() -> None:
    rows = [
        row_of(manifest(correct=True)),
        row_of(manifest(correct=False)),
        row_of(manifest(correct=False, abstained=True)),
    ]
    (version,) = dashboard.versions_of(rows)
    assert dashboard._answered(version.rows, "fault_class") == (1, 2)


def test_an_ablation_switch_is_its_own_version_under_the_same_stamp() -> None:
    """T7.3's switches move no stamp by design, so the dashboard must split on them or an arm's
    runs pool with the standing pipeline's."""
    rows = [
        row_of(manifest()),
        row_of(manifest(ablation_config={"evidence_mode": "raw"}, started="2026-10-02T00:00:00")),
    ]
    versions = dashboard.versions_of(rows)
    assert [v.variant for v in versions] == ["", "evidence_mode=raw"]
    assert versions[1].label.endswith("[evidence_mode=raw]")


def test_unstamped_and_unscored_runs_are_not_charted() -> None:
    unstamped = manifest()
    unstamped["score"]["runtime_version"] = None
    discarded = manifest()
    discarded["discarded"] = {"reason": "run failed"}
    assert dashboard.versions_of([row_of(unstamped), row_of(discarded)]) == []


def test_every_charted_version_says_what_changed_and_cites_a_file_that_exists() -> None:
    """The plan's *"version timeline annotated with what changed"*: a stamp that reaches the
    chart without a line in versions.tsv fails here, not silently as a blank cell."""
    notes = dashboard.read_notes(NOTES)
    versions = dashboard.versions_of(read_runs(REPO / "evals" / "runs"))
    missing = [v.label for v in versions if dashboard.note_for(v, notes) is None]
    assert missing == [], f"add a row to {NOTES.name} for: {missing}"
    for version in versions:
        note = dashboard.note_for(version, notes)
        assert note is not None and note.what.strip()
        assert (REPO / note.source).is_file(), (version.label, note.source)


def test_no_annotation_is_stale() -> None:
    """A row for a version no run carries is a note about nothing - usually a typo in a digest."""
    keys = set(dashboard.read_notes(NOTES))
    versions = dashboard.versions_of(read_runs(REPO / "evals" / "runs"))
    charted = {v.digest for v in versions} | {v.label for v in versions}
    assert keys <= charted, keys - charted


def test_a_switch_is_annotated_as_one_and_a_withheld_specialist_needs_its_own_row() -> None:
    notes = {"aaaaaaaaaaaa": dashboard.Note("the move", "docs/PLAN.md")}
    rows = [
        row_of(manifest()),
        row_of(manifest(ablation_config={"evidence_mode": "raw"}, started="2026-10-02T00:00:00")),
    ]
    stamp, switch = dashboard.versions_of(rows)
    assert dashboard.note_for(stamp, notes) == notes["aaaaaaaaaaaa"]
    switched = dashboard.note_for(switch, notes)
    assert switched is not None and "does not move" in switched.what
    assert switched.source == "docs/ABLATIONS.md"
    withheld = dashboard.Version(stamp.runtime, stamp.generation, "without traces")
    assert dashboard.note_for(withheld, notes) is None
    page = dashboard.render(rows, notes)
    assert 'the move <a href="../../docs/PLAN.md">docs/PLAN.md</a>' in page


def test_by_class_gives_counts_on_the_newest_world_only() -> None:
    rows = [
        row_of(manifest(generation="old", started="2026-09-01T00:00:00")),
        row_of(manifest(generation="new", truth="disk_fill", started="2026-10-01T00:00:00")),
        row_of(
            manifest(
                generation="new", truth="disk_fill", correct=False, started="2026-10-01T01:00:00"
            )
        ),
    ]
    section = "\n".join(dashboard.by_class(dashboard.versions_of(rows)))
    assert "world <code>new</code>" in section
    assert "<td>disk_fill</td><td>1/2</td>" in section
    assert "bad_config" not in section


def test_the_page_is_self_contained() -> None:
    """No script and no external asset: it must open from a clone, offline."""
    page = PAGE.read_text()
    assert "<script" not in page
    assert "http://" not in page and "https://" not in page
