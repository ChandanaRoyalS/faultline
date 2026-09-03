"""What every tool result **actually** looks like, pinned before anything else reads one.

## Why this file exists

B0 v1 shipped with three defects. Two were the same mistake made twice:

- it read `ChangeResult.records` rows as objects (`record.service`, `record.at`). They are
  **dicts**, and they carry no `service` key at all.
- it read `result.points` from a `MetricResult`. That attribute does not exist; the points live
  one level down, on each entry of `series`.

Neither raised in the one live run B0 v1 ever made, because the service it queried had no changes
and the second read was wrapped in `getattr(..., [])`. A wrong reader that returns an empty list
does not look like a bug; it looks like an absence of data, and B0 duly reported *"no error-ratio
series available"* about a service that publishes one.

Both mistakes came from writing a reader against a recollection of a type instead of against the
type. This file is the type, written down, so the next reader fails at the shape rather than
succeeding into a fallback. It is deliberately boring.

## The root cause, which is a real inconsistency and not just carelessness

**Collections on tool results do not share an element convention.**

| result | field | element |
|---|---|---|
| `ChangeResult` | `records` | `dict` |
| `BaselineResult` | `changes` | `dict` |
| `MetricResult` | `series` | `MetricSeries` model |
| `LogResult` | `lines` | `LogLine` model |
| `TraceResult` | `spans` | `TraceSpan` model |

Three of the five are models and two are dicts, and nothing in the names says which. A reader that
learns the convention from `LogResult` and applies it to `ChangeResult` is wrong; a reader that
learns it from `ChangeResult` and applies it to `TraceResult` is wrong the other way. That is
exactly what happened.

This file does not fix the inconsistency - changing a field's element type would move the bytes of
every envelope, which is a digest-locked change and belongs in `docs/QUEUE.md`. It makes the
inconsistency **loud**: `ROW_FIELDS` and `MODEL_FIELDS` below enumerate every collection on every
result type, and a new result type whose collections appear in neither fails
`test_every_collection_on_every_result_is_classified`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from faultline.tools.envelope import render
from faultline.tools.results import (
    BaselineResult,
    ChangeResult,
    LogLine,
    LogResult,
    MetricResult,
    MetricSeries,
    ToolResult,
    TraceResult,
    TraceSpan,
    Window,
)

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
WINDOW = Window(start=NOW - timedelta(minutes=30), end=NOW)


# --- the element convention, enumerated ------------------------------------------------------

ROW_FIELDS: dict[str, str] = {
    "ChangeResult": "records",
    "BaselineResult": "changes",
}
"""Collections whose elements are **dicts**. Read with `row["key"]` / `row.get("key")`."""

MODEL_FIELDS: dict[str, str] = {
    "MetricResult": "series",
    "LogResult": "lines",
    "TraceResult": "spans",
}
"""Collections whose elements are **pydantic models**. Read with `element.attribute`."""


def test_every_collection_on_every_result_is_classified() -> None:
    """**The guard that makes the inconsistency loud instead of latent.**

    A new result type, or a new collection on an existing one, fails here until someone has
    decided which convention it follows and written that decision down. The decision is cheap;
    discovering it from a wrong reader in a live run is what this repository has already paid for
    once.
    """
    classified = set(ROW_FIELDS.items()) | set(MODEL_FIELDS.items())
    unclassified: list[str] = []
    for subclass in ToolResult.__subclasses__():
        for name, info in subclass.model_fields.items():
            annotation = str(info.annotation)
            if not annotation.startswith("list["):
                continue
            if (subclass.__name__, name) not in classified:
                unclassified.append(f"{subclass.__name__}.{name}: {annotation}")

    assert unclassified == [], (
        "unclassified collection(s) - add to ROW_FIELDS or MODEL_FIELDS with a test: "
        + ", ".join(unclassified)
    )


# --- ChangeResult: dict rows, no service, ISO-string timestamps -----------------------------


def change_row(**overrides: object) -> dict:
    """A row **exactly as `ChangeRecord.as_row` emits one.**

    Not a convenience: `ChangeResult.body()` indexes `at`, `actor`, `resource`, `action` and
    `summary` with `[]` rather than `.get`, so a partial row raises `KeyError` at render time
    rather than at construction. `as_row` is the only safe producer, and a test fixture that
    hand-writes a row is writing a row that cannot be rendered.
    """
    row = {
        "at": (NOW - timedelta(minutes=4)).isoformat(),
        "actor": "deployer",
        "resource": "resource_limits",
        "action": "updated",
        "summary": "memory limit 300Mi -> 40Mi",
        "before": "300Mi",
        "after": "40Mi",
    }
    row.update(overrides)  # type: ignore[arg-type]
    return row


def test_change_records_are_dicts_and_not_objects() -> None:
    """**B0 v1's defect, in one assertion.**"""
    result = ChangeResult(service="adservice", window=WINDOW, records=[change_row()])

    assert isinstance(result.records[0], dict)
    assert not hasattr(result.records[0], "resource"), "the v1 read; it is a key, not an attribute"


def test_a_change_row_carries_no_service_because_the_service_is_the_query() -> None:
    """The service is a property of the *result*, not of the row. A reader collecting changes
    across several services must take it from `result.service` per call, which is why
    `baselines.changes_in` takes the queried service as an argument."""
    result = ChangeResult(service="adservice", window=WINDOW, records=[change_row()])

    assert "service" not in result.records[0]
    assert result.service == "adservice"


def test_a_change_rows_timestamp_is_an_iso_string_and_not_a_datetime() -> None:
    """`ChangeRecord.as_row` serialises `at`. A reader comparing it to an onset `datetime` without
    parsing raises `TypeError`; one parsing it without a timezone gets a naive value that compares
    across onset wrongly by however many hours the reader's locale is offset."""
    result = ChangeResult(service="adservice", window=WINDOW, records=[change_row()])

    at = result.records[0]["at"]
    assert isinstance(at, str)
    assert datetime.fromisoformat(at) == NOW - timedelta(minutes=4)


def test_the_canonical_row_is_whatever_change_record_emits() -> None:
    """Pinned against the producer rather than against this file's idea of it, so a field added to
    `ChangeRecord` fails here instead of silently never reaching a reader."""
    from faultline.tools.changes import Action, ChangeRecord, Resource

    record = ChangeRecord(
        id="c-1",
        service="adservice",
        at=NOW - timedelta(minutes=4),
        actor="deployer",
        resource=Resource.RESOURCE_LIMITS,
        action=Action.UPDATED,
        summary="memory limit 300Mi -> 40Mi",
        before="300Mi",
        after="40Mi",
    )

    row = record.as_row()

    # **Whole row, not just its keys.** A key-set comparison passed this file's first draft, in
    # which the fixture's `action` read "update" and the enum's value is "updated" - the same
    # class of near-miss the file exists to catch, caught only because the comparison widened.
    assert row == change_row(), "fixture and producer must not drift, in keys or in values"
    assert "service" not in row, "on the record, dropped from the row"
    assert "id" not in row, "likewise - a row is not addressable on its own"
    assert row["resource"] == "resource_limits", "the enum's value, not the enum"
    assert isinstance(row["action"], str), "serialised, so `row['action'] is Action.UPDATED` fails"


# --- MetricResult: series, each with points -------------------------------------------------


def test_a_metric_result_has_no_points_attribute() -> None:
    """**B0 v1's other defect.** `getattr(result, "points", [])` returned `[]` on every call, and
    an empty list is indistinguishable from a service that publishes no series - which is what B0
    then reported."""
    result = MetricResult(query="q", window=WINDOW)

    assert not hasattr(result, "points")
    assert hasattr(result, "series")


def test_points_live_on_each_series_as_timestamp_value_pairs() -> None:
    result = MetricResult(
        query="q",
        window=WINDOW,
        series=[MetricSeries(labels={"service_name": "cartservice"}, points=[(0.0, 0.01)])],
    )

    assert isinstance(result.series[0], MetricSeries)
    timestamp, value = result.series[0].points[0]
    assert (timestamp, value) == (0.0, 0.01)


def test_a_metric_series_timestamp_is_a_float_not_a_datetime() -> None:
    """Prometheus epoch seconds, unparsed. A reader sorting points by their first element is
    sorting by time; one passing that element to a `datetime` comparison is not."""
    series = MetricSeries(labels={}, points=[(1756900000.0, 0.5)])

    assert isinstance(series.points[0][0], float)


# --- LogResult and TraceResult: models, the opposite convention -----------------------------


def test_log_lines_are_models_and_not_dicts() -> None:
    """The opposite convention from `ChangeResult`, on a neighbouring type. This is the pair that
    makes a reader written from memory a coin flip."""
    result = LogResult(selector="{}", window=WINDOW, lines=[LogLine(at=NOW, line="boom")])

    assert isinstance(result.lines[0], LogLine)
    assert result.lines[0].at == NOW, "a real datetime here, unlike a change row's string"


def test_log_lines_come_from_both_ends_of_the_window_and_the_split_is_a_field() -> None:
    """T3.4b / ADR-0021: when `oldest_kept` is non-zero the list is two groups, not a contiguous
    stream. A reader treating `lines` as consecutive is reading a window that never existed - and
    a reader taking `lines[-1]` as "the latest" is right only by accident."""
    lines = [LogLine(at=NOW - timedelta(minutes=n), line=str(n)) for n in (30, 29, 2, 1)]
    result = LogResult(
        selector="{}", window=WINDOW, lines=lines, oldest_kept=2, newest_kept=2, truncated=True
    )

    assert result.oldest_kept + result.newest_kept == len(result.lines)
    assert "nothing in between" in result.body()


def test_trace_spans_are_models_with_a_duration_in_milliseconds() -> None:
    result = TraceResult(
        service="cartservice",
        window=WINDOW,
        spans=[
            TraceSpan(
                trace_id="abc123",
                service="cartservice",
                operation="GET /cart",
                started_at=NOW,
                duration_ms=15000.0,
            )
        ],
    )

    assert isinstance(result.spans[0], TraceSpan)
    assert result.spans[0].duration_ms == 15000.0
    assert result.spans[0].error is False, (
        "defaults false; absence of an error flag is not an error"
    )


# --- BaselineResult: two windows, and dict rows again ---------------------------------------


def test_a_baseline_result_carries_two_windows_and_the_comparison_is_the_finding() -> None:
    """T3.3b. `window` is the incident's and `baseline_window` the quiet one. A reader taking
    `window` alone has the number without the thing that makes it evidence."""
    result = BaselineResult(
        service="cartservice",
        template="latency-p95",
        query="q",
        window=WINDOW,
        baseline_window=Window(start=NOW - timedelta(hours=1), end=NOW - timedelta(minutes=30)),
        incident={"p95": 15000.0},
        baseline={"p95": 38.0},
        changes=[{"at": NOW.isoformat(), "direction": "up"}],
    )

    assert result.baseline_window is not None
    assert result.incident["p95"] != result.baseline["p95"]
    assert isinstance(result.changes[0], dict), "dict rows, like ChangeResult and unlike the rest"


# --- the base contract every result shares --------------------------------------------------


def test_error_and_empty_are_different_facts() -> None:
    """ADR-0019, and the distinction five of the nine rehearsed investigations turn on. A reader
    treating an errored result as an empty one converts *"we could not look"* into *"we looked and
    found nothing"*, which is the strongest negative evidence this system produces."""
    observed_empty = ChangeResult(service="s", window=WINDOW, records=[], empty=True)
    unavailable = ChangeResult(
        service="s", window=WINDOW, error="change log unreachable", empty=True
    )

    assert observed_empty.error is None
    assert unavailable.error is not None
    assert observed_empty.empty == unavailable.empty, (
        "`empty` alone cannot tell them apart - `error` is the discriminator"
    )


def test_a_capped_result_says_so_rather_than_looking_complete() -> None:
    """The logs failure mode named in `ToolResult.truncated`: a 500-line cap that reads as the
    whole window. One committed narrative's argument depends on knowing the difference."""
    assert LogResult(selector="{}", window=WINDOW, truncated=True).truncated is True
    assert LogResult(selector="{}", window=WINDOW).truncated is False


@pytest.mark.parametrize(
    "result",
    [
        ChangeResult(service="adservice", window=WINDOW, records=[change_row()]),
        MetricResult(
            query="q", window=WINDOW, series=[MetricSeries(labels={"a": "b"}, points=[(0.0, 1.0)])]
        ),
        LogResult(selector="{}", window=WINDOW, lines=[LogLine(at=NOW, line="x")]),
        TraceResult(
            service="s",
            window=WINDOW,
            spans=[
                TraceSpan(
                    trace_id="t", service="s", operation="op", started_at=NOW, duration_ms=1.0
                )
            ],
        ),
        BaselineResult(
            service="s", template="t", query="q", window=WINDOW, incident={}, baseline={}
        ),
    ],
    ids=["change", "metric", "log", "trace", "baseline"],
)
def test_every_populated_result_renders_without_raising(result: ToolResult) -> None:
    """**A shape error surfaces here or in production, and here is cheaper.**

    `body()` indexes rather than `.get`s in places, so a result assembled from a wrong idea of its
    own fields raises at render time - inside a tool call, mid-investigation. This is the case
    that caught a hand-written change row during the B0 v2 work.
    """
    envelope = render(result)

    assert envelope.startswith("<tool_result ")
    assert envelope.endswith(f"</tool_result:{result.id}>")
    assert result.id in envelope


def test_no_result_type_accepts_a_field_it_does_not_declare() -> None:
    """`extra="forbid"` on every result. A reader that writes back a field under a misremembered
    name fails at construction instead of storing a value nothing reads."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MetricResult(query="q", window=WINDOW, points=[(0.0, 1.0)])  # type: ignore[call-arg]
