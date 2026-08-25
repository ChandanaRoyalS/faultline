"""Turning an injection into an ordinary change record (T2.6, ADR-0019).

The injector is the only thing in this world that changes anything, so it is the change log.
That is the awkward fact ADR-0019 works around: **an agent reading the injector reads the
answer key**, so what gets written is a record an operator would have written - who, what,
when, the diff - with none of this module's own vocabulary in it.

The translation is the whole file. Every `FaultDefinition` in `injector.catalog` becomes a
resource, an action, a plain summary, and a before/after pair.
`tests/test_tools.py::test_no_change_record_leaks_the_answer_key` renders one for every fault
and greps the output.

Direction of the import: this module imports the record shape from `faultline.tools` rather
than defining its own, because the product owns its read contract and two copies of the
schema would drift the first time a field moved. `injector.catalog` already imports
`FaultClass` from `evalharness.scenario` for the same reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from faultline.tools.changes import Action, ChangeRecord, Resource
from injector.models import FaultDefinition
from injector.world import canonical_service


def _stamp() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _service_of(definition: FaultDefinition) -> str:
    return canonical_service(definition.target)


def describe(definition: FaultDefinition) -> tuple[Resource, str, str | None, str | None]:
    """(resource, summary, before, after) in operational terms, for this definition.

    Deliberately keyed on the **parameters**, not on the fault class. Keying on the class
    would put `resource_exhaustion` one refactor away from the output surface, and the class
    is the answer to the question the agent is being asked.
    """
    params = definition.params
    if "image" in params:
        return (
            Resource.IMAGE,
            f"image reference updated on {definition.target}",
            None,
            str(params["image"]),
        )
    if "env_var" in params:
        variable = str(params["env_var"])
        return (
            Resource.ENVIRONMENT,
            f"{variable} updated on {definition.target}",
            None,
            f"{variable}={params['value']}",
        )
    if "memory" in params:
        return (
            Resource.RESOURCE_LIMITS,
            f"memory limit lowered on {definition.target}",
            None,
            f"memory={params['memory']}",
        )
    if "cpus" in params:
        return (
            Resource.RESOURCE_LIMITS,
            f"cpu quota lowered on {definition.target}",
            None,
            f"cpus={params['cpus']}",
        )
    if "delay_ms" in params:
        # The sidecar case. A container appearing on a service's network namespace is an
        # ordinary infrastructure change, which is how ADR-0019 predicts change history
        # covers the two dependency_latency narratives that appeared to need `docker ps`.
        interface = params.get("interface", "eth0")
        return (
            Resource.CONTAINER,
            f"traffic-shaping container attached to {definition.target}'s network namespace",
            None,
            f"{interface} delay={params['delay_ms']}ms jitter={params.get('jitter_ms', 0)}ms",
        )
    return (Resource.CONFIG, f"configuration updated on {definition.target}", None, None)


def record_for_start(definition: FaultDefinition, at: datetime | None = None) -> ChangeRecord:
    resource, summary, before, after = describe(definition)
    return ChangeRecord(
        id=str(uuid.uuid4()),
        service=_service_of(definition),
        at=at or _stamp(),
        resource=resource,
        action=Action.CREATED if resource is Resource.CONTAINER else Action.UPDATED,
        summary=summary,
        before=before,
        after=after,
    )


def record_for_stop(definition: FaultDefinition, at: datetime | None = None) -> ChangeRecord:
    """The reversal. An operator undoing a change records the undo."""
    resource, summary, _, after = describe(definition)
    reverted = (
        f"traffic-shaping container removed from {definition.target}'s network namespace"
        if resource is Resource.CONTAINER
        else summary.replace("updated", "reverted").replace("lowered", "restored")
    )
    return ChangeRecord(
        id=str(uuid.uuid4()),
        service=_service_of(definition),
        at=at or _stamp(),
        resource=resource,
        action=Action.REMOVED if resource is Resource.CONTAINER else Action.REVERTED,
        summary=reverted,
        before=after,
        after=None,
    )
