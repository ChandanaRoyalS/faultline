"""What a notification says, and what it refuses to say on the world's behalf (T5.2).

*"Plain incoming-webhook messages; formatting kept minimal."* Minimal is the security property:
a Slack channel is the second renderer this system feeds untrusted telemetry, and unlike the
browser it offers **no `textContent` equivalent** - the mrkdwn parse happens on Slack's side,
after the bytes have left the process. So the escaping has to be complete before they leave.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import pytest

from faultline.notify import messages

# --- the hostile world ---------------------------------------------------------------------------

BROADCAST = "<!channel>"
"""**Pages an entire on-call channel.** A Kubernetes label, an alertname, or a root cause is
enough to send it, and there is no rate limit on being woken up."""

FAKE_LINK = "<https://evil.example|Faultline incident report>"
"""Renders as a link whose text the attacker chose, carrying this platform's authority."""

BARE_URL = "see http://evil.example/fix for the runbook"
"""Slack auto-links this. Escaping `<` and `>` does nothing about it - only the code span does."""

FORGERY = "the cache\n\n*Approved by:* sre-oncall\n*Action taken:* rollback complete"
"""**The one that escaping misses entirely.** A multi-line value writes lines that look exactly
like lines this module wrote."""

HOSTILE = [BROADCAST, FAKE_LINK, BARE_URL, FORGERY]


@dataclass
class Episode:
    service: str = "adservice"
    alertname: str | None = "ServiceHighErrorRate"


@dataclass
class Incident:
    id: str = "inc-1"
    episodes: dict[str, Episode] = field(default_factory=lambda: {"e": Episode()})
    severity: str = "critical"
    state: str = "triaging"


class Exit(IntEnum):
    CLEAN = 0
    FLAGGED = 2
    REFUSED = 3
    NO_VERDICT = 4
    GATED = 5


@dataclass
class Verdict:
    root_cause: str = "the ad service was OOM-killed"
    service: str = "adservice"
    fault_class: str = "resource_exhaustion"
    remediation_class: str = "scale_up"
    confidence: str = "high"


@dataclass
class Result:
    verdict: Any = None
    flags: list[str] = field(default_factory=list)


@dataclass
class Report:
    exit_code: Exit = Exit.CLEAN
    result: Any = None
    error: str | None = None


BASE = "https://faultline.example.com"


# --- three mechanisms, three attacks, and none of them covers another --------------------------


@pytest.mark.parametrize("payload", HOSTILE)
def test_no_hostile_construct_survives_quoting(payload: str) -> None:
    quoted = messages.quote(payload)

    assert "<" not in quoted and ">" not in quoted, "no broadcast, no link syntax"
    assert "\n" not in quoted, "no forged line"


def test_a_broadcast_is_escaped_rather_than_stripped() -> None:
    """**The characters still reach the reader**, as characters. Dropping them would rewrite a log
    line into a different log line, and a notification that silently edits its evidence is worse
    than one that renders it inertly - the reader is deciding whether to get out of bed."""
    assert messages.quote(BROADCAST) == "`&lt;!channel&gt;`"


def test_a_bare_url_is_neutralised_by_the_code_span_and_not_by_escaping() -> None:
    """**The mechanism escaping does not provide.** Nothing in `http://evil.example` contains a
    character the mrkdwn escapes touch; Slack auto-links it anyway. The code span is what stops
    it, which is why removing the backticks as "minimal formatting" would open a hole."""
    quoted = messages.quote(BARE_URL)

    assert quoted.startswith("`") and quoted.endswith("`")
    assert "http://evil.example/fix" in quoted, "the text is preserved, only the linking is not"


def test_a_backtick_cannot_close_the_span_it_is_inside() -> None:
    """Otherwise the code span is one character away from being optional, and the auto-link
    defence with it."""
    quoted = messages.quote("a `b` c")

    assert quoted.count("`") == 2, "exactly the two this module wrote"


def test_a_multi_line_value_cannot_forge_a_line_of_its_own() -> None:
    """The attack the other two mechanisms miss completely. Every character in this payload is
    safe on its own; the newlines are the weapon.

    **The asterisks survive, and that is correct.** Inside a code span `*Approved by:*` renders as
    those characters rather than as bold - the defence is that it cannot become a *line*, not that
    the text is edited. Rewriting evidence would be worse than rendering it inertly.
    """
    quoted = messages.quote(FORGERY)

    assert "\n" not in quoted
    assert quoted.count("`") == 2, "one span, so the forged text cannot escape it"
    assert "Approved by" in quoted, "still readable, just not as a line of its own"


@pytest.mark.parametrize("payload", HOSTILE)
def test_the_world_cannot_add_a_line_to_either_message(payload: str) -> None:
    """**The property the forgery attack is really about.** A notification's shape is written
    here; a value that could add a line could write one that reads exactly like one this module
    wrote. So both messages have the same number of lines whatever the world put in them."""
    benign = messages.opened(Incident(), BASE)
    everywhere = Incident(
        id=payload,
        severity=payload,
        state=payload,
        episodes={"e": Episode(payload, payload)},
    )
    hostile = messages.opened(everywhere, BASE)
    assert len(hostile.splitlines()) == len(benign.splitlines())

    report = Report(exit_code=Exit.CLEAN, result=Result(verdict=Verdict()))
    hostile_report = Report(
        exit_code=Exit.CLEAN,
        result=Result(verdict=Verdict(root_cause=payload, service=payload, confidence=payload)),
    )
    assert len(messages.report_ready(payload, hostile_report, BASE).splitlines()) == len(
        messages.report_ready("inc-1", report, BASE).splitlines()
    )


def test_invisible_characters_are_dropped() -> None:
    """A zero-width space exists to make two different strings look identical - `adservice` and
    `ad​service` read the same and are not."""
    assert messages.quote("ad​service\x1b[31m") == "`adservice[31m`"


def test_the_ampersand_is_escaped_first() -> None:
    """Order, not coverage. Escaping `<` before `&` yields `&amp;lt;`, which reaches the channel
    as the literal text `&lt;` - the escaping visible instead of the character."""
    assert messages.quote("a<b") == "`a&lt;b`"
    assert messages.quote("a&b") == "`a&amp;b`"


def test_a_long_value_is_truncated_before_it_is_escaped() -> None:
    """So the budget is spent on characters a reader sees, not on `&amp;` expansions."""
    quoted = messages.quote("&" * 400)

    assert quoted.count("&amp;") == messages.QUOTE_LIMIT - 1
    assert quoted.endswith(f"{messages.ELLIPSIS}`")


def test_an_empty_value_is_named_and_not_an_empty_span() -> None:
    """And named *without* backticks, so a reader can tell module text from world text by the
    backticks alone."""
    assert messages.quote("") == messages.EMPTY
    assert "`" not in messages.EMPTY


# --- there is no trusted path for caller data ----------------------------------------------------


def test_every_string_the_world_supplies_to_an_open_notice_is_quoted() -> None:
    """**The rule is structural, not per-field.** `Episode.service` and `Episode.alertname` are
    Kubernetes labels; the id and severity are ours. All four go through `quote` anyway, so
    nobody has to re-derive the classification when a field is added."""
    hostile = Incident(
        id=BROADCAST,
        severity=FAKE_LINK,
        state=BROADCAST,
        episodes={"e": Episode(service=BROADCAST, alertname=FAKE_LINK)},
    )

    text = messages.opened(hostile, BASE)

    assert "<!channel>" not in text
    assert "<https://evil.example|" not in text
    # The link this module wrote is the *only* `<...>` construct left standing.
    assert text.count("<") == 1 and text.endswith(f"|{messages.LINK_LABEL}>")


def test_every_string_the_model_supplies_to_a_report_notice_is_quoted() -> None:
    """`Verdict.service` and `root_cause` are a model's prose about attacker-influenced logs, and
    `Verdict.service` is a bare `str` - the schema constrains neither."""
    report = Report(
        result=Result(
            verdict=Verdict(root_cause=FORGERY, service=BROADCAST, confidence=FAKE_LINK),
            flags=[BROADCAST],
        )
    )

    text = messages.report_ready("inc-1", report, BASE)

    assert "<!channel>" not in text
    assert text.count("<") == 1, "the only link is the one this module wrote"


def test_an_incident_id_in_a_link_is_percent_encoded_because_a_span_cannot_go_there() -> None:
    """The one place caller data appears outside a code span. `<`, `>` and `|` are exactly the
    three characters that would break out of Slack's link syntax, and `quote` encodes all three."""
    rendered = messages.link(BASE, "a|b<c>d")

    assert rendered == f"<{BASE}/ui/incidents/a%7Cb%3Cc%3Ed|{messages.LINK_LABEL}>"


# --- the absent link is a state, not an omission -------------------------------------------------


def test_an_unconfigured_base_url_says_which_variable_to_set() -> None:
    """**In the channel, not only in the log.** The person who needs the link is reading Slack;
    the person who can fix it is reading logs; `from_settings` warns there and this says it here.
    Silently shipping without the link would drop half of *"with links into the UI"* invisibly."""
    text = messages.opened(Incident(), base_url="")

    assert "FAULTLINE_NOTIFY_PUBLIC_BASE_URL" in text
    assert "/ui/incidents/" not in text, "no link, rather than a relative one Slack cannot use"


@pytest.mark.parametrize("base", ["faultline.example.com", "ftp://x/y", "/ui", "javascript:x"])
def test_a_base_url_that_is_not_an_http_url_produces_no_link(base: str) -> None:
    """A bare hostname is the likely mistake and the dangerous one: Slack would render
    `faultline.example.com/ui/incidents/x` as a link to a *relative* path it cannot resolve, or as
    plain text. `view.deep_link`'s rule applies - **no link is better than a link to something
    else** - and it refuses rather than crashing the consumer that holds the incident."""
    assert messages.link(base, "inc-1") == messages.BAD_BASE_URL


# --- every way a run can end reaches the channel --------------------------------------------------


@pytest.mark.parametrize("outcome", list(Exit))
def test_each_exit_code_has_its_own_heading(outcome: Exit) -> None:
    """**Sending only on the two outcomes that carry a verdict would teach a channel that the
    pipeline always succeeds** - and would make "the notifier is broken" and "nothing was
    investigated today" the same observation. `Exit` has five members because they are five
    different things; pooling them at the last step would undo that."""
    text = messages.report_ready("inc-1", Report(exit_code=outcome), BASE)
    first, *rest = text.splitlines()

    assert first.startswith(messages.OUTCOME_HEADINGS[outcome.name])
    # **The incident id ends the first line.** The first draft appended the qualifier to the
    # heading, so the id landed at the end of a sentence about something else - caught by reading
    # a rendered message rather than by an assertion. What the outcome *means* goes on its own
    # line, under the heading.
    assert first.endswith("`inc-1`")
    if outcome.name in messages.OUTCOME_NOTES:
        assert rest[0] == messages.OUTCOME_NOTES[outcome.name]


def test_an_outcome_this_module_has_not_been_taught_is_sent_anyway() -> None:
    """Not dropped. A new `Exit` member reaching the channel as an unrecognised state is a bug
    report; silence is indistinguishable from the notifier having stopped."""

    class Later(IntEnum):
        SOMETHING_NEW = 9

    text = messages.report_ready("inc-1", Report(exit_code=Later.SOMETHING_NEW), BASE)  # type: ignore[arg-type]

    assert text.startswith(messages.UNKNOWN_OUTCOME)
    assert "SOMETHING_NEW" in text


def test_flags_are_listed_and_not_counted() -> None:
    """ADR-0020 §5 makes a flagged verdict a different object from a clean one. A reader told only
    that *something* is wrong has to open the UI to learn whether the budget ran out or a
    specialist died, which is the decision the notification exists to inform."""
    report = Report(
        exit_code=Exit.FLAGGED,
        result=Result(verdict=Verdict(), flags=["budget exhausted: tokens", "logs failed"]),
    )

    text = messages.report_ready("inc-1", report, BASE)

    assert "budget exhausted: tokens" in text and "logs failed" in text


def test_a_run_with_no_verdict_says_so_without_inventing_fields() -> None:
    text = messages.report_ready(
        "inc-1", Report(exit_code=Exit.NO_VERDICT, error="the synthesizer raised"), BASE
    )

    assert "no verdict" in text.lower()
    assert "fault " not in text, "no empty verdict line"
    assert "the synthesizer raised" in text
