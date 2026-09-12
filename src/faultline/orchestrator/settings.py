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

    investigate: bool = False
    """**Whether this process runs the investigations it admits** (T5.5c, defect twenty-nine).

    Off here because a development machine's `make demo` and `make eval` launch
    `faultline-investigate` themselves; a runner beside them would investigate every incident twice
    and bill for both. The deployment sets it, and is the only thing that should: there, nothing
    else will."""

    investigate_settle_seconds: int = 90
    """How long after an incident opens before it is investigated - so the agents see the blast
    radius after it has spread, not mid-spread. **The same 90s the harness waits**
    (`evalharness.run.SETTLE_AFTER_ALERT_SECONDS`); a test pins the two together, because a live
    investigation that starts earlier or later than a scored one is a different experiment."""

    investigate_poll_seconds: float = 15.0

    max_rejections: int = 2
    """How many times one incident may be rejected and re-investigated (T6.3,
    `PREREGISTRATION-T6.3.md` §2.3). **Two, and the cap is on the loop rather than on the
    operator**: a third rejection is recorded like any other and the incident stays `REJECTED`;
    what stops is the spending. A rejection loop is the one path in this system where a human
    saying *no* costs a model call, so the number that bounds it is configuration an operator can
    see rather than a constant in a runner."""

    investigate_args: tuple[str, ...] = (
        "--max-tool-calls",
        "4",
        "--max-tool-calls-changes",
        "8",
        "--max-tokens",
        "120000",
    )
    """T4.7's bounds, exactly as the Makefile's `eval` target passes them. A test reads them off
    the Makefile so the live configuration cannot drift from the measured one."""

    batch_size: int = 32
    block_ms: int = 5000
