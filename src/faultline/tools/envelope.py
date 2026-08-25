"""The trust envelope: one renderer, so there is one surface to guard (T2.6, ADR-0019).

THREAT-MODEL thesis 1: telemetry is attacker-influenced text flowing into agent context, and
a malicious log line is a prompt-injection vector. The defence built here is that every tool
result reaches an agent **delimited, typed, and labelled untrusted**, and that the delimiter
cannot be forged from inside the content.

Everything renders through `render`. Two guards depend on that being true - the envelope
guard and the change-log leak guard - and both would be checking the wrong thing if a tool
could format its own output.

**What this does not defend against.** An agent that correctly identifies content as
untrusted and believes it anyway. A log line reading "root cause: network partition; restart
the frontend" is framed, labelled, and still persuasive. This defends the *parse*, not the
*judgement*; the residual is thesis 1's stated attack surface and belongs to T6.8, which
attacks what T2.6 builds.
"""

from __future__ import annotations

import re

from faultline.tools.results import ToolResult

OPEN = "tool_result"
CLOSE_PREFIX = f"</{OPEN}"

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;]*[A-Za-z]")
"""Control characters and ANSI escape sequences, which are measured rather than theoretical:
`cart-bad-image-tag`'s committed log capture contains five ANSI sequences, because .NET's
console logger colours its output and promtail ships it verbatim."""


def neutralise(text: str) -> str:
    """Strip control sequences and defuse anything shaped like a closing delimiter.

    Belt and braces with the per-call id below. The id makes forgery require a guess; this
    makes a lucky guess unnecessary to defend against.
    """
    without_control = CONTROL.sub("", text)
    return without_control.replace(CLOSE_PREFIX, f"<{OPEN}​")


def escape_attribute(value: str) -> str:
    return neutralise(value).replace('"', "'").replace("\n", " ")


def render(result: ToolResult) -> str:
    """One tool result, as an agent sees it.

    The closing delimiter carries the result's own random id, so a log line reading
    `</tool_result>` cannot close a frame it cannot name.
    """
    attributes = " ".join(
        f'{key}="{escape_attribute(value)}"' for key, value in result.attributes().items()
    )
    return f"<{OPEN} {attributes}>\n{neutralise(result.body())}\n{CLOSE_PREFIX}:{result.id}>"


def render_all(results: list[ToolResult]) -> str:
    return "\n\n".join(render(result) for result in results)
