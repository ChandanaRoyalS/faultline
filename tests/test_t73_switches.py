"""T7.3's switches, E2 to E9 (`PREREGISTRATION-T7.3.md`, Addendum 1).

**Every switch defaults to today's behaviour**, and that half is what these tests hold hardest: the
standing pipeline must take exactly the path it took before the switch existed. The other half is
that each switch, set, does the one thing its arm registered.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from faultline.agents.contracts import Finding, RuledOut, SpecialistFindings
from faultline.agents.model import ModelRequest, ModelResponse
from faultline.agents.roles import (
    PUSH_BRIEFING_TOKENS,
    Planner,
    SpecialistRun,
    Synthesizer,
    build_specialists,
    pushed_sections,
)
from faultline.agents.triage import Triage
from faultline.context.catalog import ServiceCatalog
from faultline.context.settings import ContextSettings
from faultline.orchestrator.models import Episode, Incident, Severity
from faultline.tools import envelope as envelope_renderer
from faultline.tools.results import LogLine, LogResult, Window

AT = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)

SWITCH_ENV = (
    "FAULTLINE_CONTEXT_HOP_RADIUS",
    "FAULTLINE_CONTEXT_RETRIEVAL_MODE",
    "FAULTLINE_CONTEXT_RERANK_MODEL",
    "FAULTLINE_CONTEXT_RERANK_CANDIDATES",
    "FAULTLINE_CONTEXT_RERANK_REVISION",
    "FAULTLINE_AGENT_EVIDENCE_MODE",
    "FAULTLINE_AGENT_ROLE_MODELS",
    "FAULTLINE_AGENT_NO_CORPUS",
    "FAULTLINE_AGENT_BRIEFING_MODE",
    "FAULTLINE_AGENT_BUDGET_BRIEFING_TOKENS",
    "FAULTLINE_TOOLS_DEFAULT_LOOKBACK_SECONDS",
    "FAULTLINE_TOOLS_CHANGE_LOOKBACK_SECONDS",
    "FAULTLINE_TOOLS_MAX_WINDOW_SECONDS",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in SWITCH_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# --- the record: ablation_config, the fingerprint, the standing pipeline ----------------------


def test_the_standing_pipeline_records_no_switch(clean_env: pytest.MonkeyPatch) -> None:
    from evalharness.run import ablation_config

    assert ablation_config() == {}


@pytest.mark.parametrize(
    ("env", "value", "key"),
    [
        ("FAULTLINE_CONTEXT_HOP_RADIUS", "99", "hop_radius"),
        ("FAULTLINE_AGENT_EVIDENCE_MODE", "raw", "evidence_mode"),
        (
            "FAULTLINE_AGENT_ROLE_MODELS",
            json.dumps({"metrics": "claude-sonnet-4-6"}),
            "role_models",
        ),
        ("FAULTLINE_AGENT_NO_CORPUS", "1", "no_corpus"),
        ("FAULTLINE_CONTEXT_RETRIEVAL_MODE", "dense", "retrieval_mode"),
        ("FAULTLINE_CONTEXT_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2", "rerank_model"),
        ("FAULTLINE_TOOLS_DEFAULT_LOOKBACK_SECONDS", str(7 * 86400), "default_lookback_seconds"),
        ("FAULTLINE_AGENT_BRIEFING_MODE", "push", "briefing_mode"),
    ],
)
def test_each_arm_s_switch_is_recorded(
    clean_env: pytest.MonkeyPatch, env: str, value: str, key: str
) -> None:
    from evalharness.run import ablation_config

    clean_env.setenv(env, value)

    assert list(ablation_config()) == [key]


def test_a_pool_size_without_a_reranker_is_not_an_arm(clean_env: pytest.MonkeyPatch) -> None:
    from evalharness.run import ablation_config

    clean_env.setenv("FAULTLINE_CONTEXT_RERANK_CANDIDATES", "40")
    clean_env.setenv("FAULTLINE_CONTEXT_RERANK_REVISION", "abc123")
    assert ablation_config() == {}


def test_the_rerank_arm_records_its_pinned_revision(clean_env: pytest.MonkeyPatch) -> None:
    from evalharness.run import ablation_config

    clean_env.setenv("FAULTLINE_CONTEXT_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    clean_env.setenv("FAULTLINE_CONTEXT_RERANK_REVISION", "abc123")
    assert ablation_config() == {
        "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "rerank_revision": "abc123",
    }


def _manifest(**extra: Any) -> dict[str, Any]:
    return {"baseline": None, "models": {"default": "claude-opus-5"}, "ablation": [], **extra}


def test_the_standing_pipeline_keeps_the_fingerprint_it_had_before_the_key() -> None:
    from evalharness.evaldb import fingerprint

    before = fingerprint(_manifest())
    standing = fingerprint(_manifest(ablation_config={}))
    arm = fingerprint(_manifest(ablation_config={"evidence_mode": "raw"}))

    assert standing.fingerprint == before.fingerprint
    assert "ablation_config" not in standing.missing
    assert arm.fingerprint != before.fingerprint


def test_an_ablation_arm_is_never_the_standing_pipeline() -> None:
    from evalharness.run import STANDING_PIPELINE_KEYS, is_standing_pipeline

    assert "ablation_config" in STANDING_PIPELINE_KEYS
    assert is_standing_pipeline(_manifest(ablation_config={})) == (True, "")
    standing, why = is_standing_pipeline(_manifest(ablation_config={"briefing_mode": "push"}))
    assert not standing
    assert "briefing_mode" in why


# --- E4: per-role models ----------------------------------------------------------------------


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name

    def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover - unused
        raise AssertionError


def test_build_specialists_shares_one_model_unless_told_otherwise() -> None:
    from faultline.tools.changelog import InMemoryChangeLog
    from faultline.tools.settings import ToolSettings
    from faultline.tools.tools import Tools

    tools = Tools(ToolSettings(), changes=InMemoryChangeLog())
    opus, sonnet = _Named("claude-opus-5"), _Named("claude-sonnet-4-6")

    standing = build_specialists(tools, opus)
    tiered = build_specialists(tools, opus, models={name: sonnet for name in standing})

    assert {s._model.name for s in standing.values()} == {"claude-opus-5"}
    assert {s._model.name for s in tiered.values()} == {"claude-sonnet-4-6"}


def test_the_cli_builds_each_role_from_its_own_model_setting() -> None:
    """`role_models` was recorded and read by nothing (found 2026-10-04): the CLI built one model
    and handed it to every role."""
    import inspect

    from faultline.agents import cli

    source = inspect.getsource(cli.run)

    for role in ('"planner"', '"synthesizer"', '"scribe"', '"proposer"', "Triager.ROLE"):
        assert f"role_model({role})" in source
    assert "models={name: role_model(name) for name in SPECIALISTS}" in source
    assert "settings.no_corpus" not in source, "E5 is the harness's pass-through, not a setting"
    assert "briefing_mode=briefing_mode" in source.split("triager=(")[1]


def test_e5_is_the_harness_passing_the_existing_flag(
    clean_env: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from evalharness import run

    seen: list[list[str]] = []
    clean_env.setattr(run, "_sh", lambda cmd: seen.append(cmd) or (0, ""))
    args = SimpleNamespace(
        max_tool_calls=4,
        max_tokens=1000,
        max_tool_calls_changes=None,
        baseline=None,
        without=[],
        postgres_dsn=None,
        exclude_same_class=False,
    )
    clean_env.setattr(run, "exclusion_for", lambda scenario, a: ["scenario:x"])
    from pathlib import Path

    run._investigate("inc", "x", Path("out.json"), args)
    clean_env.setenv("FAULTLINE_AGENT_NO_CORPUS", "1")
    run._investigate("inc", "x", Path("out.json"), args)

    assert "--no-corpus" not in seen[0]
    assert seen[1][-1] == "--no-corpus"


# --- E3: raw context --------------------------------------------------------------------------


def _run(text: str = "could not reach redis-cart:6380 " * 40) -> SpecialistRun:
    result = LogResult(
        selector='{service="cart"}',
        window=Window(start=AT - timedelta(minutes=30), end=AT),
        lines=[LogLine(at=AT, line=text) for _ in range(3)],
    )
    return SpecialistRun(
        specialist="logs",
        service="cart",
        question="what do the logs say",
        result=result,
        envelope=envelope_renderer.render(result),
        findings=SpecialistFindings(
            found=[
                Finding(
                    statement="cart cannot reach its store", result_id=result.id, confidence="high"
                )
            ],
            ruled_out=[RuledOut(hypothesis="cart is idle", result_id=result.id, why="it logs")],
        ),
        response=ModelResponse(text="", model="m", input_tokens=1, output_tokens=1),
        attempts=1,
    )


def _triage() -> Any:
    incident = Incident(opened_at=AT, last_activity_at=AT)
    incident.episodes["e0"] = Episode(
        episode_key="e0",
        fingerprint="f0",
        service="cart",
        severity=Severity.CRITICAL,
        alertname="ServiceHighErrorRate",
        starts_at=AT,
        attached_at=AT,
    )
    return Triage(ServiceCatalog.from_snapshot(), ContextSettings().hop_radius).run(incident)


def _board(sections: list[Any]) -> list[str]:
    return next(s for s in sections if s.name == "evidence-board").lines


def test_the_board_is_unchanged_unless_raw_is_asked_for() -> None:
    run = _run()
    default = Synthesizer.sections(_triage(), [run], [], [])
    board = Synthesizer.sections(_triage(), [run], [], [], "board")

    assert _board(default) == _board(board)
    assert run.envelope not in "\n".join(_board(default))


def test_raw_context_gives_the_synthesizer_every_whole_envelope() -> None:
    run = _run()
    raw = _board(Synthesizer.sections(_triage(), [run], [], [], "raw"))

    assert run.envelope in raw
    assert len("\n".join(raw)) > len(
        "\n".join(_board(Synthesizer.sections(_triage(), [run], [], [])))
    )


# --- E9: push-everything ----------------------------------------------------------------------


class _Scripted:
    def __init__(self) -> None:
        self.name = "scripted"
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        plan = {
            "dispatches": [
                {
                    "specialist": "logs",
                    "service": "cartservice",
                    "question": "why",
                    "reason": "alerting",
                }
            ],
            "skipped": [],
            "rationale": "because",
        }
        return ModelResponse(
            text=json.dumps(plan), model="scripted", input_tokens=1, output_tokens=1
        )


def test_the_planner_s_brief_is_unchanged_in_disclosure_mode() -> None:
    standing, explicit = Planner(_Scripted()), Planner(_Scripted(), briefing_mode="disclosure")
    standing.plan(_triage())
    explicit.plan(_triage())

    assert standing.briefing is not None and explicit.briefing is not None
    assert standing.briefing.text == explicit.briefing.text
    assert "push-runbooks" not in standing.briefing.text


def test_push_gives_the_planner_the_allowlist_and_every_runbook_with_no_budget() -> None:
    planner = Planner(_Scripted(), briefing_mode="push", briefing_tokens=10)
    planner.plan(_triage())

    assert planner.briefing is not None
    text = planner.briefing.text
    assert "Actions this system is permitted to take:" in text
    assert "Every class and action runbook:" in text
    assert "class-process-freeze" in text and "action-restart-service" in text
    assert not planner.briefing.dropped, "push mode drops nothing"


class _Empty:
    """A model whose every reply fails the schema. The brief is assembled before the model is
    asked, so a role's `briefing` can be read after the refusal."""

    name = "empty"

    def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(text="{}", model="empty", input_tokens=1, output_tokens=1)


def _brief_of(call: Any, role: Any) -> str:
    from faultline.agents.roles import SchemaValidationError

    with pytest.raises(SchemaValidationError):
        call()
    assert role.briefing is not None
    assert not role.briefing.dropped
    return str(role.briefing.text)


def test_push_reaches_triage_and_the_scribe_and_disclosure_leaves_them_as_they_were() -> None:
    """ "Every role's brief" (Addendum 1, E9): triage and the scribe are briefed too."""
    from faultline.agents.contracts import Verdict
    from faultline.agents.roles import Scribe, Triager

    triage = _triage()
    verdict = Verdict.model_validate(
        {
            "root_cause": "cart is frozen",
            "service": "cartservice",
            "fault_class": "process_freeze",
            "remediation_class": "restart",
            "confidence": "medium",
            "evidence": [],
            "reasoning": "silent",
            "open_questions": [],
            "alternatives": [],
        }
    )
    texts: dict[str, dict[str, str]] = {}
    for mode in ("disclosure", "push"):
        triager = Triager(_Empty(), briefing_mode=mode)
        scribe = Scribe(_Empty(), briefing_mode=mode)
        texts[mode] = {
            "triage": _brief_of(lambda t=triager: t.judge(triage, []), triager),
            "scribe": _brief_of(
                lambda s=scribe: s.draft(triage, [], verdict, retrieved=["incident-7 / cause"]),
                scribe,
            ),
        }
    standing_triager, standing_scribe = Triager(_Empty()), Scribe(_Empty())
    assert (
        _brief_of(lambda: standing_triager.judge(triage, []), standing_triager)
        == (texts["disclosure"]["triage"])
    )
    assert (
        _brief_of(lambda: standing_scribe.draft(triage, [], verdict), standing_scribe)
        == (texts["disclosure"]["scribe"])
    )
    for role in ("triage", "scribe"):
        assert "Every class and action runbook:" not in texts["disclosure"][role]
        assert "Every class and action runbook:" in texts["push"][role]
        assert "Actions this system is permitted to take:" in texts["push"][role]
    assert "incident-7 / cause" in texts["push"]["scribe"]
    assert "incident-7 / cause" not in texts["disclosure"]["scribe"]


def test_the_scribe_is_handed_the_retrieved_incidents() -> None:
    import inspect

    from faultline.agents import investigation

    assert "retrieved=result.retrieved," in inspect.getsource(investigation)


def test_the_pushed_sections_are_the_three_roles_union() -> None:
    names = [s.name for s in pushed_sections(allowlist=True, runbooks=True, retrieved=["a past"])]

    assert names == ["push-allowlist", "push-runbooks", "push-past-incidents"]
    assert PUSH_BRIEFING_TOKENS >= 1_000_000


# --- E6 and E7: dense-only and the reranker ---------------------------------------------------


class _Cursor:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self._rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.log.append(sql)
        if sql.startswith("SELECT id FROM incident_chunks WHERE TRUE"):
            self._rows = [("doc#0",), ("doc#1",), ("doc#2",)]
        elif sql.startswith("WITH tq"):
            self._rows = [("doc#2",)]
        else:
            self._rows = [
                (
                    key,
                    "doc",
                    "s",
                    int(key[-1]),
                    f"body {key}",
                    "o",
                    "dev",
                    None,
                    None,
                    None,
                    None,
                    "t",
                    "p",
                )
                for key in ("doc#0", "doc#1", "doc#2")
            ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _Conn:
    def __init__(self) -> None:
        self.log: list[str] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self.log)


class _Embedder:
    name = "fake"
    dimensions = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 1.0] for _ in texts]


def _store(clean_env: pytest.MonkeyPatch, **kwargs: Any) -> tuple[Any, _Conn]:
    from faultline.context.store import PgVectorPastIncidentStore

    conn = _Conn()
    return PgVectorPastIncidentStore(conn, _Embedder(), normalisation=0, **kwargs), conn


def test_hybrid_asks_both_arms_and_dense_only_skips_the_text_query(
    clean_env: pytest.MonkeyPatch,
) -> None:
    hybrid, hybrid_conn = _store(clean_env)
    dense, dense_conn = _store(clean_env, mode="dense")

    hybrid.search("cart cannot reach redis", k=2)
    hits = dense.search("cart cannot reach redis", k=2)

    assert any(sql.startswith("WITH tq") for sql in hybrid_conn.log)
    assert not any(sql.startswith("WITH tq") for sql in dense_conn.log)
    assert [h.chunk.document_id for h in hits] and all(h.text_rank is None for h in hits)


class _Reverse:
    name = "reverse"

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(i) for i in range(len(texts))]


def test_the_reranker_reorders_the_pool_and_keeps_k(clean_env: pytest.MonkeyPatch) -> None:
    store, _ = _store(clean_env, reranker=_Reverse(), rerank_candidates=3)
    plain, _ = _store(clean_env)

    reranked = [h.chunk.text for h in store.search("q", k=2)]
    standing = [h.chunk.text for h in plain.search("q", k=2)]

    assert len(reranked) == 2
    assert reranked != standing


def test_no_reranker_is_built_unless_one_is_named(clean_env: pytest.MonkeyPatch) -> None:
    store, _ = _store(clean_env)
    assert store._reranker is None
    clean_env.setenv("FAULTLINE_CONTEXT_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    with pytest.raises(ValueError, match="pinned or not at all"):
        _store(clean_env)
    clean_env.setenv("FAULTLINE_CONTEXT_RERANK_REVISION", "abc123")
    named, _ = _store(clean_env)
    assert named._reranker is not None and named._reranker.name.startswith("cross-encoder/")
    assert named._reranker.revision == "abc123"


# --- the stamps -------------------------------------------------------------------------------


def test_no_switch_moves_either_stamp(clean_env: pytest.MonkeyPatch) -> None:
    from evalharness.capability import capability_version
    from faultline.agents.stamp import runtime_version

    assert capability_version() == "cap:91279a09"
    assert runtime_version() == "faultline/0.0.1+prompts:9ce16b66bbcc"
