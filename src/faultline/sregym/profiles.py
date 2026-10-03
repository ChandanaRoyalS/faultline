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
    """The span-metric spelling in SREGym's Prometheus, or `None` where the application emits no
    traces SREGym's collector can turn into metrics. Read on the dev problems."""

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
            span_metrics=None,
        ),
        Profile(
            application="sregym-social-network",
            app_name="Social Network",
            front_door="nginx-web-server",
            span_metrics=None,
            deployments={"nginx-web-server": "nginx-thrift"},
        ),
    )
}
"""Keyed by `/get_app`'s `app_name`. An application not here is not in the run (the run's
registration: the three applications with a snapshot), and the driver refuses it."""

PROFILE_READ = False
"""Whether the dev read has confirmed `span_metrics` and `deployments` for all three. **False
until it has**, and the pilot's registration requires it true before the first attempt."""


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
