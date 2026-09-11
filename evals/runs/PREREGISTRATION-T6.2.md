# Pre-registration — T6.2, the action plane: an executor that can act, and the first measurement of whether the agent's fixes work

**Written and committed before any code of the executor exists.** T6.2 is the first Phase 6 task
that adds something the investigation runtime has never had near it — a process that can change the
world — and ADR-0028 §3 says why that is *"a second system"* and not a later commit in the first.
This document registers what the second system is, what it must never be, how it is proved, and
the one measurement it makes possible: **executing the proposals dev sweep 12 already recorded, once
each, against a fresh injection of the same fault, and scoring whether the world recovered.**

The measurement costs **no model calls**. The proposals exist; executing them is world time.

---

## 1. What T6.2 is, in the plan's words

Execution plan: *"A separate executor service holding the only write credentials: allowlisted,
parameter-validated actions (rollback, restart, flag toggle, scale) executed only with a valid
single-use approval token; append-only audit; kill switch."* Why: *"The flagship safety mechanism:
even a fully prompt-injected investigation agent cannot execute a write, because the tokens it
holds cannot. Structural security, not prompt-level."* How: *"Process separation with distinct
credentials; action-bound tokens minted at approval time; blast-radius check re-validates the
target against incident scope; every executed action records its inverse where one exists,
enabling one-click revert."* Deliverable: *"Executor service + audit log + kill switch."*

Proposal, safety: *"all mutations require human approval minting a single-use, action-bound token
(approve this rollback, not 'approve')"*; *"append-only audit table; every executed action records
its inverse where one exists; kill switch env flag that halts all execution while leaving
investigation running."*

**What the tree has** (Phase 6 audit, ~10%): the allowlist as a read-only versioned document with
four classes and `scale` recorded as unperformable (ADR-0032, ADR-0029); the proposer validated
against it (T3.9, ADR-0028); `AWAITING_APPROVAL` / `EXECUTING` in the state machine with
`record_approval_outcome` a stub that names this task; `Proposal` carrying `action_id`, `target`,
`expected_effect`, `confirm_within_seconds`, `if_wrong`, `risk`, `blast_radius`. **What it lacks**:
everything that acts.

**What T6.3 owns and this does not**: the approve and reject surface in the UI and Slack, the
rejection reason, the re-investigation trigger, the drafted scenario, the sev-1 acknowledgment gate.
T6.2 ships the token's mint and verify as a library plus one operator command, so that the executor
can be proved without a UI; T6.3 puts a button in front of the same function.

---

## 2. Scope — what is built

### 2.1 The executor, a separate process

`faultline-execute`: a process that reads approved actions and performs them. It is the **only**
thing in the product that holds the world's write credential, which in this world is access to the
Docker socket and the world's compose files — the same credential the injector holds as the
harness's chaos tool, and the one the investigation runtime has never held (ADR-0019 §4, ADR-0028
§3). In the deployment it is its own container with the socket mounted; `faultline`, `orchestrator`
and `caddy` mount nothing of the kind, and a test says so.

**The investigation runtime gains no import path to it.** `faultline.agents` and `faultline.tools`
may not import `faultline.executor`, `injector.docker` or `subprocess`; an AST guard in the tests
holds this, on the model of `tests/test_allowlist.py`.

### 2.2 What an action does in this world — registered here because it is not obvious

The world has no CD system. Every change it has ever seen is a compose override the injector wrote
and a container it recreated (`_ComposeOverrideFault`), or a traffic-shaping sidecar it attached.
**So "the previous image" and "the previous configuration" are not in change history** — every
record the injector emits carries `before=None` (`injector.changelog.describe`), deliberately, and
the allowlist's preconditions *"a prior image tag … is recorded in change history"* can never be
met by reading them. This was not known when ADR-0032 wrote those preconditions, and it is a
finding of this pre-registration rather than of the build.

**Marked decision: the prior state is the world's declared definition.** `rollback_image` and
`revert_config` recreate the target from the three hashed compose files with no generated override
— which is what a rollback to the last known-good definition means when the definition is in git.
The precondition is evaluated as **drift**: the running container's image or environment differs
from what the declared definition would produce. No drift, no rollback: refused `unexecutable`,
with the diff that was empty. `restart_service` recreates the target under whatever it currently
runs — override included — because a restart that also reverted would be two actions under one
name. `scale_service` refuses as the catalog says (ADR-0029). Nothing else exists.

**This makes the executor's rollback and the injector's revert the same operation on the same
world**, and they must agree about it: an executed rollback records itself in the injector's state
so that `faultline-inject stop` does not later "revert" a fault that is already gone and count it
as a revert. That coupling is the price of a world with one change mechanism; ADR-0038 (written with
the build) records it.

### 2.3 The token

Single-use and action-bound: an HMAC over `incident_id`, `proposal_id`, `action_id`, canonical
`target`, `catalog_version` and an expiry, under a key only the executor and the minting side hold.
Verified on every execution: the token names *this* proposal's action against *this* target under
*this* catalog, has not been used, and has not expired. A token for a rollback is not a token for a
restart; a token minted under `catalog_version: 1` is refused after the catalog moves (ADR-0032's
*"pin it per approval"*). Used tokens are recorded, so replay is refused with the first use named.

### 2.4 Blast radius, re-validated at execution

The proposal's `target` is canonicalised (`injector.world.canonical_service`) and must be in the
incident's scoped topology — the services the alert and its dependency-graph neighbourhood name,
as recorded on the incident at synthesis. A target outside that set is refused before the token is
even checked, which is the order the proposal's failure table specifies (*"Action-target mismatch
hard-rejects before the approval is even requested"*).

### 2.5 The audit, append-only

`action_audit`: one row per attempt — executed or refused — with the proposal, the token's id (never
the token), the caller, the incident, the exact compose command, its exit, a hash of its output,
the refusal reason where there is one, and **the inverse** where one exists (`restart_service` has
none and says so; the other two record the override that was dropped, so the fault can be put back
for a re-test). Append-only is enforced at the database, not asserted in code: the migration grants
`INSERT` and `SELECT` on the table and revokes `UPDATE` and `DELETE` from the application role, and
a test tries both and expects the refusal.

### 2.6 The kill switch

`FAULTLINE_EXECUTOR_KILL_SWITCH=1` refuses every execution with the reason *kill switch*, records
the refusal in the audit, and changes nothing about investigation — the orchestrator keeps opening,
the agent keeps proposing, incidents reach `AWAITING_APPROVAL` and stay there. **On the deployment
it is on by default until T6.3 exists**, because a deployment with an executor and no approval
surface has no legitimate path to a token, and a switch that is off in that state is a switch
nobody would notice being off.

### 2.7 The state machine

`record_approval_outcome` is built: `PROPOSING → AWAITING_APPROVAL` when a proposal exists and the
agent's turn has ended; `AWAITING_APPROVAL → EXECUTING` on a verified token; `EXECUTING → RESOLVED`
on an executed action whose `expected_effect` window has elapsed, or `→ FAILED` on an execution
error, with the audit row named in the trigger. Refusals leave the incident in `AWAITING_APPROVAL`.

### 2.8 What does not change, registered

- **The stamp does not move.** No prompt changes, no contract changes: `prompts:06f24e827915`
  stays, and every dev sweep 12 run remains comparable with everything after. A stamp move here
  would mean the executor reached into the investigation runtime, which is the one thing it must
  not do.
- **The world does not move.** No compose file in the digest changes; `90e9f29e578e` stays.
- **The tool surface does not change.** `cap:dd651ccc` stays; the agent gains no tool.
- **No published figure changes.** Every fix-class number keeps its meaning — *the agent named a
  fix* (ADR-0028 §4) — and the measurement in §4 is a different benchmark with a different name.

---

## 3. The proof — structural, and free

What T6.2 delivers is a property, and properties are proved by tests that try to violate them:

1. the investigation runtime cannot reach the executor (AST guard, three forbidden imports);
2. a replayed token is refused, naming its first use;
3. a token for another target, another action, another incident, or an older catalog is refused;
4. a target outside the incident's scope is refused before token verification;
5. the kill switch refuses and records while `record_agent_outcome` keeps advancing incidents;
6. `UPDATE` and `DELETE` on `action_audit` are refused by the database;
7. every executed action's row carries an inverse or the string `no inverse: <reason>`;
8. `scale_service` refuses with ADR-0029's reason;
9. in `deploy/compose.yml`, exactly one service mounts the Docker socket and it is `executor`.

Then one live proof on the development Mac, recorded in `docs/evidence/t6.2-first-execution/`:
inject `shipping-wrong-image`, wait for the incident, mint a token for the recorded proposal
`rollback_image → shippingservice` from run `20260909T105155Z`, execute, and watch: the audit row,
the inverse, the recreate, the alert resolving, `faultline-inject stop` finding nothing to revert.
Then the same token again (refused), the kill switch (refused), and the wrong target (refused).
**No model call in any of it.**

---

## 4. The measurement — do the agent's fixes work?

This is the *repair* benchmark `docs/design/t7.50-action-plane-vs-oracle.md` §4 calls design C:
*"separate a diagnosis benchmark from a repair benchmark, scored apart."* It has never been
measured because nothing could act. It is scoreable from what the proposal already carries — the
`expected_effect` predicate and `confirm_within_seconds` — and from what the harness already knows:
the injector knows what it injected and whether it is still in force.

**It is not a loop.** Every proposal was written by an agent that could not act and whose turn had
ended (ADR-0028 §5, T7.50 §2). Executing it later, against a fresh injection, with no agent running,
observes nothing back into any context. Diagnosis figures are untouched by construction.

### 4.1 The material

Dev sweep 12, arm A (the full pipeline), 45 scored runs across the two attempts (15 + 30):
**25 executable proposals and 20 abstentions.** The executable ones are 16 `revert_config`, 7
`rollback_image`, 2 `restart_service` — and they collapse to **nine distinct (scenario, action,
target) triples**, which is what is executed, once each:

| scenario | fault class | proposed action | target | runs proposing it |
|---|---|---|---|---|
| cart-bad-image-tag | bad_deploy | rollback_image | cartservice | 4 |
| shipping-wrong-image | bad_deploy | rollback_image | shippingservice | 3 |
| cart-redis-misconfig | bad_config | revert_config | cartservice | 3 |
| shipping-quote-misconfig | bad_config | revert_config | shippingservice | 3 |
| payment-telemetry-blackout | bad_config | revert_config | paymentservice | 2 |
| ad-memory-squeeze | resource_exhaustion | revert_config | adservice | 1 |
| frauddetection-memory-squeeze | resource_exhaustion | revert_config | frauddetectionservice | 4 |
| cart-dependency-latency | dependency_latency | revert_config | cartservice | 3 |
| redis-cart-dependency-latency | dependency_latency | restart_service | cartservice | 2 |

Abstentions are not executed; there is nothing to execute. The three `dependency_latency`
abstentions on `redis-cart` and the four on `product-catalog-flag-failure` are recorded as such.

### 4.2 The protocol, per triple

1. Baseline gate admits (`faultline-gate`).
2. Inject the scenario's fault; wait for the incident to open and the agent-free settle to pass —
   no investigation is run; the incident is opened by the world's own alert and left in `TRIAGING`.
3. Mint a token for the recorded proposal against this incident; execute.
4. Record the outcome as one of four, in this order of precedence:
   - **refused** — with the executor's reason (precondition, scope, token, kill switch);
   - **executed, recovered** — the incident's alerts resolve within the proposal's
     `confirm_within_seconds`, and the injector reports the fault no longer in force;
   - **executed, not recovered** — the action ran, the window elapsed, alerts still firing;
   - **error** — the compose command failed; the world is restored by hand before continuing.
5. `faultline-inject stop --all` (a no-op after a recovery, and the test of §2.2's coupling), then
   the 300 s settle.

About fifteen minutes a triple; **about two and a half hours of world time; $0.00 of model spend.**
Every step writes to `docs/evidence/t6.2-repair-replay/<scenario>/` — the token id, the audit row,
the alert timeline, the injector's state before and after.

### 4.3 What is scored

Per triple: the outcome above. In aggregate, **recovered / executable**, quoted with n = 9 and with
the refusals listed by reason beside it — never folded into a percentage as if a refusal were a
failure of the fix. A refusal on precondition is a fact about the executor's model of the world; a
refusal on scope is a fact about the proposer; neither is a fact about whether the fix would have
worked. R = 1 on a deterministic operation: the same override dropped twice recovers the same
world twice, so repeats measure the world's noise and not the executor's.

---

## 5. Predictions

Each with its consequence named.

### 1. The stamp, the world and the tool surface do not move
`prompts:06f24e827915`, `90e9f29e578e`, `cap:dd651ccc`, before and after. **Any movement is the
executor having reached into the runtime, and the build stops until the path is found and cut.**

### 2. The nine structural tests pass, and the AST guard fails on a planted import
Written to fail first: a one-line `import subprocess` planted in `faultline/tools/tools.py` must
turn the guard red before it is removed. A guard that has never been red has not been shown to see.

### 3. The live proof executes on the first attempt and refuses the three refusals
`rollback_image → shippingservice` on a fresh `shipping-wrong-image`: executed, recovered, inverse
recorded, `faultline-inject stop` finds nothing. **A recovery the injector still counts as a revert
is §2.2's coupling unbuilt, and it outranks the recovery.**

### 4. Both `rollback_image` triples recover
`cart-bad-image-tag` and `shipping-wrong-image`: the drift check sees the override's image, the
recreate from the declared definition restores the shop's image, the `ServiceHighErrorRate` alert
resolves inside 300 s. **2 of 2.**

### 5. Five of the six `revert_config` triples recover; the dependency-latency one is refused
`cart-redis-misconfig`, `shipping-quote-misconfig`, `payment-telemetry-blackout`,
`frauddetection-memory-squeeze`, `ad-memory-squeeze`: drift present, recreate restores, alerts
resolve — **5 of 5 recover** (four bad_config or resource_exhaustion faults are compose overrides
and one, `ad-memory-squeeze`, is too). **`cart-dependency-latency → revert_config → cartservice` is
refused on precondition**: the fault is a traffic-shaping sidecar on the network namespace, not an
override, so `cartservice` shows no drift and there is nothing to revert. This refusal is the
correct behaviour and a scored outcome, not an error — and it is the same fact prediction 5 of
T6.1 recorded from the other side: on the two `dependency_latency` scenarios the agent's fixes
were wrong in kind, and an executor that is honest about the world says so before doing anything.

### 6. `restart_service → cartservice` on `redis-cart-dependency-latency` executes and does not recover
There is no precondition to refuse on. The recreate runs; the latency is on `redis-cart`'s
interface, not in `cartservice`'s process; alerts keep firing through the window. **Executed, not
recovered** — the first measured instance of the failure table's *"remediation proposed for the
wrong service"*, and the reason the human stands between proposal and execution.

### 7. Aggregate: 7 recovered of 8 executed, 1 refused, 0 errors
Quoted as such, with the refusal beside it. **Zero errors is the prediction that matters**: an
error is the executor breaking the world it was asked to fix, and one error stops the replay.

### 8. Nothing in the replay changes any diagnosis figure
`faultline-eval-db load` after the replay changes no row of any existing run; README's table
regenerates byte-identical. **A moved row means the replay wrote into a run directory it had no
business in.**

### 9. The kill switch is on, on the deployment, and the deployment still investigates
After the redeploy that carries the executor: an incident opened on the VM reaches
`AWAITING_APPROVAL` and stays; the executor's audit shows the refusal; nothing changes in the world.

### 10. Cost
$0.00 of model spend across the build, the proof and the replay. World time about three hours on
the development Mac, plus the redeploy. **Any model call in this task is a defect** — there is no
role in it that should be asking a model anything.

---

## 6. What this changes afterwards

ADR-0038 records the executor's design with the build (§2.2's decision about prior state, the
token, the coupling with the injector). ADR-0028 §5 gains the amendment T7.50 queued — that the
oracle control is sequencing, not withholding — because the executor now exists and the sentence is
load-bearing. ADR-0032 gains an addendum correcting its preconditions to drift. `docs/RESULTS.md`
gains a section, *Repair replay — dev sweep 12's proposals, executed*, quoting §4.3's aggregate with
its refusals, clearly separated from every diagnosis figure and never in README's table. The Phase 6
audit row for T6.2 moves from ~10% to delivered or to what remains, on this document's reading.
`docs/THREAT-MODEL.md` thesis 2 is re-read against a system that can now act. T6.3's
pre-registration follows, with the approval surface, the rejection loop and the sev-1 gate.

## 7. What this cannot establish

Nothing about the proposer's *judgement* beyond what §4 scores — nine triples across four classes
is 1–2 per class. Nothing about `scale`, which this world cannot perform. Nothing about a real CD
system: in this world the declared definition and the last known-good are the same thing, and in
a world with a deploy history they are not, which is where a real `rollback_image` would read its
argument. Nothing about the human loop — no approval has been given by anyone through anything but
a command line until T6.3. And nothing that makes any existing number better: the diagnosis
benchmark is exactly as it was, and this document is the wall between it and the one it starts.
