"""One approved action, executed once - or refused with a reason, in a fixed order.

The order is the safety argument, so it is written out rather than left to the code's shape:

1. **Kill switch.** Before anything is read. A switched-off executor does nothing, learns nothing,
   and records that it was asked.
2. **The token's shape.** Signature and expiry (`tokens.verify`). A forged or stale token is
   refused before its claims are believed about anything - including which incident it names.
3. **The incident the token names.** Must exist and must not be terminal. An incident that has
   resolved has no world to fix; an approval that arrives after the fact is recorded and refused.
4. **Nothing else is trusted from the caller.** The incident, the action and the target all come
   from the verified claims; a caller supplies a token and a name for the audit, and that is all.
5. **Blast radius.** The canonical target must be inside the incident's scope - the services its
   alerts and their dependency neighbourhood name, recomputed from the incident's episodes with
   the same catalog and radius synthesis used. **Before single-use and before the catalog**, which
   is the order the proposal's failure table specifies: *"action-target mismatch hard-rejects
   before the approval is even requested"*.
6. **Single use.** The audit is asked whether this token id has already been spent.
7. **The catalog.** The action exists, is `available` (so `scale_service` refuses with ADR-0029's
   reason), and the token was granted under the catalog version now in force.
8. **Precondition: drift.** For `rollback_image` and `revert_config`, the running container must
   differ from the declared definition in the field the action would change. No drift, no
   rollback - refused `unexecutable`, with the (empty) diff recorded. `restart_service` has no
   precondition.
9. **Perform.** One compose command. Its argv, exit and output hash go to the audit; a non-zero
   exit is `error`, and the world is left as the command left it, with the operator told.
10. **Record and advance.** The audit row is appended before the incident moves to `EXECUTING`,
    so a crash between the two leaves a ledger entry and not a moved incident with no record.

Refusals at steps 1-8 leave the incident where it was and consume nothing. Steps 9-10 consume
the token whether or not the command succeeded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultline.executor.audit import AuditRecord, AuditStore
from faultline.executor.tokens import Claims, TokenError, verify
from faultline.orchestrator.machine import is_terminal
from faultline.orchestrator.models import Incident

DRIFT_FIELDS: dict[str, tuple[str, ...]] = {
    "rollback_image": ("image", "running"),
    "revert_config": ("environment", "memory", "nano_cpus", "running"),
    "restart_service": (),
}
"""Which fields of the running definition each action compares against the declared one.

**`running` joined both on 2026-09-11, from the repair replay's second triple.**
`cart-bad-image-tag` stops the container first and fails the recreate with a phantom tag, so the
only cartservice container is the old healthy one, stopped, wearing the declared image - and the
first version of this table, which compared image, environment and limits and never asked whether
the service was *up*, refused `rollback_image` as *no drift*. A declared service that is not
running is the most basic drift there is; the prediction that both `rollback_image` triples recover
failed on exactly this, and the re-attempt is pre-registered in
`evals/runs/REPLAY-2026-09-11-t6.2.md`.

`revert_config` covers everything a configuration change can move in this world - environment,
the memory limit, the CPU quota - because the allowlist's `config_revert` is *"restore the
service's previous environment and configuration"* and a resource limit is configuration. The
image is `rollback_image`'s alone: a service whose only drift is its image tag has had a deploy,
not a config change, and an executor that reverted it under the wrong name would be scoring the
proposer right for the wrong reason."""


@dataclass(frozen=True, slots=True)
class Drift:
    """The difference between what runs and what is declared, per field the action compares."""

    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    """`{field: {"running": ..., "declared": ...}}` for every field that differs."""

    @property
    def present(self) -> bool:
        return bool(self.fields)

    def as_dict(self) -> dict[str, Any]:
        return {"drift": self.fields}


def drift_between(
    running: dict[str, Any], declared: dict[str, Any], fields: tuple[str, ...]
) -> Drift:
    """Field by field. Environment is compared on the declared keys only: a container carries
    dozens of variables the image or the platform set, and the declared definition names the
    ones the world chose. A declared key missing from the container, or present with another
    value, is drift; an extra key on the container is not."""
    differences: dict[str, dict[str, Any]] = {}
    for name in fields:
        if name == "environment":
            declared_env: dict[str, str] = declared.get("environment") or {}
            running_env: dict[str, str] = running.get("environment") or {}
            moved = {
                key: {"running": running_env.get(key), "declared": value}
                for key, value in declared_env.items()
                if running_env.get(key) != value
            }
            if moved:
                differences["environment"] = moved
        elif running.get(name) != declared.get(name):
            differences[name] = {"running": running.get(name), "declared": declared.get(name)}
    return Drift(differences)


class RefusedError(Exception):
    """The executor did not act. `outcome` is the audit outcome; `reason` is recorded verbatim."""

    def __init__(self, reason: str, *, outcome: str = "refused") -> None:
        super().__init__(reason)
        self.reason = reason
        self.outcome = outcome


@dataclass(slots=True)
class Performed:
    command: list[str]
    exit_code: int
    output: str
    inverse: str

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output.encode("utf-8", "replace")).hexdigest()


class World:
    """The executor's view of the world and its only way of changing it. Wraps the injector's
    clients, which hold the credential; nothing in `faultline.agents` can construct one."""

    def __init__(self, settings: Any | None = None, runner: Any | None = None) -> None:
        from injector.docker import ComposeCli, DockerCli, SubprocessRunner
        from injector.engine import Engine
        from injector.settings import InjectorSettings

        self._settings = settings or InjectorSettings()
        self._runner = runner if runner is not None else SubprocessRunner()
        self._compose = ComposeCli(self._runner, self._settings)
        self._docker = DockerCli(self._runner)
        self._engine = Engine(self._settings, runner=self._runner)

    def declared(self, service: str) -> dict[str, Any]:
        return self._compose.declared_definition(service)

    def running(self, service: str) -> dict[str, Any]:
        from injector.world import SERVICE_CONTAINERS

        return self._docker.running_definition(SERVICE_CONTAINERS.get(service, service))

    def active_override_files(self, service: str) -> list[str]:
        from injector.models import ComposeServiceRestore, CpuQuotaRestore
        from injector.world import canonical_service

        return sorted(
            injection.restore.override_file
            for injection in self._engine.active().values()
            if isinstance(injection.restore, ComposeServiceRestore | CpuQuotaRestore)
            and canonical_service(injection.restore.service) == canonical_service(service)
        )

    def recreate_declared(self, service: str, drift: dict[str, Any] | None = None) -> Performed:
        """`rollback_image` and `revert_config`: the service comes back as the world defines it.
        The inverse is the override files that were in force, copied into the record so the
        fault can be put back for a re-test; then the injector is told
        (`Engine.acknowledge_external_restore`)."""
        overrides = self.active_override_files(service)
        inverse_parts = []
        for path in overrides:
            try:
                inverse_parts.append(f"--- {path}\n{Path(path).read_text()}")
            except OSError:
                inverse_parts.append(f"--- {path} (unreadable at execution time)")
        if inverse_parts:
            inverse = "re-apply the override(s) below and recreate the service:\n" + "\n".join(
                inverse_parts
            )
        elif drift:
            # A live change (`docker update`) leaves no file. The running values that differed
            # are the inverse - `docker update --memory <running>` puts them back.
            inverse = "no override was in force; re-apply the running values that differed: " + (
                json.dumps(drift, sort_keys=True)
            )
        else:
            inverse = (
                "no override was in force and no drift was recorded; the inverse is whatever "
                "change produced the state this world did not record"
            )
        performed = self._recreate(service, overrides=())
        if performed.exit_code == 0:
            forgotten = self._engine.acknowledge_external_restore(service)
            if forgotten:
                performed.output += f"\ninjector: forgot {', '.join(forgotten)}"
        performed.inverse = inverse
        return performed

    def recreate_as_is(self, service: str) -> Performed:
        """`restart_service`: recreate under whatever it currently runs, overrides included."""
        overrides = [Path(p) for p in self.active_override_files(service)]
        performed = self._recreate(service, overrides=tuple(overrides))
        performed.inverse = "no inverse: a restart discards process state and nothing restores it"
        return performed

    def _recreate(self, service: str, *, overrides: tuple[Path, ...]) -> Performed:
        from injector.docker import CommandError

        argv = self._compose._base_args()
        for override in overrides:
            argv += ["-f", str(override)]
        argv += ["up", "-d", "--no-build", "--no-deps", "--force-recreate", service]
        try:
            result = self._runner.run(argv, cwd=self._settings.world_dir)
            return Performed(
                command=list(argv),
                exit_code=result.returncode,
                output=result.stdout + result.stderr,
                inverse="",
            )
        except CommandError as exc:
            result = exc.result
            return Performed(
                command=list(argv),
                exit_code=result.returncode,
                output=result.stdout + result.stderr,
                inverse="",
            )


def incident_scope(
    incident: Incident, catalog: Any | None = None, hop_radius: int | None = None
) -> set[str]:
    """The services this incident is about: what its alerts named and their dependency-graph
    neighbourhood, canonical. **Recomputed, not stored**: `Triage` is a pure function of the
    incident's episodes, the catalog snapshot and the hop radius, and synthesis ran it on exactly
    these inputs, so the recomputation is the recorded value (ADR-0038 says why a stored copy would
    be the same list one column over)."""
    from faultline.agents.triage import Triage
    from faultline.context.catalog import ServiceCatalog
    from faultline.context.settings import ContextSettings
    from injector.world import canonical_service

    result = Triage(
        catalog or ServiceCatalog.from_snapshot(),
        hop_radius if hop_radius is not None else ContextSettings().hop_radius,
    ).run(incident)
    scope = {canonical_service(member.service) for member in result.blast_radius}
    scope |= {
        canonical_service(episode.service)
        for episode in incident.episodes.values()
        if episode.service
    }
    return scope


class Executor:
    def __init__(
        self,
        *,
        key: str,
        kill_switch: bool,
        incidents: Any,
        audit: AuditStore,
        world: World | None,
        catalog: Any | None = None,
        scope_of: Any | None = None,
        now: Any | None = None,
    ) -> None:
        from faultline.context.allowlist import load_allowlist

        self._key = key
        self._kill_switch = kill_switch
        self._incidents = incidents
        self._audit = audit
        self._world = world
        self._catalog = catalog or load_allowlist()
        self._scope_of = scope_of or incident_scope
        self._now = now or (lambda: datetime.now(UTC))

    def execute(self, token: str, *, caller: str) -> AuditRecord:
        """Steps 1-10 above. Always returns the audit row it wrote; never raises for a refusal."""
        claims: Claims | None = None
        incident: Incident | None = None
        try:
            if self._kill_switch:
                raise RefusedError(
                    "kill switch is on (FAULTLINE_EXECUTOR_KILL_SWITCH); nothing executes while "
                    "it is. Investigation is unaffected.",
                    outcome="kill_switch",
                )
            try:
                claims = verify(token, key=self._key, now=self._now())
            except TokenError as exc:
                raise RefusedError(f"token refused: {exc}") from exc
            incident = self._incidents.get(claims.incident_id)
            if incident is None:
                raise RefusedError(f"incident {claims.incident_id} does not exist")
            if is_terminal(incident.state):
                raise RefusedError(
                    f"incident {incident.id} is {incident.state.value}; there is no world left "
                    "to fix"
                )
            scope = self._scope_of(incident)
            if claims.target not in scope:
                raise RefusedError(
                    f"target {claims.target} is outside the incident's scope "
                    f"{sorted(scope)} - action-target mismatch, refused before the approval is "
                    "considered"
                )
            spent = self._audit.spent(claims.token_id)
            if spent is not None:
                raise RefusedError(
                    f"token {claims.token_id} was already spent by audit row {spent.id} at "
                    f"{spent.at.isoformat()} ({spent.outcome})"
                )
            action = self._catalog.by_id(claims.action_id)
            if action is None:
                raise RefusedError(f"action {claims.action_id!r} is not in the allowlist catalog")
            if action.status != "available":
                why = action.unperformable_reason or ""
                raise RefusedError(f"action {action.id} is {action.status}: {why}".strip())
            if claims.catalog_version != self._catalog.catalog_version:
                raise RefusedError(
                    f"token was granted under catalog version {claims.catalog_version}; the "
                    f"catalog is now version {self._catalog.catalog_version}. Re-approve against "
                    "the current catalog."
                )
            if self._world is None:
                raise RefusedError("this executor has no world to act on")
            drift = Drift()
            fields = DRIFT_FIELDS.get(action.id)
            if fields is None:
                raise RefusedError(f"action {action.id} has no executor in this world")
            if fields:
                drift = drift_between(
                    self._world.running(claims.target), self._world.declared(claims.target), fields
                )
                if not drift.present:
                    raise RefusedError(
                        f"unexecutable: {claims.target} shows no drift from its declared "
                        f"definition on {', '.join(fields)}; there is nothing to "
                        f"{action.remediation_class}"
                    )
            if action.id == "restart_service":
                performed = self._world.recreate_as_is(claims.target)
            else:
                performed = self._world.recreate_declared(claims.target, drift.fields)
            record = AuditRecord(
                incident_id=incident.id,
                proposal_id=claims.proposal_id,
                action_id=claims.action_id,
                target=claims.target,
                token_id=claims.token_id,
                caller=caller,
                outcome="executed" if performed.exit_code == 0 else "error",
                reason="" if performed.exit_code == 0 else f"command exited {performed.exit_code}",
                command=performed.command,
                exit_code=performed.exit_code,
                output_sha256=performed.output_sha256,
                inverse=performed.inverse,
                drift=drift.as_dict(),
                at=self._now(),
            )
            self._audit.append(record)
            self._advance(incident, record)
            return record
        except RefusedError as refusal:
            record = AuditRecord(
                incident_id=claims.incident_id if claims else "",
                proposal_id=claims.proposal_id if claims else "",
                action_id=claims.action_id if claims else "",
                target=claims.target if claims else "",
                token_id=claims.token_id if claims else None,
                caller=caller,
                outcome=refusal.outcome,
                reason=refusal.reason,
                at=self._now(),
            )
            self._audit.append(record)
            return record

    def _advance(self, incident: Incident, record: AuditRecord) -> None:
        from faultline.orchestrator.machine import ApprovalOutcome, record_approval_outcome

        outcome = ApprovalOutcome(
            kind="executed" if record.outcome == "executed" else "failed", audit_id=record.id
        )
        record_approval_outcome(incident, outcome)
        self._incidents.save_investigation_state(incident)
