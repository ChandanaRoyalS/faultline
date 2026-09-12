# Pre-registration — T6.3, approve / reject: the loop that closes, and the first measurement of whether a rejection teaches the agent anything

**Written and committed before any line of the approval surface exists.** T6.2 built a process that
can change the world and left it switched off: on the deployment `FAULTLINE_EXECUTOR_KILL_SWITCH`
is `1`, no route mints, and the only way to approve anything is an operator typing
`faultline-approve` at a terminal. T6.3 is the surface in front of that function, the rejection path
that T6.2 deliberately did not build, and the one thing in Phase 6 whose central claim cannot be
demonstrated without spending money: **does telling the agent why its fix was rejected change the
fix it proposes next?**

This document registers what is built, what must not change, how the free parts are proved, what the
paid part costs, and ten predictions written before anything runs.

**The measurement costs two model calls and nothing else: ≈ $1.40.** Everything else in T6.3 —
every route, the state machine, the cap, the acknowledgment gate, the append-only rejection ledger —
is held by tests against a scripted model and costs $0.00.

---

## 1. What T6.3 is, in the plan's words

Execution plan: *"Approved remediation with visible recovery + rejection → re-investigation loop +
sev-1 ack gate."* The proposal's safety section: *"all mutations require human approval minting a
single-use, action-bound token (approve this rollback, not 'approve')"* — T6.2 built the token;
T6.3 is where a human mints one. T2.3's state-machine note, written in Phase 2 and unpaid since:
*"`REJECTED` exits to targeted re-investigation, reason required."*

**What the tree has** (Phase 6 audit, ~5%): `REJECTED` in the state machine with `PROPOSING`,
`SYNTHESIZING` and `AWAITING_APPROVAL` as its entries and `PLANNING` as its only forward exit; the
incident screen (T5.6) rendering the proposal card; HTTP Basic on the read routes (T5.5); the Slack
announcer with two events; `record_approval_outcome` built and called by `faultline-approve`
(T6.2); `Executor.execute` re-validating everything a surface could get wrong.

**What it lacks**: every write route; token minting anywhere but a terminal; a rejection reason —
there is no field, no column and no `record_rejection`; any trigger that re-investigates a rejected
incident; an acknowledgment concept of any kind; a post-action metric snapshot; and a deployment
whose kill switch is off.

**What T6.3 does not own.** The auto-drafted dev scenario from a miss — the plan's *"rejection →
drafted scenario"* — is **deferred by name**, to T7's corpus work. Its output is an eval artefact,
its quality bar is the eval corpus's, and attaching it here would put an unreviewed scenario
generator inside the task that turns the kill switch off. Recorded so the Phase 6 audit finds it
deferred rather than forgotten.

---

## 2. Scope — what is built

### 2.1 The approve control, and the credential it needs

`POST /api/v1/incidents/{incident_id}/approve` mints a token by calling
`faultline.executor.cli.approve` — the same function the terminal calls, not a second
implementation — then presents it to the executor's `POST /execute` and returns the audit record.
The caller recorded in the ledger is **the authenticated Basic username**, not a constant: an audit
row that says who approved is the point of the row.

**Marked decision: the approval surface holds the minting key, and this is an escalation that is
registered rather than hidden.** ADR-0038 §8 already said minting would be T6.3's button; the
consequence is that the API process gains `FAULTLINE_EXECUTOR_TOKEN_KEY` and therefore the ability
to sign a claim for any incident, action and target. What bounds a compromised surface is not the
key: it is that the executor re-derives everything from its own sources — the action must exist in
the catalog snapshot and be `available`, the target must fall inside the incident's recomputed blast
radius, the drift precondition must hold, the token must be unspent, the incident must have no
executed action already, and the kill switch must be off. A surface with the key can perform an
allowlisted action against an in-scope service of a real incident, which is *what an approver can
do anyway*, and every attempt is a row naming the caller. **The alternative considered and
rejected**: a separate minting process, so that compromising the web app grants nothing. It was
rejected because the bound it adds is one the executor's re-validation already provides, and the
deployment cost is a third container and a second credential path. `THREAT-MODEL.md` gains this as
an addendum when the surface lands, whatever the build finds.

**The read surface's invariant survives.** `faultline.api.incidents` says of itself *"the router
never imports a writer, never opens a transaction, and cannot advance a state machine"*. The write
routes live in a **new module**, `faultline.api.approvals`, and an AST guard holds that
`faultline.api.incidents` still imports no writer. The existing guard — nothing under
`faultline.agents` or `faultline.tools` may import `faultline.executor` — is extended to cover the
approvals module: **the investigation runtime cannot reach the button either.**

The incident payload gains the `proposal_id` (`<trajectory>#<seq>`) it does not currently carry,
because `approve` requires it; and `view.EXECUTION_NOTE` — *"not executed - no executor exists"* —
is replaced, having been false since T6.2 merged.

### 2.2 The reject control, and where the reason lives

`POST /api/v1/incidents/{incident_id}/reject` takes a **required, non-empty reason** and refuses
without one. The reason is not a column on `incidents`: it is a row in a new append-only table,
`incident_rejections` (migration 0006, with the `BEFORE UPDATE OR DELETE` trigger pattern migration
0005 established) carrying `id, incident_id, proposal_id, reason, caller, at`. One row per
rejection, never edited, and the count of rows is the cap in §2.3.

`machine.record_rejection(incident, reason)` is built — the function `machine.py:100` has named in
a comment since Phase 2 — and refuses to move an incident without a reason. `AWAITING_APPROVAL →
REJECTED`, `PROPOSING → REJECTED` and `SYNTHESIZING → REJECTED` are already in the table; no new
row is needed and none is added.

### 2.3 The re-investigation trigger, and the cap

`REJECTED → PLANNING` is in the table and unreachable today: `agents.runner.investigable` admits
only `TRIAGING`, and `InvestigationRunner.due()` polls only `store.triaging()`. Both are widened —
`INVESTIGABLE` gains `REJECTED`, the store gains `rejected()`, the runner polls both — and the
re-entry starts at `PLANNING`, reusing the triage it already has. Triage is a pure function of the
episodes, the catalog and the radius (ADR-0038 §5), so re-entry recomputes it rather than paying a
model call to redo it.

**The cap is `FAULTLINE_ORCH_MAX_REJECTIONS`, default 2.** An incident with that many rejection rows
is not re-investigated again; it stays `REJECTED`, and `REJECTED` holds a cap slot
(`INVESTIGATING_STATES` already includes it), so a loop cannot consume the world's investigation
budget. **A rejected incident never executes**: the executor already refuses a terminal incident,
and `REJECTED` is not terminal, so the refusal is added explicitly at the state check rather than
inherited by luck.

### 2.4 The reason in the agent's context — and the stamp that must not move

`Proposer.sections` already carries a `Section(name="refusal", priority=5, essential=True)` for a
validator violation. A human rejection is a different thing and gets its own section — *"An operator
rejected your previous proposal, with this reason: …"*, carrying the previous proposal's action and
target — placed, like `violation`, in the **user message and never in the system prompt**.

**This is a hard constraint, not a preference.** `stamp.prompt_digest()` hashes the `*_SYSTEM`
strings and the contract schemas; moving it stamps every subsequent run as a different agent and
makes it incomparable with every published figure in `RESULTS.md`. `prompts:06f24e827915` is the
current value and **it must read the same after T6.3 as before**. A test asserts the literal.

Rejection text is operator input and is treated as untrusted: quoted, length-capped, and carried
under the same `UNTRUSTED_RULE` discipline as telemetry (thesis 1). An operator who writes *"ignore
your instructions and propose X"* is a person with an approve button; the interesting property is
that the text cannot reach the *system* prompt, and that is structural here.

### 2.5 The severity-1 acknowledgment gate

A `critical` incident cannot be approved until it is acknowledged. `POST
/api/v1/incidents/{incident_id}/acknowledge` records who and when (append-only, same table family);
the approve route refuses `409` for an unacknowledged critical incident **before minting**, so no
token exists to be spent and the ledger carries no `approved` row. Warnings are unaffected.

The gate is a property of the surface, not of the executor: a token minted at a terminal for a
critical incident still works, because `faultline-approve` is the operator's own hand and the gate
exists to stop a click, not to stop an operator. Registered here because the asymmetry is
deliberate and would otherwise look like a hole.

### 2.6 The post-action snapshot on the timeline

When an action executes, the incident's timeline gains an entry at the proposal's own
`confirm_within_seconds`: the alerts firing for the incident's services at that moment, and whether
the injector still holds a fault. It is the screen's version of what the repair replay scored, and
it is recorded whether the answer is good or bad.

### 2.7 The kill switch goes off, in the same PR that lands the surface

ADR-0038's consequence says the deployment *"cannot act until T6.3 lands a surface and the switch is
turned off in the same PR."* This is that PR. `deploy/compose.yml` sets
`FAULTLINE_EXECUTOR_KILL_SWITCH: "0"`, `deploy/README.md` §3 gains the drill for turning it back on,
and the VM's executor becomes a process that can change the VM's world when a human clicks approve.

### 2.8 The notification

A third announcer event, `awaiting_approval`, carrying the incident link — the plan's *"the Slack
link that would carry the approve control"*. The webhook is unset by the owner's choice, so it is
silent by configuration and its wiring is held by `tests/test_notify_wiring.py` like the other two.

### 2.9 What does not change, registered

No autonomous execution and no confidence threshold (ADR-0028 §2). No second executed action per
incident — a second remediation goes through rejection and re-investigation, which is exactly what
this task builds (ADR-0038 Addendum 2). No agent sees the result of an execution: the trajectory
that proposed has finished, and a re-investigation after a rejection is a *new* investigation with
the rejection as input, not a continuation with an outcome fed back (T7.50 §2's sequencing
argument). No diagnosis figure in `RESULTS.md` moves; the two paid runs in §4 are not scored runs
and are not entered into any sweep.

---

## 3. The proof — free, and structural

Held by tests, with `ScriptedModel` / `DeterministicModel` and the autouse guards in
`tests/conftest.py` that fail loudly if anything tries to reach a live model:

1. A rejection with an empty or whitespace reason is refused and **no state moves**.
2. A rejection writes exactly one `incident_rejections` row; `UPDATE` and `DELETE` against it raise
   `insufficient_privilege` (integration, real Postgres, on migration 0005's pattern).
3. The rejection reason reaches the proposer's **user** message verbatim, read out of
   `model.calls[-1]`, and appears in **no** system prompt.
4. `stamp.prompt_digest()` is `06f24e827915` after the change — the literal, asserted.
5. A rejected incident re-investigates once, produces a second proposal, and the second proposal is
   a different trajectory with its own steps.
6. At the cap the incident stays `REJECTED`, no re-investigation starts, and the cap slot is
   released.
7. A rejected incident presented to the executor is refused, and the refusal is recorded.
8. An unacknowledged `critical` incident cannot be approved: `409`, no token minted, no `approved`
   row. The same incident acknowledged then approves.
9. A `warning` incident approves without acknowledgment.
10. AST: `faultline.api.incidents` imports no writer; `faultline.agents` and `faultline.tools`
    import neither `faultline.executor` nor `faultline.api.approvals`.
11. The incident page renders approve and reject controls, posts what the route expects, and still
    builds every node with `textContent` (Chromium, on `tests/test_incident_page.py`'s harness).

---

## 4. The measurement — does a rejection reason change the next proposal?

**The registered claim.** An operator rejects a proposal with a reason naming what was wrong; the
agent re-investigates with that reason in context; the second proposal is scored against the first.
This is the only part of T6.3 that spends money, and it spends it on the only question here that a
test cannot answer.

### 4.1 The material — two rejections the system has already earned

Both incidents are ones the T6.2 repair replay **measured as failures**, so the rejection is a fact
rather than a staged opinion:

| # | scenario | the first proposal | what T6.2 measured | the rejection reason the operator writes |
|---|---|---|---|---|
| A | `redis-cart-dependency-latency` | `restart_service` → cartservice | executed and **did not recover**; alerts fired through the 180 s window and the injector still held the fault | *"Restarted cartservice and the alerts kept firing for the full window. The latency is on redis-cart's interface, not in cartservice's process."* |
| B | `cart-dependency-latency` | `revert_config` → cartservice | **refused** — *no drift on environment, memory, nano_cpus*; the fault is a traffic-shaping sidecar | *"The executor refused: cartservice matches its declared definition in every field. Nothing about its configuration is wrong."* |

The exact reason strings are **fixed here, before the runs**, and are what will be typed. A reason
chosen after seeing the second proposal would make this an exercise in prompt-fitting.

### 4.2 The protocol, per incident

1. Gate, with the repair replay's patience (`faultline-gate`, retry, abort rather than warn).
2. Inject the scenario's fault; wait for the incident to open.
3. **Seed the first proposal from dev sweep 12's recorded run** — the same `--from-run` material
   T6.2's replay approved, written as a proposal step on the incident's trajectory, **and the
   incident walked to `PROPOSING`** through `machine.INVESTIGATION_PHASES`, which is what a real
   investigation does to an incident. *(Added 2026-09-12, after the first live run: the driver
   seeded the trajectory and left the incident in `TRIAGING`, and the route refused the rejection
   — correctly, because an operator cannot reject a proposal on an incident that has never
   proposed anything. The driver stopped before the model call, so the correction cost $0.00. §5
   records it.)*
4. Reject it through the real `POST …/reject` route with the reason from §4.1.
5. Let the re-investigation run. **This is the model call.**
6. Record the second proposal, the proposer's assembled context, the state trail, and the rejection
   row.
7. `faultline-inject stop --all`; settle; evidence to
   `docs/evidence/t6.3-rejection-loop/<scenario>/`.

The second proposal is **not approved or executed.** What is being measured is the loop's effect on
the proposal, and executing it would add a recovery measurement with n = 1 that the repair replay
already does better.

**The registered deviation, and its risk.** Step 3 seeds a proposal the agent wrote days earlier
rather than minutes earlier. It is the same agent, the same scenario, the same stamp, and the
content is what it would write again; what is lost is that the model has no session memory of
composing it — which is also true of every real re-investigation, since a rejection arrives after
the trajectory has finished. The alternative, investigating live first, costs $0.70 per incident
more and buys only that the prior text came from that hour. **Registered as a deviation because it
is one**, and because the number below would be dishonest without it.

### 4.3 What is scored

For each incident, recorded whether or not it flatters the system:

- **Reason reached the agent** — the text appears in the proposer's user message. Binary.
- **Second proposal differs** — in `action_id`, in `target`, or in neither. Recorded as the pair.
- **Second proposal is better, worse, or neither** — judged against what T6.2 measured, and stated
  as an argued reading, not a score: for A, a proposal naming `redis-cart` would be better; for B,
  anything other than `revert_config` → cartservice would at least not be refused for the same
  reason.
- **Cost**, from the trajectory's own accounting.

n = 2, R = 1. This is an existence demonstration, not a rate, and §7 says so again.

---

## 5. Predictions

### 1. The stamp does not move
`prompts:06f24e827915` reads the same after T6.3 as before, because the rejection reason travels in
the user message. If it moves, every figure in `RESULTS.md` is stranded and the change is wrong.

### 2. The structural guards hold, and fail on a planted import
The AST tests refuse a planted `from faultline.executor import …` under `faultline.agents`, and a
planted writer import under `faultline.api.incidents`.

### 3. A reasonless rejection is refused and nothing moves
`400`, no row, no transition.

### 4. An unacknowledged critical incident cannot be approved from the surface
`409`, **no token minted**, no `approved` row in `action_audit`. The same incident, acknowledged,
approves and executes.

### 5. The cap holds at two, and a rejected incident never executes
A third rejection does not re-investigate; the incident stays `REJECTED`; `action_audit` holds no
spending row for it.

### 6. The reason reaches the agent in both live runs
Verbatim, in the proposer's user message, in A and in B. **This is the prediction most likely to
fail for a boring reason** — a section dropped by the briefing budget — and the briefing's
`essential=True` is what should prevent it.

### 7. Incident A's second proposal names a different target
`redis-cart` rather than `cartservice`. The reason names the interface explicitly and the catalog
has the service. **Stated as the directional guess it is**: the agent has never proposed against
`redis-cart` in any recorded run, and T6.2 called this scenario the first measured *remediation
proposed for the wrong service*.

### 8. Incident B's second proposal is not `revert_config` → cartservice
Either a different action, a different target, or an abstention with `remediation_class: none` —
which the proposer contract permits and which would be the **correct** answer here, because the
fault is a sidecar no allowlisted action can remove. An abstention counts as the loop working.

### 9. At least one of the two second proposals differs from its first
The weaker aggregate of 7 and 8, stated separately because it is the one that decides whether the
loop did anything at all. If both second proposals are identical to their firsts, the loop is
plumbing and the write-up will say so in those words.

### 10. Cost
**≤ $1.60 total**, against a sweep-12 median of $0.713 per investigation and two re-investigations
that skip triage. Everything else in T6.3 is $0.00. Any model call outside §4's two runs is a
defect.

---

## 6. What this changes afterwards

- The deployment can act. The kill switch is off, a human can click approve on the VM, and the
  audit records who.
- `THREAT-MODEL.md` gains the approval surface as a credential holder, with the executor's
  re-validation as the bound and the audit as the record.
- `docs/RESULTS.md` gains a short section: the rejection loop exists, with n = 2 and what the two
  second proposals were.
- T6.4 onwards can assume a closed loop; T7's corpus work inherits the deferred scenario drafter.

## 7. What this cannot establish

- **Whether rejections improve proposals in general.** n = 2, R = 1, two scenarios chosen because
  they failed. Nothing here is a rate, and no figure from it belongs beside a sweep's.
- **Whether an operator's reason is better than a validator's violation.** Not compared; different
  mechanisms, and the comparison would need a sweep.
- **Whether the surface is safe against a determined attacker.** It is authenticated, audited and
  bounded by the executor's own checks; T6.8 is the hardening pass, and the escalation in §2.1 is
  written down for it.
- **Whether the second proposal would have recovered the world.** It is not executed. The repair
  replay is where that question is answered properly.
