r"""What a notification says - and why none of it is trusted (T5.2).

T5.2's deliverable: *"Webhook notifications on incident open and report ready, with links into
the UI."* Its note: ***"Plain incoming-webhook messages; formatting kept minimal."***

## Minimal formatting is a security property here, not a matter of taste

`faultline.api.view` established that world-produced text reaching a **renderer** is an injection
surface distinct from the same text reaching a *model* (THREAT-MODEL thesis 1). A Slack channel is
the second renderer this system feeds, and it is a worse one than the browser in one specific way:
the browser has `textContent`, which is a route into the DOM that cannot execute markup. **Slack's
incoming webhook has no equivalent.** The `text` field is parsed as mrkdwn, and the parse happens
on Slack's side, after the bytes have left this process.

So `view.py`'s answer - *label the untrusted parts and let the renderer decide* - is not available.
Here this module writes the final bytes, so it can do the stronger thing instead:

> **There is no trusted path for caller data.** The only text in a message that is not escaped and
> quoted is a string literal in this module. Not the root cause, not the service name, not the
> alertname, not the incident id.

That rule costs nothing (a uuid renders the same either way) and removes the step where somebody
has to decide, per field, whether the world could have touched it. `Verdict.service` is a bare
`str` filled in by a model reading attacker-influenced logs; `Episode.service` and
`Episode.alertname` are Kubernetes labels. Classifying those correctly today is easy and staying
correct as fields are added is not, which is the same argument `capability_version()` makes about
introspecting `Tools` rather than maintaining a list.

## Three separate jobs, three separate mechanisms

`quote()` does three things and they defend against three different attacks. Removing any one of
them leaves a hole the other two do not cover:

**Escaping `&`, `<`, `>`** stops `<!channel>` and `<!here>`, which **page an entire on-call
channel** with no rate limit on being woken up, and stops Slack's explicit link syntax, which
renders a link to an address of the attacker's choosing under text of their choosing.

**Wrapping in a code span** - having stripped backticks first, so the span cannot be closed from
inside - stops Slack **auto-linking a bare URL**, which the escaping does not touch at all: a log
line reading `see http://evil.example/fix` becomes a clickable link carrying this platform's
authority. It also stops `*`, `_` and `~` mangling the text, which is the cosmetic half.

**Collapsing whitespace and dropping unprintables** stops a multi-line value **forging the rest of
the message**. A root cause containing `\n\n*Approved by:* sre-oncall` is otherwise
indistinguishable from a line this module wrote.

The third is the one that would have been missed. The first two are about the reader clicking
something; the third is about the reader *believing* something, and a notification whose body can
be authored by the monitored system is a notification that can say anything.

## The link is absolute, and the platform still does not know its own URL

`view.py` made Grafana deep links relative for exactly this reason: *"the platform does not know
its own public URL and guessing one is how a demo link 404s on a stranger's machine."* A Slack
message has no origin to be relative to, so the URL has to come from configuration. When it has
not been configured **the message says so in the channel** rather than quietly shipping without
the half of the deliverable that says *"with links into the UI"* - the operator who needs to set
it is the one reading the message.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote as percent_encode
from urllib.parse import urlsplit

QUOTE_LIMIT = 240
"""How much of one caller-supplied value survives into a message.

A cap rather than a full quotation because a root cause is prose of unbounded length and a
notification is a nudge toward the UI, not a replacement for it. Applied to the text a reader
sees, before escaping, so the limit is not silently spent on `&amp;`.
"""

ELLIPSIS = "…"

MRKDWN_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))
"""Slack's documented escapes, **in this order**: `&` first, or the ampersands introduced by the
other two would be escaped again and `<` would reach the channel as `&amp;lt;`."""

EMPTY = "(none)"
"""Module-authored, so deliberately *not* in a code span - everything quoted is caller data, and a
reader can tell the two apart by the backticks alone."""

UI_PATH = "/ui/incidents/"
"""Where `faultline.api.incidents.page_router` serves T5.1's screen."""

LINK_LABEL = "open in Faultline"

NO_BASE_URL = (
    "(no link: set FAULTLINE_NOTIFY_PUBLIC_BASE_URL to this platform's externally reachable "
    "URL - until then a notification cannot reach the UI)"
)

BAD_BASE_URL = (
    "(no link: FAULTLINE_NOTIFY_PUBLIC_BASE_URL is not an http(s) URL, and a link built from it "
    "would land a reader somewhere other than this incident)"
)

OUTCOME_HEADINGS = {
    "CLEAN": "*Report ready*",
    "FLAGGED": "*Report ready — flagged*",
    "NO_VERDICT": "*No verdict*",
    "GATED": "*Gated before fan-out*",
    "REFUSED": "*Refused*",
}
"""One heading per `faultline.agents.runner.Exit`, matched by **name** rather than by importing it.

Keeping this module a leaf is worth a lookup: `faultline.notify` importing `faultline.agents` would
make the orchestrator's notification path depend on the agent runtime, which needs an optional
extra. Matched by name rather than by integer value so a reordering of the enum is a missing
heading (visible, handled below) rather than a message that confidently says the wrong word.
"""

OUTCOME_NOTES = {
    "FLAGGED": "read the flags before acting on this",
    "NO_VERDICT": "the synthesizer produced nothing that validated; "
    "the trajectory holds everything that ran before it stopped",
    "GATED": "triage declined it as noise or a duplicate - no specialist ran, "
    "and nothing was spent",
    "REFUSED": "the incident was in a state the machine does not investigate",
}
"""A line of its own, under the heading.

**Not appended to the heading.** The first draft read `*Report ready* - flagged, read the flags
before acting `inc-…``, where the incident id lands at the end of a sentence about something else
and stops being the thing the line is about. Caught by rendering a realistic message and reading
it rather than by an assertion - the same way T5.1's washed-out body text was.
"""

UNKNOWN_OUTCOME = "*Investigation finished*"
"""When `Exit` grows a member this module has not been taught. **Not a dropped notification**: the
outcome is quoted beside it, so an unrecognised state reaches the channel as an unrecognised state
rather than as silence, which is indistinguishable from the notifier being broken.
"""


def quote(value: object) -> str:
    """One caller-supplied value, rendered so it can be read and not obeyed.

    **Everything that is not a literal in this module goes through here.** See the module
    docstring for what each of the three steps defends against; the short version is that
    escaping stops `<!channel>`, the code span stops auto-linking, and the whitespace collapse
    stops a value forging the rest of the message.
    """
    text = " ".join(str(value).split())
    # Unprintables survive `split()` - `\x1b` is not whitespace, and neither is a zero-width
    # space, which exists to make two different strings look identical.
    text = "".join(character for character in text if character.isprintable())
    # Before the span is applied, so nothing inside it can close it early.
    text = text.replace("`", "'")
    if len(text) > QUOTE_LIMIT:
        text = text[: QUOTE_LIMIT - 1].rstrip() + ELLIPSIS
    for character, entity in MRKDWN_ESCAPES:
        text = text.replace(character, entity)
    return f"`{text}`" if text else EMPTY


def quoted_list(values: list[str]) -> str:
    return ", ".join(quote(value) for value in values) if values else EMPTY


def link(base_url: str, incident_id: str) -> str:
    """A link to T5.1's screen for this incident, or a marked absence naming what to configure.

    The incident id is percent-encoded rather than quoted: **a code span cannot exist inside a
    link target**, so the one place caller data has to appear unquoted is the one place it is
    encoded instead. `urllib.parse.quote` encodes `<`, `>` and `|`, which are exactly the three
    characters that would break out of Slack's `<url|label>` syntax.
    """
    base = base_url.strip().rstrip("/")
    if not base:
        return NO_BASE_URL
    parts = urlsplit(base)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return BAD_BASE_URL
    return f"<{base}{UI_PATH}{percent_encode(str(incident_id), safe='')}|{LINK_LABEL}>"


def opened(incident: Any, base_url: str = "") -> str:
    """*"Notifications on incident open"* - what an on-call reader needs to decide to look.

    Duck-typed over `Incident` the way `faultline.api.view` is over its inputs: the seam this
    module needs is four attribute reads, and depending on the orchestrator's dataclass would make
    a notifier that cannot be exercised without one.
    """
    episodes = list(getattr(incident, "episodes", {}).values())
    services = sorted({e.service for e in episodes if getattr(e, "service", None)})
    alertnames = sorted({e.alertname for e in episodes if getattr(e, "alertname", None)})
    severity = getattr(incident, "severity", "")
    return "\n".join(
        [
            f"*Incident opened* {quote(getattr(incident, 'id', ''))}",
            f"severity {quote(getattr(severity, 'value', severity))} · "
            f"{len(episodes)} episode(s) · state "
            f"{quote(getattr(getattr(incident, 'state', ''), 'value', ''))}",
            f"services: {quoted_list(services)}",
            f"alerts: {quoted_list(alertnames)}",
            link(base_url, str(getattr(incident, "id", ""))),
        ]
    )


def report_ready(incident_id: str, report: Any, base_url: str = "") -> str:
    """*"Notifications on ... report ready"*, for every way a run can end.

    **Including the ways that produce no report.** T5.2 names one event and `Exit` has five
    outcomes; sending only on the two that carry a verdict would teach a channel that the pipeline
    always succeeds, and would make "the notifier is broken" and "nothing was investigated today"
    the same observation. `runner.Exit` exists precisely because those outcomes are different
    things, and a notification that pooled them would undo that distinction at the last step.
    """
    outcome = getattr(getattr(report, "exit_code", None), "name", "")
    heading = OUTCOME_HEADINGS.get(outcome)
    lines = [
        f"{heading or UNKNOWN_OUTCOME} {quote(incident_id)}"
        + ("" if heading else f" - outcome {quote(outcome or 'unnamed')}")
    ]
    if note := OUTCOME_NOTES.get(outcome):
        lines.append(note)

    result = getattr(report, "result", None)
    verdict = getattr(result, "verdict", None) if result is not None else None
    if verdict is not None:
        lines += [
            f"fault {quote(getattr(verdict, 'fault_class', ''))} · "
            f"fix {quote(getattr(verdict, 'remediation_class', ''))} · "
            f"service {quote(getattr(verdict, 'service', ''))} · "
            f"confidence {quote(getattr(verdict, 'confidence', ''))}",
            f"root cause: {quote(getattr(verdict, 'root_cause', ''))}",
        ]

    error = getattr(report, "error", None)
    if error:
        lines.append(f"error: {quote(error)}")

    flags = list(getattr(result, "flags", []) or []) if result is not None else []
    if flags:
        # Listed rather than counted. ADR-0020 §5 makes a flagged verdict a different object from
        # a clean one, and a reader who has to open the UI to learn *which* flag has been told
        # only that something is wrong.
        lines.append(f"flags: {quoted_list([str(flag) for flag in flags])}")

    lines.append(link(base_url, incident_id))
    return "\n".join(lines)
