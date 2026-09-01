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


HARNESS_VOCABULARY: frozenset[str] = frozenset(
    {
        "inject",
        "injected",
        "injection",
        "injector",
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
"""Terms whose appearance **anywhere** an agent can see is a leak, in any context.

Two kinds, and both reveal something no responder could know. The injector's own vocabulary -
`inject`, `chaos`, `pumba`, `netem`, `rehearsal` - reveals that the incident was manufactured.
The four `fault_class` values are the answer key itself, and `ARTIFACTS.md` forbids handing the
reader the classification for the same reason it forbids opening a narrative with the diagnosis.

`scenario` and `rehearsal` are here because the scenario id would carry the harness's existence
even without the class - and the id itself is banned separately, since ids like
`cart-redis-misconfig` are not in this list but *are* the answer key. See `tests/test_tools.py`.
"""

PROSE_VOCABULARY: frozenset[str] = frozenset({"fault"})
"""Ordinary incident-response English, banned **only where its appearance is evidence of a leak**
(T4.2).

`fault` is the one word on the original list that a real narrative legitimately needs. It is
banned in a *change record* because that text is rendered from the injector's own model, where
"fault" is the injector's word for what it did - so the string appearing there is evidence the
rendering leaked. It is not banned in a narrative, because the scribe composes prose from
validated findings and has no access to the injector's model at all: the same string there is a
responder writing English.

**Found by the guard's first live refusal**, and the sentence is worth quoting because it
contains no banned word at all:

> "No prior value was recorded for the Redis address, so it is genuinely unsettled whether 6380
> replaced a working endpoint or was set for the first time over a default."

The match is a substring one, so `fault` fires on **`default`** - and `faulty`, and
`defaulting`. That sentence is exemplary responder prose about a Redis port, on a scenario whose
whole subject is a port that is not the default, and it cost run 3 its entire narrative
(`docs/evidence/t4.1-first-scored-run/`).
"""

BANNED_VOCABULARY: frozenset[str] = HARNESS_VOCABULARY | PROSE_VOCABULARY
"""Everything banned from **machine-derived** agent-visible text - the change tool's rendered
output surface (ADR-0019).

Unchanged in content and in matching from T2.6: substring matching over text derived from the
answer key, where an over-match costs nothing and a miss costs the experiment. The narrative
guard uses `HARNESS_VOCABULARY` with word boundaries instead; see `faultline.agents.narrative`
and ADR-0019's leak-boundary section for why the two differ.
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


KNOWN_LEAKING_FAULTS: frozenset[str] = frozenset()
"""**Empty since T7.1, and that is the point.** No fault in the catalog leaks its answer.

It held `flag-service-bad-deploy` and `flag-service-crashloop` from ADR-0019 until T7.1. Both
deploy a stub image, and the artifact used to be named after what it does -
`faultline/ffs-stub:broken` and `faultline/ffs-stub:crashloop`. An honest image-change record
has to name the image it deployed, so the **tag was the answer key**: `crashloop` stated the
fault outright, and `faultline/` gave away the harness besides.

The fix was locked behind `ffs_stub_source_digest` until the catalog was re-recorded against
one world, which is exactly what T7.1 does. The variants are now numbered - `ffs-stub:1`
healthy, `:2` and `:3` faulty, over entry points named to match - so a change record can say
which image was deployed without describing what it does. The guard still asserts that this
set is exactly what leaks, so it now asserts that **nothing** does.

The original reasoning is kept below because it is the argument for why a number is enough,
and because a future variant added carelessly would recreate the defect.

Both scenarios were also **blocked** and could never be rehearsed -
`featureflagservice` emits no span metrics, so no fault on it can page
(`evals/scenarios/flag-service-crashloop.yaml:3`). No bundle exists and no scored run can
reach them. That is no longer the load-bearing reason, and it should not be: a leak
tolerated because nobody can reach it is a leak waiting for the scenario to become reachable.
T7.1 took the rename rather than keeping the argument.
"""


"""A table in the platform Postgres, beside incidents.

Decided at implementation (ADR-0019). The product reads a table; the injector's state files
stay the injector's own, and the tool is a query rather than a file read - which matters
because the runtime contract (ADR-0004) requires the agent runtime to be packageable without
Faultline's filesystem.
"""
