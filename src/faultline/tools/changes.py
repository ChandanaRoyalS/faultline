"""Change records: the shape, the storage, and the leak boundary (T2.6, ADR-0019).

**Change history is the first tool, not the third.** It is consulted in all nine rehearsed
investigations - more often than metrics or logs - and in five of them the load-bearing
finding is that *nothing changed*. Three scenarios' root causes are a container
resource-limit change and are visible nowhere else (`docs/PLAN.md`, T2.6).

**The uncomfortable part.** This world has no CD system, so the real record of what changed
is the injector's own state - and an agent reading the injector reads the answer key. The
boundary is that the injector emits **generic change records**: who, what, when, the diff, in
the vocabulary an operator would use. No fault class, no scenario id, no injector words.

That is the same discipline `ARTIFACTS.md` already imposes on narrative prose, for the same
reason it gives: open a narrative with "the flag service was deployed with a broken image"
and "you have written an answer key, and retrieval will hand it to the agent verbatim". A
change record naming a fault class does it in one field instead of one sentence.

Enforced by `tests/test_tools.py`, which renders a record for **every** fault in
`injector.catalog` and greps the full output surface. A guard that read the model rather than
the rendered text would be the same mistake as a drift guard comparing `callCount`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

SYSTEM_ACTOR = "platform-automation"
"""Who the change log says made a change.

**An implemented default, and ADR-0019 marks it for decision.** A fixed synthetic operator is
the safe choice: it says "a system did this" without inventing a person, and it cannot
correlate with the answer. A roster of names would make ranking change history a more
realistic task and is one more field that could leak a pattern. Not `faultline`, which is the
one value that would defeat the whole boundary.
"""


class Resource(StrEnum):
    """What kind of thing changed. Operational vocabulary, not fault vocabulary."""

    IMAGE = "image"
    ENVIRONMENT = "environment"
    RESOURCE_LIMITS = "resource_limits"
    CONTAINER = "container"
    CONFIG = "config"


class Action(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"
    REVERTED = "reverted"


class ChangeRecord(BaseModel):
    """One change to one service, as an operator would have recorded it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    service: str
    """Canonical (ADR-0017), so a caller keys on one identity."""

    at: datetime
    actor: str = SYSTEM_ACTOR
    resource: Resource
    action: Action
    summary: str
    before: str | None = None
    after: str | None = None
    """The value matters, not just that something changed: `cart-redis-misconfig`'s
    investigation turns on reading `REDIS_ADDR` set to `redis-cart:6380`."""

    def as_row(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "actor": self.actor,
            "resource": self.resource.value,
            "action": self.action.value,
            "summary": self.summary,
            "before": self.before,
            "after": self.after,
        }


BANNED_VOCABULARY: frozenset[str] = frozenset(
    {
        "inject",
        "injected",
        "injection",
        "injector",
        "fault",
        "faultline",
        "chaos",
        "scenario",
        "rehearsal",
        "rehearse",
        "pumba",
        "netem",
        "bad_deploy",
        "bad_config",
        "dependency_latency",
        "resource_exhaustion",
    }
)
"""Words that must not appear in anything an agent can see.

Fault-class values and injector vocabulary. `scenario` and `rehearsal` are here because the
scenario id would carry the harness's existence even without the class - and the id itself is
banned separately, since ids like `cart-redis-misconfig` are not in this list but *are* the
answer key. See `tests/test_tools.py`.
"""

WORLD_OWNED_TOKENS: frozenset[str] = frozenset({"FAULTLINE_ENABLED_FLAGS"})
"""Exempt, and it is a real leak rather than a false positive.

The feature-flag stub reads `FAULTLINE_ENABLED_FLAGS`, because we wrote the stub (ADR-0006)
and named its variable after ourselves. `product-catalog-flag-failure` changes exactly that
variable, so an honest change record has to name it, and an agent that reads it learns a
system called faultline is involved. It does not learn the answer.

Renaming it is not free: `compose/ffs-stub/` feeds `ffs_stub_source_digest`, so editing it
invalidates every recorded bundle (ADR-0014). It belongs with the other digest-locked changes
queued for T7.1's re-record - see `CATALOG.md`, "The fixes we are not taking, and why".
Exempted here explicitly rather than removed from the banned list, so the exemption is one
line and visible.
"""


KNOWN_LEAKING_FAULTS: frozenset[str] = frozenset(
    {"flag-service-bad-deploy", "flag-service-crashloop"}
)
"""Faults that cannot be rendered as a non-leaking change record, and why that is tolerable.

Found by the guard rather than by review. Both deploy a stub image built for this harness,
and the artifact is named after what it does: `faultline/ffs-stub:broken` and
`faultline/ffs-stub:crashloop`. An honest image-change record has to name the image that was
deployed, and the **tag is the answer key** - `crashloop` states the fault outright.

Not exempted the way `FAULTLINE_ENABLED_FLAGS` is, because that would wave through a token
that gives away the diagnosis rather than merely the harness's existence. Instead the two are
pinned: `tests/test_tools.py` asserts these and only these leak, so a third one is a failure.

Tolerable today for one reason: **both scenarios are blocked** and can never be rehearsed -
`featureflagservice` emits no span metrics, so no fault on it can page
(`evals/scenarios/flag-service-crashloop.yaml:3`). No bundle exists and no scored run can
reach them. If T7.0 or T7.1 makes the flag service observable, these tags have to be renamed
before either scenario is rehearsed - and renaming them edits `compose/ffs-stub/`, which
feeds `ffs_stub_source_digest`, so it belongs with the digest-locked changes queued for
T7.1's re-record.
"""


SCHEMA = """
CREATE TABLE IF NOT EXISTS change_records (
    id        TEXT PRIMARY KEY,
    service   TEXT        NOT NULL,
    at        TIMESTAMPTZ NOT NULL,
    actor     TEXT        NOT NULL,
    resource  TEXT        NOT NULL,
    action    TEXT        NOT NULL,
    summary   TEXT        NOT NULL,
    before    TEXT,
    after     TEXT
);

CREATE INDEX IF NOT EXISTS change_records_service_at_idx ON change_records (service, at);
"""
"""A table in the platform Postgres, beside incidents.

Decided at implementation (ADR-0019). The product reads a table; the injector's state files
stay the injector's own, and the tool is a query rather than a file read - which matters
because the runtime contract (ADR-0004) requires the agent runtime to be packageable without
Faultline's filesystem.
"""
