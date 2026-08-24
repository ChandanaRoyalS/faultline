"""The global investigation concurrency cap, and what overflow does (T2.2, ADR-0001/0016).

ADR-0001 committed to "a global investigation concurrency cap with severity-ordered
overflow" and named no number, no severity source and no queue discipline. ADR-0016 supplies
all three. This is the mechanism.

**Found while implementing, and stronger than ADR-0016 states.** The ADR records that the
cap "cannot be exercised by the eval catalog", because `require_no_active_faults` means one
incident at a time. Implementing it showed the reach is wider than the catalog: with
`TimeOverlapPolicy`, a firing episode joins *any* live incident, so at most one incident is
ever non-terminal and **the cap is unreachable by construction, not merely untested**. It
becomes reachable the moment a policy can decline to correlate - which is T2.4's
`DependencyPolicy`. The cap and the graph-based policy are coupled, and neither ADR-0016 nor
ADR-0001 says so. `tests/test_orchestrator.py` therefore exercises admission through a
policy that always declines, which is that shape.

**What the severity ordering is currently worth.** `compose/prometheus/alert-rules.yml`
defines exactly two severities, and the catalog's scenarios alert almost entirely
`ServiceHighErrorRate` with one `ServiceNoTraffic` - both `critical`. A severity-ordered
queue over entries that nearly all share one severity is FIFO with extra steps. It is
implemented because ADR-0001 committed to it and it costs nothing, not because it currently
discriminates, and it should not be reported as working prioritisation until something
measures it doing work.
"""

from __future__ import annotations

from datetime import datetime

from faultline.orchestrator.models import Incident


class InvestigationCap:
    """Admission control. Holds no state - the store knows who is investigating."""

    def __init__(self, max_concurrent: int) -> None:
        self.max_concurrent = max_concurrent

    def has_room(self, active: int) -> bool:
        return active < self.max_concurrent

    @staticmethod
    def next_admission(queued: list[Incident]) -> Incident | None:
        """Highest severity first, oldest first within a severity.

        Strict priority. It can starve a `warning` under sustained `critical` load, and the
        alternative - aging, where a queued incident's priority rises with its wait - is a
        mechanism whose tuning would have no evidence behind it. ADR-0016 chose strict
        priority because the cap is a small integer on a single-operator system and
        sustained overload has never been observed. Revisit when the queue is ever seen
        non-empty for a sustained period.
        """
        if not queued:
            return None
        return min(
            queued,
            key=lambda i: (-i.severity.rank, i.opened_at or datetime.max),
        )
