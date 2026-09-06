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

    grafana_url: str = "http://localhost:3000"
    """**Where a citation's deep link sends a reader** - the only setting in this class no tool
    reads. `faultline.api.view` does.

    It sits beside the others because it is the same kind of fact under the same rule: an endpoint
    the deployment knows and an agent cannot name. `jaeger_url` is already a *UI* base rather than
    an API root, so this is not a new species of value here.

    **It exists because the link did not work.** `view.deep_link` built `/explore?left=...` as a
    bare relative path, reasoning that *"the platform does not know its own public URL"* - true,
    and about the wrong URL. A deep link needs **Grafana's** address, which the platform is told,
    exactly as it is told Prometheus's and Loki's. Relative, the link resolved against whatever
    host served the incident page - `faultline-ingest` on :8000, which serves no `/explore` route.
    Every citation on the page 404'd, on the development machine and everywhere else. The tests
    asserted the string began with `/explore?`, never that it reached anything.

    T5.1's deliverable is *"Incident view with evidence cards + citation deep-links"*, and the
    clickable citation is the demo's third beat in the proposal's own script. Found auditing
    Phase 5 against the specification's wording, after an earlier pass had marked T5.1 complete on
    the strength of the function existing.

    The default is the development Grafana, published on 3000 by `compose/telemetry.yml`."""

    postgres_dsn: str = "postgresql://faultline:faultline-dev@localhost:5432/faultline"

    max_log_lines: int = 500
    """Matches the rehearsal recorder's cap, so a bundle and a tool see the same shape."""

    max_window_seconds: int = 6 * 60 * 60
    """The ceiling on any telemetry window - the widest read `promql_query`, `logql_query` and
    `trace_query` will perform. **Its justification changed and the number did not.** It was
    Prometheus retention (CATALOG.md, "Prometheus keeps 6 hours"); T7.1 raised retention to 15d
    in `compose/telemetry.yml` and this docstring was not updated until T3.2b. It stays six hours
    as a *policy* bound: a full twelve times the default lookback, and the plan says unbounded
    requests are refused, so something must be the bound. `WindowPolicy` is the only reader."""

    default_lookback_seconds: int = 30 * 60
    """How far before onset every specialist's window opens - the plan's `onset - 30 min`. The
    forward end is the moment of investigation, not a fixed offset."""

    change_lookback_seconds: int = 24 * 60 * 60
    """The change analyst alone reaches back a day - the plan's `onset - 24 h`, "because causes
    precede symptoms". Its ceiling is this plus `max_window_seconds` (see `WindowPolicy`)."""

    max_spans: int = 200
