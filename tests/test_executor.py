"""The action plane (T6.2): the properties `PREREGISTRATION-T6.2.md` §3 says are proved by trying
to violate them.

Every test here runs without a world, a database or a key on disk: the world is a fake that
answers `declared`/`running` and records what it was asked to recreate, the stores are the in-memory
doubles, and the key is a string. What is tested is the *order* in `executor.core` and what each
refusal says - because the order is the safety argument.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from faultline.context.allowlist import load_allowlist
from faultline.executor import tokens
from faultline.executor.app import build_app
from faultline.executor.audit import InMemoryAuditStore
from faultline.executor.cli import ApproveError, approve
from faultline.executor.core import Executor, Performed, drift_between
from faultline.executor.settings import ExecutorSettings
from faultline.orchestrator.machine import (
    ApprovalOutcome,
    TransitionError,
    record_approval_outcome,
    transition,
)
from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity
from faultline.orchestrator.store import InMemoryIncidentStore

KEY = "0123456789abcdef0123456789abcdef"
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
CATALOG = load_allowlist()


def incident(
    state: IncidentState = IncidentState.PROPOSING, service: str = "shippingservice"
) -> Incident:
    inc = Incident(state=state, opened_at=NOW - timedelta(minutes=10))
    inc.episodes["ep1"] = Episode(
        episode_key="ep1",
        fingerprint="fp1",
        service=service,
        severity=Severity.CRITICAL,
        alertname="ServiceHighErrorRate",
        starts_at=NOW - timedelta(minutes=10),
        attached_at=NOW - timedelta(minutes=10),
    )
    return inc


def token_for(
    inc: Incident,
    *,
    action_id: str = "rollback_image",
    target: str = "shippingservice",
    catalog_version: int | None = None,
    key: str = KEY,
    ttl: int = 900,
    now: datetime = NOW,
) -> tuple[str, tokens.Claims]:
    return tokens.mint(
        incident_id=inc.id,
        proposal_id="20260909T105155Z-shipping-wrong-image",
        action_id=action_id,
        target=target,
        catalog_version=CATALOG.catalog_version if catalog_version is None else catalog_version,
        confirm_within_seconds=300,
        key=key,
        ttl_seconds=ttl,
        now=now,
    )


class FakeWorld:
    """Answers the two halves of the drift check and records every recreate."""

    def __init__(self, *, running: dict[str, Any], declared: dict[str, Any], exit_code: int = 0):
        self._running = running
        self._declared = declared
        self._exit = exit_code
        self.recreated: list[tuple[str, str]] = []

    def running(self, service: str) -> dict[str, Any]:
        return self._running

    def declared(self, service: str) -> dict[str, Any]:
        return self._declared

    def recreate_declared(self, service: str, drift: dict[str, Any] | None = None) -> Performed:
        self.recreated.append((service, "declared"))
        return Performed(
            command=["docker", "compose", "up", "-d", "--force-recreate", service],
            exit_code=self._exit,
            output="recreated",
            inverse="re-apply the override(s) below and recreate the service:\n--- x.yml\nimage: b",
        )

    def recreate_as_is(self, service: str) -> Performed:
        self.recreated.append((service, "as-is"))
        return Performed(
            command=["docker", "compose", "up", "-d", "--force-recreate", service],
            exit_code=self._exit,
            output="recreated",
            inverse="no inverse: a restart discards process state and nothing restores it",
        )


DRIFTED = {"image": "shop:bad", "environment": {}, "memory": 0, "nano_cpus": 0}
DECLARED = {"image": "shop:good", "environment": {}, "memory": 0, "nano_cpus": 0}


def make_executor(
    store: InMemoryIncidentStore,
    audit: InMemoryAuditStore,
    *,
    world: Any | None = None,
    kill_switch: bool = False,
    scope: set[str] | None = None,
    key: str = KEY,
) -> Executor:
    return Executor(
        key=key,
        kill_switch=kill_switch,
        incidents=store,
        audit=audit,
        world=world if world is not None else FakeWorld(running=DRIFTED, declared=DECLARED),
        catalog=CATALOG,
        scope_of=lambda inc: scope if scope is not None else {"shippingservice", "checkoutservice"},
        now=lambda: NOW,
    )


# --- the token -----------------------------------------------------------------------------------


def test_a_token_round_trips_and_names_exactly_what_was_approved() -> None:
    inc = incident()
    token, claims = token_for(inc)
    back = tokens.verify(token, key=KEY, now=NOW)
    assert back == claims
    assert back.action_id == "rollback_image" and back.target == "shippingservice"


def test_a_tampered_token_is_refused_as_forged_not_as_wrong() -> None:
    """Change one byte of the payload - the target - and the signature no longer verifies. The
    message says *signature*, not which claim moved: a forger learns nothing from it."""
    inc = incident()
    token, _ = token_for(inc)
    payload, signature = token.split(".")
    import base64
    import json

    raw = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    raw["target"] = "cartservice"
    forged = (
        base64.urlsafe_b64encode(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(tokens.TokenError, match="signature"):
        tokens.verify(f"{forged}.{signature}", key=KEY, now=NOW)


def test_a_token_under_another_key_is_refused() -> None:
    token, _ = token_for(incident(), key="another-key-entirely")
    with pytest.raises(tokens.TokenError, match="signature"):
        tokens.verify(token, key=KEY, now=NOW)


def test_an_expired_token_is_refused_and_says_when_it_expired() -> None:
    token, claims = token_for(incident(), ttl=60)
    with pytest.raises(tokens.TokenError, match=re.escape(claims.expires_at)):
        tokens.verify(token, key=KEY, now=NOW + timedelta(seconds=61))


def test_no_key_means_no_signing_and_no_verifying() -> None:
    """An empty key would sign every token identically; refusing is the only honest behaviour."""
    with pytest.raises(tokens.TokenError, match="empty key"):
        token_for(incident(), key="")
    token, _ = token_for(incident())
    with pytest.raises(tokens.TokenError, match="empty key"):
        tokens.verify(token, key="", now=NOW)


def test_garbage_is_refused_by_shape() -> None:
    with pytest.raises(tokens.TokenError, match="form"):
        tokens.verify("not-a-token", key=KEY, now=NOW)


# --- the order -----------------------------------------------------------------------------------


def test_the_kill_switch_refuses_first_records_and_consumes_nothing() -> None:
    """Step 1. Before the token is even looked at - a kill-switched executor with a garbage token
    says *kill switch*, not *bad token*. And the approval stands: the same token executes once the
    switch is off, because the refusal was the executor's state and not the approver's."""
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, claims = token_for(inc)

    off = make_executor(store, audit, kill_switch=True).execute("garbage", caller="t")
    assert off.outcome == "kill_switch"
    assert "Investigation is unaffected" in off.reason
    assert off.token_id is None

    refused = make_executor(store, audit, kill_switch=True).execute(token, caller="t")
    assert refused.outcome == "kill_switch"
    assert store.get(inc.id).state is IncidentState.AWAITING_APPROVAL

    executed = make_executor(store, audit).execute(token, caller="t")
    assert executed.outcome == "executed", executed.reason
    assert audit.spent(claims.token_id) is executed


def test_the_kill_switch_leaves_investigation_running() -> None:
    """The plan: *"halts all execution while leaving investigation running."* The agent's own
    transitions keep advancing an incident while the executor refuses everything."""
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.TRIAGING)
    store.save(inc)
    executor = make_executor(store, audit, kill_switch=True)

    transition(inc, IncidentState.PLANNING, trigger="planner started")
    assert inc.state is IncidentState.PLANNING
    assert executor.execute("anything", caller="t").outcome == "kill_switch"
    transition(inc, IncidentState.INVESTIGATING, trigger="dispatched")
    assert inc.state is IncidentState.INVESTIGATING


def test_a_forged_token_is_refused_before_any_incident_is_read() -> None:
    audit = InMemoryAuditStore()

    class NeverRead:
        def get(self, incident_id: str) -> Any:
            raise AssertionError("the incident store was consulted for a forged token")

    executor = Executor(
        key=KEY, kill_switch=False, incidents=NeverRead(), audit=audit, world=None, catalog=CATALOG
    )
    record = executor.execute("nope.nope", caller="t")
    assert record.outcome == "refused" and "token refused" in record.reason


def test_a_token_for_a_missing_or_terminal_incident_is_refused() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    ghost = incident()
    token, _ = token_for(ghost)
    assert "does not exist" in make_executor(store, audit).execute(token, caller="t").reason

    resolved = incident(IncidentState.RESOLVED)
    store.save(resolved)
    token, _ = token_for(resolved)
    record = make_executor(store, audit).execute(token, caller="t")
    assert record.outcome == "refused" and "no world left to fix" in record.reason


def test_a_target_outside_the_incidents_scope_is_refused_before_the_token_is_spent() -> None:
    """Step 5 before steps 6-8: the failure table's *"action-target mismatch hard-rejects before
    the approval is even requested"*. The reason names the scope so the approver can see why."""
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, claims = token_for(inc, target="paymentservice")

    record = make_executor(store, audit).execute(token, caller="t")

    assert record.outcome == "refused"
    assert "outside the incident's scope" in record.reason
    assert "shippingservice" in record.reason
    assert audit.spent(claims.token_id) is None
    assert store.get(inc.id).state is IncidentState.AWAITING_APPROVAL


def test_a_token_is_single_use_and_the_refusal_names_its_first_use() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, _ = token_for(inc)
    executor = make_executor(store, audit)

    first = executor.execute(token, caller="t")
    assert first.outcome == "executed", first.reason
    # A second presentation: the incident is now EXECUTING, still non-terminal, so it is the audit
    # and not the state machine that refuses - which is what single-use means.
    second = executor.execute(token, caller="t")

    assert second.outcome == "refused"
    assert "already spent" in second.reason and first.id in second.reason


def test_a_token_for_another_action_or_an_older_catalog_is_refused() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)

    unknown, _ = token_for(inc, action_id="reboot_everything")
    assert "not in the allowlist" in make_executor(store, audit).execute(unknown, caller="t").reason

    stale, _ = token_for(inc, catalog_version=CATALOG.catalog_version + 1)
    record = make_executor(store, audit).execute(stale, caller="t")
    assert "catalog version" in record.reason and "Re-approve" in record.reason


def test_scale_refuses_with_the_adr_that_measured_it() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, _ = token_for(inc, action_id="scale_service")

    record = make_executor(store, audit).execute(token, caller="t")

    assert record.outcome == "refused"
    assert "unperformable" in record.reason and "ADR-0029" in record.reason


def test_no_drift_means_unexecutable_with_the_empty_diff_recorded() -> None:
    """Step 8, and the pre-registration's §2.2: the prior state is the declared definition, so a
    service that already matches it has nothing to roll back to."""
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, _ = token_for(inc)
    world = FakeWorld(running=DECLARED, declared=DECLARED)

    record = make_executor(store, audit, world=world).execute(token, caller="t")

    assert record.outcome == "refused"
    assert "unexecutable" in record.reason and "no drift" in record.reason
    assert world.recreated == []


def test_rollback_only_sees_image_drift_and_revert_only_sees_config_drift() -> None:
    """A service whose only drift is its image has had a deploy, not a config change. Executing
    `revert_config` on it would score the proposer right for the wrong reason."""
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    world = FakeWorld(running=DRIFTED, declared=DECLARED)  # image drift only

    revert, _ = token_for(inc, action_id="revert_config")
    record = make_executor(store, audit, world=world).execute(revert, caller="t")
    assert record.outcome == "refused" and "environment, memory, nano_cpus" in record.reason

    rollback, _ = token_for(inc, action_id="rollback_image")
    record = make_executor(store, audit, world=world).execute(rollback, caller="t")
    assert record.outcome == "executed"
    assert record.drift == {"drift": {"image": {"running": "shop:bad", "declared": "shop:good"}}}


def test_an_executed_action_records_its_command_hash_inverse_and_moves_the_incident() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, claims = token_for(inc)
    world = FakeWorld(running=DRIFTED, declared=DECLARED)

    record = make_executor(store, audit, world=world).execute(token, caller="chandana")

    assert record.outcome == "executed"
    assert record.command[-1] == "shippingservice" and record.exit_code == 0
    assert record.output_sha256 and len(record.output_sha256) == 64
    assert record.inverse.startswith("re-apply the override")
    assert record.token_id == claims.token_id and record.caller == "chandana"
    assert world.recreated == [("shippingservice", "declared")]
    assert store.get(inc.id).state is IncidentState.EXECUTING


def test_restart_recreates_as_is_and_says_it_has_no_inverse() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, _ = token_for(inc, action_id="restart_service")
    world = FakeWorld(running=DECLARED, declared=DECLARED)  # no drift, and none needed

    record = make_executor(store, audit, world=world).execute(token, caller="t")

    assert record.outcome == "executed"
    assert world.recreated == [("shippingservice", "as-is")]
    assert record.inverse.startswith("no inverse:")


def test_a_failed_command_is_an_error_that_spends_the_token_and_fails_the_incident() -> None:
    """Steps 9-10: the world may be half-changed, so the token is spent (no automatic retry -
    ADR-0028 §2) and the incident is FAILED with the audit row named."""
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, claims = token_for(inc)
    world = FakeWorld(running=DRIFTED, declared=DECLARED, exit_code=1)

    record = make_executor(store, audit, world=world).execute(token, caller="t")

    assert record.outcome == "error" and "exited 1" in record.reason
    assert audit.spent(claims.token_id) is record
    assert store.get(inc.id).state is IncidentState.FAILED


def test_the_audit_row_is_written_before_the_incident_moves() -> None:
    """Step 10's ordering: a crash between the two leaves a ledger entry, not a moved incident
    with no record."""
    store = InMemoryIncidentStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, _ = token_for(inc)

    class Ordered(InMemoryAuditStore):
        def append(self, record: Any) -> None:
            assert store.get(inc.id).state is IncidentState.AWAITING_APPROVAL, (
                "moved before recorded"
            )
            super().append(record)

    make_executor(store, Ordered()).execute(token, caller="t")
    assert store.get(inc.id).state is IncidentState.EXECUTING


# --- drift ---------------------------------------------------------------------------------------


def test_drift_compares_environment_on_declared_keys_only() -> None:
    running = {"environment": {"A": "1", "B": "changed", "PATH": "/usr/bin"}, "memory": 100}
    declared = {"environment": {"A": "1", "B": "2"}, "memory": 100}
    drift = drift_between(running, declared, ("environment", "memory"))
    assert drift.fields == {"environment": {"B": {"running": "changed", "declared": "2"}}}
    assert drift_between(running, declared, ("memory",)).present is False


def test_a_declared_key_missing_from_the_container_is_drift() -> None:
    drift = drift_between({"environment": {}}, {"environment": {"X": "1"}}, ("environment",))
    assert drift.fields == {"environment": {"X": {"running": None, "declared": "1"}}}


# --- the state machine ---------------------------------------------------------------------------


def test_approval_moves_proposing_and_triaging_to_awaiting_and_execution_to_executing() -> None:
    proposed = incident(IncidentState.PROPOSING)
    record_approval_outcome(proposed, ApprovalOutcome(kind="approved", audit_id="a1"))
    assert proposed.state is IncidentState.AWAITING_APPROVAL

    manual = incident(IncidentState.TRIAGING)
    record_approval_outcome(manual, ApprovalOutcome(kind="approved", audit_id="a2"))
    assert manual.state is IncidentState.AWAITING_APPROVAL

    record_approval_outcome(manual, ApprovalOutcome(kind="executed", audit_id="a3"))
    assert manual.state is IncidentState.EXECUTING
    record_approval_outcome(manual, ApprovalOutcome(kind="refused", audit_id="a4"))
    assert manual.state is IncidentState.EXECUTING


def test_approval_is_not_granted_from_a_state_where_an_agent_is_mid_flight() -> None:
    """Only TRIAGING and PROPOSING lead to AWAITING_APPROVAL (ADR-0016 Addendum 4). An incident an
    agent is planning would have two processes moving it."""
    for state in (IncidentState.PLANNING, IncidentState.INVESTIGATING, IncidentState.SYNTHESIZING):
        inc = incident(state)
        with pytest.raises(TransitionError):
            record_approval_outcome(inc, ApprovalOutcome(kind="approved"))


def test_an_unknown_outcome_kind_is_an_error_not_a_silent_no_op() -> None:
    with pytest.raises(ValueError, match="unknown approval outcome"):
        record_approval_outcome(incident(), ApprovalOutcome(kind="shrug"))


# --- approve -------------------------------------------------------------------------------------


def _settings(**overrides: Any) -> ExecutorSettings:
    return ExecutorSettings(token_key=KEY, **overrides)


PROPOSAL = {
    "remediation_class": "rollback",
    "action_id": "rollback_image",
    "target": "shipping-service",  # the container name - approve canonicalises it
    "confirm_within_seconds": 300,
}


def test_approve_mints_records_and_moves_the_incident() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.PROPOSING)
    store.save(inc)

    token, record = approve(
        incident_id=inc.id,
        incidents=store,
        audit=audit,
        settings=_settings(),
        catalog=CATALOG,
        proposal=PROPOSAL,
        proposal_id="traj#7",
        caller="chandana",
        now=NOW,
    )

    claims = tokens.verify(token, key=KEY, now=NOW)
    assert claims.target == "shippingservice", "canonicalised from the container name"
    assert claims.proposal_id == "traj#7" and claims.catalog_version == CATALOG.catalog_version
    assert record.outcome == "approved" and record.token_id == claims.token_id
    assert token not in record.reason and token not in record.as_dict().values()
    assert store.get(inc.id).state is IncidentState.AWAITING_APPROVAL
    assert audit.spent(claims.token_id) is None, "an approval does not spend the token"


def test_approve_refuses_an_abstention_and_an_unknown_action() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.PROPOSING)
    store.save(inc)
    with pytest.raises(ApproveError, match="not in the allowlist"):
        approve(
            incident_id=inc.id,
            incidents=store,
            audit=audit,
            settings=_settings(),
            catalog=CATALOG,
            proposal={**PROPOSAL, "action_id": "nuke"},
            proposal_id="p",
            caller="t",
            now=NOW,
        )
    with pytest.raises(ApproveError, match="does not exist"):
        approve(
            incident_id="nobody",
            incidents=store,
            audit=audit,
            settings=_settings(),
            catalog=CATALOG,
            proposal=PROPOSAL,
            proposal_id="p",
            caller="t",
            now=NOW,
        )


def test_the_approved_token_executes_end_to_end() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.PROPOSING)
    store.save(inc)
    token, _ = approve(
        incident_id=inc.id,
        incidents=store,
        audit=audit,
        settings=_settings(),
        catalog=CATALOG,
        proposal=PROPOSAL,
        proposal_id="traj#7",
        caller="t",
        now=NOW,
    )
    record = make_executor(store, audit).execute(token, caller="t")
    assert record.outcome == "executed" and record.proposal_id == "traj#7"
    assert [r.outcome for r in audit.for_incident(inc.id)] == ["approved", "executed"]


# --- the served endpoint -------------------------------------------------------------------------


def test_the_served_executor_takes_a_token_and_returns_the_audit_row() -> None:
    store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
    inc = incident(IncidentState.AWAITING_APPROVAL)
    store.save(inc)
    token, claims = token_for(inc)
    client = TestClient(build_app(_settings(), executor=make_executor(store, audit)))

    assert client.get("/healthz").json() == {"status": "ok", "kill_switch": False}
    response = client.post("/execute", json={"token": token, "caller": "ui"})

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "executed" and body["token_id"] == claims.token_id
    assert body["caller"] == "ui"
    assert client.post("/execute", json={"token": token}).json()["outcome"] == "refused"


def test_the_served_executor_has_no_route_that_mints_lists_or_revokes() -> None:
    app = build_app(_settings(), executor=object())
    paths = {route.path for route in app.routes}
    assert paths >= {"/healthz", "/execute"}
    assert not any(
        p for p in paths if "approve" in p or "mint" in p or "revoke" in p or "audit" in p
    )


# --- running state is drift (2026-09-11, from the repair replay's second triple) ------------------


def test_a_stopped_container_is_drift_for_both_rollback_and_revert(tmp_path: Any) -> None:
    """`cart-bad-image-tag` refused as *no drift*: the injector stops the container and fails the
    recreate, so the only container is the old one, stopped, wearing the declared image. A declared
    service that is not running has drifted whatever else matches."""
    stopped = {**DECLARED, "running": False, "exists": True}
    declared = {**DECLARED, "running": True}
    for action in ("rollback_image", "revert_config"):
        store, audit = InMemoryIncidentStore(), InMemoryAuditStore()
        inc = incident(IncidentState.AWAITING_APPROVAL)
        store.save(inc)
        token, _ = token_for(inc, action_id=action)
        world = FakeWorld(running=stopped, declared=declared)

        record = make_executor(store, audit, world=world).execute(token, caller="t")

        assert record.outcome == "executed", (action, record.reason)
        assert record.drift["drift"]["running"] == {"running": False, "declared": True}


def test_a_missing_container_is_drift_too() -> None:
    drift = drift_between(
        {"image": None, "running": False, "exists": False},
        {"image": "shop:good", "running": True},
        ("image", "running"),
    )
    assert set(drift.fields) == {"image", "running"}


def test_the_docker_client_reports_a_missing_container_as_not_running() -> None:
    from injector.docker import DockerCli
    from tests.fakes import FakeRunner

    runner = FakeRunner(returncodes={"inspect": 1})
    definition = DockerCli(runner).running_definition("ghost")
    assert definition == {
        "image": None,
        "environment": {},
        "memory": 0,
        "nano_cpus": 0,
        "running": False,
        "exists": False,
    }


def test_the_docker_client_reads_running_state_with_the_rest() -> None:
    from injector.docker import DockerCli
    from tests.fakes import FakeRunner

    runner = FakeRunner(stdout={"inspect": '"shop:v1"\t["A=1","PATH=/bin"]\t419430400\t0\tfalse\n'})
    definition = DockerCli(runner).running_definition("cart-service")
    assert definition["image"] == "shop:v1" and definition["environment"] == {
        "A": "1",
        "PATH": "/bin",
    }
    assert definition["memory"] == 419430400 and definition["running"] is False
