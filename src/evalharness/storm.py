"""The alert storm (T6.7 piece 4, `PREREGISTRATION-T6.7.md`): two hundred alerts at once, with the
model off, and what the platform does with them.

**A load test of the platform, never of the agent.** The receiver, the stream, the orchestrator's
dedupe, correlation and cap are what a storm exercises; an investigation is what a storm must not
trigger two hundred times. So this runs against a development platform whose orchestrator does
not investigate (`FAULTLINE_ORCH_INVESTIGATE` unset - the default), and it **refuses any receiver
that is not on the loopback interface**: the deployment's orchestrator investigates everything it
admits, and 200 alerts there is up to 200 times $0.70.

Three passes, each waited to a drained stream (`XINFO GROUPS` lag and pending both zero):

1. **the storm** - N distinct alerts, one per POST, `concurrency` in flight;
2. **the re-notification** - the same N again, which dedupe must fold to nothing;
3. **the resolves** - the same N with `status: resolved`, so the incidents close and the database
   is left with resolved incidents on its record rather than firing ones.

Once a second throughout, `/metrics` (`faultline_incidents_queued`, `faultline_investigations_
active`), `XLEN` and the group's lag are sampled. At the end the incident table is read for what
opened after the storm began, with episodes per incident, and the pre-registration's ten
predictions are scored. Everything goes to an evidence directory that refuses to be rewritten.

The moving parts are behind `Platform`, a seam: `LivePlatform` is HTTP, Redis and Postgres, and
`tests/test_storm.py` substitutes a fake to exercise the generator, the scoring and the refusal
without a world.
"""

from __future__ import annotations

import json
import random
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence" / "t6.7-reliability"

ALERT_RULES: tuple[tuple[str, str], ...] = (
    ("ServiceHighErrorRate", "critical"),
    ("ServiceHighLatency", "warning"),
    ("ServiceNoTraffic", "critical"),
)
"""The three rules `compose/prometheus/alert-rules.yml` defines, with their severities. Restated
here rather than parsed, because that file is digest-locked and this harness must not become a
reader of it; `tests/test_storm.py` holds the two in agreement."""

CAP = 3
"""`OrchestratorSettings.max_concurrent`, restated for the queue-depth prediction."""

DRAIN_SECONDS = 60
SETTLE_SECONDS = 60


class NotLoopbackError(RuntimeError):
    """The receiver is not on this machine. The deployment investigates what it admits."""


def require_loopback(url: str) -> None:
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise NotLoopbackError(
            f"faultline-storm only runs against a receiver on the loopback interface; {url!r} is "
            "not. The deployment's orchestrator investigates every incident it admits, and a storm "
            "there is a bill."
        )


# --- the storm ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StormAlert:
    service: str
    alertname: str
    severity: str
    replica: int
    fingerprint: str

    def payload(self, status: str, starts_at: datetime, ends_at: datetime | None) -> dict[str, Any]:
        labels = {
            "alertname": self.alertname,
            "service_name": self.service,
            "severity": self.severity,
            "replica": str(self.replica),
            "job": "faultline-storm",
        }
        alert = {
            "status": status,
            "labels": labels,
            "annotations": {"summary": f"storm: {self.alertname} on {self.service}"},
            "startsAt": starts_at.isoformat(),
            "endsAt": (ends_at or datetime(1, 1, 1, tzinfo=UTC)).isoformat(),
            "generatorURL": "http://faultline-storm/",
            "fingerprint": self.fingerprint,
        }
        return {
            "version": "4",
            "status": status,
            "receiver": "faultline",
            "groupKey": f'{{}}:{{alertname="{self.alertname}", service_name="{self.service}"}}',
            "groupLabels": {"alertname": self.alertname, "service_name": self.service},
            "commonLabels": labels,
            "externalURL": "http://faultline-storm/",
            "alerts": [alert],
        }


def generate(n: int, services: list[str], seed: int) -> list[StormAlert]:
    """Exactly `n` distinct alerts: every (service, rule) pair once per cycle, `replica`
    incrementing each cycle, order shuffled by `seed` so arrival order is not the catalog's."""
    pairs = [(s, name, sev) for s in sorted(services) for name, sev in ALERT_RULES]
    alerts: list[StormAlert] = []
    replica = 0
    while len(alerts) < n:
        for service, alertname, severity in pairs:
            if len(alerts) == n:
                break
            fingerprint = f"storm{seed:04x}-{replica:02d}-{alertname}-{service}"
            alerts.append(StormAlert(service, alertname, severity, replica, fingerprint))
        replica += 1
    random.Random(seed).shuffle(alerts)
    return alerts


# --- the platform seam ----------------------------------------------------------------------------


@dataclass(slots=True)
class Posted:
    status: int
    seconds: float
    published: int = 0
    duplicates: int = 0
    error: str = ""


@dataclass(slots=True)
class Sample:
    at: float
    queued: int | None
    active: int | None
    xlen: int | None
    lag: int | None
    pending: int | None


@dataclass(slots=True)
class IncidentRow:
    id: str
    state: str
    opened_at: str
    episodes: int
    episode_keys: list[str]


class Platform(Protocol):
    def post(self, payload: dict[str, Any]) -> Posted: ...
    def sample(self) -> Sample: ...
    def incidents_since(self, moment: datetime) -> list[IncidentRow]: ...
    def container_restarts(self) -> dict[str, int]: ...
    def orchestrator_errors(self) -> int: ...


class LivePlatform:
    """HTTP to the receiver, Redis for the stream, Postgres for the incidents."""

    def __init__(
        self, *, ingest_url: str, metrics_url: str, redis_url: str, postgres_dsn: str
    ) -> None:
        require_loopback(ingest_url)
        self._ingest = ingest_url.rstrip("/")
        self._metrics = metrics_url
        self._redis_url = redis_url
        self._dsn = postgres_dsn
        from faultline.orchestrator.settings import OrchestratorSettings

        self._stream = OrchestratorSettings().stream
        self._group = OrchestratorSettings().group

    def post(self, payload: dict[str, Any]) -> Posted:
        body = json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self._ingest}/api/v1/alerts",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                reply = json.loads(response.read().decode() or "{}")
                return Posted(
                    status=response.status,
                    seconds=time.monotonic() - started,
                    published=int(reply.get("published", 0)),
                    duplicates=int(reply.get("duplicates", 0)),
                )
        except urllib.error.HTTPError as exc:
            return Posted(status=exc.code, seconds=time.monotonic() - started, error=str(exc))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return Posted(status=0, seconds=time.monotonic() - started, error=str(exc))

    def sample(self) -> Sample:
        queued = active = None
        try:
            with urllib.request.urlopen(self._metrics, timeout=5) as response:
                text = response.read().decode()
            queued = _gauge(text, "faultline_incidents_queued")
            active = _gauge(text, "faultline_investigations_active")
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        xlen = lag = pending = None
        try:
            import redis

            client = redis.from_url(self._redis_url, socket_timeout=5)
            xlen = int(client.xlen(self._stream))
            for group in client.xinfo_groups(self._stream):
                name = group.get("name")
                if (name.decode() if isinstance(name, bytes) else name) == self._group:
                    lag = int(group.get("lag") or 0)
                    pending = int(group.get("pending") or 0)
            client.close()
        except Exception:
            pass
        return Sample(time.time(), queued, active, xlen, lag, pending)

    def incidents_since(self, moment: datetime) -> list[IncidentRow]:
        import psycopg

        rows: list[IncidentRow] = []
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT i.id, i.state, i.opened_at, "
                "COALESCE(array_agg(e.episode_key) FILTER (WHERE e.episode_key IS NOT NULL), '{}') "
                "FROM incidents i LEFT JOIN incident_episodes e ON e.incident_id = i.id "
                "WHERE i.opened_at >= %s GROUP BY i.id ORDER BY i.opened_at",
                (moment,),
            )
            for incident_id, state, opened_at, keys in cur.fetchall():
                rows.append(
                    IncidentRow(
                        str(incident_id), str(state), opened_at.isoformat(), len(keys), list(keys)
                    )
                )
        return rows

    def container_restarts(self) -> dict[str, int]:
        try:
            out = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            ).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            return {}
        restarts: dict[str, int] = {}
        for name in out:
            if "faultline" not in name and name not in {"postgres", "redis"}:
                continue
            try:
                count = subprocess.run(
                    ["docker", "inspect", "--format", "{{.RestartCount}}", name],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                ).stdout.strip()
                restarts[name] = int(count or 0)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                continue
        return restarts

    def orchestrator_errors(self) -> int:
        return -1  # the host daemon's stderr is not reachable from here; the note reads it by hand


def _gauge(text: str, name: str) -> int | None:
    for line in text.splitlines():
        if line.startswith(name + " ") or line.startswith(name + "{"):
            try:
                return int(float(line.rsplit(" ", 1)[1]))
            except ValueError:
                return None
    return None


# --- the run --------------------------------------------------------------------------------------


@dataclass(slots=True)
class PassResult:
    name: str
    posts: int
    statuses: dict[str, int]
    published: int
    duplicates: int
    p50_ms: float
    p99_ms: float
    max_ms: float
    seconds: float
    drained_after_seconds: float | None


@dataclass(slots=True)
class Verdict:
    prediction: str
    held: bool | None
    detail: str


@dataclass(slots=True)
class StormReport:
    n: int
    seed: int
    concurrency: int
    started_at: str
    passes: list[PassResult] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    incidents: list[IncidentRow] = field(default_factory=list)
    incidents_after_pass_2: int = 0
    restarts_before: dict[str, int] = field(default_factory=dict)
    restarts_after: dict[str, int] = field(default_factory=dict)
    verdicts: list[Verdict] = field(default_factory=list)


class Sampler:
    def __init__(self, platform: Platform, samples: list[Sample], every: float = 1.0) -> None:
        self._platform, self._samples, self._every = platform, samples, every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="storm-sampler")

    def _run(self) -> None:
        while not self._stop.is_set():
            self._samples.append(self._platform.sample())
            self._stop.wait(self._every)

    def __enter__(self) -> Sampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def run_pass(
    name: str,
    platform: Platform,
    payloads: list[dict[str, Any]],
    *,
    concurrency: int,
    wait_drained: bool,
    clock: Any = time.monotonic,
    sleep: Any = time.sleep,
) -> PassResult:
    started = clock()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        posted = list(pool.map(platform.post, payloads))
    finished = clock()
    drained: float | None = None
    if wait_drained:
        deadline = finished + DRAIN_SECONDS
        while clock() < deadline:
            sample = platform.sample()
            if sample.lag == 0 and sample.pending == 0:
                drained = clock() - finished
                break
            sleep(1.0)
    statuses: dict[str, int] = {}
    for p in posted:
        statuses[str(p.status)] = statuses.get(str(p.status), 0) + 1
    latencies = [p.seconds * 1000 for p in posted]
    return PassResult(
        name=name,
        posts=len(posted),
        statuses=statuses,
        published=sum(p.published for p in posted),
        duplicates=sum(p.duplicates for p in posted),
        p50_ms=round(statistics.median(latencies), 1) if latencies else 0.0,
        p99_ms=round(_percentile(latencies, 0.99), 1),
        max_ms=round(max(latencies), 1) if latencies else 0.0,
        seconds=round(finished - started, 2),
        drained_after_seconds=None if drained is None else round(drained, 1),
    )


def score(report: StormReport) -> list[Verdict]:
    """The pre-registration's ten predictions, against the run. `held=None` is *not measured*."""
    p1, p2, p3 = report.passes[0], report.passes[1], report.passes[2]
    all_ok = all(set(p.statuses) == {"200"} for p in report.passes)
    verdicts = [
        Verdict(
            "P1 every POST 200", all_ok, ", ".join(f"{p.name}: {p.statuses}" for p in report.passes)
        ),
        Verdict(
            "P2 published/deduplicated per pass",
            (p1.published, p1.duplicates, p2.published, p2.duplicates, p3.published)
            == (report.n, 0, 0, report.n, report.n),
            f"pass 1 {p1.published}/{p1.duplicates}, pass 2 {p2.published}/{p2.duplicates}, "
            f"pass 3 {p3.published}/{p3.duplicates}",
        ),
    ]
    opened = len(report.incidents)
    verdicts.append(Verdict("P3 incidents opened in [1, 6]", 1 <= opened <= 6, f"{opened} opened"))
    seen: dict[str, str] = {}
    twice: list[str] = []
    for incident in report.incidents:
        for key in incident.episode_keys:
            if key in seen and seen[key] != incident.id:
                twice.append(key)
            seen[key] = incident.id
    verdicts.append(Verdict("P4 no episode in two incidents", not twice, f"{len(twice)} shared"))
    queued = [s.queued for s in report.samples if s.queued is not None]
    peak = max(queued) if queued else None
    held_before = next((s.active for s in report.samples if s.active is not None), 0) or 0
    free = max(0, CAP - held_before)
    expected_peak = max(0, opened - free)
    last = queued[-1] if queued else None
    verdicts.append(
        Verdict(
            "P5 queue peak = max(0, incidents - free slots), 0 at the end",
            None if peak is None else (peak == expected_peak and last == 0),
            f"peak {peak}, expected {expected_peak} ({held_before} slot(s) held before the storm), "
            f"last sample {last}",
        )
    )
    drains = [p.drained_after_seconds for p in report.passes]
    verdicts.append(
        Verdict(
            "P6 each pass drains within 60 s",
            all(d is not None and d <= DRAIN_SECONDS for d in drains),
            f"drained after {drains} s",
        )
    )
    verdicts.append(
        Verdict(
            "P7 receiver p99 < 500 ms",
            all(p.p99_ms < 500 for p in report.passes),
            ", ".join(f"{p.name} p99 {p.p99_ms} ms" for p in report.passes),
        )
    )
    states = {i.state for i in report.incidents}
    verdicts.append(
        Verdict(
            "P8 every storm incident resolved", states <= {"resolved"}, f"states {sorted(states)}"
        )
    )
    restarted = {
        k: (report.restarts_before.get(k, 0), v)
        for k, v in report.restarts_after.items()
        if v != report.restarts_before.get(k, 0)
    }
    verdicts.append(
        Verdict(
            "P9 no container restarted",
            None if not report.restarts_after else not restarted,
            f"restarts changed: {restarted}" if restarted else "none",
        )
    )
    verdicts.append(
        Verdict(
            "P10 pass 2 opened nothing",
            report.incidents_after_pass_2 == opened,
            f"{report.incidents_after_pass_2} after pass 2, {opened} at the end",
        )
    )
    return verdicts


def run_storm(
    platform: Platform,
    *,
    n: int,
    seed: int,
    concurrency: int,
    services: list[str],
    evidence_dir: Path,
    clock: Any = time.monotonic,
    sleep: Any = time.sleep,
    wall: Any = lambda: datetime.now(UTC),
) -> StormReport:
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise SystemExit(f"evidence already captured, refusing to rewrite it: {evidence_dir}")
    alerts = generate(n, services, seed)
    onset = wall()
    report = StormReport(
        n=n,
        seed=seed,
        concurrency=concurrency,
        started_at=onset.isoformat(),
        restarts_before=platform.container_restarts(),
    )
    firing = [a.payload("firing", onset, None) for a in alerts]
    with Sampler(platform, report.samples):
        print(f"=== pass 1: {n} distinct alerts, {concurrency} in flight", flush=True)
        report.passes.append(
            run_pass(
                "storm",
                platform,
                firing,
                concurrency=concurrency,
                wait_drained=True,
                clock=clock,
                sleep=sleep,
            )
        )
        _say(report.passes[-1])
        _mark(platform, report)
        print("=== pass 2: the same alerts again", flush=True)
        report.passes.append(
            run_pass(
                "re-notification",
                platform,
                firing,
                concurrency=concurrency,
                wait_drained=True,
                clock=clock,
                sleep=sleep,
            )
        )
        _say(report.passes[-1])
        _mark(platform, report)
        report.incidents_after_pass_2 = len(platform.incidents_since(onset - timedelta(seconds=1)))
        print("=== pass 3: the resolves", flush=True)
        resolved_at = wall()
        resolves = [a.payload("resolved", onset, resolved_at) for a in alerts]
        report.passes.append(
            run_pass(
                "resolves",
                platform,
                resolves,
                concurrency=concurrency,
                wait_drained=True,
                clock=clock,
                sleep=sleep,
            )
        )
        _say(report.passes[-1])
        _mark(platform, report)
        deadline = clock() + SETTLE_SECONDS
        while clock() < deadline:
            rows = platform.incidents_since(onset - timedelta(seconds=1))
            if rows and all(r.state == "resolved" for r in rows):
                break
            sleep(2.0)
    report.incidents = platform.incidents_since(onset - timedelta(seconds=1))
    report.restarts_after = platform.container_restarts()
    report.verdicts = score(report)
    _write(report, evidence_dir)
    return report


def _mark(platform: Platform, report: StormReport) -> None:
    """One explicit sample at the end of each pass, so the state a pass leaves is in the record
    even when the once-a-second sampler did not land there."""
    report.samples.append(platform.sample())


def _say(result: PassResult) -> None:
    print(
        f"  {result.posts} posts in {result.seconds}s: statuses {result.statuses}; "
        f"published {result.published}, duplicates {result.duplicates}; "
        f"p50 {result.p50_ms} ms, p99 {result.p99_ms} ms, max {result.max_ms} ms; "
        f"drained after {result.drained_after_seconds} s",
        flush=True,
    )


def _write(report: StormReport, evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "storm.json").write_text(json.dumps(asdict(report), indent=2, default=str))
    lines = [
        f"# Alert storm — {report.started_at[:16]}Z",
        "",
        f"**{report.n} distinct alerts, {report.concurrency} in flight, seed {report.seed}, three "
        f"passes.** `PREREGISTRATION-T6.7.md` §2 scored below. $0.00: no investigation ran.",
        "",
        "| pass | posts | statuses | published | dedup | p50 | p99 | max | drained after |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in report.passes:
        lines.append(
            f"| {p.name} | {p.posts} | {p.statuses} | {p.published} | {p.duplicates} | "
            f"{p.p50_ms} ms | {p.p99_ms} ms | {p.max_ms} ms | {p.drained_after_seconds} s |"
        )
    lines += ["", "| prediction | held | detail |", "|---|---|---|"]
    for v in report.verdicts:
        held = "**yes**" if v.held else ("not measured" if v.held is None else "**no**")
        lines.append(f"| {v.prediction} | {held} | {v.detail} |")
    lines += ["", f"**Incidents opened: {len(report.incidents)}**", ""]
    for i in report.incidents:
        lines.append(
            f"- `{i.id[:8]}` {i.state}, {i.episodes} episodes, opened {i.opened_at[11:19]}Z"
        )
    queued = [s.queued for s in report.samples if s.queued is not None]
    lines += [
        "",
        f"Samples: {len(report.samples)}; queue depth peak {max(queued) if queued else 'unread'}; "
        f"restarts before/after: {report.restarts_before} / {report.restarts_after}.",
    ]
    (evidence_dir / "STORM.md").write_text("\n".join(lines) + "\n")


# --- the CLI --------------------------------------------------------------------------------------


def run_cli(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="faultline-storm",
        description="Two hundred alerts at once against a development platform, model off (T6.7).",
    )
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=67)
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--ingest-url", default="http://localhost:8000")
    p.add_argument("--metrics-url", default="http://localhost:8000/metrics")
    p.add_argument("--redis-url", default="redis://localhost:6379/0")
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument("--evidence-root", default=str(EVIDENCE_ROOT))
    p.add_argument(
        "--label", default=None, help="evidence goes to storm-<label>/; default: the UTC stamp"
    )
    args = p.parse_args(argv)

    from faultline.context.catalog import ServiceCatalog
    from faultline.context.settings import ContextSettings

    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    try:
        platform = LivePlatform(
            ingest_url=args.ingest_url,
            metrics_url=args.metrics_url,
            redis_url=args.redis_url,
            postgres_dsn=dsn,
        )
    except NotLoopbackError as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    label = args.label or datetime.now(UTC).strftime("%Y-%m-%dT%H%MZ")
    report = run_storm(
        platform,
        n=args.n,
        seed=args.seed,
        concurrency=args.concurrency,
        services=sorted(ServiceCatalog.from_snapshot().services),
        evidence_dir=Path(args.evidence_root) / f"storm-{label}",
    )
    held = sum(1 for v in report.verdicts if v.held)
    print(f"\n{held} of {len(report.verdicts)} predictions held; evidence in storm-{label}/")
    for v in report.verdicts:
        mark = "yes" if v.held else ("n/a" if v.held is None else "NO ")
        print(f"  {mark}  {v.prediction} - {v.detail}")
    return 0 if all(v.held is not False for v in report.verdicts) else 1
