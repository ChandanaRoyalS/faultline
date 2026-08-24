"""Where the orchestrator reads events and keeps incidents (T2.2).

Four of these are ADR-0016's placeholders: `max_concurrent`, `settle_window_seconds`,
`claim_idle_seconds`, `poison_delivery_threshold`. Each has a reason recorded there and
**none has a measurement** - they are defaults to be replaced by T4.1's first runs, not
decisions. They are settings rather than constants for exactly that reason.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Orchestrator configuration. Every field is overridable via FAULTLINE_ORCH_*."""

    model_config = SettingsConfigDict(env_prefix="FAULTLINE_ORCH_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    stream: str = "faultline:alerts"
    """What T2.1 publishes to (ADR-0015)."""

    group: str = "orchestrator"
    consumer: str = "orchestrator-1"
    dead_letter_stream: str = "faultline:alerts:dead"

    postgres_dsn: str = "postgresql://faultline:faultline-dev@localhost:5432/faultline"
    """The platform profile's `postgres`. Dev credentials are in docker-compose.yml; a real
    deployment supplies its own through the environment."""

    max_concurrent: int = 3
    """**Placeholder.** The binding constraint is model spend and rate limits, and no
    measurement of an investigation's cost or duration exists - T3.x is unbuilt and T4.1 has
    not run. Set it from T4.1 rather than defending it now."""

    settle_window_seconds: int = 300
    """**Placeholder, and the one with a real trade-off.** A recovery-caused alert cannot
    appear sooner than its rule's `for` clause after the remediation: 2m for
    `ServiceHighErrorRate`, 3m for `ServiceHighLatency`, ~6m for `ServiceNoTraffic` (3m of
    `for` on top of a `[3m]` window that must empty first). 5m catches the first two - both
    recovery alerts ever measured were `ServiceHighErrorRate` - and lets a recovery-caused
    `ServiceNoTraffic` open a second incident. 7m catches all three and puts every closure 7
    minutes behind the world. ADR-0016 flags this rather than asserting it."""

    claim_idle_seconds: int = 60
    """**Placeholder.** Long enough not to steal from a slow-but-alive consumer, short enough
    not to strand a crashed one's work. No measurement behind it."""

    poison_delivery_threshold: int = 5
    """**Placeholder.** After this many deliveries an entry goes to the dead-letter stream
    instead of cycling forever."""

    batch_size: int = 32
    block_ms: int = 5000
