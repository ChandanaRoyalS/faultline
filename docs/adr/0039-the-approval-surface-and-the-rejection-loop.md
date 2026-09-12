# ADR-0039: The approval surface, the rejection loop, and what the measurement changed

- **Status:** accepted
- **Date:** 2026-09-12
- **Task:** T6.3 (approve / reject UX)
- **Relates to:** ADR-0038 (the executor — this is the surface its consequence said it would take),
  ADR-0028 (the proposer; §5's one action per incident), ADR-0016 (the state machine; `REJECTED`
  has been in its table since Phase 2 with nothing able to walk it), ADR-0032 (the allowlist),
  ADR-0022 §1.2 (an abstention is a proposal), `evals/runs/PREREGISTRATION-T6.3.md` (written first;
  this ADR is held to it), `evals/runs/LOOP-2026-09-12-t6.3.md` (the measurement)

## Context

T6.2 built a process that can change the world and left it switched off. T2.3 wrote *"`REJECTED`
exits to targeted re-investigation, reason required"* in Phase 2, and for four phases there was
nowhere to put a reason, so the only forward edge out of `REJECTED` was unreachable. T6.3 is the
surface in front of the executor, the rejection path, and the deployment's kill switch going off.

## 1. Where the write routes live, and why not beside the read ones

`faultline.api.incidents` says of itself: *"the router never imports a writer, never opens a
transaction, and cannot advance a state machine."* That sentence was worth keeping true, so the
write routes are a **different module** — `faultline.api.approvals` — behind the same credential on
the same process, and `tests/test_executor_boundary.py` holds both halves by AST: the read surface
imports no writer, and the investigation runtime imports neither the executor nor the approval
router. **The agent cannot reach the button any more than it can reach the socket.**

Approve calls `executor.cli.approve` — the same function the terminal calls, not a second
implementation — so a rule added there (one action per incident, ADR-0038 Addendum 2) is a rule the
button obeys without being told. The token is presented to the executor over HTTP, because the
executor is the container with the Docker socket and the web process must never be; it is never
returned to the browser, which has no use for a bearer credential.

**The caller recorded in the ledger is the authenticated username**, taken from the dependency that
verified the credential. An audit row that says *who approved* is the point of the row, and a
caller a request body could claim would not be one.

## 2. The escalation, registered before the build

**The approval surface holds the minting key.** `PREREGISTRATION-T6.3.md` §2.1 says so and
`THREAT-MODEL.md` thesis 2 now records it: the web process can sign a claim for any incident, action
and target. What bounds a compromised surface is **not the key** — it is the executor re-deriving
everything from its own sources (catalog, blast radius, drift, single use, one action per incident,
kill switch). A key-holder can do what an approver can do on a real incident and nothing else, and
every attempt is a row naming the caller.

A separate minting process was considered and rejected: the bound it adds is one the re-validation
already provides, at the cost of a third container and a second credential path. **Revisit if** the
surface ever gains a second authentication mechanism, or T6.8 finds the Basic credential
insufficient.

## 3. The rejection is a ledger, not a flag

`incident_rejections` (migration 0006), append-only at the database on migration 0005's pattern:
one row per rejection, never a column holding the latest. The second rejection of an incident is the
interesting one — it says the re-investigation did not help — and a column would overwrite the
first. The count of rows **is** the re-investigation cap (`FAULTLINE_ORCH_MAX_REJECTIONS`, default
2), so the ledger is load-bearing rather than decorative.

`machine.record_rejection` will not move an incident without a reason, and refuses to reject one
that is `EXECUTING` — in the machine rather than at the route, on ADR-0038 Addendum 2's lesson that
a rule enforced by whichever layer happens to be asked is a rule about that layer.

## 4. The reason reaches the agent in the user message, and this is not a preference

`stamp.prompt_digest()` hashes the `*_SYSTEM` prompts and the contract schemas. Operator text in
`PROPOSER_SYSTEM` would move it and strand every figure in `RESULTS.md`, which were all measured
under `prompts:06f24e827915`. And operator text is **untrusted input** — a person with an approve
button is still a person typing into a box that reaches a model — and the system prompt is the one
place this system never puts untrusted input (`THREAT-MODEL.md` thesis 1). The section is quoted,
capped, marked as evidence rather than as an order, and `essential=True`.

**That flag was load-bearing and the measurement proved it.** In both live runs the briefing budget
dropped `runbooks` — the largest block — to fit. An ordinary rejection section would have gone with
it, and the measurement would have silently scored an agent that was never told.

## 5. The kill switch

Off, on the deployment, in the PR that landed the surface — which is what ADR-0038's consequence
said it would take. `deploy/README.md` §3.11 is the drill for turning it back on: a `sed` and one
`up -d`, costing nothing and interrupting nothing, because investigation is unaffected and every
token presented while it is on is refused *and recorded*.

## 6. What the measurement changed — the fourth thing

`LOOP-2026-09-12-t6.3.md`. Three of four attempts stopped before the model call, each on a different
defect, for a total of $0.00; the fourth cost $1.43 and the reason reached the proposer in 2 of 2.

**The finding that matters for this ADR is the one about the instrument.** The first attempt's
rejection was refused because the driver had seeded a proposal onto a trajectory and left the
incident in `TRIAGING`. The available repair was to add `TRIAGING → REJECTED` to ADR-0016's table —
and that would have been **changing the product to fit the measurement**. The rule the machine was
applying is correct: an operator cannot reject a proposal on an incident that has never proposed
anything. T6.2 faced a superficially identical situation and went the other way — a stopped service
*was* drift, and the executor's model of the world really was one field short (ADR-0038 Addendum 1).
The difference is not a matter of taste. It is whether the system or the instrument is the one
describing the world wrongly, and it has to be asked each time.

**Both second proposals abstained**, and neither is an agent giving up: each names the true mechanism
(a traffic-shaping sidecar on a network namespace), says what would end the incident, says why that
is not an allowlisted action, carries a falsifier for the abstention itself, and states the cost of
not acting. One of them generalised from the operator's report — *"the operator already ran
restart_service and the latency persisted, and restart, revert_config and rollback_image all share
that same recreate mechanic"* — to rule out the entire remaining class of available actions. Nothing
in the brief said those three share a mechanic.

**ADR-0022 §1.2's position is strengthened and its scope is now visible**: an abstention is a
proposal, it is frequently the correct one under an allowlist, and a loop that can only be scored on
whether the agent named an action would have scored this run as two failures.

## Consequences

- The deployment can act: a click changes the VM's world, recorded, with the caller named.
- `REJECTED → PLANNING` is walkable after four phases, and `INVESTIGABLE` has two doors.
- Operator text now reaches a model on the ordinary path, which is a new class of input to the
  system and is treated as untrusted at every step.
- The rejection loop costs one investigation per rejection, which is the reason it has a cap and the
  reason the cap is configuration rather than a constant.
- `faultline-gate` stopped overclaiming (found sideways by this task; see the measurement §3).

## Revisit if

T6.8's hardening re-reads the surface's single Basic credential; a second executor or a second world
appears; the cap of two is ever reached in practice; or a sweep is funded that could turn §4's
existence demonstration into a rate.
