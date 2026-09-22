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

    world: str = "v1"
    """Which demo generation the tools are pointed at - `v1` or `v2` (T7.1, ADR-0042).

    **It selects the span-metric names and nothing else** (`faultline.tools.spanmetrics`): v1 wires
    the collector's `spanmetrics` as a processor and v2 as a connector, and the two emit different
    series names for the same quantity.

    **It belongs here for the reason the endpoints do.** ADR-0004's runtime contract requires the
    runtime to take what it observes from configuration rather than assuming a compose network;
    which world it observes is that kind of fact, and an agent must no more be able to name it than
    it can name a host.

    **Defaults to `v1`, and a world is opted into rather than defaulted into.** Every published
    figure was measured on v1 (ADR-0026), and a wrong value here is an empty PromQL result rather
    than an error - the query succeeds, the agent reads *no data*, and nothing fails loudly.
    """

    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    tempo_url: str = "http://localhost:3200"
    """The trace store the trace tool reads (T6.1), published by `compose/telemetry.yml`.

    This replaced `jaeger_url`. Jaeger stays in the world as the demo's own UI and the collector
    still exports to it; the tool no longer reads it. `docs/evidence/t2.4-dependency-graph/` was
    captured from Jaeger's API and stays what it was - a recording is not re-sourced."""

    max_traces: int = 10
    """How many traces one search may fetch whole. Ten traces of a busy service is more than the
    span cap admits; the cap, not this, is the bound that usually bites."""

    grafana_url: str = "http://localhost:3000"
    """**Where a citation's deep link sends a reader** - the only setting in this class no tool
    reads. `faultline.api.view` does.

    It sits beside the others because it is the same kind of fact under the same rule: an endpoint
    the deployment knows and an agent cannot name.

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

    breaker_threshold: int = 3
    """Consecutive failed calls before a backend is open for the rest of the run (T6.7 piece 5,
    `reliability.breaker`). One Loki timeout is weather; three in a row is a backend that is down,
    and a specialist with twelve calls against it should spend three `HTTP_TIMEOUT`s, not twelve.
    While open every call to that backend returns a typed result whose `error` says *modality
    unavailable* without contacting it - failure row 12's Detection and Mitigation. No half-open
    inside a run: runs are minutes long and the next run starts closed."""
