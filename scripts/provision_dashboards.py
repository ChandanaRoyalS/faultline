"""Push Faultline's Grafana dashboards to the running world (T1.2).

**Why this is a script and not a compose mount.** Provisioning a dashboard the ordinary
way means mounting files into the Grafana service in `compose/telemetry.yml` — which is
the third entry in `InjectorSettings.compose_files` and therefore an input to
`compose_digest`. Editing it re-founds the world every recorded figure describes, for a
panel that cannot change a single thing the harness measures: the agent reaches Prometheus
and Loki through its own tools and never touches Grafana. ADR-0030 makes that argument in
full, and `tests/test_dashboard_provisioning.py` keeps this path narrow enough that it
cannot become a way around the digest.

Needs no credentials: the demo's Grafana runs with anonymous access at `org_role = Admin`
and the login form disabled (`world/src/grafana/grafana.ini`). It serves under a `/grafana`
sub-path, so both bases are probed rather than assumed.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "compose" / "dashboards"
BASES = ("http://localhost:3000/grafana", "http://localhost:3000")
HEALTH_PATH = "/api/health"
DASHBOARD_PATH = "/api/dashboards/db"
WAIT_SECONDS = 120


def _get(url: str, timeout: float = 3.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def wait_for_grafana() -> str:
    """Return the working base URL, or exit non-zero having said why."""
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        for base in BASES:
            try:
                payload = json.loads(_get(base + HEALTH_PATH))
            except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
                continue
            if payload.get("database") == "ok":
                return base
        time.sleep(2)
    sys.exit(
        f"Grafana did not answer {HEALTH_PATH} within {WAIT_SECONDS}s on either of {BASES}.\n"
        "The world is half-wired: it is up, and its dashboards are not. Check `make world-ps`."
    )


def push(base: str, path: Path) -> None:
    body = json.dumps(
        {"dashboard": json.loads(path.read_text()), "overwrite": True, "folderId": 0}
    ).encode()
    request = urllib.request.Request(
        base + DASHBOARD_PATH, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    print(f"  {path.name} -> {base}{result.get('url', '')} (version {result.get('version')})")


def main() -> None:
    dashboards = sorted(DASHBOARD_DIR.glob("*.json"))
    if not dashboards:
        sys.exit(f"No dashboards found in {DASHBOARD_DIR}")
    base = wait_for_grafana()
    print(f"Provisioning {len(dashboards)} dashboard(s) to {base}")
    for path in dashboards:
        push(base, path)


if __name__ == "__main__":
    main()
