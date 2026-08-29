# ADR-0028: The proposer, and what it would take to act

- **Status:** accepted (design; nothing built)
- **Date:** 2026-08-29
- **Task:** T7.18
- **Builds on:** ADR-0003 (runtime), ADR-0019 (tool layer), ADR-0020 (agent layer), ADR-0022 (scoring), ADR-0008 (contamination), ADR-0027 (two working fixes)

## Context

ADR-0020 designed nine roles and built eight. The proposer was left out and the action plane has
never had a task number. Its one-line sketch — *"Input: the RCA. Tools: none. Produces: a
remediation class and **a concrete action**"* — is the part of that ADR the record since has most
to say about, and this ADR disagrees with half of it.

T7.17 sharpened why it matters. Every fix-class number in this repository says the agent **named**
a fix. Not one says a fix was carried out, and T7.17 had to establish by hand — eight live
injections — that one of the named fixes even works. A benchmark that scores remediation without
ever executing one is scoring vocabulary.

## 1. What a proposal is

**A proposal is a falsifiable claim about a change, not the change.** Its shape:

| field | why |
|---|---|
| `remediation_class` | the scored label, one of ADR-0020's five |
| `target` | the service the change lands on, from the graph — **not free text** |
| `rests_on: list[result_id]` | the evidence, by id, resolvable against the stored envelope |
| `expected_effect` | what should be observed afterwards, as a predicate over telemetry the four tools can already reach |
| `confirm_within` | how long that should take, so "it did not work" is decidable rather than argued |
| `if_wrong` | what observation would falsify it |

**Not a command string, and the reason is not squeamishness.** Three arguments, in order of
weight:

**A command is not checkable and a predicate is.** `docker restart cart-service` can be diffed
against ground truth and nothing else. `expected_effect: cartservice p95 returns below 250ms
within 5 minutes` can be *evaluated against the world*, which is the only thing that would make
this benchmark measure remediation rather than phrasing. T7.17 is the demonstration: the question
"did the delay clear, and stay cleared" was answerable; "was the string right" would not have been.

**A command string is untrusted text with an execution path attached.** ADR-0019's whole leak
boundary rests on nothing constructing a path from agent input. A free-text command is exactly
that construction, arriving through the one role that was supposed to have no tools. §3.

**The four tools already define the vocabulary.** `expected_effect` is a predicate over PromQL and
LogQL — surfaces that exist, are read-only by construction, and are already how the harness decides
anything. A proposal that cannot express its expected effect in them is proposing something this
system cannot observe, and **that is a finding about the proposal**, not a gap to paper over with
prose. It is the same discipline T7.5 and T7.6 applied to narratives: say only what the tools can
reach.

**Marked decision — `target` is drawn from the dependency graph, not free text.** The alternative
(free string, validated later) was rejected for ADR-0011's reason: the world has two naming schemes
and they are not interchangeable. A proposer emitting `cartservice` where the action plane needs
`cart-service` is a class of failure worth designing out rather than measuring.

## 2. Whether the proposer acts — it does not

**Marked decision: the proposer proposes. A separate executor exists, and a human stands between
them. Approval is per-proposal, and there is no autonomous path.**

The argument, not the assertion:

**The system cannot yet tell a right proposal from a lucky one.** T7.17 measured a fault with two
working fixes and found the register had spent three stamps scoring one of them wrong. If the
project's own understanding of "which fix is correct" was wrong for that long with a human reading
every result, an automatic executor would have been acting on it throughout.

**Nothing in the record establishes a false-positive rate for proposals**, because no proposal has
ever been made. Approving a category of action requires knowing how often it is wrong; the number
does not exist and cannot be assumed. That is the same standard this repository applies to every
other figure.

**The blast radius of a wrong fix is not bounded by the fault.** `restart` on a misdiagnosed
service takes down something that was working. ADR-0013 measured the shape: a 0.02 CPU quota on
`frontend` produced twelve `ServiceNoTraffic` alerts and took the world down from the ingress. An
executor acting on a wrong `target` is that, with nobody having asked for it.

**What is never automatic:** any change to a world the agent did not itself provision. There is no
confidence threshold that promotes a proposal to an action. **A threshold would be the wrong
mechanism** — it makes the model's own calibration the safety boundary, and ADR-0020 already
declines to trust that anywhere else (it is why citations resolve against a store rather than being
believed).

**What a refusal looks like.** The executor refuses, records, and does not partially apply:

- **the proposal is unexecutable** — no executor exists for that `remediation_class`/`target`
  pair; refused as `unexecutable`, which is a *scored outcome* (§4), not an error
- **the world moved** — the baseline gate refuses, or the target's container id changed since the
  proposal was written, so the proposal describes a world that is gone
- **the evidence will not resolve** — a `result_id` in `rests_on` is not in the store, which is
  what a fabricated citation looks like (ADR-0020 §4's rule, reused rather than restated)
- **no approval** — the default, and the only one that needs no reason

A refusal is recorded with its reason and is **never** retried automatically. ADR-0003's bounded
re-ask is for schema violations, not for actions; re-asking an executor is a retry loop against a
live world.

## 3. The tool surface — a write tool does not belong in this runtime

This is the position ADR-0020's sketch most needs revising, and ADR-0019 supplies the argument.

**Read-only here is not enforced by credentials.** ADR-0019 §4 measured it: Prometheus runs with
`--web.enable-lifecycle` and Loki's push endpoint is open, both unauthenticated. *"Read-only is
therefore a property of the tool surface, not of the credential."* The only thing standing between
this agent and a write today is that **no tool constructs one**.

**So adding one write tool removes the property for the whole runtime, not for one role.** The four
specialists do not gain a capability by name — they gain one by *neighbourhood*. Everything about
the current safety story is structural ("nothing constructs a path from agent input"), and a
structural property has no per-role scope. Once the runtime can execute, "the metrics specialist
cannot write" becomes a policy claim about prompt text, which is the weakest kind, and the kind
ADR-0019 explicitly refused to rely on.

**The leak guard gets a second boundary it was not designed for.** It runs over finished prose and
asks *what would a responder never know* — the harness vocabulary and the four class labels. It has
nothing to say about an action. A proposal that names the injector's own vocabulary in its
`expected_effect` is a leak of the same kind, and the existing guard would not see it: it guards
the scribe's text, not a structured object. **Marked decision: the proposal contract is
leak-guarded on its free-text fields under the scribe's vocabulary rule, and its structured fields
are constrained enough not to need it.**

**Marked decision: the executor is a separate process with its own credentials, outside the
investigation runtime, and the investigation runtime gains no write tool.** The agent emits a
proposal as data; the executor is not reachable from agent context. This keeps ADR-0019's sentence
literally true rather than approximately true — the investigation runtime still holds a surface
with no write path — and it means a compromised investigation cannot act, only ask.

The rejected alternative is a fifth tool, `apply_remediation`, gated by an approval flag. It is
simpler and it is wrong: the gate becomes a runtime condition rather than a structural property,
and the difference between those two is the whole of ADR-0019 §4.

## 4. Scoring — what is scored is the prediction, not the string

T7.17 already established that *"the proposal matches ground truth"* is the wrong test: a fault can
have more than one working fix, and `also_correct_remediation` exists because scoring against
whichever the author wrote first grades on taste.

**Marked decision: a proposal is scored on four independent axes, reported separately and never
collapsed into one number.**

| axis | question | how it is decided |
|---|---|---|
| **class** | is the remediation class one that works? | ADR-0027's accepted set — labelled class or a measured member |
| **target** | is it the right service? | against the bundle's injection target |
| **grounding** | does `rests_on` resolve, and does it support the claim? | ids resolve against the store; the existing citation validator |
| **prediction** | did `expected_effect` describe what actually happened? | **only decidable by executing it** |

The fourth axis is the one that makes this worth building, and it is the one that does not exist
until an executor does. Until then a proposal is scored on three axes and the fourth is reported as
**not measured** — not as passed, and not omitted. That is ADR-0022 §2's rule about printing the
zeroes, applied to a category that is structurally empty rather than merely unobserved.

**A proposal that is right by an untested route counts as correct, and is marked.** This is
ADR-0027's `correct_by_alternative` doing exactly what it was built for, one step further out:
if a proposal names a remediation not in the accepted set and the execution axis shows it *worked*,
it is **correct, and it is a catalog defect** — the accepted set was incomplete, and the run just
measured a fix nobody had tested. It goes to the dispute register, not to the error count.
**Marked decision: an unexpected working fix promotes to `also_correct_remediation` only after a
deliberate re-test, never automatically from one scored run.** One observation of a fix working is
n=1 against a world that varies, and T7.17 spent eight attempts for a reason.

**`unexecutable` is a scored outcome, not an error.** A proposal can be correct and unexecutable
— T7.13's whole finding was that this world has faults whose remediation nothing here can carry
out. Folding that into "wrong" would repeat the mistake T7.11 made when it recorded a metrics gap
as a no-alert discard.

**Abstention keeps its meaning.** A proposer that declines is neither right nor wrong (ADR-0022
§1.2), and given §2's approval boundary, abstention is frequently the correct output.

## 5. Contamination — a third axis, and it is the sharpest one

**The proposer sees the verdict and nothing else.** Not the bundle, not the injection, not the
scenario file, not the change log beyond what the specialists already cited. It receives a
structured RCA and the `result_id`s behind it, and it may resolve those against the store. This is
ADR-0020's routing argument reused: the reason the synthesizer holds no tools is that raw envelopes
must not reach the role that writes durable material, and a proposal is durable material — it is
the thing an executor acts on.

**The axes ADR-0008 names do not cover the risk this role creates.**

**Axis 1 (cross-scenario) applies unchanged.** Proposal prompts are hill-climbable and must never
be tuned against holdout. Nothing new.

**Axis 2 (self-reference) applies unchanged**, through the verdict the proposer inherits.

**Axis 3 — the world as an oracle. New, and created by execution.** If a proposal can be executed
and the result observed, the world answers "was your diagnosis right?" without the agent having
diagnosed anything. A loop that proposes, executes, observes and re-proposes converts diagnosis
into **search** — and it would score well, because the fault is real and a small number of
candidate fixes covers most of the catalog. That is not a better investigator; it is a worse one
with a working oracle.

**Marked decision: one proposal per incident, executed at most once, and no observation of the
result re-enters agent context.** The execution outcome goes to the trajectory and the scorer,
never back to the model. This is the same shape as ADR-0003's bounded re-ask — bounded, and bounded
for a reason that is about measurement, not cost. If a later task wants a propose→observe→re-propose
loop, it needs its own pre-registration and its own scoring, because it is measuring a different
capability and would make every prior number incomparable.

**And it belongs in ADR-0008 rather than here.** ADR-0008 anticipated *"if a fifth contamination
axis appears"*; this is one, and it appears from a capability rather than from a corpus. Recorded
here, to be folded into ADR-0008 when the role is built.

## 6. What it costs, and what a first implementation would not include

**The stamp moves.** `PROPOSER_SYSTEM` enters `prompt_digest` the moment it exists, and the
`Proposal` contract enters `_CONTRACTS`. `runtime_version` goes from `1b0e7cbb4c47` to something
else, and **every recorded run becomes incomparable with everything after**. This is not avoidable
and should not be worked around: it is the stamp doing its job. It does mean the proposer must land
**with** a re-sweep, the way T7.10 re-founded the benchmark after the world moved — otherwise the
record has a discontinuity nobody measured.

**The budget gains a role.** ADR-0020's per-agent bounds get a tenth entry. T4.7 measured what
happens when a bound is wrong (a starved planner reproduced as a scenario-level failure), so the
proposer's bound is a **measured** number from its first sweep, not a guess carried forward.

**The trajectory gains a table.** `trajectory_proposals`, and — per T7.10's lesson, learned by a
scenario dying on `UndefinedColumn` — **with an `ALTER` beside the `CREATE TABLE IF NOT EXISTS`,
because the in-memory double the tests use will not catch its absence.**

### A first implementation includes

The `Proposal` contract; `PROPOSER_SYSTEM`; the role wired after the synthesizer; the
`PROPOSING` state ADR-0020 already reserves; the trajectory table; the three scorable axes
(class, target, grounding); `unexecutable` as an outcome; and the stamp move with its re-sweep.

### It does not include

The executor, any write tool, any credential on the world, the approval interface, the prediction
axis, or any autonomous path. **Those are a second system**, and §3 is the argument for why they
are not simply a later commit in this one.

## Consequences

- The record gains, for the first time, a role whose output is *checkable by doing* — and a
  written reason why the first version deliberately does not do it.
- ADR-0020's sketch is revised on two points, marked: the proposer produces a **predicate**, not a
  concrete action; and the action plane lives **outside** the investigation runtime.
- **Every fix-class number in the repository keeps its current meaning: the agent named a fix.**
  Nothing here retroactively changes that, and §4's fourth axis is the only thing that would.

Revisit if: an executor is built (fold axis 3 into ADR-0008 and re-pre-register the loop), or a
scored run produces an unexpected working fix (§4's promotion rule applies, with a re-test).
