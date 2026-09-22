"""Print the firing alerts every 30 s for N minutes. The observation loop for every T7.0 attempt.

    python3 evals/attempts/watch.py 12

Stdlib only, no quoting to get wrong, and it prints the clock so the transcript is the timeline.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

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
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        try:
            names = firing()
            print(f"{stamp}  {', '.join(names) if names else 'quiet'}", flush=True)
        except Exception as exc:  # a poll must never end the observation
            print(f"{stamp}  (query failed: {exc})", flush=True)
        if i < ticks - 1:
            time.sleep(30)


if __name__ == "__main__":
    main()
