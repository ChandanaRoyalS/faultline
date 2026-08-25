"""One HTTP client for Prometheus and Loki, shared by everything that reads the world.

**Extracted a third time, and the last one was predicted.** `evalharness.prom`'s docstring
records the shape of this: it came out of `evalharness.rehearse` when the baseline recorder
became a second consumer, and named T4.1's scoring harness as the third, because "all three
have to ask the same questions the same way - a baseline measured with one query and a
scenario scored with a slightly different one is not a comparison". T2.6's tool layer is the
fourth, and it is the one that could not simply import the others: ADR-0004 draws a boundary
around benchmark infrastructure, and the product depending on the eval harness inverts it.

So the **transport** lives here and both sides import it (ADR-0019). What did not move is the
harness's `METRIC_QUERIES` and `runtime_query`: those are a fixed capture set, and an agent
composes its own PromQL. The thing that must not drift is *how* a query is executed - the
endpoints, `step=15`, the whole-second timestamps - and that is exactly what is in this file.

`tests/test_telemetry.py` pins the URLs this builds for every one of the harness's capture
queries, byte for byte. An extraction that changed a parameter would make every baseline
recorded before it incomparable with every run scored after it, which is the failure the
original docstring exists to prevent, arriving through the fix instead of through the drift.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

PROMETHEUS = "http://localhost:9090"
LOKI = "http://localhost:3100"

HTTP_TIMEOUT = 20


class QueryError(RuntimeError):
    """A telemetry query failed or returned something unusable."""


def now() -> datetime:
    """Whole seconds, deliberately.

    Every timestamp a bundle records is stamped to the second, and every duration in it is
    reported in seconds. Keeping sub-second precision here means a duration computed from
    the raw datetimes can differ by one from the difference of the two stamps beside it -
    a manifest that disagrees with itself for no reason. Truncating at the source removes
    the class of mismatch instead of tolerating it in each consumer.
    """
    return datetime.now(UTC).replace(microsecond=0)


def stamp(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def get_json(base: str, path: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        payload: Any = json.loads(response.read().decode())
    if not isinstance(payload, dict):
        raise QueryError(f"{url} did not return a JSON object")
    return payload


def query_range(
    query: str, start: datetime, end: datetime, step: int = 15, *, base: str
) -> dict[str, Any]:
    """Range query. **`base` is required and keyword-only, deliberately.**

    It had a default of `PROMETHEUS`, and that default was the one implicit endpoint in the
    codebase - every other call site passes its base to `get_json` explicitly. T2.6's tool
    layer inherited the default and silently ignored `ToolSettings.prometheus_url`, which
    contradicts ADR-0004's runtime contract: the agent runtime must receive telemetry
    endpoints from configuration rather than assuming Faultline's compose network. The two
    values happened to be identical, so nothing failed and nothing showed.

    Removing the default makes that class of bug impossible rather than fixed: a caller that
    has an endpoint setting cannot forget to pass it, because there is nothing to fall back
    to. Keyword-only so the addition cannot be absorbed positionally by a stale call.
    """
    return get_json(
        base,
        "/api/v1/query_range",
        {
            "query": query,
            "start": str(int(start.timestamp())),
            "end": str(int(end.timestamp())),
            "step": str(step),
        },
    )
