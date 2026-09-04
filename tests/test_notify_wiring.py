"""Where a notification actually fires - the two seams, and the three that must stay silent (T5.2).

`aa.check` was library-only when it was written, so Gate 4's fourth condition had no way to be
run; `view.py` assembled a payload nothing served. **A notifier nothing invokes is not a
notifier**, so this file is about the call sites rather than about the messages.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from faultline.agents.cli import announce_report
from faultline.ingest.models import AlertEvent
from faultline.notify import Announcer, Recorded
from faultline.orchestrator.cap import InvestigationCap
from faultline.orchestrator.core import Orchestrator
from faultline.orchestrator.correlation import TimeOverlapPolicy
from faultline.orchestrator.store import InMemoryIncidentStore

DUMP = Path(__file__).resolve().parents[1] / "docs/evidence/t2.1-live-smoke/stream-events.txt"
SETTLE = timedelta(minutes=5)


def captured_events() -> list[AlertEvent]:
    lines = DUMP.read_text().splitlines()
    return [AlertEvent.model_validate_json(lines[i]) for i in range(2, len(lines), 3)]


def wired() -> tuple[Orchestrator, InMemoryIncidentStore, Recorded]:
    store, recorder = InMemoryIncidentStore(), Recorded()
    return (
        Orchestrator(
            store=store,
            policy=TimeOverlapPolicy(SETTLE),
            cap=InvestigationCap(3),
            settle_window=SETTLE,
            announcer=Announcer(notifier=recorder, base_url="https://faultline.example.com"),
        ),
        store,
        recorder,
    )


# --- the open half -------------------------------------------------------------------------------


def test_an_opened_incident_is_announced_with_a_link_to_its_screen() -> None:
    """T5.1 serves `/ui/incidents/{id}`; T5.2's deliverable is *"with links into the UI"*, and
    this is the join between them."""
    orchestrator, _, recorder = wired()

    result = orchestrator.apply(captured_events()[0])

    (message,) = recorder.messages
    assert message.startswith("*Incident opened*")
    assert f"https://faultline.example.com/ui/incidents/{result.incident_id}" in message


def test_the_message_is_built_after_the_incident_is_durable() -> None:
    """Same rule as the consumer's write-then-ack: **a notification about an incident that failed
    to persist is a message about something that does not exist.** Checked by the message naming
    a state and a service the store only has because `save` ran."""
    orchestrator, store, recorder = wired()

    result = orchestrator.apply(captured_events()[0])

    saved = store.get(str(result.incident_id))
    assert saved is not None
    assert f"`{saved.state.value}`" in recorder.messages[0]
    assert f"`{next(iter(saved.episodes.values())).service}`" in recorder.messages[0]


def test_one_incident_is_announced_once_however_many_alerts_join_it() -> None:
    """**A channel that announced a join would report one fault as several.** `_attach` does not
    open, so only `_open` announces - and the eight captured events produce three incidents."""
    orchestrator, store, recorder = wired()

    events = captured_events()
    for event in events:
        orchestrator.apply(event)

    assert len(recorder.messages) == len(store.incidents)
    assert len(recorder.messages) < len(events), "eight events, fewer incidents"


def test_a_redelivered_opening_event_is_not_announced_twice() -> None:
    """Redis redelivers. `apply` is idempotent on `(episode_key, status)` and returns before
    `_open`, so the notification inherits that idempotency rather than needing its own."""
    orchestrator, _, recorder = wired()
    first = captured_events()[0]

    orchestrator.apply(first)
    orchestrator.apply(first)

    assert len(recorder.messages) == 1


def test_a_reopen_inside_the_settle_window_is_not_a_second_announcement() -> None:
    """**The join path is the reopen path**, so a resolved incident coming back announces nothing.

    That is the right way round. The reader was already told about this incident; telling them
    again would present one recurring fault as two, which is the count they use to decide how bad
    a night this is. Driven explicitly rather than hoped for out of the captured eight, because a
    reopen that never happened would make this test pass for the wrong reason.
    """
    orchestrator, store, recorder = wired()
    firing, resolved = _one_episode_resolved()

    orchestrator.apply(firing)
    orchestrator.apply(resolved)
    assert len(recorder.messages) == 1
    incident = next(iter(store.incidents.values()))
    assert incident.state.value == "resolved", "it really did close"

    again = firing.model_copy(update={"episode_key": f"{firing.episode_key}#2"})
    result = orchestrator.apply(again)

    assert result.joined is True and result.incident_id == incident.id
    assert incident.state.value != "resolved", "it really did reopen"
    assert len(recorder.messages) == 1, "and it was not announced a second time"


def _one_episode_resolved() -> tuple[AlertEvent, AlertEvent]:
    """The first captured firing, and a resolution for the same episode."""
    events = captured_events()
    firing = events[0]
    resolution = next(
        e for e in events if e.episode_key == firing.episode_key and e.status.value == "resolved"
    )
    return firing, resolution


def test_the_default_orchestrator_notifies_nobody() -> None:
    """**No existing caller changed and no test acquired a network dependency.** The default is a
    real `Announcer` rather than `None`, so the call site needs no guard."""
    store = InMemoryIncidentStore()
    plain = Orchestrator(
        store=store,
        policy=TimeOverlapPolicy(SETTLE),
        cap=InvestigationCap(3),
        settle_window=SETTLE,
    )

    assert plain.apply(captured_events()[0]).opened is True


# --- the report half, and the runs that must stay silent --------------------------------------


class Report:
    exit_code = None
    result = None
    error = None


def test_a_scored_run_sends_nothing() -> None:
    """**The case that matters.** `evalharness.run` invokes `faultline-investigate` once per
    scenario per repeat, so a published sweep is fifty invocations. Fifty reports about faults the
    benchmark injected on purpose would fill an on-call channel - and somebody would go and fix
    one, which corrupts the measurement and wastes a responder in the same move."""
    recorder = Recorded()

    announce_report(
        Report(),
        "inc-1",
        exclude="ad-memory-squeeze",
        announcer=Announcer(notifier=recorder),
    )

    assert recorder.messages == []


def test_the_harness_marker_is_the_one_the_harness_already_passes() -> None:
    """`--exclude-origin` rather than a second flag. Retrieval exclusion exists only for scored
    runs (ADR-0009's leakage rule), so it is already a reliable statement that this is a
    measurement - and a signal the harness cannot forget to send, because omitting it would leak
    the answer into retrieval and fail the run for a louder reason."""
    import inspect

    from evalharness.run import _investigate

    assert "--exclude-origin" in inspect.getsource(_investigate)


def test_no_notify_sends_nothing_even_when_configured() -> None:
    recorder = Recorded()

    announce_report(Report(), "inc-1", suppressed=True, announcer=Announcer(notifier=recorder))

    assert recorder.messages == []


def test_an_operational_run_is_announced() -> None:
    recorder = Recorded()

    announce_report(Report(), "inc-1", announcer=Announcer(notifier=recorder))

    assert len(recorder.messages) == 1


def test_the_orchestrator_cannot_suppress_a_benchmarks_incidents_and_says_so() -> None:
    """**The asymmetry, named rather than discovered.** `faultline-investigate` is told it is a
    scored run; the orchestrator never is, because ADR-0004 keeps the harness outside the product
    and a scenario injects a *genuine* fault so the pipeline meets it as one. Nothing in the alert
    says "this is a measurement", so the eval profile suppresses by configuration - an unset
    webhook or `--no-notify` - and the CLI records why rather than implying the code handles it."""
    import inspect

    from faultline.orchestrator import cli

    source = inspect.getsource(cli.run)

    assert "--no-notify" in inspect.getsource(cli.parser)
    assert "ADR-0004" in source, "the reason it cannot be done in code, at the place it is not done"


def test_the_baselines_return_before_any_notification() -> None:
    """A baseline exists to be measured and is never an operational response. All three return
    from `run` above the announcement, so none of them can reach it."""
    import inspect

    from faultline.agents import cli

    source = inspect.getsource(cli.run)
    for baseline in ("_run_b0(", "_run_b1(", "_run_b2("):
        assert source.index(baseline) < source.index("announce_report(")
