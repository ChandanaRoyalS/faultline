"""The incident's opening: standard health alarms, since SREGym gives no alert (T7.2, ADR-0044).

A Faultline incident is alert episodes and nothing else (`faultline.orchestrator.models`). Triage
seeds its blast radius from the alerting services and the planner's first retrieval query is built
from them, so an incident with no episode would give the investigation nowhere to start. SREGym
hands an agent an application and a namespace, and its Prometheus carries no alert rules.

**The owner's decision of 2026-10-02**: the adapter evaluates a fixed list of standard alarms at
the start, and again once a minute for up to five minutes until one fires, and opens the incident
from whichever do. If none fires, the incident is opened on the application's front door. The
rules are adapter registration §4's, verbatim, and they are never changed after a scored attempt:

- kube-prometheus' pod and replica rules, scoped to the namespace;
- Faultline's own three v2 rules (`compose/prometheus/alert-rules-v2.yml`), thresholds unchanged,
  where the application has span metrics.

**One departure from both**, stated in the registration: a rule's `for:` duration cannot be applied
by a single evaluation, so a rule fires on its condition holding when evaluated.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity
from faultline.sregym.mcp import McpClient, backend_error, python_literal
from faultline.sregym.profiles import Profile
from faultline.sregym.toolset import matrix

FALLBACK_ALERT = "SREGymProblemReported"
"""The fallback episode's alertname, as registered."""

EVALUATIONS = 6
"""At the start, then once a minute for five minutes."""

INTERVAL_SECONDS = 60


@dataclass(frozen=True, slots=True)
class Alarm:
    name: str
    expression: str
    severity: Severity
    keyed_by: str
    """The label that names what fired: `pod`, `deployment`, `statefulset` or `service_name`."""


def kube_alarms(namespace: str) -> list[Alarm]:
    ns = f'namespace="{namespace}"'
    return [
        Alarm(
            "KubePodCrashLooping",
            "max by (pod) (max_over_time(kube_pod_container_status_waiting_reason"
            f'{{{ns},reason="CrashLoopBackOff"}}[5m])) >= 1',
            Severity.WARNING,
            "pod",
        ),
        Alarm(
            "KubePodNotReady",
            f'max by (pod) (kube_pod_status_phase{{{ns},phase=~"Pending|Unknown|Failed"}}) > 0',
            Severity.WARNING,
            "pod",
        ),
        Alarm(
            "KubeContainerWaiting",
            "max by (pod) (kube_pod_container_status_waiting_reason"
            f'{{{ns},reason!="CrashLoopBackOff"}}) > 0',
            Severity.WARNING,
            "pod",
        ),
        Alarm(
            "KubeDeploymentReplicasMismatch",
            f"kube_deployment_spec_replicas{{{ns}}} != "
            f"kube_deployment_status_replicas_available{{{ns}}}",
            Severity.WARNING,
            "deployment",
        ),
        Alarm(
            "KubeStatefulSetReplicasMismatch",
            f"kube_statefulset_status_replicas_ready{{{ns}}} != kube_statefulset_replicas{{{ns}}}",
            Severity.WARNING,
            "statefulset",
        ),
    ]


def faultline_alarms(profile: Profile) -> list[Alarm]:
    """Faultline's three v2 rules, on the application's span-metric spelling, or none."""
    world = profile.span_metrics
    if world is None:
        return []
    return [
        Alarm(
            "ServiceHighErrorRate",
            f'sum by (service_name) (rate({world.calls}{{status_code="STATUS_CODE_ERROR"}}[5m])) '
            f"/ sum by (service_name) (rate({world.calls}[5m])) > 0.05",
            Severity.CRITICAL,
            "service_name",
        ),
        Alarm(
            "ServiceHighLatency",
            "histogram_quantile(0.95, sum by (service_name, le) "
            f'(rate({world.duration_bucket}{{span_kind!="SPAN_KIND_INTERNAL"}}[5m]))) > 250',
            Severity.WARNING,
            "service_name",
        ),
        Alarm(
            "ServiceNoTraffic",
            f'sum by (service_name) (rate({world.calls}{{service_name!="frontend-proxy"}}[5m])) '
            "== 0 and sum by (service_name) "
            f'(rate({world.calls}{{service_name!="frontend-proxy"}}[30m] offset 10m)) > 0',
            Severity.CRITICAL,
            "service_name",
        ),
    ]


def alarms_for(namespace: str, profile: Profile) -> list[Alarm]:
    return kube_alarms(namespace) + faultline_alarms(profile)


@dataclass(frozen=True, slots=True)
class Firing:
    alarm: Alarm
    service: str
    at: datetime


class Opener:
    """Evaluates the alarms through `get_metrics` and builds the incident."""

    def __init__(
        self,
        client: McpClient,
        profile: Profile,
        namespace: str,
        *,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._profile = profile
        self._namespace = namespace
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.evaluations = 0
        self.errors: list[str] = []
        self.fallback = False

    def _instant(self, expression: str) -> list[dict[str, Any]]:
        text = self._client.call("prometheus", "get_metrics", {"query": expression})
        error = backend_error(text)
        if error is not None:
            raise RuntimeError(error)
        return matrix(python_literal(text))

    def _owners(self) -> dict[str, str]:
        """Pod -> its Deployment or StatefulSet, from kube-state-metrics' owner series."""
        ns = f'namespace="{self._namespace}"'
        replicasets = {
            e["metric"].get("replicaset", ""): e["metric"].get("owner_name", "")
            for e in self._instant(f'kube_replicaset_owner{{{ns},owner_kind="Deployment"}}')
        }
        owners: dict[str, str] = {}
        for entry in self._instant(f"kube_pod_owner{{{ns}}}"):
            labels = entry["metric"]
            pod, kind, name = (
                labels.get("pod", ""),
                labels.get("owner_kind"),
                labels.get("owner_name"),
            )
            if kind == "ReplicaSet" and name:
                owners[pod] = replicasets.get(name, name)
            elif kind == "StatefulSet" and name:
                owners[pod] = name
        return owners

    def evaluate(self) -> list[Firing]:
        """One round over every alarm. A rule whose query fails is recorded and skipped."""
        self.evaluations += 1
        now = self._clock()
        firings: list[Firing] = []
        owners: dict[str, str] | None = None
        for alarm in alarms_for(self._namespace, self._profile):
            try:
                entries = self._instant(alarm.expression)
            except Exception as exc:
                self.errors.append(f"{alarm.name}: {exc}")
                continue
            for entry in entries:
                label = str(entry.get("metric", {}).get(alarm.keyed_by, ""))
                if not label:
                    continue
                if alarm.keyed_by == "pod":
                    if owners is None:
                        try:
                            owners = self._owners()
                        except Exception as exc:
                            self.errors.append(f"owners: {exc}")
                            owners = {}
                    workload = owners.get(label, "")
                    if not workload:
                        continue
                    service = self._profile.service(workload)
                elif alarm.keyed_by == "service_name":
                    service = label
                else:
                    service = self._profile.service(label)
                firings.append(Firing(alarm, service, now))
        unique = {(f.alarm.name, f.service): f for f in firings}
        return list(unique.values())

    def fire(self) -> list[Firing]:
        """Evaluate until something fires, at most `EVALUATIONS` times a minute apart."""
        for round_ in range(EVALUATIONS):
            if round_:
                self._sleep(INTERVAL_SECONDS)
            firings = self.evaluate()
            if firings:
                return firings
        return []

    def open(self) -> Incident:
        firings = self.fire()
        now = self._clock()
        if not firings:
            self.fallback = True
            firings = [
                Firing(
                    Alarm(FALLBACK_ALERT, "", Severity.CRITICAL, "service_name"),
                    self._profile.front_door,
                    now,
                )
            ]
        return incident_from(firings, now)


def incident_from(firings: list[Firing], now: datetime) -> Incident:
    """One episode per `(alarm, service)`, starting when it was evaluated. No correlation rule
    decided anything, so `join_rule` stays unset."""
    episodes: dict[str, Episode] = {}
    for firing in sorted(firings, key=lambda f: (f.alarm.name, f.service)):
        fingerprint = hashlib.sha256(f"{firing.alarm.name}|{firing.service}".encode()).hexdigest()
        key = f"{fingerprint[:16]}:{int(firing.at.timestamp())}"
        episodes[key] = Episode(
            episode_key=key,
            fingerprint=fingerprint[:32],
            service=firing.service,
            severity=firing.alarm.severity,
            alertname=firing.alarm.name,
            starts_at=firing.at,
            attached_at=now,
        )
    return Incident(
        state=IncidentState.TRIAGING,
        opened_at=now,
        last_activity_at=now,
        episodes=episodes,
    )
