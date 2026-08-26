"""Rendering the incident narrative, and refusing to render a leaking one (T3.4, ADR-0020 §4).

**This is where thesis 1 is cut.** T2.4b seeds the past-incident corpus from exactly this kind
of record, so a hostile log line copied into one is retrieved next month as institutional
knowledge with its trust label gone. Two mechanisms, and the first is the one that does the
work:

1. **Quotes are resolved from the store, never from the model's context.** The scribe emits
   `result_id`s; this module looks each one up and embeds what was actually stored. A
   `result_id` the store does not hold is a refusal, not a blank - a citation nobody can
   resolve is exactly what a fabricated one looks like.
2. **The leak guard runs over the finished text.** The same `BANNED_VOCABULARY` and
   `WORLD_OWNED_TOKENS` the change-record guard uses (T2.6), because a narrative naming a fault
   class hands the reader the answer key in one word, the way `ARTIFACTS.md` says a narrative
   opening with the root cause does in one sentence.
"""

from __future__ import annotations

from faultline.agents.contracts import NarrativeDraft
from faultline.agents.trajectory import TrajectoryStore
from faultline.tools.changes import BANNED_VOCABULARY, WORLD_OWNED_TOKENS

QUOTE_LINES = 6
"""How much of a stored envelope a citation shows. Enough to be evidence, short enough that a
narrative is not a transcript."""


class UnknownCitationError(RuntimeError):
    """A `result_id` the trajectory store does not hold.

    Refused rather than dropped: a citation that cannot be resolved is indistinguishable from
    one that was invented, and silently omitting it would turn a fabricated reference into a
    paragraph with no reference at all - which reads as unsupported prose rather than as an
    error.
    """


class NarrativeLeakError(RuntimeError):
    """Banned vocabulary in the finished narrative. **Fails the render.**"""


def leaked_words(text: str) -> list[str]:
    """Banned vocabulary present in `text`, with the world's own tokens exempted.

    `FAULTLINE_ENABLED_FLAGS` is the world's variable name and leaks this harness's existence
    rather than the answer (T2.6); it is exempt here for the same reason and no other token is.
    """
    scrubbed = text
    for token in WORLD_OWNED_TOKENS:
        scrubbed = scrubbed.replace(token, "")
    lowered = scrubbed.lower()
    return sorted(word for word in BANNED_VOCABULARY if word in lowered)


def render(draft: NarrativeDraft, store: TrajectoryStore) -> str:
    """The finished narrative, with every citation resolved against stored evidence."""
    lines = [f"# {draft.title}", ""]
    for section in draft.sections:
        lines += [f"## {section.heading}", "", section.body, ""]
        for result_id in section.citations:
            envelope = store.envelope(result_id)
            if envelope is None:
                raise UnknownCitationError(
                    f"{result_id} is not in the trajectory store. A narrative may only quote "
                    "evidence that was recorded, and an unresolvable citation is what a "
                    "fabricated one looks like."
                )
            excerpt = "\n".join(envelope.splitlines()[:QUOTE_LINES])
            lines += [f"> Evidence `{result_id}`:", "", "```", excerpt, "```", ""]

    narrative = "\n".join(lines).rstrip() + "\n"
    leaked = leaked_words(narrative)
    if leaked:
        raise NarrativeLeakError(
            f"the narrative mentions {leaked}. This text becomes corpus material at T2.4b, so "
            "it is written from the responder's chair - what was visible, not what we know "
            "because we caused it (ADR-0020 §4, evals/scenarios/ARTIFACTS.md)."
        )
    return narrative
