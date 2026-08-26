"""What produced a trajectory, derived rather than typed (T4.1).

`Trajectory.runtime_version` was a string literal, and it said `"t3.3"` on every trajectory
ever written - including T3.5's, three tasks later. A field whose job is to say what produced a
record, and which says the wrong thing for free, is worse than no field: it answers the
question confidently and wrongly, and the answer looks maintained.

**The stamp is computed from the code the model was actually held to**, so it cannot fall
behind unless that code stops changing:

- the distribution version of `faultline`, and
- a digest over every role's system prompt and the JSON schema of every contract those
  prompts promise the model.

Those two are what determines what a run *is*. Change a prompt and the agent is a different
agent; change a contract and it is answering a different question; and either without the other
is exactly the kind of change a version string usually misses. The digest is order-independent
over a sorted key list so a reordering of the module does not move it.

**Budget bounds are deliberately outside the stamp** (decided T4.7). They are experiment
parameters, not identity: the stamp answers *which agent is this* - the prompts it was given and
the contracts it was held to - while a bound answers *how much was it allowed to spend*. Both
matter, and they are different questions.

Folding bounds in was considered and rejected on two grounds. It would orphan every stamped
figure recorded before the change, since none of those digests covered a bound. And, decisively,
it would make the comparison T4.7 exists to run unexpressible: raising one bound and re-running
is a statement about *the same agent given more room*, and a stamp that moved with the budget
would call those two different agents and hide the very thing being measured.

The obligation the decision creates is that a bound must never be implicit. The run manifest
records all four - not the two a CLI happens to take - and the scored report and every sweep
table print the budget **beside** the stamp. A figure quoted without its bounds is as misleading
as one quoted without its model, and the fix is that both travel, not that both fuse.

**No git, no subprocess.** ADR-0004 keeps benchmark infrastructure out of the product, and a
product that shells out to `git` to describe itself does not work from a wheel. The harness
records the git sha separately in its own run manifest (`evalharness.provenance`), where that
already belongs - so a run is identified by both, from the side that can legitimately know each.
"""

from __future__ import annotations

import hashlib
import json
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pydantic import BaseModel

from faultline.agents.contracts import DispatchPlan, NarrativeDraft, SpecialistFindings, Verdict

_CONTRACTS: tuple[type[BaseModel], ...] = tuple(
    sorted((DispatchPlan, SpecialistFindings, Verdict, NarrativeDraft), key=lambda m: m.__name__)
)
"""Every schema a role prompt promises the model it will be held to."""

DIGEST_CHARS = 12
"""Enough to be unambiguous in a table, short enough to read. Not a security boundary."""


def _package_version() -> str:
    try:
        return version("faultline")
    except PackageNotFoundError:  # pragma: no cover - only when running from a bare tree
        return "0+unknown"


@cache
def prompt_digest() -> str:
    """A digest over the prompts and the contracts, together.

    Imported lazily inside the function because `faultline.agents.roles` imports the tool layer,
    and a stamp that drags the tool layer into every importer of this module would be a
    surprising dependency for a version string.
    """
    from faultline.agents import roles

    parts: dict[str, Any] = {
        "prompts": {
            name: getattr(roles, name)
            for name in sorted(dir(roles))
            if name.endswith("_SYSTEM") and isinstance(getattr(roles, name), str)
        },
        "untrusted_rule": roles.UNTRUSTED_RULE,
        "contracts": {model.__name__: model.model_json_schema() for model in _CONTRACTS},
    }
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:DIGEST_CHARS]


def runtime_version() -> str:
    """The stamp written onto every trajectory, e.g. `faultline/0.1.0+prompts:3f9c1a0b2d4e`."""
    return f"faultline/{_package_version()}+prompts:{prompt_digest()}"
