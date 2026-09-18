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

**One datasource too, since T6.6 / Q73.** `faultline-self-metrics` points Grafana at the
platform's own Prometheus (`prometheus-self` in `docker-compose.yml` and `deploy/compose.yml`),
which scrapes the platform's `/metrics`. The alternative was a scrape job in the world's
Prometheus, whose config is inside `observability_digest` and pinned by
`generations.CURRENT_OBSERVABILITY` - four lines that would have cost every recorded figure its
stamp. A datasource is the same class of thing as a dashboard under ADR-0030's argument: Grafana
reads it, nothing the harness measures does. The API surface this script may touch widens by
exactly that one resource and the guard tests name it.
"""

from __future__ import annotations

import argparse
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
DATASOURCE_PATH = "/api/datasources"
DATASOURCE_BY_UID_PATH = "/api/datasources/uid/"
WAIT_SECONDS = 120

SELF_METRICS_UID = "faultline-self-metrics"
"""What `compose/dashboards/faultline-self.json`'s Prometheus panels name. Held equal by test."""
SELF_METRICS_URL = "http://host.docker.internal:9091"
"""Where the world's Grafana - a container - reaches the platform's Prometheus on a development
machine: the port the platform's compose project publishes, through Docker Desktop's name for
the host. A deployment passes `--self-metrics-url http://prometheus-self:9090` (deploy/README
§3.4); a Linux development host passes the bridge address, because Docker Engine does not define
the name. **A value posted to Grafana, not a host this script contacts** - Grafana contacts it."""


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


def _request(url: str, method: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as failure:
        return failure.code, {}


def ensure_self_metrics_datasource(base: str, url: str) -> None:
    """Create or update the one datasource, by uid, so running this twice is running it once.

    Provisioning-file datasources are `editable: false` and Grafana refuses API writes to them;
    this one is API-owned from the start, which is the trade for not touching `telemetry.yml`.
    `isDefault` stays false: the demo's own Prometheus is what a person expects Explore to open.
    """
    body = {
        "uid": SELF_METRICS_UID,
        "name": "Faultline self-metrics",
        "type": "prometheus",
        "access": "proxy",
        "url": url,
        "isDefault": False,
        "jsonData": {"httpMethod": "POST", "timeInterval": "15s"},
    }
    status, _ = _request(base + DATASOURCE_BY_UID_PATH + SELF_METRICS_UID, "GET")
    if status == 200:
        status, _ = _request(base + DATASOURCE_BY_UID_PATH + SELF_METRICS_UID, "PUT", body)
        verb = "updated"
    else:
        status, _ = _request(base + DATASOURCE_PATH, "POST", body)
        verb = "created"
    if status not in (200, 201):
        sys.exit(f"datasource {SELF_METRICS_UID}: Grafana answered {status} on {verb.rstrip('d')}")
    print(f"  datasource {SELF_METRICS_UID} -> {url} ({verb})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--self-metrics-url",
        default=SELF_METRICS_URL,
        help="where Grafana reaches the platform's own Prometheus (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    dashboards = sorted(DASHBOARD_DIR.glob("*.json"))
    if not dashboards:
        sys.exit(f"No dashboards found in {DASHBOARD_DIR}")
    base = wait_for_grafana()
    print(f"Provisioning {len(dashboards)} dashboard(s) to {base}")
    for path in dashboards:
        push(base, path)
    ensure_self_metrics_datasource(base, args.self_metrics_url)


if __name__ == "__main__":
    main()
