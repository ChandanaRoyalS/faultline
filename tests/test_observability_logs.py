"""T6.6 piece 4: one JSON object per line, with the trace id when there is one.

Everything here runs without the `observability` extra. The trace id is supplied by
monkeypatching `tracing.current_ids`, which is the only seam the formatter reads it through -
so the join is tested without an SDK, and the SDK's own test (`test_observability_tracing`)
covers that `current_ids` says the truth when live.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest

from faultline.observability import logs, tracing

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root_restored() -> object:
    """Put the root logger back exactly as pytest had it, handlers and level both."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


def _one_line(stream: io.StringIO) -> dict[str, object]:
    lines = [ln for ln in stream.getvalue().splitlines() if ln]
    assert len(lines) == 1, lines
    return json.loads(lines[0])


def test_a_record_is_one_json_object_with_the_fixed_fields(root_restored: object) -> None:
    out = io.StringIO()
    assert logs.configure(component="orchestrator", stream=out, fmt="json") == "json"

    logging.getLogger("faultline.orchestrator.runner").info("investigating %s", "inc-1")

    line = _one_line(out)
    assert line["msg"] == "investigating inc-1"
    assert line["level"] == "INFO"
    assert line["logger"] == "faultline.orchestrator.runner"
    assert line["component"] == "orchestrator"
    assert line["ts"].endswith("+00:00"), "UTC, and says so"
    assert "trace_id" not in line, "not traced reads as absence, not as an empty string"


def test_the_orchestrator_s_info_line_now_comes_out(root_restored: object) -> None:
    """**The finding.** No commit in this repository ever configured logging, so the root logger
    sat at `WARNING` and `investigating <id> (attempt n)` - `log.info`, #233 - was dropped by
    every process that ran it while the warning beside it came out through the last-resort
    handler. Reproduced first, then asserted fixed."""
    root = logging.getLogger()
    root.handlers[:] = []
    root.setLevel(logging.WARNING)  # what `logging.getLogger()` starts at in a fresh process
    assert not logging.getLogger("faultline.orchestrator.runner").isEnabledFor(logging.INFO)

    out = io.StringIO()
    logs.configure(component="orchestrator", stream=out)
    logging.getLogger("faultline.orchestrator.runner").info("investigating %s (attempt %d)", "x", 1)

    assert _one_line(out)["msg"] == "investigating x (attempt 1)"


def test_a_line_written_inside_a_span_carries_its_ids(
    root_restored: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The join. Loki's derived field reads `trace_id` off the line and links to Tempo."""
    ids = ("e420efea2fe46357cc202aaf0a53802e", "a1b2c3d4e5f60718")
    monkeypatch.setattr(tracing, "current_ids", lambda: ids)
    out = io.StringIO()
    logs.configure(component="investigator", stream=out)

    logging.getLogger("faultline.agents.investigation").warning("retrieval empty")

    line = _one_line(out)
    assert line["trace_id"] == "e420efea2fe46357cc202aaf0a53802e"
    assert line["span_id"] == "a1b2c3d4e5f60718"


def test_extra_fields_become_fields_and_unserialisable_ones_become_strings(
    root_restored: object,
) -> None:
    out = io.StringIO()
    logs.configure(component="api", stream=out)

    logging.getLogger("t").info("opened", extra={"incident": "inc-9", "when": Path("/x")})

    line = _one_line(out)
    assert line["incident"] == "inc-9"
    assert line["when"] == "/x"


def test_an_exception_lands_in_exc(root_restored: object) -> None:
    out = io.StringIO()
    logs.configure(component="orchestrator", stream=out)
    try:
        raise RuntimeError("poll failed")
    except RuntimeError:
        logging.getLogger("t").exception("investigation runner: poll failed; will retry")

    line = _one_line(out)
    assert line["level"] == "ERROR"
    assert "RuntimeError: poll failed" in str(line["exc"])


def test_configure_twice_installs_one_handler_and_leaves_others_alone(
    root_restored: object,
) -> None:
    """Idempotent, and polite: pytest's capture handler, or an operator's, is not ours to remove."""
    root = logging.getLogger()
    theirs = logging.NullHandler()
    root.addHandler(theirs)
    before = len(root.handlers)

    logs.configure(component="api", stream=io.StringIO())
    logs.configure(component="api", stream=io.StringIO())

    assert logs.installed()
    assert len(root.handlers) == before + 1
    assert theirs in root.handlers


def test_text_format_is_for_a_terminal_and_shows_the_trace_only_when_present(
    root_restored: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(logs.FORMAT_VAR, "text")
    out = io.StringIO()
    assert logs.configure(component="api", stream=out) == "text"

    logging.getLogger("t").info("plain")
    monkeypatch.setattr(tracing, "current_ids", lambda: ("ff" * 16, "aa" * 8))
    logging.getLogger("t").info("traced", extra={"incident": "inc-2"})

    plain, traced = out.getvalue().splitlines()
    assert plain.endswith("INFO    t plain") and "trace=" not in plain
    assert "trace=" + "ff" * 16 in traced and traced.endswith("traced incident=inc-2")


def test_an_unknown_format_value_is_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(logs.FORMAT_VAR, "yaml")
    assert logs.chosen_format() == "json"
    assert logs.chosen_format("TEXT") == "text"


# --- the entry points ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "component"),
    [
        ("src/faultline/ingest/app.py", "api"),
        ("src/faultline/orchestrator/cli.py", "orchestrator"),
        ("src/faultline/agents/cli.py", "investigator"),
    ],
)
def test_each_daemon_configures_logs_beside_tracing(path: str, component: str) -> None:
    """**Piece 2 shipped `configure()` with no caller** and no test could see it. This one can:
    the three entry points name their component to both modules, in the source."""
    source = (REPO_ROOT / path).read_text()

    assert f'logs.configure(component="{component}")' in source
    assert f'tracing.configure(component="{component}")' in source
    assert source.index("logs.configure(") < source.index("tracing.configure("), (
        "logs first, so anything the SDK says while installing is already in the same shape"
    )


def test_uvicorn_is_started_without_its_own_logging_config() -> None:
    """Otherwise its loggers keep their own handlers and `propagate=False`, and the access log
    comes out beside ours as plain text - two shapes on one stream."""
    source = (REPO_ROOT / "src/faultline/ingest/app.py").read_text()

    assert "log_config=None" in source


def test_a_bare_record_formats_with_no_filter_and_no_sdk() -> None:
    """Same property as `tracing`: useful with nothing installed, and a record that never passed
    through `TraceContext` - one from a handler somebody else attached the formatter to - still
    formats rather than raising on a missing attribute."""
    record = logging.LogRecord("t", logging.INFO, "", 0, "m", (), None)

    line = json.loads(logs.JsonFormatter().format(record))

    assert line["msg"] == "m" and line["component"] == "" and "trace_id" not in line
