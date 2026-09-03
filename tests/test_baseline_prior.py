"""B2 — the model's prior, with nothing to look at (T4.7).

The sharpest of the three baselines, because it is the one that can embarrass the project.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from evalharness import baseline_prior as b2
from faultline.agents.model import ModelRequest, ModelResponse

ANCHOR = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def verdict_reply(**overrides: Any) -> str:
    payload = {
        "root_cause": "adservice is most likely out of memory",
        "fault_class": "resource_exhaustion",
        "remediation_class": "config_revert",
        "confidence": "low",
        "evidence": [],
        "reasoning": "the alert names adservice and frontend is downstream of it",
        "open_questions": ["adservice memory series", "recent changes on adservice"],
    }
    payload.update(overrides)
    return json.dumps(payload)


class ScriptedModel:
    def __init__(self, replies: list[str], name: str = "scripted-fake") -> None:
        self._replies = list(replies)
        self._name = name
        self.calls: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        text = self._replies.pop(0) if self._replies else verdict_reply()
        return ModelResponse(text=text, model=self._name, input_tokens=900, output_tokens=120)


class Member:
    def __init__(self, service: str) -> None:
        self.service = service


class Triage:
    def __init__(self, alerting: list[str]) -> None:
        self.alerting = [Member(s) for s in alerting]
        self.blast_radius = [Member(s) for s in alerting]
        self.unmeasured_edges: list[str] = []


class Episode:
    def __init__(self, key: str, service: str, alertname: str, minutes: int) -> None:
        self.episode_key = key
        self.service = service
        self.alertname = alertname
        self.severity = "critical"
        self.starts_at = ANCHOR.replace(minute=minutes)


class Incident:
    id = "inc-1"
    title = "frontend error ratio above threshold"

    def __init__(self) -> None:
        self.episodes = {
            "e1": Episode("e1", "frontend", "ServiceHighErrorRate", 1),
            "e0": Episode("e0", "adservice", "ServiceHighErrorRate", 0),
        }


def catalog() -> Any:
    from faultline.context.catalog import ServiceCatalog

    return ServiceCatalog.from_snapshot()


def investigate(model: Any) -> Any:
    return b2.investigate(
        incident=Incident(),
        triage=Triage(["frontend", "adservice"]),
        catalog=catalog(),
        anchor=ANCHOR,
        model=model,
    )


# --- no tool access, enforced by the signature rather than by the prompt ---------------------


def test_investigate_takes_no_tools_argument_at_all() -> None:
    """**"No tool access" is a fact about the signature, not an instruction in a prompt.**

    A rule stated only in a system prompt is a rule a model can be argued out of - which is what
    THREAT-MODEL thesis 1 is about, applied to a baseline. Stated here it cannot be reached.
    """
    import inspect

    parameters = set(inspect.signature(b2.investigate).parameters)

    assert "tools" not in parameters
    assert parameters == {
        "incident",
        "triage",
        "catalog",
        "anchor",
        "model",
        "effort",
        "max_tokens",
    }


def test_the_module_never_imports_the_tool_layer() -> None:
    """The stronger version of the same guarantee: there is no path from this module to a tool,
    so no future edit reaches one by accident.

    Checked over the **parsed imports**, not the source text - the docstrings cite
    `faultline.tools.changes` by name when explaining the leak boundary, and a grep would call
    that a violation. A guard that fails on prose is a guard someone deletes.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/evalharness/baseline_prior.py").read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]

    assert [name for name in imported if name.startswith("faultline.tools")] == []


def test_it_makes_exactly_one_model_call() -> None:
    model = ScriptedModel([verdict_reply()])

    run = investigate(model)

    assert len(model.calls) == 1
    assert run.verdict.fault_class == "resource_exhaustion"


# --- the separation that makes B2 a control -------------------------------------------------


def test_importing_b2_does_not_move_the_agents_stamp() -> None:
    from faultline.agents.stamp import prompt_digest

    # The ledger constant lives in `test_harness_run.py` as TOP3_DIGEST. Asserted by value here
    # rather than imported, so this file fails loudly if B2's prompt ever leaks into the
    # agent's digest - importing the constant would make the two move together and prove nothing.
    assert prompt_digest() == "ba8684b01201", "B2 must not appear in the agent's stamp."


def test_b2s_prompt_is_not_a_role_prompt() -> None:
    from faultline.agents import roles

    assert not hasattr(roles, "B2_SYSTEM")


def test_every_baseline_carries_a_distinct_runtime() -> None:
    """Three baselines and the agent are four comparability generations, never one."""
    from evalharness import baseline_agent, baselines
    from faultline.agents.stamp import runtime_version as agent_runtime

    stamps = {
        agent_runtime(),
        baselines.BASELINE_RUNTIME,
        baseline_agent.runtime_version(),
        b2.runtime_version(),
    }

    assert len(stamps) == 4
    assert ":B2:" in b2.runtime_version()


def test_the_b2_runtime_moves_when_its_prompt_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    """B2's behaviour is *entirely* a prompt - no tools, no loop - so a hand-maintained version
    marker would be the only thing between two incomparable generations, and it is exactly the
    thing that gets forgotten."""
    before = b2.runtime_version()
    monkeypatch.setattr(b2, "B2_SYSTEM", b2.B2_SYSTEM + "\n\nThink step by step.")

    assert b2.runtime_version() != before


# --- the brief: alert text and catalog, and nothing derived from the answer -------------------


def test_the_alert_text_is_ordered_oldest_first() -> None:
    """Which service alerted *first* is the one signal in this brief that carries causal
    information, and it is destroyed by dict ordering. The fixture deliberately stores the later
    episode first."""
    text = b2.alert_text(Incident())

    assert text.index("adservice") < text.index("frontend")


def test_the_brief_names_no_fault_class_and_no_scenario() -> None:
    """**The leak boundary, one layer up from `faultline.tools.changes`.** A baseline handed a
    labelled incident measures the label. `HARNESS_VOCABULARY` is the same list the change-log
    guard greps for."""
    from faultline.tools.changes import HARNESS_VOCABULARY

    text = b2.brief(Incident(), Triage(["frontend"]), catalog(), ANCHOR).lower()

    leaked = sorted(word for word in HARNESS_VOCABULARY if word in text)
    assert leaked == [], f"the brief leaks harness vocabulary: {leaked}"

    # **The scope, stated so it is not "fixed" later.** The guard is on the incident-specific
    # brief, not on the system prompt: the prompt names all four fault classes because that is
    # the taxonomy the model must choose from, exactly as the synthesizer's does. Naming the
    # options is not naming the answer.
    assert "bad_deploy" in b2.B2_SYSTEM, "the prompt legitimately carries the taxonomy"
    assert len(HARNESS_VOCABULARY) > 10, "a guard over an empty vocabulary passes vacuously"


def test_the_brief_carries_the_topology_it_is_meant_to_reason_over() -> None:
    text = b2.brief(Incident(), Triage(["frontend"]), catalog(), ANCHOR)

    assert "SERVICE CATALOG" in text
    assert "->" in text, "measured call edges"
    assert "known absent from the graph" in text, "the catalog's absences are part of the map"


def test_a_truncated_catalog_says_it_was_truncated() -> None:
    """A briefing longer than the incident buries it, so the map is capped - and a capped map
    presented as a complete one is the `ToolResult.truncated` failure mode in a different
    costume."""
    text = b2.catalog_text(catalog(), limit=2)

    assert "more measured edges, not shown" in text


# --- citing evidence it cannot have ---------------------------------------------------------


def test_evidence_cited_without_looking_is_recorded_and_then_emptied() -> None:
    """**A finding that falls out of B2 for free.**

    B2 read nothing, so every result id it offers is fabricated and a citation validator would
    reject all of them. Dropping them silently would hide a real behaviour; keeping them in
    `evidence` would put an unresolvable id in a scored artifact. So the artifact's `evidence` is
    empty, the claim is kept in the baseline block, and the run is flagged.
    """
    model = ScriptedModel([verdict_reply(evidence=["tr_deadbeef", "tr_c0ffee"])])

    run = investigate(model)
    written = b2.artifact("i", "t", [], 0, None, run)

    assert run.invented_evidence == ["tr_deadbeef", "tr_c0ffee"]
    assert written["verdict"]["evidence"] == [], "no id here resolves to anything"
    assert written["baseline"]["cited_without_looking"] == ["tr_deadbeef", "tr_c0ffee"]
    assert "invented_evidence" in written["flags"]


def test_an_honest_empty_citation_is_not_flagged() -> None:
    run = investigate(ScriptedModel([verdict_reply()]))

    assert run.invented_evidence == []
    assert b2.artifact("i", "t", [], 0, None, run)["flags"] == []


# --- scored by the same code path as everything else ----------------------------------------


def test_concluding_without_looking_is_the_method_here_and_not_an_error() -> None:
    """The same behaviour B1 records as a failure. What makes a run valid is what the run was
    for, and B2 exists to answer from its prior."""
    run = investigate(ScriptedModel([verdict_reply()]))

    assert run.error is None
    assert run.verdict is not None
    assert b2.artifact("i", "t", [], 0, None, run)["baseline"]["tool_calls"] == 0


def test_the_artifact_has_every_field_the_scorer_reads() -> None:
    run = investigate(ScriptedModel([verdict_reply()]))
    written = b2.artifact("i-1", "t-1", ["frontend"], 1, "scenario:ad-memory-squeeze", run)

    for field_name in (
        "trajectory_id",
        "blast_radius",
        "unmeasured_edges",
        "verdict",
        "flags",
        "failed_dispatches",
        "narrative_error",
    ):
        assert field_name in written, f"the scorer reads {field_name}"
    assert written["verdict"]["fault_class"] == "resource_exhaustion"
    assert written["retrieved"] == []
    assert written["proposal"] is None


def test_a_reply_that_never_validates_is_recorded_rather_than_raised() -> None:
    run = investigate(ScriptedModel(["not json", "still not json"]))

    assert run.verdict is None
    assert run.error is not None and "no valid verdict" in run.error


def test_all_three_baselines_and_the_agent_are_four_distinct_configs() -> None:
    """T4.7 wants baselines as *"ordinary configs in the eval DB"*, which only means anything if
    they are distinct."""
    from evalharness import evaldb

    common = {"scenario_id": "ad-memory-squeeze", "models": {"planner": "claude-opus-5"}}
    fingerprints = {
        evaldb.fingerprint(common).fingerprint,
        *(
            evaldb.fingerprint({**common, "baseline": name}).fingerprint
            for name in ("b0", "b1", "b2")
        ),
    }

    assert len(fingerprints) == 4
