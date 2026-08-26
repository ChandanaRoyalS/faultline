# T3.5 live smoke — one investigation, driven only through the CLI

Scenario: **`cart-dependency-latency`** (dev split), chosen because no agent run has faced its
fault class. T3.3 used `cart-redis-misconfig`; T3.4/b/c used `shipping-wrong-image` three times.

Files: `transcript.txt` is every CLI invocation and its output verbatim, including the two
refusals; `*-verdict.json` and `*-narrative.md` are what the runner wrote under `--out`.

## Baseline before injection

Checked by hand at 03:26:35Z — still no gate on this path (the T4.1 note in `docs/PLAN.md`).
**0 active alerts**, no service with p95 over 1000ms, 15 services reporting, no open incidents,
no active injections. `frontend-proxy` at 0.000 req/s is the clean state, per the committed
baseline's 181 samples of 0.0. Nothing needed repairing.

## The run

    $ faultline-investigate --list
    1 investigable incident(s):
      a7aab1ff-...  triaging  4 episode(s)  warning  cartservice, checkoutservice, frontend, loadgenerator

    $ faultline-investigate a7aab1ff-... --exclude-origin cart-dependency-latency \
        --out docs/evidence/t3.5-runner-smoke --max-tool-calls 4 --max-tokens 120000
    incident a7aab1ff-...  state triaging  anchor 03:42:45
    triage: 12 services, severity warning, start from cartservice, 4 unmeasured edge(s) crossed

    states: triaging -> planning -> investigating -> synthesizing
    trajectory: 68ac9a67-8328-4e90-89ed-5c4409821316
    investigation: 2 round(s), 5 dispatch(es), 15 step(s)
    ...
    flags: none
    exit=0

| | |
|---|---|
| incident | `a7aab1ff-d443-4bd4-925a-cc7b31064a50` |
| trajectory | `68ac9a67-8328-4e90-89ed-5c4409821316` — 15 steps |
| tokens | in 30,888 / out 12,625 / **43,513** |
| cost | **$0.4701** |
| exit code | **0** (a verdict, nothing flagged) |
| injected | 03:39:20Z → reverted 03:49:39Z |

### State transitions, including the one the CLI did not make

    triaging -> planning -> investigating -> synthesizing        (the runner)
                                          -> resolved            (the orchestrator, 03:52)

The incident resolved from `SYNTHESIZING` when its alerts cleared — a transition ADR-0016's
table already allowed — **and kept its `investigation_id` through the orchestrator's own write.**
That is the `COALESCE` in the upsert doing exactly what it was put there for, verified live
rather than argued.

Every evidence README from T3.4 to T3.4c ends with a line about an incident stuck in `triaging`.
This one does not.

## The verdict against ground truth

| | agent | `incident.md` |
|---|---|---|
| fault class | **`bad_config`** | `dependency_latency` |
| class of fix | **`config_revert`** | `restart` |
| confidence | medium | — |

**Both wrong, and the mechanism exactly right.** The agent reconstructed the fault in full:

> "a fixed 300ms, zero-jitter egress delay on eth0 … cartservice's server-side GetCart/EmptyCart
> spans are ~301-305ms and are almost entirely consumed by single Redis operations (HGET
> ~301-304ms, HMSET ~300-302ms) — i.e. one 300ms egress hop per Redis call … Because
> checkoutservice makes two sequential cart calls on every PlaceOrder, the penalty compounds"

`incident.md` records the same doubling and warns it is the trap: "Anyone expecting the p95 to
rise by exactly 300ms would have doubted a correct measurement." The agent measured it and
explained it.

It then classified on *what changed* rather than on *what the symptom is*. `incident.md` is
explicit about why the fix is `restart`: "Nothing was deployed and no configuration was wrong,
so there was nothing to roll back or revert; the container simply needed replacing." The agent
proposed `config_revert` for a fault where there is no configuration to revert.

Worth separating: the fault-class taxonomy asks what kind of fault it is, and a shaping rule
attached to a network namespace is genuinely readable as either "a dependency got slow" or
"something was configured wrong". That is a real ambiguity in the label set, not only a mistake
by the agent, and it is the first time an agent run has met a class other than `bad_deploy` or
`bad_config`. **T4.2 will need a position on it.** Recorded as a note in `docs/PLAN.md`.

### Retrieval earned its keep, for the first time

    exclude_origin='scenario:cart-dependency-latency'  k=3
    returned=['scenario:cart-bad-image-tag', 'scenario:cart-bad-image-tag', 'scenario:cart-redis-misconfig']

The scenario under test was excluded from its own investigation. What came back was used:

> "the flat/absent cartservice error metrics must not be read as 'cart is healthy' — the
> spanmetrics denominator was also empty, so the metric source is unusable, and **two past
> incidents in this corpus record responders being misled by exactly that reading**."

That is the empty-error-ratio artifact that sent T3.4's agent to the wrong service. Here the
agent named it, refused it, and cited the corpus for why. ADR-0008 anticipated retrieval
misleading; this is the other direction, measured.

Two of the three hits are the same document (`cart-bad-image-tag` twice, different chunks).
Whether `k` should count chunks or documents is unexamined and worth a look before T4.1.

## Two defects this smoke found

**1. A failed start permanently retired a live incident.** The first attempt raised
`ModuleNotFoundError: No module named 'anthropic'` — the optional extras had been dropped by an
earlier `uv sync` — *before the first model call*. The runner moved the incident to `FAILED`,
`FAILED` is terminal in ADR-0016's table, and `INVESTIGABLE` is `{triaging}`. One absent
optional dependency retired incident `329f8872` for good; it is still in the database as
`failed`, and the transcript shows the CLI refusing it.

Nothing had investigated it. **A failed start is not a failed investigation**, and the fix is to
tell them apart by whether a single trajectory step was recorded:

- steps recorded → a partial investigation. `FAILED`, trajectory attached, evidence preserved.
- no steps → nothing happened. The incident stays exactly where it was, and the next attempt
  finds it there.

Recorded in ADR-0016 §5 and pinned by
`test_a_failure_before_anything_ran_leaves_the_incident_where_it_was`.

**2. "The trajectory is persisted up to the failure" was not true.** `Investigation` saved only
before the scribe and at the end, so a run that died in the synthesizer left *nothing* in the
store — three specialists' worth of evidence gone with the exception. Found by the hermetic test
written for the claim, before the live run. Now saved on the failure path too, and a trajectory
with no steps is deliberately not saved: an empty row is indistinguishable from an investigation
that produced no evidence.

## An artifact of this run, stated so nobody reads it as a finding

The change-history window contains **two** records, not one:

    03:35:08  platform-automation  container removed: traffic-shaping container removed ...
    03:39:20  platform-automation  container created: traffic-shaping container attached ...

The removal is the revert of the aborted first attempt; the creation is the re-injection. A
single rehearsal produces only the second. The agent reasoned about the pair and raised it as an
open question — "whether the 03:35:08 detach / 03:39:20 re-attach is part of a running chaos
experiment with a scheduled end" — which is good reading of a signal that should not have been
there. **The window is not representative and no conclusion should be drawn from how the agent
handled it.**

The records themselves are not a leak: T2.6's guard scrubbed them to "traffic-shaping container"
and "platform-automation", which is what a real change log would show for a netem change on a
container's network namespace. The word "chaos" is the agent's own inference, not a word the
envelope contained.

## Housekeeping

Reverted 03:49:39Z. Recovery confirmed 03:52:27Z: **0 active alerts**, no service p95 over
1000ms, no active injections, incident `a7aab1ff` resolved with its investigation id intact.
Ingest and orchestrator stopped.

`make check`: 319 passed, 1 skipped.
