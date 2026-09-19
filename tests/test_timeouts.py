"""T6.7 piece 1 - the timeout audit: every external call is bounded, every bound is smaller than
the budget it runs inside, and the bounds are the ones the design note's table says.

**What listing them found, before any test was written.** `AgentSettings.timeout_seconds` had no
reader: `build_model` constructed both clients without it, so the clients' own 600 s default ran
- equal to the whole wall-clock budget, so one hung call could spend all of it before `Resilient`
consulted the run's deadline (Q33's 6596 s run). The Anthropic SDK retried twice on its own inside
`Resilient`'s four attempts, silently. And the approve route waited 30 s for an executor whose one
command is bounded at 300 s. Three bounds that did not bind; each is a test below now.

The subprocess half of the audit is `tests/test_subprocess_timeouts.py`; this file covers the
HTTP, provider and database paths and the *relations* between bounds, which is what an audit is
for - a value is only right relative to the thing it sits inside.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from faultline import telemetry
from faultline.agents import model as model_module
from faultline.agents.budget import Budget
from faultline.agents.settings import AgentSettings
from faultline.agents.trajectory import orphan_ceiling_seconds
from faultline.api import app as api_app
from faultline.api.executor_client import ExecutorClient
from faultline.api.settings import ApiSettings
from faultline.notify.slack import SlackWebhook
from faultline.orchestrator import consumer
from faultline.orchestrator.settings import OrchestratorSettings
from injector.docker import COMMAND_TIMEOUT_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"


# --- every call is bounded ------------------------------------------------------------------------


def _calls(path: Path, *, attr: str, value: str | None = None) -> list[ast.Call]:
    tree = ast.parse(path.read_text())
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != attr:
            continue
        if value is not None:
            base = node.func.value
            base_name = getattr(base, "attr", None) or getattr(base, "id", None)
            if base_name != value:
                continue
        found.append(node)
    return found


def _has_keyword(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def test_every_urlopen_in_src_carries_a_timeout() -> None:
    """`urllib` blocks forever by default. Every HTTP read the platform or the harness makes -
    telemetry backends, the self-hosted model lane, Slack, the executor, the eval drivers - names
    its bound at the call."""
    unbounded = [
        f"{path.relative_to(SRC)}:{call.lineno}"
        for path in SRC.rglob("*.py")
        for call in _calls(path, attr="urlopen")
        if not _has_keyword(call, "timeout")
    ]
    assert unbounded == [], unbounded


def test_every_anthropic_client_is_built_with_a_timeout_and_without_the_sdk_s_own_retries() -> None:
    """The SDK's `max_retries` defaults to 2 and retries on its own schedule, inside whatever
    loop wraps it. For the agent that loop is `Resilient`, which counts attempts, records
    substitutions and honours the run's deadline; two silent inner retries per attempt make
    twelve network calls of one logical call and record none of them. The judge keeps the SDK's
    retries: it has no outer loop, and a judge that fails a grade on one 529 would lose a scored
    row to a transient - that asymmetry is deliberate and this test names it."""
    agent = SRC / "faultline" / "agents" / "model.py"
    judge = SRC / "evalharness" / "judge.py"

    agent_clients = _calls(agent, attr="Anthropic", value="anthropic")
    assert agent_clients, "the agent no longer constructs an Anthropic client here"
    for call in agent_clients:
        assert _has_keyword(call, "timeout"), f"model.py:{call.lineno}"
        retries = next(kw for kw in call.keywords if kw.arg == "max_retries")
        assert isinstance(retries.value, ast.Constant) and retries.value.value == 0

    for call in _calls(judge, attr="Anthropic", value="anthropic"):
        assert _has_keyword(call, "timeout"), f"judge.py:{call.lineno}"


def _init_default(path: Path, class_name: str, parameter: str) -> object:
    """The default of one `__init__` parameter, read from the source."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            init = next(
                f for f in node.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"
            )
            args = init.args
            names = [a.arg for a in args.args]
            defaults = [None] * (len(names) - len(args.defaults)) + list(args.defaults)
            value = defaults[names.index(parameter)]
            assert isinstance(value, ast.Constant), parameter
            return value.value
    raise AssertionError(f"{class_name} not found in {path}")


# --- the dead setting has a reader ----------------------------------------------------------------


def test_build_model_passes_the_configured_timeout_to_both_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finding. `AgentSettings.timeout_seconds` existed since T3.2 and nothing read it."""
    built: list[tuple[str, float]] = []

    class Fake:
        def __init__(self, name: str, base_url: str | None = None, *, timeout: float) -> None:
            built.append((name, timeout))

    monkeypatch.setattr(
        model_module, "AnthropicModel", lambda name, *, timeout: Fake(name, timeout=timeout)
    )
    monkeypatch.setattr(model_module, "OpenAICompatibleModel", Fake)

    model_module.build_model("m1", timeout=42.0)
    model_module.build_model("m2", provider="openai-compatible", base_url="http://x", timeout=7.0)

    assert built == [("m1", 42.0), ("m2", 7.0)]


def test_the_entry_point_hands_the_setting_to_build_model() -> None:
    """Held in the source, because the entry point builds a real model and cannot run here."""
    source = (SRC / "faultline" / "agents" / "cli.py").read_text()

    assert "timeout=_settings.timeout_seconds" in source


# --- the bounds, and the relations between them ---------------------------------------------------


def test_a_model_call_s_timeout_is_a_fraction_of_the_wall_clock_budget() -> None:
    """One hung call must leave budget for the retry after it. At 600 s (the old value, equal to
    the budget) it did not; `Resilient`'s deadline is checked between attempts, never mid-call,
    so the first attempt alone could outlive the run."""
    settings = AgentSettings()
    budget = Budget()

    assert settings.timeout_seconds == 180.0
    assert settings.timeout_seconds * 3 <= budget.wall_clock_seconds
    # The clients' own defaults agree with the setting, so a caller that forgets to pass it gets
    # the same bound rather than the old 600 s. `AnthropicModel` is never constructed in a test
    # (conftest replaces the name), so its default is read off the source.
    assert _init_default(
        SRC / "faultline" / "agents" / "model.py", "AnthropicModel", "timeout"
    ) == (settings.timeout_seconds)
    assert model_module.OpenAICompatibleModel("m", "http://x")._timeout == settings.timeout_seconds


def test_a_specialist_s_worst_case_tool_time_fits_inside_the_budget() -> None:
    """Twelve tool calls against a backend that times out each one is the row-12 shape - a dead
    Loki. Before the tool breaker (piece 5) that is twelve times `HTTP_TIMEOUT`; it must still
    fit."""
    settings = AgentSettings()

    assert telemetry.HTTP_TIMEOUT == 20
    worst = telemetry.HTTP_TIMEOUT * settings.budget_max_tool_calls_per_specialist
    assert worst < Budget().wall_clock_seconds


def test_the_approve_route_outlives_the_executor_s_command() -> None:
    """The approver's answer must be the executor's, not a client-side timeout over an action
    that then completes. The executor's compose command is bounded at 300 s; the route waits
    that plus thirty for the executor's own bookkeeping."""
    api = ApiSettings()

    assert COMMAND_TIMEOUT_SECONDS == 300
    assert api.executor_timeout_seconds > COMMAND_TIMEOUT_SECONDS
    assert api.executor_timeout_seconds - COMMAND_TIMEOUT_SECONDS <= 60
    assert ExecutorClient("http://x", timeout=api.executor_timeout_seconds)._timeout == 330.0


def test_the_redis_socket_outlives_its_own_blocking_read() -> None:
    """T2.2's invariant, restated in the audit's terms: the socket timeout is the block plus a
    margin, so a blocking read that returns nothing is a legal empty read, not a socket error."""
    settings = OrchestratorSettings()

    assert consumer.SOCKET_TIMEOUT_MARGIN_SECONDS == 5.0
    assert consumer.socket_timeout_for(settings.block_ms) == settings.block_ms / 1000 + 5.0


def test_the_orphan_ceiling_is_the_budget_twice() -> None:
    assert orphan_ceiling_seconds() == 2 * Budget().wall_clock_seconds


def test_the_read_surface_s_connection_has_a_statement_timeout() -> None:
    """A statement that never returns holds a page, a scrape and the approve routes on one
    process. Thirty seconds: longer than any read this surface makes, shorter than the patience
    of the thing waiting."""
    source = (SRC / "faultline" / "api" / "app.py").read_text()

    assert api_app.STATEMENT_TIMEOUT_MS == 30_000
    assert 'options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"' in source


def test_a_slack_post_is_bounded_short() -> None:
    """A notification is a courtesy; five seconds is the most an orchestrator poll should spend
    on one."""
    assert SlackWebhook("https://hooks.example.invalid/x")._timeout == 5.0


def test_the_table_in_the_design_note_names_every_bound_asserted_here() -> None:
    """The design note carries the table a reader will open; this file carries the assertions.
    If a value moves in one and not the other, the table is wrong, which is the worse of the two."""
    note = (REPO_ROOT / "docs" / "design" / "t6.7-reliability-pass.md").read_text()
    for value in ("180 s", "20 s", "330 s", "30 000 ms", "5 s", "600 s", "1200 s", "300 s"):
        assert value in note, value
