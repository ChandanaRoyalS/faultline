"""What the adapter knows about each SREGym application it runs (T7.2, ADR-0044).

One `Profile` per application in the run's registration. Each field says where its value came
from. **A field marked `read on the dev problems` is a placeholder until the dev read**: the
adapter's registration (§2) fixes those names from the three dev problems before the pilot, and
`PROFILE_READ` records whether that has happened. Nothing here is tuned on a scored problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultline.tools.spanmetrics import V2, WorldMetrics


@dataclass(frozen=True, slots=True)
class Profile:
    """One application, as the adapter addresses it."""

    application: str
    """The `FAULTLINE_CONTEXT_APPLICATION` key whose snapshot and catalog this application uses
    (Q125, Q128)."""

    app_name: str
    """`/get_app`'s `app_name` for it, read from SREGym's problem table
    (`docs/evidence/t7.2-run/problems.csv`)."""

    front_door: str
    """The fallback episode's service when no alarm fires (adapter registration §4)."""

    span_metrics: WorldMetrics | None
    """The span-metric spelling in SREGym's Prometheus, or `None` for none.

    **Read on the dev problems (`docs/evidence/t7.2-pilot/t72-pilot-devread-*.txt`): v2's spelling
    for all three.** The shop has series for 18 services. Hotel Reservation has them for
    `reservation` alone, the one service that restarted after SREGym repointed its trace exporter
    (Q127). Social Network has none, because as shipped none of its services sends a trace. Which
    services have series is therefore decided per service, at query time (`McpToolSet`), by the
    owner's decision of 2026-10-03, so that *not traced* is never read as *no traffic*."""

    deployments: dict[str, str] = field(default_factory=dict)
    """Span service name -> Deployment or StatefulSet name, **only where they differ**. Read from
    the topology captures (`g4-social-mediafrontend.txt`: `nginx-thrift` serves as
    `nginx-web-server`); completed on the dev problems."""

    def deployment(self, service: str) -> str:
        """The workload a service's pods belong to."""
        return self.deployments.get(service, service)

    def service(self, deployment: str) -> str:
        """The span name for a workload: the reverse of `deployment`."""
        for service, name in self.deployments.items():
            if name == deployment:
                return service
        return deployment


PROFILES: dict[str, Profile] = {
    profile.app_name: profile
    for profile in (
        Profile(
            application="sregym-astronomy-shop",
            app_name="OpenTelemetry Demo Astronomy Shop",
            front_door="frontend",
            span_metrics=V2,
        ),
        Profile(
            application="sregym-hotel-reservation",
            app_name="Hotel Reservation",
            front_door="frontend",
            span_metrics=V2,
        ),
        Profile(
            application="sregym-social-network",
            app_name="Social Network",
            front_door="nginx-web-server",
            span_metrics=V2,
            deployments={"nginx-web-server": "nginx-thrift"},
        ),
    )
}
"""Keyed by `/get_app`'s `app_name`. An application not here is not in the run (the run's
registration: the three applications with a snapshot), and the driver refuses it."""

PROFILE_READ = True
"""Whether the dev read has confirmed `span_metrics` and `deployments` for all three.

**True since the dev read of 2026-10-03** (pilot registration, part A, and its Addendum 1):

- the span-metric spelling is v2's, decided per service (above);
- the only workload named differently from its span service is `nginx-thrift`;
- the server is in UTC, so `get_logs`' timestamps are read correctly as UTC.

**Loki's labels are not read by part A.** SREGym skips Loki under the external harness, so the
pilot reads them after attempt 1 and stops if `namespace` and `pod` are not both labels."""


def profile_for(app_name: str) -> Profile:
    try:
        return PROFILES[app_name]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(
            f"SREGym application {app_name!r} is not in the run; known: {known}"
        ) from None


def profile_by_application(application: str) -> Profile:
    for profile in PROFILES.values():
        if profile.application == application:
            return profile
    raise ValueError(f"no SREGym profile for application {application!r}")
