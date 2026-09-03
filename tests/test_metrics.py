"""T4.3's metric panel, and the properties that keep its numbers honest."""

from __future__ import annotations

from evalharness import metrics


def envelope(**attributes: str) -> str:
    """A rendered envelope's opening tag plus a body, in the shape `envelope.render` emits."""
    tag = " ".join(f'{key}="{value}"' for key, value in attributes.items())
    return f"<tool_result {tag}>\nbody text\n</tool_result:{attributes.get('id', 'x')}>"


# --- the parse is pinned to the renderer -------------------------------------------------


def test_the_parse_reads_back_exactly_what_the_renderer_wrote() -> None:
    """**The property the whole validity metric rests on.**

    Validity is read out of the envelope rather than a status column, which is only safe because
    `escape_attribute` replaces every `"` with `'` before rendering - so inside a rendered tag
    every quote is a delimiter and the parse cannot be confused by content. This asserts that
    against the real renderer rather than against a hand-built string, so the parse cannot drift
    if the renderer changes.
    """
    from faultline.tools.envelope import render
    from faultline.tools.results import LogResult

    result = LogResult(
        selector='{service="cart"}',
        error='the query failed: unexpected "}"',
    )
    parsed = metrics.envelope_attributes(render(result))

    assert parsed["tool"] == "logql_query"
    assert parsed["trust"] == "untrusted"
    assert "error" in parsed, "an errored call must be visible to the panel"


def test_the_body_cannot_forge_an_attribute() -> None:
    """Only the opening tag is parsed. The body is neutralised untrusted content and may contain
    anything shaped like an attribute - a log line reading `error="..."` must not make a valid
    call look invalid, which is the same injection thesis the envelope exists for."""
    forged = (
        '<tool_result id="1" tool="logql_query" empty="false">\nerror="forged"\n</tool_result:1>'
    )

    assert "error" not in metrics.envelope_attributes(forged)


# --- validity ----------------------------------------------------------------------------


def test_an_empty_result_is_a_valid_call() -> None:
    """**ADR-0019's distinction, and the reason this metric is worth having.** A window that was
    observed and held nothing is evidence; only a query that failed to parse or execute is
    invalid. Scoring an empty result as invalid would penalise a specialist for asking a question
    whose answer was no."""
    panel = metrics.tool_calls(
        [
            ("logql_query", {"service": "a"}, envelope(id="1", empty="true")),
            ("promql_query", {"service": "b"}, envelope(id="2", empty="false")),
        ]
    )

    assert panel.total == 2
    assert panel.errored == 0
    assert panel.empty == 1
    assert panel.validity_rate == 1.0


def test_an_errored_call_is_invalid() -> None:
    panel = metrics.tool_calls(
        [
            ("logql_query", {"service": "a"}, envelope(id="1", error="parse failure")),
            ("logql_query", {"service": "b"}, envelope(id="2")),
        ]
    )

    assert panel.errored == 1
    assert panel.valid == 1
    assert panel.validity_rate == 0.5


def test_a_run_that_made_no_tool_call_has_no_validity_rate() -> None:
    """**`None`, not 1.0.** A run that asked nothing has not achieved perfect validity, and a
    fabricated 1.0 averaged into a catalog figure would reward a pipeline for asking less."""
    assert metrics.tool_calls([]).validity_rate is None
    assert metrics.tool_calls([]).redundancy_rate is None


# --- redundancy --------------------------------------------------------------------------


def test_redundancy_counts_the_repeat_and_not_the_original() -> None:
    """The number is *calls that bought nothing*, so the first of a repeated pair is not counted.
    Keyed on `(tool, service, window)` because two queries of one tool against different services
    are two questions."""
    window = ["2026-09-03T00:00:00Z", "2026-09-03T00:30:00Z"]
    panel = metrics.tool_calls(
        [
            ("logql_query", {"service": "cart", "window": window}, envelope(id="1")),
            ("logql_query", {"service": "cart", "window": window}, envelope(id="2")),
            ("logql_query", {"service": "checkout", "window": window}, envelope(id="3")),
        ]
    )

    assert panel.redundant == 1
    assert panel.total == 3


# --- context budget ----------------------------------------------------------------------


def test_overflow_is_counted_per_briefing_not_per_role() -> None:
    """A role briefed twice - the planner, across two rounds - has two chances to overflow and
    both are facts about the run."""
    panel = metrics.briefings(
        {
            "dropped_sections": 3,
            "briefings": [
                {"role": "planner", "over_budget": False, "estimated_tokens": 900, "budget": 4000},
                {"role": "planner", "over_budget": True, "estimated_tokens": 4200, "budget": 4000},
                {
                    "role": "synthesizer",
                    "over_budget": True,
                    "estimated_tokens": 8685,
                    "budget": 4000,
                },
            ],
        }
    )

    assert panel.total == 3
    assert panel.over_budget == 2
    assert panel.overflow_rate is not None
    assert round(panel.overflow_rate, 4) == round(2 / 3, 4)
    assert panel.largest_estimated_tokens == 8685
    assert panel.dropped_sections == 3


def test_a_run_before_progressive_disclosure_has_no_briefings_and_no_rate() -> None:
    """Runs recorded before T3.2c carry no `disclosure` payload. Absent is not zero-overflow."""
    assert metrics.briefings(None).overflow_rate is None
    assert metrics.briefings({}).total == 0


# --- latency -----------------------------------------------------------------------------


def test_the_gate4_comparison_is_per_run_and_says_so() -> None:
    """Gate 4 names the **dev-set median** at ≤ 3 minutes. `within_gate4` is a per-run comparison
    against that threshold and is not the gate's condition - one run inside it proves nothing."""
    assert metrics.Latency(investigation_ms=179_000).within_gate4 is True
    assert metrics.Latency(investigation_ms=181_000).within_gate4 is False
    assert metrics.GATE4_TIME_TO_REPORT_MS == 180_000


def test_the_panel_prints_n_a_rather_than_inventing_a_rate() -> None:
    rendered = "\n".join(metrics.MetricPanel().render())

    assert "validity n/a" in rendered
    assert "1.00" not in rendered.split("validity")[1].split("\n")[0]
