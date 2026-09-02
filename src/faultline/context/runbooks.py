"""Hand-authored runbooks (T2.4b).

These are the knowledge artifacts ADR-0008 stamps `origin: authored` and T4.1b's exclusion
filter **never excludes** - they are legitimate institutional knowledge rather than a
rehearsal of a scenario, so a run investigating scenario S may still read them.

That exemption is exactly why their content is constrained. A runbook naming a holdout
scenario's root cause would leak that answer into every scored run afterwards, permanently,
through the one channel the quarantine does not filter. `tests/test_runbooks.py` enforces the
boundary mechanically: no runbook may name any catalog scenario, dev or holdout. What belongs
here is what is true of the world - its alert rules, its fault classes, its measured limits -
never what is true of one scenario.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

RUNBOOK_DIR = "runbooks"
FRONT_MATTER = "---"


class Runbook(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    origin: str
    applies_to: list[str] = Field(default_factory=list)
    """Service names, or `any` for a runbook that is not service-specific."""

    signals: list[str] = Field(default_factory=list)
    """Alert rule names that bring a reader here."""

    actions: list[str] = Field(default_factory=list)
    """Allowlist entry ids this runbook may lead to proposing."""

    body: str


def runbooks_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "knowledge" / RUNBOOK_DIR
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"no knowledge/{RUNBOOK_DIR} above {__file__}")


def parse(text: str) -> Runbook:
    """Front matter, then prose. Deliberately not a general markdown parser.

    A runbook that does not open with `---` is malformed rather than bodyless: silently
    treating the whole file as prose would produce a record with no id, which would then be
    unfindable rather than obviously broken.
    """
    if not text.startswith(FRONT_MATTER):
        raise ValueError("a runbook must open with YAML front matter")
    _, front, body = text.split(FRONT_MATTER, 2)
    fields: Any = yaml.safe_load(front)
    return Runbook(**fields, body=body.strip())


@cache
def load_runbooks() -> tuple[Runbook, ...]:
    return tuple(parse(path.read_text()) for path in sorted(runbooks_dir().glob("*.md")))
