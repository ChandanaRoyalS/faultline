"""Read a service's log back from Loki - the (c) read-back for a T7.0 attempt.

    python3 evals/attempts/logs.py SERVICE "needle" [MINUTES] [LIMIT]

Counts the lines of `{service="SERVICE"} |= "needle"` over the last MINUTES (default 30) and
prints the first LIMIT of them (default 3), oldest first. The label is Promtail's `service`, which
is the container name, and the query is the one the agent's `logql_query` tool would run - so a
hit here is a line the agent can see, and a zero is a line it cannot. Stdlib only, 3.9-safe; the
LogQL is built here so no quoting crosses a shell boundary.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

from paint import green, red

LOKI = "http://localhost:3100"


def _get(path: str, **params: str) -> dict:
    url = LOKI + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.load(resp)["data"]


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    service, needle = sys.argv[1], sys.argv[2]
    minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    selector = f'{{service="{service}"}} |= {json.dumps(needle)}'
    end_ns = time.time_ns()
    start_ns = end_ns - minutes * 60 * 1_000_000_000

    counted = _get("/loki/api/v1/query", query=f"sum(count_over_time({selector} [{minutes}m]))")
    count = int(float(counted["result"][0]["value"][1])) if counted["result"] else 0
    print(f"{selector}  over the last {minutes} min")
    print(red(f"  {count} lines") if count else green("  0 lines"))

    lines = _get(
        "/loki/api/v1/query_range",
        query=selector,
        start=str(start_ns),
        end=str(end_ns),
        limit=str(limit),
        direction="forward",
    )
    for stream in lines["result"]:
        for _ts, line in stream["values"][:limit]:
            print("  " + line[:220])


if __name__ == "__main__":
    main()
