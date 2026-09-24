"""Read a window back through the agent's own tools - the (a)(c)(d)(b) read-back for a rehearsal.

    FAULTLINE_TOOLS_WORLD=v2 uv run python -m evalharness.readback SERVICE START END [--errors]

START and END are UTC clock times today (`03:00`) or ISO timestamps. What is printed is exactly
what an investigating agent would be handed for that service over that window: the error-ratio
and p95 series, the service's log lines from both ends of the window, its traces as span trees
(errors only with `--errors`), and its change history - or the tools' own refusal or error
where a backend is down, which is itself a fact worth recording.

Lives in the harness rather than beside `evals/attempts/`' stdlib helpers, because it *must* go
through `faultline.tools`: the point of a T7.0 #5 rehearsal is that the evidence the attempt
measured is reachable by the agent, not by curl. Hence `uv run`, and hence not held to the
helpers' Python 3.9 rule.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from faultline.tools.metrics import MetricTemplate, render_query
from faultline.tools.settings import ToolSettings
from faultline.tools.spanmetrics import metrics_for
from faultline.tools.tools import Tools


def _moment(text: str) -> datetime:
    if len(text) == 5 and text[2] == ":":
        today = datetime.now(UTC).date()
        return datetime.combine(today, datetime.strptime(text, "%H:%M").time(), tzinfo=UTC)
    return datetime.fromisoformat(text).astimezone(UTC)


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    service, start, end = sys.argv[1], _moment(sys.argv[2]), _moment(sys.argv[3])
    errors_only = "--errors" in sys.argv[4:]

    settings = ToolSettings()
    tools = Tools(settings)
    world = metrics_for(settings.world)
    print(f"== {service} over {start:%H:%M}..{end:%H:%M} UTC, world {settings.world} ==\n")

    for template in (MetricTemplate.ERROR_RATIO, MetricTemplate.LATENCY_P95):
        result = tools.promql_query(render_query(template, service, world), start, end, step=30)
        print(f"-- promql_query {template.value} --")
        print(result.body())
        print()

    print("-- logql_query --")
    print(tools.logql_query(service, start, end, limit=20).body())
    print()

    print(f"-- trace_query{' (errors only)' if errors_only else ''} --")
    print(tools.trace_query(service, start, end, only_errors=errors_only).body())
    print()

    print("-- change_history --")
    print(tools.change_history(service, start, end).body())


if __name__ == "__main__":
    main()
