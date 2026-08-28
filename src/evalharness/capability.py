"""`CAPABILITY_VERSION` - what a responder could have seen when a narrative was written (T7.8).

A narrative is only as current as the last capability change. Twice now a claim that was true
when written was silently falsified by capability arriving later, and neither time did anything
catch it:

* **T2.6 built a change log.** Four narratives asserting *"what changed: nothing"* became false
  the day it existed, and stayed wrong for weeks.
* **T7.1 re-recorded every bundle** and did force a narrative rewrite - and the rewrite still
  missed that `ad-memory-squeeze`'s log capture now held sixteen restart attempts, because the
  review compared front matter against the manifest and never opened `logs/`.

`recorded_from` already pins a narrative to a *recording* and breaks when that changes. This
pins it to a *capability set* and breaks when that changes. The two failures are different: a
re-record changes what was seen, a capability change changes what could have been seen.

## What it covers

Three inputs, two of them derived so they cannot drift:

1. **The agent-facing tool surface**, read off `Tools` at runtime - the method names an agent can
   call. Adding, removing or renaming a tool moves this and nothing else does.
2. **`CAPTURE_SET`**, the set of files a bundle holds. A new capture is new evidence a narrative
   could cite.
3. **`TOOL_BEHAVIOUR_REVISION`**, the one hand-maintained input, defined next to the tools it
   describes. It exists because the derivable parts miss changes like two-ended truncation, which
   altered what `logql_query` returns without touching its name.

## What it deliberately does not cover

* **Prompts and contracts.** That is `runtime_version`, and conflating them would make every
  prompt experiment look like a capability change - there have been five, and none of them
  changed what a responder could see.
* **The world.** That is `world.compose_digest`. A re-record is the other trigger and has its own
  guard; this one would double-fire on it and teach people to ignore both.
* **Whether a tool works well.** A tool that returns the wrong answer has the same capability
  version as one that returns the right answer. This says what could be asked, not what came back.
"""

from __future__ import annotations

import hashlib
import inspect
import json

from evalharness.provenance import CAPTURE_SET
from faultline.tools.tools import TOOL_BEHAVIOUR_REVISION, Tools

DIGEST_CHARS = 8


def tool_surface() -> list[str]:
    """The tool names an agent can call, read off the class rather than written down."""
    return sorted(
        name
        for name, _ in inspect.getmembers(Tools, inspect.isfunction)
        if not name.startswith("_")
    )


def capability_inputs() -> dict[str, object]:
    """Everything the version is computed from, so a failure can say what moved."""
    return {
        "tools": tool_surface(),
        "capture_set": CAPTURE_SET,
        "tool_behaviour_revision": TOOL_BEHAVIOUR_REVISION,
    }


def capability_version() -> str:
    """A short digest of the capability set, e.g. `cap:3f9c1a0b`."""
    encoded = json.dumps(capability_inputs(), sort_keys=True, separators=(",", ":")).encode()
    return f"cap:{hashlib.sha256(encoded).hexdigest()[:DIGEST_CHARS]}"


STALE_NARRATIVE_MESSAGE = """{name}: written against {found}, current capability is {current}.

The capability set has moved since this narrative was written, so claims about what a responder
could or could not reach may now be false. This guard checks a STAMP, NOT THE PROSE - passing it
means somebody reviewed the narrative, never that its claims were verified.

What changed:
{changes}

What a review must cover, in this order:
  1. THE CAPTURES, and logs/ first. Both misses so far were here: four narratives said
     "what changed: nothing" after a change log existed, and ad-memory-squeeze said its logs
     held "not even a startup banner" while the capture held sixteen.
  2. Claims that a tool returned nothing, which a tool added since may now answer.
  3. Claims resting on a series' first or last sample - a series disappearing is late by up
     to five minutes (see ARTIFACTS.md).
  4. Front matter LAST. Checking it first is what let T7.1's review pass while the prose was
     wrong.

When the review is done, set `capability: {current}` in the front matter."""
