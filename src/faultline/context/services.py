"""The service catalog: what the system knows about each service (T2.4).

Distinct from `faultline.context.catalog`, which answers a narrower question - whether a
service is usable for *graph reasoning*. This is the git-versioned document T2.4 asks for:
owners, tiers, SLOs, runbook links and declared dependencies, exposed beside the graph API.

Every field is grounded in something except one, and ADR-0035 says which.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

CATALOG_NAME = "services.yaml"


class Slo(BaseModel):
    """Taken from the alert rules, which ADR-0012 grounded in a measured quiet baseline.

    Not invented: `tests/test_services.py` parses `compose/prometheus/alert-rules.yml` and
    fails if these numbers stop matching the thresholds that actually page.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    p95_latency_ms: int
    error_ratio: float
    source: str


class ServiceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    container: str
    kind: str
    tier: str
    owner: str
    depends_on: list[str] = Field(default_factory=list)
    """**A measured lower bound**, seeded from the dependency snapshot rather than declared
    from memory. A span-derived graph holds the edges exercised during its capture window, so
    an absent edge means "not seen", never "not there"."""

    runbooks: list[str] = Field(default_factory=list)
    """Empty until Q15 seeds the runbook corpus. T2.4b's allowlist landed; its runbooks did
    not, and linking to documents that do not exist would be worse than linking to none."""

    slo: Slo | None = None


class ServiceDirectory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: int = Field(ge=1)
    services: list[ServiceRecord]

    def get(self, name: str) -> ServiceRecord | None:
        return next((s for s in self.services if s.name == name), None)

    def by_owner(self, owner: str) -> list[ServiceRecord]:
        return [s for s in self.services if s.owner == owner]

    @property
    def applications(self) -> list[ServiceRecord]:
        return [s for s in self.services if s.kind == "application"]


def catalog_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "knowledge" / CATALOG_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no knowledge/{CATALOG_NAME} above {__file__}")


@cache
def load_services() -> ServiceDirectory:
    raw: Any = yaml.safe_load(catalog_path().read_text())
    return ServiceDirectory.model_validate(raw)
