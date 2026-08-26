# T3.3 — the first real dispatch

Two stages, run separately so a failure localises. Stage 1 passed on the second attempt at it
(the first found a bad key file, recorded below). Stage 2 ran a real investigation of a live
`cart-redis-misconfig` injection with `claude-opus-5`, and **found the root cause**.

| | |
|---|---|
| stage 1, boundary | **PASS** — 26 in / 4 out tokens, 1.4s |
| stage 2, first dispatch | **PASS** — 2 rounds, 6 dispatches, 14 trajectory steps |
| tokens, stage 2 | **19,463 in / 7,368 out = 26,831** |
| cost, stage 2 | **$0.28** at $5/$25 per Mtok |
| world | injected 01:09:26Z, reverted 01:21:32Z, **0 firing alerts by 01:28:14Z** |

## Files

- **`stage1-boundary.txt`** — one trivial prompt through the boundary.
- **`stage2-dispatch.txt`** — the full run: incident, triage, both plans, every finding.

## Stage 1

```
model: claude-opus-5   effort: high
api key: read from the environment by the SDK; not a setting, not printed
response text   : 'OK'
tokens          : in=26 out=4      latency: 1.4s
usage in store  : in=26 out=4
STAGE 1: PASS
```

The first attempt at this stage failed with `401 invalid x-api-key` — the key file held a shell
command line rather than a credential. That is what the stage is for: the same 401 folded into
stage 2 would have arrived after a fault was injected, with a world to revert and no way to tell
an auth failure from a dispatch failure.

## The world had to be repaired first

`checkoutservice` and `frontend` were both at the top latency bucket (15000ms p95) with one
`ServiceHighLatency` alert firing, and `accountingservice` was at **0.000 req/s** while checkout
served 1.34 req/s — a Kafka consumer that had not reconnected. `CATALOG.md`'s documented fix
applied exactly:

```
docker restart accounting-service frauddetection-service checkout-service
```

After it: frontend 15000ms → 46.5ms, checkout → 40.2ms, accounting back to 0.113 req/s, **0
firing alerts**. Injecting into the state before that would have produced an incident whose
blast radius was contaminated by a pre-existing checkout fault — which is what the rehearsal
recorder's baseline gate exists to refuse, and this path has no such gate.

## Stage 2 — the incident

Ten episodes correlated into one incident. Triage: **14 services, severity critical, start from
`checkoutservice`, 5 unmeasured edges crossed.**

```
frontend, checkoutservice, loadgenerator   ServiceHighErrorRate   01:12:00
shipping, currency, quote, frauddetection, email   ServiceNoTraffic   01:15:15
cartservice                                ServiceNoTraffic       01:15:30
accountingservice                          ServiceNoTraffic       01:17:45
```

## What the planner chose, and why

**Round 1 — three of four. `logs` skipped.**

> *rationale:* "The blast radius points to a single upstream fault under checkoutservice, so I
> need change history to find a trigger and metrics to order the onsets. Traces are justified
> here because five unmeasured edges, including paymentservice, cannot be attributed any other
> way."
>
> *skipped `logs`:* "Traces plus metrics should localize the failing dependency; logs can be
> added later if the culprit span needs an error message explained."

This is the behaviour the required `skipped` field exists to force. The planner dispatched three,
named the fourth, and gave a reason that turned out to be a plan — logs *were* added later, in
round 2, exactly as it said.

It also used the unmeasured-edge count the brief gives it, and used it correctly: five unmeasured
edges are why it wanted traces, because membership through an unmeasured edge is not evidence.

**Round 2 — three of four again, `traces` skipped, everything re-scoped to `cartservice`.**

> *rationale:* "Round one converged on a single failing edge — checkoutservice's GetCart call
> into cartservice — so the only open question is why cartservice is failing. […] correcting the
> first round's overly narrow checkoutservice-only, 15-minute scope."
>
> *skipped `traces`:* "Traces already did their job: they pinpointed the deepest error span
> (cartservice GetCart) and ruled out latency, payment, and other dependencies; a second trace
> query would return the same five-span shape and add nothing."

The one follow-up round did what ADR-0020 designed it for: a cross-evidence question the first
round opened, answered by dispatching again rather than by arming the synthesizer.

## What the specialists found

The investigation reached the correct root cause. From the logs specialist on `cartservice`:

> "a repeating startup sequence of connecting to the cart Redis endpoint, failing to connect,
> then an unhandled exception terminating the process from `Program.Main` via
> `RedisCartStore.InitializeAsync`… roughly 20-45s between attempts, recurring at least seven
> times" — and "the connection target recorded in the startup line is the cart Redis host on
> **port 6380** […] which is a candidate misconfiguration."

From the changes specialist on `cartservice`:

> "A single change is recorded […] `platform-automation` applied an environment variable update
> setting the Redis endpoint address, timestamped roughly three minutes before the 01:12Z
> incident marker" — pointing at "a non-default port (6380 rather than the conventional 6379)."

That is `cart-redis-misconfig`'s ground truth, found from evidence rather than from the answer
key. **The change record named the fault without naming the harness** — `platform-automation`,
an environment update, a before/after — which is T2.6's leak boundary holding under a real agent
reading it.

`ruled_out` earned its place. The traces specialist eliminated five hypotheses including *"an
unmeasured/uninstrumented paymentservice call is where the error hides"* — "failing traces
terminate at the cart lookup […] execution never proceeds past order preparation." The metrics
specialist on `cartservice` got an **empty** result and ruled out three things from it, then
said plainly that "an empty result is ambiguous between 'no traffic' and 'no instrumentation /
label mismatch'". That is the `empty`-versus-`error` distinction ADR-0019 built, being used.

## Structured output: 6 of 8 valid first try

```
attempts: planner 2, changes 1, metrics 1, traces 1, planner 1, logs 1, changes 1, metrics 2
```

Two completions needed the one retry. Both were **truncation, not malformation** — and that is a
defect this run found.

## Found by the run and fixed in this branch

The first stage-2 attempt **died with a `JSONDecodeError`**. A 40-line log envelope produced a
findings object longer than the 1200-token specialist cap; the reply was cut off mid-JSON, the
re-ask said only "that did not validate against the schema", and the model produced the same
too-long reply again. The second failure raised out of the dispatch loop and killed an
investigation that already had findings from three other specialists.

Three fixes, all in this branch:

- **A truncated reply is re-asked as truncation.** `stop_reason == "max_tokens"` now produces
  "your reply was cut off at the token limit… reply again, complete and much shorter" instead of
  a schema complaint that invites the same answer.
- **Specialist `max_tokens` raised 1200 → 3000.**
- **A specialist that fails twice fails alone.** It is recorded as a trajectory step with its
  `schema_failure` and `stop_reason`, and the other dispatches continue — the same argument
  ADR-0020 §5 makes about budget exhaustion, applied to a failure it did not anticipate.

After the fix, both retries succeeded on the second attempt.

## Trajectory rows

```
trajectories            1
trajectory_steps       14
trajectory_tool_calls   6
trajectory_retrievals   0
```

Six tool calls, six stored envelopes, one per dispatch. Zero retrievals — the past-incident
corpus belongs to the synthesizer, which does not exist yet.

## Recovery

Reverted 01:21:32Z. By 01:24 four alerts were still firing, including `ServiceHighErrorRate` on
`emailservice` — the post-revert recovery artifact measured in three previous runs. By **01:28:14Z:
0 firing alerts, 14 services serving**, only `frontend-proxy` at zero, which is its healthy
steady state. `faultline-inject status`: no active injections.

## What this did not exercise

- **Budget exhaustion.** 26,831 of 60,000 tokens, 6 of 8 permitted tool calls, well inside the
  wall clock. The flagged-verdict path is tested and unobserved live.
- **A third round.** The cap held at two because the budget stops it, not because the planner
  stopped asking — round 2's rationale reads like a planner that would have continued.
- **Retrieval.** No `exclude_origin` row exists in this trajectory, so ADR-0008's axis-2
  assertion has still only been exercised in the T2.4b smoke.
- **Scoring.** Nothing compared these findings to the bundle's ground truth. T4.2 owns that.
