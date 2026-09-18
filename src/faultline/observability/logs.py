"""One JSON object per line on the daemons, with the trace id of the span in scope (T6.6, piece 4).

## What this is for

Loki already holds every line the containers write, labelled by service (`promtail-config.yml`).
What it cannot do is join a line to a trace, because nothing on the line names one. After this,
a log line written inside an `investigation` span carries that span's `trace_id`, so the two
Grafana panels - the agent's trace and the agent's log - agree on a key, and Loki's derived-field
link from `trace_id` to Tempo works the way it works for the shop's own services.

## What was found writing it

**Nothing in `src/` has ever configured logging.** No `basicConfig`, no handler, no level - not
in any commit. Python's last-resort handler prints `WARNING` and above to stderr as bare
messages; everything below it is dropped at the root logger's default level. So the
orchestrator's `investigating <incident> (attempt n)` line - `log.info`, written at #233 - has
never been emitted by any process that ran it. The warnings beside it were. This module is the
first configuration the daemons have had, and the test for the finding is the one that asserts
`INFO` now comes out.

## Shape

`configure(component=...)` installs one handler on the root logger, at `INFO`, writing to
stderr. The format is JSON lines unless `FAULTLINE_LOG_FORMAT=text`, which is for a person
tailing a daemon in a terminal - the same lines, readable. Prints are untouched: `tracing:
exporting to ...` and the CLIs' output stay on stdout, because a person is reading those and
the design note says so (§5, piece 4).

Every record carries `ts`, `level`, `logger`, `msg`, `component`; `trace_id` and `span_id` only
when non-empty, so *not traced* is legible as absence; `exc` when there is one; and any `extra=`
keys the caller passed, so `log.info("investigating", extra={"incident": id})` puts `incident`
on the line as a field rather than inside the message.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

from faultline.observability import tracing

FORMAT_VAR = "FAULTLINE_LOG_FORMAT"
"""`json` (the default) or `text`. Anything else is read as `json`."""

_MARK = "_faultline_observability"
"""Set on the handler this module installs, so `configure()` can find and replace its own
without touching a handler pytest, uvicorn or an operator put there."""

_RESERVED = frozenset(
    {
        *vars(logging.LogRecord("", 0, "", 0, "", (), None)),
        "message",
        "asctime",
        "trace_id",
        "span_id",
        "component",
    }
)
"""Attributes every `LogRecord` has, plus the ones this module writes. Whatever else is on a
record arrived through `extra=` and is a field the caller wants on the line."""


class TraceContext(logging.Filter):
    """Stamp `trace_id`, `span_id` and `component` on every record. Always passes the record."""

    def __init__(self, component: str) -> None:
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id, record.span_id = tracing.current_ids()
        record.component = self.component
        return True


class JsonFormatter(logging.Formatter):
    """One object per line. Keys in a fixed order so the eye can scan a stream of them."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "component": getattr(record, "component", ""),
        }
        trace_id = getattr(record, "trace_id", "")
        if trace_id:
            line["trace_id"] = trace_id
            line["span_id"] = getattr(record, "span_id", "")
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                line[key] = value
        return json.dumps(line, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """The same fields for a terminal. The trace id appears only when there is one."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        head = f"{ts} {record.levelname:<7} {record.name}"
        trace_id = getattr(record, "trace_id", "")
        if trace_id:
            head += f" trace={trace_id}"
        extras = " ".join(
            f"{k}={v}"
            for k, v in vars(record).items()
            if k not in _RESERVED and not k.startswith("_")
        )
        line = f"{head} {record.getMessage()}"
        if extras:
            line += f" {extras}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def chosen_format(explicit: str | None = None) -> str:
    """`json` unless asked for `text`."""
    value = (explicit if explicit is not None else os.environ.get(FORMAT_VAR, "")).strip().lower()
    return "text" if value == "text" else "json"


def configure(
    *,
    component: str,
    level: int = logging.INFO,
    stream: TextIO | None = None,
    fmt: str | None = None,
) -> str:
    """Install the daemon's handler on the root logger. Returns the format installed.

    Idempotent: a second call replaces the handler this module installed and leaves every other
    handler alone. Called by the entry points - API, orchestrator, investigator - and by
    nothing in a library module, for the reason `tracing.configure` gives.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _MARK, False):
            root.removeHandler(existing)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    setattr(handler, _MARK, True)
    handler.addFilter(TraceContext(component))
    which = chosen_format(fmt)
    handler.setFormatter(JsonFormatter() if which == "json" else TextFormatter())
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    return which


def installed() -> bool:
    """Whether this module's handler is on the root logger."""
    return any(getattr(h, _MARK, False) for h in logging.getLogger().handlers)
