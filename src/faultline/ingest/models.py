"""The wire shapes: what Alertmanager sends, and what T2.2 reads off the stream (T2.1).

Both halves are measured rather than inferred. `docs/evidence/t2.1-webhook/README.md`
records eight live deliveries captured against a `cart-redis-misconfig` injection, with a
full field inventory; every field below is one that capture actually carried.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

GO_ZERO_TIME = datetime(1, 1, 1, tzinfo=UTC)
"""What Alertmanager puts in `endsAt` while an alert is firing.

Measured: `0001-01-01T00:00:00Z` on every firing delivery in the capture. It is Go's zero
`time.Time` rendered as RFC3339, so it parses as a valid date and is not one. Anything that
compares it as a timestamp concludes the alert ended two thousand years ago.
"""


class AlertStatus(StrEnum):
    """The two values the capture contains. Alertmanager v4 defines no others."""

    FIRING = "firing"
    RESOLVED = "resolved"


class Alert(BaseModel):
    """One alert inside a delivery - the unit of identity, and the unit of dedupe.

    `extra="allow"` deliberately. This is external input from a component we do not
    version-pin to ourselves: a future Alertmanager adding a field must not turn every
    delivery into a 422 and drop real incidents on the floor. Unknown fields are carried
    through to the stream rather than silently discarded, so nothing is lost either.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    status: AlertStatus
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    generator_url: str | None = Field(default=None, alias="generatorURL")
    fingerprint: str

    @field_validator("ends_at", mode="after")
    @classmethod
    def _zero_time_is_absent(cls, value: datetime | None) -> datetime | None:
        """Go's zero time means "still firing", so it becomes absent rather than a date."""
        return None if value is not None and value == GO_ZERO_TIME else value

    @property
    def service_name(self) -> str | None:
        """The raw label. Kept as delivered; `AlertEvent.service` is the normalised form."""
        return self.labels.get("service_name")

    @property
    def alertname(self) -> str | None:
        return self.labels.get("alertname")

    @property
    def episode_key(self) -> str:
        """One firing-to-resolved lifetime of one alert.

        `fingerprint` identifies the alert across all of its episodes; it is stable across
        firing and resolved deliveries and unmoved by annotation drift (measured - the same
        alert reported 29.25% firing and 10.08% resolved under one fingerprint). `startsAt`
        is what separates two episodes of that same alert.
        """
        return f"{self.fingerprint}@{self.starts_at.isoformat()}"

    @property
    def delivery_key(self) -> str:
        """The dedupe key: this episode in this state.

        Seeing it twice means a repeat notification - `repeat_interval`, or an Alertmanager
        retry - not a second transition.
        """
        return f"{self.episode_key}:{self.status.value}"


class WebhookPayload(BaseModel):
    """An Alertmanager v4 webhook body.

    **`alerts` is a list and is treated as one.** Every delivery in the capture carried
    exactly one alert, but that is a consequence of our `group_by: [alertname,
    service_name]` - a grouping key as fine as the alerts themselves - and not of the
    protocol. Editing `compose/prometheus/alertmanager.yml` would put several alerts behind
    one request with no other signal, so the unit here is the alert, never the POST.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    version: str
    status: AlertStatus
    receiver: str
    alerts: list[Alert] = Field(default_factory=list)
    group_key: str = Field(default="", alias="groupKey")
    group_labels: dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    external_url: str = Field(default="", alias="externalURL")
    truncated_alerts: int = Field(default=0, alias="truncatedAlerts")


EVENT_VERSION = 1
"""The stream event's shape. T2.2 reads this; bump it only for a breaking change."""


class AlertEvent(BaseModel):
    """One alert-episode transition, as published to the stream. **The T2.2 contract.**

    Ingest's whole output. It is deliberately a transition and not an incident: whether two
    events belong to the same incident is correlation, which is T2.2's decision and needs
    context ingest does not have (ADR-0015).
    """

    model_config = ConfigDict(extra="forbid")

    event_version: int = EVENT_VERSION
    received_at: datetime
    """When the receiver took the delivery. The listener's clock, not Alertmanager's."""

    fingerprint: str
    episode_key: str
    status: AlertStatus
    service: str | None
    """`service_name` put through `canonical_service`, so the orchestrator can key on one
    identity without knowing the world names services two ways. `None` when the alert
    carries no `service_name` label - not every rule is per-service."""

    starts_at: datetime
    ends_at: datetime | None
    """Absent while firing. Go's zero time is normalised away here, not passed on."""

    alert: dict[str, Any]
    """The full alert object as delivered, under Alertmanager's own field names.

    Faithful delivery: everything the capture showed, including fields this model does not
    name, so a consumer is never forced back to the webhook to answer a question."""

    group_key: str
    """Which Alertmanager group carried it. Records the grouping in force at delivery time,
    which is the thing that decides how many alerts share a POST."""
