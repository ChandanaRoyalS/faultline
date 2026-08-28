"""Which evidence classes can answer "was the target idle, or absent?" (T7.5).

**Derived from a bundle's own captures, never asserted by hand.** T7.4 characterised this by
reading the twelve recorded bundles and found four of nine distinct targets export runtime
metrics and two scenarios can answer the question by no class at all. That was a one-off
analysis; this makes it a recorded property of every bundle.

Only two classes can answer it:

* **runtime metrics** - an idle process still reports its heap, a dead one reports nothing.
* **logs** - a restarting process repeats itself, a never-created one leaves a stream that
  stops dead. Only decisive if the service is talkative at rest: a service that logs nothing
  in normal operation is silent during the fault for reasons that have nothing to do with it.

Two classes cannot, and are excluded on principle rather than by measurement:

* **span metrics and traces** - their absence *is* the ambiguity being resolved.
* **change history** - it says what changed, not what is running.

**This is derivation, not backfill.** ADR-0014 refused to backfill `compose_digest` into older
bundles because a digest asserts something about the world outside the capture, and writing one
in after the fact would claim a capture was taken against a world that did not exist when it was
taken. Reachability asserts nothing outside the bundle: it is a reading of files the bundle
already contains, in the way that counting a log's lines is. Computing it for an existing bundle
adds no claim that was not already sitting in its own `metrics/` directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TALKATIVE_LINES = 10
"""Below this, a log capture cannot answer the question and is not counted as a class.

A threshold rather than "any lines at all", because the two zero-class targets T7.4 found are
not silent by a hair: `productcatalogservice` recorded **0** lines and `featureflagservice`
**2**, against 116-500 for every target that can answer. Nothing in the catalog sits near this
boundary, so its exact value is not load-bearing - but it is a threshold and is named as one
rather than hidden in a truth test.
"""

RUNTIME_CAPTURE = "metrics/runtime.json"


def _populated(payload: dict[str, Any]) -> int:
    return len([r for r in payload.get("data", {}).get("result", []) if r.get("values")])


def derive(bundle: Path) -> dict[str, Any]:
    """The reachability record for one recorded bundle.

    Returns the classes that can answer, the evidence for each, and whether the answer is that
    none can. Absent captures count as absent evidence rather than raising: a bundle recorded
    under capture set 1 has no `runtime.json`, and that is a fact about it, not an error.
    """
    runtime_path = bundle / RUNTIME_CAPTURE
    runtime_series = (
        _populated(json.loads(runtime_path.read_text())) if runtime_path.is_file() else 0
    )

    log_lines = 0
    for log in sorted((bundle / "logs").glob("*.txt")) if (bundle / "logs").is_dir() else []:
        log_lines += len(
            [x for x in log.read_text().splitlines() if x.strip() and not x.startswith("#")]
        )

    classes: list[str] = []
    if runtime_series:
        classes.append("runtime")
    if log_lines >= TALKATIVE_LINES:
        classes.append("logs")

    return {
        "answers_idle_or_absent": classes,
        "none_can_answer": not classes,
        "runtime_series": runtime_series,
        "target_log_lines": log_lines,
        "derived_from": "the bundle's own captures (T7.5)",
    }


def answering_classes(bundle: Path) -> list[str]:
    """Just the classes, for a caller that does not want the evidence."""
    return list(derive(bundle)["answers_idle_or_absent"])
