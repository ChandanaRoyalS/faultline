"""Print the firing alerts every 30 s for N minutes. The observation loop for every T7.0 attempt.

    python3 evals/attempts/watch.py 12

Stdlib only, no quoting to get wrong, and it prints the clock so the transcript is the timeline.

**Runs on the system `python3`, which on a Mac is 3.9.** The first A1 attempt (2026-09-22 13:46)
died on `from datetime import UTC` - 3.11+ - before its first poll, and the attempt was void by
the protocol's own rule. These helpers deliberately need nothing newer than 3.9 so that the
observation loop cannot depend on which interpreter happened to be first on the PATH.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from paint import green, red, yellow

PROM = "http://localhost:9090"


def firing() -> list[str]:
    url = PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": 'ALERTS{alertstate="firing"}'})
    with urllib.request.urlopen(url, timeout=10) as resp:
        rows = json.load(resp)["data"]["result"]
    return sorted(
        f"{r['metric'].get('alertname', '?')}/{r['metric'].get('service_name', '?')}" for r in rows
    )


def main() -> None:
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    ticks = int(minutes * 2)
    for i in range(ticks):
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")  # noqa: UP017
        try:
            names = firing()
            print(f"{stamp}  {red(', '.join(names)) if names else green('quiet')}", flush=True)
        except Exception as exc:  # a poll must never end the observation
            print(f"{stamp}  {yellow(f'(query failed: {exc})')}", flush=True)
        if i < ticks - 1:
            time.sleep(30)


if __name__ == "__main__":
    main()
