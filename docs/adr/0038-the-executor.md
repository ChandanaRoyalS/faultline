# ADR-0038: The executor — the one process that can change the world, and what building it changed

- **Status:** accepted
- **Date:** 2026-09-11
- **Task:** T6.2 (action plane)
- **Relates to:** ADR-0028 (the proposer, and what it would take to act), ADR-0032 (the
  allowlist), ADR-0029 (why `scale` is unperformable), ADR-0019 §4 (read-only is a property of the
  tool surface), ADR-0016 (the state machine; Addendum 4 is this task's row), T7.50 (the oracle
  analysis), `evals/runs/PREREGISTRATION-T6.2.md` (written first; this ADR is held to it)

## Context

Until today nothing in this repository could change the world except the injector, which is the
harness's chaos tool and runs under the operator's hand. The proposer (T3.9) emits *a falsifiable
claim about a change, never the change* (ADR-0028 §1), and the pipeline stopped there. The plan's
T6.2 is the second system ADR-0028 §3 said the executor had to be: *"a separate process with its
own credentials, outside the investigation runtime, and the investigation runtime gains no write
tool."* This ADR records the design as built, and the four things building it changed about what
the pre-registration assumed.

## 1. The credential, and where it lives

In this world the write credential is **the Docker socket and the world's compose files**. There
is no CD system, no flag service with an API, no Kubernetes; a rollback is `docker compose up -d
--force-recreate <service>` from the declared definition, and the ability to run it is the ability
to change anything. `faultline.executor` is the only package under `faultline/` that constructs the
injector's `ComposeCli` and `DockerCli`, and `tests/test_executor_boundary.py` holds by AST that
nothing under `faultline.agents` or `faultline.tools` imports `faultline.executor`,
`injector.docker`, `injector.engine` or `subprocess`. In the deployment the executor is its own
container, the only one that mounts the socket (`tests/test_deploy.py` counts), and it joins the
docker group by id rather than running as root.

ADR-0019 §4's sentence — *read-only is a property of the tool surface, not of the credential* —
stays literally true of the investigation runtime. The executor is not part of that surface; it is
a different process that the surface cannot name.

## 2. What an action does here — the first thing building changed

The pre-registration's §2.2 found, before a line was written, that every change record the
injector emits carries `before=None` by design (`injector.changelog.describe`), so ADR-0032's
preconditions *"a prior image tag … is recorded in change history"* could never be met by reading
them. **Marked decision: the prior state is the world's declared definition** — the three hashed
compose files with no generated override — and the precondition is **drift**: the running
container differs from what the declared definition would produce, in the field the action would
change.

`rollback_image` compares the image and nothing else; `revert_config` compares environment (on the
declared keys), the memory limit and the CPU quota. The split is deliberate: a service whose only
drift is its image tag has had a deploy, and an executor that reverted it under `revert_config`
would be scoring the proposer right for the wrong reason. `restart_service` compares nothing and
recreates the service under whatever it currently runs, override included — a restart that also
reverted would be two actions under one name. `scale_service` refuses with ADR-0029's reason.

`ComposeCli.declared_definition` renders `docker compose config --format json` over exactly
`InjectorSettings.compose_files`; `DockerCli.running_definition` reads one `docker inspect`. Both
live in the injector's client module because that is where the credential already is.

## 3. The coupling — the second thing

Because the world has one change mechanism, **an executed rollback and an injector revert are the
same recreate.** Left alone, the injector's state file would still list the fault; `faultline-inject
stop --all` would recreate the service a second time and count a revert the executor had already
performed — a recovery misattributed to the harness. `Engine.acknowledge_external_restore(service)`
is the seam: after a successful `recreate_declared`, the executor tells the injector, which drops
the entries a recreate-from-declared made moot - the override-file restores (config, image, CPU
quota) *and* the live memory limit set by `docker update`, which a recreate resets to the declared
limit - removes their override files, emits the stop record change history would have carried,
and **recreates nothing**. A traffic-shaping sidecar on the same service is a different restore
kind and stays active, because the executor did not touch it.

The inverse the audit records is the override file's contents where one was in force; for a live
memory change there is no file, and the inverse is the running values that differed from the
declared definition, which is what `docker update --memory <running>` would need.


## 4. The token

HMAC-SHA256 over a JSON payload of `token_id`, `incident_id`, `proposal_id`, `action_id`, canonical
`target`, `catalog_version`, `confirm_within_seconds`, `issued_at`, `expires_at`; compared in
constant time; `<base64url(payload)>.<base64url(mac)>` and nothing negotiable. An empty key
refuses to sign or verify. Fifteen-minute TTL by default.

**Single use is the audit's job.** A token cannot know whether it has been presented; the ledger
can, and `spent(token_id)` looks for a row with a spending outcome. The two halves live in
different places on purpose: forging a token needs the key *and* a table that refuses edits. And
**a refusal does not spend the token** — a token refused because the kill switch was on is still a
valid approval once it is off; making the approver re-approve for the executor's own configuration
would be blaming the human for the machine.

## 5. The order — the safety argument, written down

`executor.core`'s docstring lists it and the tests hold it: kill switch; token shape; the incident
the token names, non-terminal; **blast radius before single-use and before the catalog** (the
proposal's failure table: *"action-target mismatch hard-rejects before the approval is even
requested"*); single use; catalog (exists, `available`, same `catalog_version`); drift; perform;
**record before advance**. A crash between the audit row and the state transition leaves a ledger
entry and not a moved incident with no record.

**Scope is recomputed, not stored — the third thing.** The pre-registration said *"as recorded on
the incident at synthesis"*; nothing on the trajectory records triage's radius, and adding a column
for it would have been a copy of a deterministic function's output. `Triage(catalog, hop_radius)
.run(incident)` is a pure function of the incident's episodes, the catalog snapshot and the radius,
and synthesis ran it on exactly those inputs; `incident_scope` runs it again and adds the alerting
services themselves. Same list, one column fewer.

## 6. The audit

`action_audit`, migration 0005: one row per attempt with five outcomes — `approved`, `refused`,
`kill_switch`, `executed`, `error` — and a `BEFORE UPDATE OR DELETE` trigger that raises
`insufficient_privilege` whoever the caller is. A trigger and not a `REVOKE`, because the
application role owns the table and an owner can grant back what was revoked.
`tests/test_integration_executor.py` tries both statements against real Postgres and expects the
refusal. The token's *id* is in the row; the token never is.

## 7. The state machine — the fourth thing

ADR-0016's table had `PROPOSING → AWAITING_APPROVAL` and nothing else into that state. The
pre-registration's repair replay needs an incident **no agent has investigated** to receive an
approved action, and so does any operator who wants to remediate by hand through the same executor
rather than around it. Addendum 4 adds `TRIAGING → AWAITING_APPROVAL` — from `TRIAGING` only, the
one non-terminal state in which no investigation is running that could later try to move the
incident somewhere else. `record_approval_outcome` is built: `approved` → `AWAITING_APPROVAL`,
`executed` → `EXECUTING`, `failed` → `FAILED`, `refused` → no move. `EXECUTING → RESOLVED` is the
orchestrator's ordinary alert-resolution path; the executor does not declare recovery.

## 8. What is deliberately not here

No autonomous path, no confidence threshold, no retry of a failed action (ADR-0028 §2 — an
`error` spends the token and fails the incident). No route that mints, lists or revokes on the
served endpoint; minting is `faultline-approve`'s (and T6.3's button), and the ledger is read from
the database. No observation of the execution's result re-enters any agent context: the agent that
wrote the proposal has finished before anyone can approve it (T7.50 §2's sequencing argument, now
load-bearing). And nothing that changes any published diagnosis figure — the repair replay the
pre-registration §4 describes is a different benchmark under a different name.

## Consequences

- The plan's flagship safety sentence — *even a fully prompt-injected investigation agent cannot
  execute a write, because the tokens it holds cannot* — is now a statement about a system that
  exists, and `THREAT-MODEL.md` thesis 2 is rewritten from "there is no executor" to what actually
  holds.
- The deployment gains a container with the socket and the kill switch on. It can refuse, record,
  and prove it cannot be reached from Caddy; it cannot act until T6.3 lands a surface and the
  switch is turned off in the same PR.
- `deploy/.env` gains three mandatory values: the token key, the socket's group id, and the
  checkout path the executor mounts at the host's own path so override files resolve identically.
- The image gains the Docker CLI and the compose plugin, pinned, for one process's use.

## Revisit if

T6.3 lands (the kill switch, the approval surface, the rejection loop); a real CD system ever
exists in this world (then §2's "declared definition" is not the previous state and
`rollback_image` needs an argument); or a second executor is proposed for a second world.

## Addendum 1 (2026-09-11) — the replay's two corrections: a stopped service is drift, and the proof's order

**Running state joins the drift check.** The repair replay's second triple, `cart-bad-image-tag →
rollback_image`, was refused as *no drift on image*. The injector stops the container first and
fails the recreate with a tag that resolves nowhere, so the only cartservice container is the old
healthy one, stopped, wearing the declared image - and §2's drift model compared image,
environment and limits and never asked whether the service was up. `DockerCli.running_definition`
now reads `State.Running` and reports a missing container as not running and not existing;
`ComposeCli.declared_definition` declares `running: True`, because compose has no vocabulary for
"stopped"; `running` is a drift field for both `rollback_image` and `revert_config`. The agent's
proposal had been right; the executor's model of the world was one field short, and the measurement
is what found it. `REPLAY-2026-09-11-t6.2.md` §3 pre-registers the second attempt.

**The proof's refusals are presented before the recovery wait.** The first live proof presented the
replayed token and the wrong-target token after the world had recovered; the orchestrator had
resolved the incident by then and §5's order refused both at step 3 - *incident is resolved* - before
single-use or scope were reached. Three refusals fired and two demonstrated the wrong property. The
driver now presents them while the incident is `EXECUTING`; the tests hold the order; the second
attempt is pre-registered in the same document. §5's order itself is unchanged - a terminal incident
*should* refuse before anything else is considered - what changed is when the demonstration asks.

## Addendum 2 (2026-09-11) — one action per incident is the executor's rule too

The proof's second run minted a fresh approval for an incident already `EXECUTING`, and the state
machine refused it: no `EXECUTING → AWAITING_APPROVAL` row. That refusal was ADR-0028 §5 - *one
proposal per incident, executed at most once* - being enforced by the only layer that happened to
be asked. It should not depend on which layer is asked. §5's order gains a clause at the single-use
step, after scope: an incident with an executed or errored action in `action_audit` refuses a second
token, naming the first action and its row. `faultline-approve` refuses to mint for an `EXECUTING`
or terminal incident and is idempotent for one awaiting approval - several tokens, each single-use,
no second transition. A second remediation goes through rejection and re-investigation (T6.3), never
through a second token.
