"""The extraction is byte-preserving, or baselines and scored runs stop being comparable.

`evalharness.prom`'s docstring is the reason this file exists: the client came out of
`rehearse` for the baseline recorder, was named as T4.1's dependency too, and "all three have
to ask the same questions the same way - a baseline measured with one query and a scenario
scored with a slightly different one is not a comparison".

T2.6 moved the transport to `faultline.telemetry` so the tool layer could use it without the
product importing the eval harness (ADR-0004, ADR-0019). That fix could cause the exact
failure the docstring warns about, if the move changed a parameter. So the URLs the harness's
four capture queries produce are pinned here, character for character.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from evalharness.prom import METRIC_QUERIES
from faultline import telemetry

START = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
END = datetime(2026, 8, 25, 12, 20, tzinfo=UTC)

CAPTURE_URLS = {
    "error-ratio": (
        "http://localhost:9090/api/v1/query_range?query=sum+by%28service_name%29+%28rate%28"
        "calls_total%7Bstatus_code%3D%22STATUS_CODE_ERROR%22%7D%5B2m%5D%29%29+%2F+sum+by%28"
        "service_name%29+%28rate%28calls_total%5B2m%5D%29%29"
        "&start=1787659200&end=1787660400&step=15"
    ),
    "call-rate": (
        "http://localhost:9090/api/v1/query_range?query=sum+by%28service_name%29+%28rate%28"
        "calls_total%5B2m%5D%29%29&start=1787659200&end=1787660400&step=15"
    ),
    "latency-p95": (
        "http://localhost:9090/api/v1/query_range?query=histogram_quantile%280.95%2C+sum+by"
        "%28service_name%2C+le%29+%28rate%28latency_bucket%5B2m%5D%29%29%29"
        "&start=1787659200&end=1787660400&step=15"
    ),
    "alerts-firing": (
        "http://localhost:9090/api/v1/query_range?query=ALERTS%7Balertstate%3D%22firing%22%7D"
        "&start=1787659200&end=1787660400&step=15"
    ),
}


class _Recorder:
    """Stands in for `urllib.request.urlopen`, recording the URL and answering nothing."""

    urls: ClassVar[list[str]] = []

    def __init__(self, url: str, timeout: Any = None) -> None:
        _Recorder.urls.append(url)

    def __enter__(self) -> _Recorder:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def read(self) -> bytes:
        return b'{"data":{"result":[]}}'


def urls_for(queries: list[str], base: str = telemetry.PROMETHEUS) -> list[str]:
    _Recorder.urls = []
    with patch("urllib.request.urlopen", _Recorder):
        for query in queries:
            telemetry.query_range(query, START, END, base=base)
    return list(_Recorder.urls)


def test_the_capture_queries_build_the_same_urls_after_the_extraction() -> None:
    """The four series every rehearsal bundle holds, pinned character for character."""
    built = urls_for(list(METRIC_QUERIES.values()))

    assert dict(zip(METRIC_QUERIES, built, strict=True)) == CAPTURE_URLS


def test_the_harness_and_the_tool_layer_share_one_client() -> None:
    """Not two copies that agree today. `evalharness.prom` re-exports rather than redefines,
    so there is one function and drift is impossible rather than merely unlikely."""
    from evalharness import prom
    from faultline.tools import tools

    assert prom.query_range is telemetry.query_range
    assert prom.get_json is telemetry.get_json
    assert prom.PROMETHEUS == telemetry.PROMETHEUS
    assert tools.telemetry is telemetry


def test_step_and_whole_second_timestamps_survived_the_move() -> None:
    """The two conventions a careless extraction would drop: `step=15`, and timestamps
    truncated to whole seconds so a duration never disagrees with the stamps beside it."""
    built = urls_for(["up"])[0]

    assert "step=15" in built
    assert "start=1787659200&end=1787660400" in built, "whole seconds, no fractions"
    assert telemetry.now().microsecond == 0


def test_the_endpoint_is_required_rather_than_defaulted() -> None:
    """The fix for T2.6's defect, pinned as a property of the client rather than of a caller.

    `query_range` used to default its base to `PROMETHEUS`, and it was the only implicit
    endpoint in the codebase - every other call site passes one to `get_json` explicitly. The
    tool layer inherited that default and ignored its own `prometheus_url` setting. With no
    default there is nothing to inherit, so the class of bug is gone rather than fixed.
    """
    import inspect

    parameters = inspect.signature(telemetry.query_range).parameters

    assert parameters["base"].default is inspect.Parameter.empty, "base must have no default"
    assert parameters["base"].kind is inspect.Parameter.KEYWORD_ONLY, (
        "keyword-only, so adding it cannot be absorbed positionally by a stale call"
    )
    with pytest.raises(TypeError, match="base"):
        telemetry.query_range("up", START, END)  # type: ignore[call-arg]


def test_the_eval_harness_passes_its_endpoints_explicitly() -> None:
    """The same class, checked on the other consumer.

    The harness has no endpoint *configuration* to ignore - it has module constants - and it
    passes them explicitly at every call site, `get_json` and `query_range` alike. So there
    was never a setting being silently dropped here. What is pinned is that no call relies on
    an implicit endpoint, which is the property that failed in the tool layer.
    """
    from evalharness import baseline, rehearse

    for module in (baseline, rehearse):
        source = inspect.getsource(module)
        for call in re.findall(r"query_range\((?![^)]*base=)[^)]*\)", source):
            raise AssertionError(f"{module.__name__} calls query_range without base: {call}")
        for call in re.findall(r"get_json\(\s*([A-Za-z_.]+)", source):
            assert call in {"LOKI", "PROMETHEUS", "self._settings.loki_url"}, (
                f"{module.__name__} builds a get_json base from {call}"
            )
