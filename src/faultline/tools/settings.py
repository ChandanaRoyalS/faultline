"""Where the tools reach, and nothing an agent can influence (T2.6, ADR-0019)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ToolSettings(BaseSettings):
    """Overridable via FAULTLINE_TOOLS_*.

    **Endpoints come from configuration, never from an agent.** ADR-0004's runtime contract
    requires it - the runtime must receive telemetry endpoints from configuration rather than
    assuming Faultline's compose network - and THREAT-MODEL thesis 2 needs it: an agent that
    could name a host could point a tool anywhere.
    """

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_TOOLS_", env_file=".env", extra="ignore"
    )

    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    jaeger_url: str = "http://localhost:8080/jaeger/ui"
    """Through frontend-proxy. `/jaeger/api/...` returns the UI's HTML with a 200 - Jaeger's
    query service serves the SPA for paths it does not recognise - so the working prefix is
    `/jaeger/ui/api/...` (measured, docs/evidence/t2.4-dependency-graph/)."""

    postgres_dsn: str = "postgresql://faultline:faultline-dev@localhost:5432/faultline"

    max_log_lines: int = 500
    """Matches the rehearsal recorder's cap, so a bundle and a tool see the same shape."""

    max_window_seconds: int = 6 * 60 * 60
    """Prometheus retention (CATALOG.md, "Prometheus keeps 6 hours"). A window longer than
    retention returns a truthful-looking partial answer, which is worse than a refusal."""

    max_spans: int = 200
