"""The baseline gate: refuse to inject onto a world that is not quiet (T4.1, ADR-0022 §3.1).

**It refuses, it does not warn.** ADR-0022: a run that proceeds and is marked suspect produces
a number someone will quote. The scenario is reported `not_attempted` with the failing signal,
and nothing is injected.

The model already existed on the other path - T1.5's rehearsal recorder refuses a dirty
baseline and refuses a world that has been up for less than five minutes - and the agent path
had nothing. T3.4's smoke found the world already degraded (checkoutservice and frontend pinned
at 15000ms p95, accountingservice at 0.000 req/s) and the check that caught it was a human
deciding to look; T3.4b, T3.4c and T3.5 all repeated it by hand. Three consecutive tasks doing
the same manual check is a specification.

**Half of that founding reading was misread, and T7.14 corrected it.** `accountingservice` at
0.000 req/s was a real fault. `checkoutservice and frontend pinned at 15000ms` was not
degradation: those two services, and `loadgenerator` behind them, carry a low-rate population of
genuinely slow requests that sits within a percentage point of the 95th percentile at the world's
resting throughput, so p95 lands either at its 38ms baseline or in the thousands depending on
which side of 5% the tail fell. Measured at rest over 12 hours: two excursions, 60 and 15 minutes
long, 12.6% of wall clock, on a world whose median p95 was 37.8ms - its committed baseline. The
gate still refuses on them, and should. It no longer calls them degradation. See ADR-0025.

Two facts have to be encoded or the gate fails on a healthy world, and both are measured:

1. **`frontend-proxy` sits at 0.000 req/s when everything is fine.** The committed clean
   baseline `evals/baselines/20260824T033742Z` records it at 181 consecutive samples of 0.0,
   min and max alike. Reading zero traffic there as a fault would block every run forever.
2. **A container recreated in the last five minutes makes its p95 meaningless.** CATALOG.md's
   world-hazards section: readings taken 0.8, 4.0 and 14.2 minutes after cart reverts were
   written up as evidence that cartservice is bimodal and reaches 353ms unprompted. It is not
   and it does not. The recorder's `require_settled_containers` is that fact as a gate, and it
   is reused here rather than restated.

3. **A resolved incident is not a finished incident until its settle window has elapsed.**
   The orchestrator reopens a resolved incident when a firing episode arrives inside that
   window (`TIME_OVERLAP_SETTLE`), which is correct behaviour and is exactly how a new run's
   alerts get swallowed by the previous run's incident. T4.7's first sweep attempt lost a
   scenario to it: 22 events, one incident, and the scenario after it had nothing of its own
   to investigate. The fix at the time was a person noticing and waiting the window out; this
   is that person, written down.

Thresholds are **placeholders** in ADR-0016's sense - reasons, no measurements. Set them from
T4.1's own first runs. The settle window is **not** one of them: it is read from the
orchestrator's own settings on every call, so a deployment that changes the window moves the
gate with it and no edit here is needed.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from evalharness import baseline as baseline_mod
from evalharness.prom import METRIC_QUERIES, PROMETHEUS, firing_alerts, now, query_range
from evalharness.rehearse import (
    MIN_CONTAINER_UPTIME_SECONDS,
    RehearsalError,
    container_uptimes,
    require_settled_containers,
)

P95_CEILING_MS = 1000.0
"""Above this, something is wrong that is not this run's fault. A placeholder: chosen because
every clean reading taken across T3.4-T3.5 sat far below it and every degraded one far above."""

EXPECTED_SILENT = frozenset({"frontend-proxy"})
"""Services whose zero request rate is the healthy state. See the module docstring, fact 1."""


def settle_window() -> timedelta:
    """The orchestrator's settle window, read from its configuration rather than copied.

    A constant here would be a second source of truth for a number ADR-0016 explicitly calls a
    placeholder to be replaced by measurement. Reading it means the gate refuses on whatever
    window the orchestrator is actually running, including one set from the environment.
    """
    from faultline.orchestrator.settings import OrchestratorSettings

    return timedelta(seconds=OrchestratorSettings().settle_window_seconds)


INGEST_HEALTH_PATH = "/healthz"
PIPELINE_IDLE_MULTIPLE = 6
"""How many `block_ms` a live consumer may sit idle before it counts as gone.

`idle` is time since the consumer last *interacted* with Redis, and a blocking `XREADGROUP`
refreshes it every `block_ms`, so a healthy consumer's idle is bounded by roughly that interval
plus whatever it spends processing. Six is generous enough not to fire on a slow ack and tight
enough to notice a dead consumer inside half a minute.

Read as a multiple of the orchestrator's own `block_ms` rather than as a fixed number of seconds,
for T4.13's reason: a deployment that changes the block interval moves this with it, and no edit
here is needed."""


def ingest_base_url() -> str:
    """Where the harness reaches ingest, from its own side of the network.

    `IngestSettings.host` is what the server binds - typically `0.0.0.0`, which is an address to
    listen on and not one to connect to. Alertmanager reaches the same app at
    `host.docker.internal` because it is inside a container; the harness is on the host, so it
    uses loopback and the configured port.
    """
    from faultline.ingest.settings import IngestSettings

    return f"http://localhost:{IngestSettings().port}"


def ingest_accepting(url: str) -> bool | None:
    """Does the ingest app answer on its health route?

    **Proves:** a process is bound to the port, the ASGI app booted, and routing works.
    **Does not prove** that `POST /api/v1/alerts` succeeds - that is a different route which
    validates a payload and writes to Redis, and it can fail while `/healthz` still answers.
    A stronger check would have to post a real alert, which would put a fabricated episode into
    the store the run is about to measure, so it is deliberately not done.

    `None` means the question could not be asked at all, which the caller treats as down: the
    reason this check exists is that nothing was listening.
    """
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}{INGEST_HEALTH_PATH}", timeout=5) as r:
            return bool(200 <= r.status < 300)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def consumer_idle_ms() -> int | None:
    """Milliseconds since the orchestrator's consumer last spoke to Redis.

    **Proves:** something is attached to the consumer group and actively polling it. Measured:
    with the orchestrator up, `idle` sat at 93-905ms against a 5000ms block; killed, it grew 1:1
    with wall clock - 6963, 17001, 29046ms.

    **Does not prove** that an event would be processed successfully once read - the consumer could
    read and then fail on the database write - nor that the attached client is the orchestrator
    rather than something else using the same consumer name.

    **It cannot be produced by a quiet world, which is the point.** Redis tracks two clocks here
    and only one of them is a liveness signal: `idle` is time since the last interaction, which a
    blocking read refreshes whether or not it returns anything, while `inactive` is time since the
    last *successful* read and grows whenever the world has nothing to say. Reading `inactive`
    would fire on every quiet world - exactly the conflation this check exists to avoid.

    `None` means no consumer, no group, or no stream: all of them are "not consuming".
    """
    from faultline.orchestrator.settings import OrchestratorSettings

    settings = OrchestratorSettings()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=5)
        consumers = client.xinfo_consumers(settings.stream, settings.group)
    except Exception:
        return None
    idles = [int(c["idle"]) for c in consumers if "idle" in c]
    return min(idles) if idles else None


class GateRefusedError(RuntimeError):
    """The world is not fit to inject into. **Nothing was injected.**

    `discard_reason` is what the manifest records. Subclasses narrow it so a refusal that means
    something different is distinguishable afterwards rather than sharing one label - the same
    shape T7.12 gave `RunError`. See `PipelineDownError`.
    """

    discard_reason = "baseline gate refused"


class PipelineDownError(GateRefusedError):
    """The alert pipeline is not assembled, which is not the world failing to alert (T7.25).

    **A third refusal, distinct from both of T7.12's discard reasons and from an ordinary gate
    refusal.** T7.24 injected while `faultline-ingest` and `faultline-orchestrate` were down. The
    fault fired exactly on schedule - checkoutservice reached 27.6% errors and four
    `ServiceNoTraffic` alerts stood on the board - and no incident was ever opened, because nothing
    was listening at the webhook and nothing was consuming the stream. Left alone that run would
    have waited out the correlate budget and recorded `no-alert`, which reads as a fact about the
    scenario. It was a fact about the harness.
    """

    discard_reason = "pipeline-down"


@dataclass
class GateReading:
    """Every check the gate made and what it saw. Goes into the run manifest verbatim.

    Recorded whether the gate passed or refused: a run's manifest saying *what quiet looked
    like that day* is what makes two runs comparable, and a refusal is a measurement too.
    """

    firing_alerts: list[str] = field(default_factory=list)
    p95_over_ceiling: dict[str, float] = field(default_factory=dict)
    p95_excursions: dict[str, Excursion] = field(default_factory=dict)
    ingest_accepting: bool | None = None
    consumer_idle_ms: int | None = None
    pipeline_down: list[str] = field(default_factory=list)
    silent_services: list[str] = field(default_factory=list)
    unexpected_silent: list[str] = field(default_factory=list)
    services_reporting: int = 0
    youngest_container: tuple[str, int] | None = None
    active_injections: str = ""
    open_incidents: list[str] = field(default_factory=list)
    settling_incidents: list[dict[str, Any]] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.refusals

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "firing_alerts": self.firing_alerts,
            "p95_over_ceiling_ms": self.p95_over_ceiling,
            "p95_excursions": {s: e.as_dict() for s, e in self.p95_excursions.items()},
            "ingest_accepting": self.ingest_accepting,
            "consumer_idle_ms": self.consumer_idle_ms,
            "pipeline_down": self.pipeline_down,
            "silent_services": self.silent_services,
            "unexpected_silent": self.unexpected_silent,
            "services_reporting": self.services_reporting,
            "youngest_container": list(self.youngest_container)
            if self.youngest_container
            else None,
            "active_injections": self.active_injections,
            "open_incidents": self.open_incidents,
            "settling_incidents": self.settling_incidents,
            "refusals": self.refusals,
        }


def _window_by_service(query: str, window_seconds: int = 180) -> dict[str, list[float]]:
    """Every sample per service over a short window."""
    from datetime import timedelta

    from evalharness.prom import series_points

    end = now()
    payload = query_range(query, end - timedelta(seconds=window_seconds), end, 15, base=PROMETHEUS)
    return {
        service: [v for _, v in points]
        for service, points in series_points(payload).items()
        if points
    }


def _latest_by_service(query: str, window_seconds: int = 180) -> dict[str, float]:
    """The last sample per service over a short window. One shape, two callers."""
    return {s: v[-1] for s, v in _window_by_service(query, window_seconds).items()}


@dataclass(frozen=True)
class Excursion:
    """What a p95 window looked like, not just where it ended (T7.14).

    **The gate refused four times before this existed and recorded one scalar each time.** None
    of those manifests can say whether the world was spiking or had been slow for an hour, so
    diagnosing them meant going to the live world - and by then the window was gone. Twice a
    reader took the scalar for evidence that the world was degraded: T3.4's smoke, which this
    module's docstring still cites as founding evidence, and T7.13, which called it a
    sample-starved histogram. It is neither. See `docs/adr/0025`.
    """

    samples_over: int
    samples: int
    median_ms: float
    max_ms: float

    @property
    def sustained(self) -> bool:
        """Over the ceiling for the whole window - an episode, not a spike."""
        return self.samples_over == self.samples

    def describe(self) -> str:
        shape = "sustained" if self.sustained else "intermittent"
        return (
            f"{self.samples_over} of {self.samples} samples over, {shape}, "
            f"median {self.median_ms:.0f}ms, max {self.max_ms:.0f}ms"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "samples_over": self.samples_over,
            "samples": self.samples,
            "sustained": self.sustained,
            "median_ms": self.median_ms,
            "max_ms": self.max_ms,
        }


KNOWN_TAIL_SERVICES = frozenset({"checkoutservice", "frontend", "loadgenerator"})
"""Services measured to enter multi-minute p95 excursions on a world at rest (T7.14).

Named so a refusal can say "this is the characterised one" instead of leaving the next reader to
rediscover it. **They are not exempted from anything** - the gate still refuses, because injecting
during an excursion would put a pre-existing alert into the scenario's blast radius. Naming is not
forgiveness; see ADR-0025 for why de-sensitising the rule would falsify two recorded bundles."""


def read(
    open_incidents: list[str] | None = None,
    resolved_incidents: list[tuple[str, datetime]] | None = None,
) -> GateReading:
    """Take every reading. **Does not raise** - `require` decides what the readings mean.

    Split so the readings land in the manifest even when the gate refuses, and so the whole
    thing is testable without a world.

    `resolved_incidents` is `(id, resolved_at)` for incidents that have already reached a
    terminal state. The gate decides which of them are still settling; the caller does not
    need to know the window.
    """
    reading = GateReading(open_incidents=list(open_incidents or []))

    # **Before anything about the world**, because a world that alerts perfectly into a pipeline
    # nobody is running produces a run that looks like a scenario that does not alert (T7.24).
    from faultline.orchestrator.settings import OrchestratorSettings

    ingest_url = ingest_base_url()
    reading.ingest_accepting = ingest_accepting(ingest_url)
    reading.consumer_idle_ms = consumer_idle_ms()
    ceiling = PIPELINE_IDLE_MULTIPLE * OrchestratorSettings().block_ms
    if reading.ingest_accepting is not True:
        reading.pipeline_down.append(
            f"ingest is not accepting on {ingest_url}{INGEST_HEALTH_PATH} "
            "- start it with `uv run faultline-ingest`"
        )
    if reading.consumer_idle_ms is None:
        reading.pipeline_down.append(
            "no consumer is attached to the orchestrator's group - start it with "
            "`uv run faultline-orchestrate`"
        )
    elif reading.consumer_idle_ms > ceiling:
        reading.pipeline_down.append(
            f"the orchestrator's consumer last spoke to Redis {reading.consumer_idle_ms}ms ago, "
            f"over the {ceiling}ms ceiling - it is attached but not polling. Restart it with "
            "`uv run faultline-orchestrate`"
        )
    if reading.pipeline_down:
        reading.refusals.append(
            "the alert pipeline is not assembled: " + "; ".join(reading.pipeline_down) + ". "
            "This is NOT the world failing to alert - the fault would fire and no incident would "
            "open, which records as `no-alert` and reads as a fact about the scenario (T7.24)."
        )

    reading.firing_alerts = firing_alerts()
    if reading.firing_alerts:
        reading.refusals.append(f"{len(reading.firing_alerts)} alert(s) firing")

    windows = _window_by_service(METRIC_QUERIES["latency-p95"])
    reading.p95_over_ceiling = {
        s: v[-1] for s, v in windows.items() if v and v[-1] > P95_CEILING_MS
    }
    reading.p95_excursions = {
        s: Excursion(
            samples_over=sum(1 for x in v if x > P95_CEILING_MS),
            samples=len(v),
            median_ms=median(v),
            max_ms=max(v),
        )
        for s in reading.p95_over_ceiling
        for v in [windows[s]]
    }
    if reading.p95_over_ceiling:
        worst = ", ".join(
            f"{s} at {v:.0f}ms ({reading.p95_excursions[s].describe()})"
            for s, v in sorted(reading.p95_over_ceiling.items())
        )
        reading.refusals.append(f"p95 above {P95_CEILING_MS:.0f}ms: {worst}")
        known = sorted(set(reading.p95_over_ceiling) & KNOWN_TAIL_SERVICES)
        if known:
            reading.refusals.append(
                f"note: {', '.join(known)} - the characterised at-rest excursion (ADR-0025), "
                "not evidence the world is degraded. Real, and a real reason to refuse: it "
                "would land in the injected fault's blast radius. Wait it out and retry."
            )

    rates = _latest_by_service(METRIC_QUERIES["call-rate"])
    reading.services_reporting = len(rates)
    reading.silent_services = sorted(s for s, v in rates.items() if v == 0.0)
    reading.unexpected_silent = [s for s in reading.silent_services if s not in EXPECTED_SILENT]
    if reading.unexpected_silent:
        reading.refusals.append(
            f"serving no traffic: {', '.join(reading.unexpected_silent)} "
            f"(frontend-proxy at zero is the healthy state and is not counted)"
        )

    uptimes = container_uptimes()
    reading.youngest_container = uptimes[0] if uptimes else None
    try:
        require_settled_containers()
    except RehearsalError as young:
        reading.refusals.append(str(young).splitlines()[0])

    reading.active_injections = baseline_mod.active_injections()
    if not baseline_mod.world_is_quiet(reading.active_injections):
        reading.refusals.append(f"injector reports active faults: {reading.active_injections}")

    if reading.open_incidents:
        reading.refusals.append(
            f"{len(reading.open_incidents)} non-terminal incident(s) in the store: "
            f"{', '.join(reading.open_incidents)} - a new alert would correlate into one "
            "rather than opening its own"
        )

    window = settle_window()
    moment = now()
    for incident_id, resolved_at in sorted(resolved_incidents or [], key=lambda row: row[1]):
        clears_at = resolved_at + window
        if clears_at <= moment:
            continue
        reading.settling_incidents.append(
            {
                "incident_id": incident_id,
                "resolved_at": resolved_at.isoformat(),
                "seconds_remaining": int((clears_at - moment).total_seconds()),
            }
        )
    for settling in reading.settling_incidents:
        reading.refusals.append(
            f"incident {settling['incident_id']} resolved at {settling['resolved_at']} and is "
            f"still inside the orchestrator's {int(window.total_seconds())}s settle window - a "
            f"firing episode now would reopen it rather than open a new incident, and this "
            f"run's alerts would be attributed to the previous one. "
            f"Wait {settling['seconds_remaining']}s."
        )
    return reading


def require(
    open_incidents: list[str] | None = None,
    resolved_incidents: list[tuple[str, datetime]] | None = None,
) -> GateReading:
    """Read, then refuse if anything is wrong. The readings travel on the exception."""
    reading = read(open_incidents, resolved_incidents)
    if not reading.passed:
        detail = "\n".join(f"  - {why}" for why in reading.refusals)
        # A pipeline that is not assembled gets its own type, so the discard says which of the
        # three things went wrong rather than collapsing into "the world was not quiet".
        error = PipelineDownError if reading.pipeline_down else GateRefusedError
        raise error(
            f"baseline gate refused; nothing was injected.\n{detail}\n"
            f"The world must be quiet before a scored run, or the run measures the world's "
            f"prior state as well as the fault (ADR-0022 §3.1). Containers settle in "
            f"{MIN_CONTAINER_UPTIME_SECONDS}s."
        )
    return reading
