"""The tool surface as an interface, so a second implementation can sit behind it (T7.2).

**Why this exists.** [ADR-0004](../../../docs/adr/0004-benchmark-target.md)'s runtime contract
binds the agent runtime to receive *"telemetry and tool endpoints from configuration rather than
assuming Faultline's compose network"*, and `ToolSettings` satisfies that for addresses: the three
backend URLs are settings, not constants. **What it does not satisfy is transport.** T0.5 read
SREGym's harness and found its tools are *"MCP over SSE, not HTTP APIs"* - five servers mounted at
`/kubectl`, `/prometheus`, `/loki`, `/jaeger`, `/submit` - so pointing `prometheus_url` at the
benchmark does not work. The address is configurable and the protocol is compiled in.

`Tools` is one implementation of this surface: HTTP, against the compose world, with a circuit
breaker per backend and a window policy in front. A benchmark driver is a second one. Neither
needs to know about the other, which is what an interface is for.

**Structural, and deliberately not a base class.** `Tools` does not inherit from `ToolSet` and
must not. `evalharness.capability.tool_surface()` computes the capability stamp from
`inspect.getmembers(Tools, inspect.isfunction)`, which walks the MRO - **inherited functions
included**.

**The danger is latent rather than immediate, and the distinction is worth stating exactly,
because the first version of this paragraph got it wrong.** Making `Tools` a subclass today moves
nothing: the protocol declares the same five names the class already has, so the surface is
identical and the digest is unchanged - measured, not assumed. What inheritance would do is make
the capability digest **depend on this file**, so that a method added to the protocol alone - a
sixth tool declared here and implemented nowhere - would move `cap:` and restamp every narrative
without anyone touching the tool implementation. Structural typing keeps the agent's surface
defined in exactly one place, which is the class that implements it.

`tests/test_tool_interface.py` holds both halves - that the protocol matches the surface, and
that the surface is unchanged.

**Not the only tool protocol, and the other one is narrower on purpose.**
`evalharness.baselines.ToolLayer` declares the two tools B0 is allowed, because *"a baseline with
the same reach as the system it controls for measures nothing."* This one is the agent's full
surface. They are separate for the same reason they are named differently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from faultline.tools.metrics import MetricTemplate
from faultline.tools.ranking import RankingContext
from faultline.tools.results import (
    BaselineResult,
    ChangeResult,
    LogResult,
    MetricResult,
    TraceResult,
)
from faultline.tools.window import WindowPolicy

# **The typed results are imported and the implementation is not.** `results`, `metrics`,
# `ranking` and `window` are the shared vocabulary - `roles.py` already imports all four directly -
# while `tools.py` is one implementation of the surface below. Nothing here imports it, and
# `tools.py` does not import this, so a second implementation can be written without either
# module learning about the other. An earlier draft typed every return as `Any` to avoid the
# question and mypy caught it four times: a protocol that erases its own return types gives the
# agent layer less checking than the concrete class it replaced, which is a worse interface than
# no interface.


@runtime_checkable
class ToolSet(Protocol):
    """Everything an agent can ask of the world, and nothing else.

    The five methods are exactly what `capability.tool_surface()` reports, which is what the
    capability stamp is computed from - so an implementation that satisfies this protocol offers
    the agent the surface every recorded run was measured against. **A sixth method here without
    one on `Tools` would be a lie about the agent's reach**, and the guard fails on it.

    `window_policy` is an attribute rather than a method because it is not a tool an agent calls:
    it decides what a tool may read. A second implementation still needs one, because the windows
    a specialist asks for are derived from it (`Specialist.window`) and the refusals it produces
    are part of what the agent sees.
    """

    window_policy: WindowPolicy

    def promql_query(
        self, query: str, start: datetime, end: datetime, step: int = 15
    ) -> MetricResult: ...

    def metric_baseline(
        self,
        service: str,
        template: MetricTemplate,
        start: datetime,
        end: datetime,
        step: int = 15,
    ) -> BaselineResult: ...

    def logql_query(
        self, service: str, start: datetime, end: datetime, limit: int | None = None
    ) -> LogResult: ...

    def trace_query(
        self, service: str, start: datetime, end: datetime, only_errors: bool = False
    ) -> TraceResult: ...

    def change_history(
        self,
        service: str,
        start: datetime,
        end: datetime,
        ranking: RankingContext | None = None,
    ) -> ChangeResult: ...
