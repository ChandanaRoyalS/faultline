"""`ToolSet` — the tool surface as an interface, and the stamp it must not move (T7.2, step 2).

[ADR-0004](../docs/adr/0004-benchmark-target.md)'s runtime contract binds the agent to take its
*"telemetry and tool endpoints from configuration"*, and `ToolSettings` does that for addresses.
T0.5's read of SREGym's harness found the harder half: its tools are **MCP over SSE**, so the
transport differs and not just the address. `faultline.tools.interface.ToolSet` is the surface a
second implementation has to satisfy; these guards hold the two properties that make the
extraction safe rather than merely tidy.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any

from evalharness.capability import capability_version, tool_surface
from faultline.tools.interface import ToolSet
from faultline.tools.settings import ToolSettings
from faultline.tools.tools import Tools
from faultline.tools.window import WindowPolicy

CAPABILITY_AT_EXTRACTION = "cap:dd651ccc"
"""The stamp before `ToolSet` existed, recorded here so the guard below can be read without
running git. Every narrative stamp and every recorded run is against this value."""


def protocol_methods() -> list[str]:
    return sorted(
        name
        for name, _ in inspect.getmembers(ToolSet, inspect.isfunction)
        if not name.startswith("_")
    )


def test_the_protocol_declares_exactly_the_surface_the_stamp_is_computed_from() -> None:
    """**A protocol that drifts from the class is a lie about the agent's reach.**

    `capability.tool_surface()` reads the public functions off `Tools`, and the capability stamp
    is a digest over that list. `ToolSet` is what a second implementation will be written
    against - so a method here that `Tools` does not have promises a benchmark driver a tool the
    agent has never had, and a method on `Tools` missing here silently narrows what any
    alternative implementation offers.

    Equality rather than a subset, in both directions, for exactly that reason.
    """
    assert protocol_methods() == tool_surface(), (
        f"ToolSet declares {protocol_methods()} and Tools offers {tool_surface()}. The protocol "
        "is what a second implementation is written against and the surface is what the "
        "capability stamp is computed from; they are the same list or one of them is wrong."
    )


def test_the_extraction_did_not_move_the_capability_stamp() -> None:
    """**The reason `Tools` does not inherit from `ToolSet`, as a test.**

    `tool_surface()` uses `inspect.getmembers(Tools, inspect.isfunction)`, which walks the MRO -
    **inherited functions included**.

    **Inheriting would not move the stamp today, and the guard is still worth having.** That was
    checked by making `Tools` a subclass and running this file: the stamp held, because the
    protocol declares the same five names the class already has. What inheritance would change is
    *what the digest depends on* - a sixth method added to the protocol and implemented nowhere
    would then move `cap:` and restamp fifteen narratives, with no edit to the tool layer at all.
    So the MRO assertion below is not protecting today's digest; it is keeping the agent's surface
    defined in one place, which is the class that implements it.

    Both halves are asserted: the stamp is where it was, and `Tools` satisfies the protocol
    without a base class.
    """
    assert capability_version() == CAPABILITY_AT_EXTRACTION, (
        f"the capability stamp moved to {capability_version()} from {CAPABILITY_AT_EXTRACTION}. "
        "If ToolSet became a base class of Tools, make it structural again; if a tool was really "
        "added or removed, this constant and the narrative stamps move together, deliberately."
    )
    # `issubclass` is unavailable here - a protocol with a data member (`window_policy`) refuses
    # it - and the MRO is the property that actually matters anyway: inheritance is what would
    # put this module inside `tool_surface()`'s walk.
    assert ToolSet not in Tools.__mro__, (
        "Tools inherits from ToolSet. It must satisfy the protocol structurally instead - "
        "inheritance puts the protocol's methods inside the capability digest."
    )
    assert isinstance(Tools(ToolSettings()), ToolSet)


class _StubTools:
    """A second implementation that shares no code with `Tools`.

    **This is the whole point of the extraction, so it is asserted rather than assumed.** It is
    not a mock of `Tools` and does not subclass it; it is the shape a benchmark driver would take
    - different transport, same surface. If this stops satisfying `ToolSet`, the interface has
    stopped being implementable by anything but the class it was extracted from.
    """

    def __init__(self) -> None:
        self.window_policy = WindowPolicy(ToolSettings())

    def promql_query(self, query: str, start: datetime, end: datetime, step: int = 15) -> Any:
        raise NotImplementedError

    def metric_baseline(
        self, service: str, template: Any, start: datetime, end: datetime, step: int = 15
    ) -> Any:
        raise NotImplementedError

    def logql_query(
        self, service: str, start: datetime, end: datetime, limit: int | None = None
    ) -> Any:
        raise NotImplementedError

    def trace_query(
        self, service: str, start: datetime, end: datetime, only_errors: bool = False
    ) -> Any:
        raise NotImplementedError

    def change_history(
        self, service: str, start: datetime, end: datetime, ranking: Any = None
    ) -> Any:
        raise NotImplementedError


def test_something_that_is_not_tools_can_satisfy_the_surface() -> None:
    """The extraction is worth nothing if only `Tools` can satisfy `ToolSet`."""
    stub = _StubTools()

    assert isinstance(stub, ToolSet)
    assert Tools not in type(stub).__mro__


def test_a_specialist_accepts_the_second_implementation() -> None:
    """**The agent layer takes the interface, not the class** - which is the deliverable.

    `Specialist` is where every tool call in the pipeline goes through, and B1 dispatches through
    it too. Constructing one over a stub that shares no code with `Tools` is the check that the
    annotation change reached the thing it was for. The window it derives comes from the stub's
    own policy, so nothing here touches the HTTP implementation.
    """
    from faultline.agents.roles import Specialist

    specialist = Specialist("metrics", _StubTools(), model=None)  # type: ignore[arg-type]
    window = specialist.window(datetime(2026, 9, 3, 12, 0), datetime(2026, 9, 3, 12, 20))

    assert window.start < window.end
