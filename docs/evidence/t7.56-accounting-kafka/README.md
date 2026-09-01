# T7.56 — `accounting-kafka-misconfig`, measured and abandoned at G1

**The scenario was abandoned at the first gate and never recorded. No bundle exists, no slot was
taken, and Q9 is not discharged.**

The disqualification criteria were committed before the world was touched
([`docs/design/t7.56-holdout-bad-config.md`](../../design/t7.56-holdout-bad-config.md), commit
`3097a1b`). G1 said:

> **The container stays up** — passes if `RestartCount` on `accounting-service` is unchanged for
> the whole window and uptime is continuous. Disqualifying because a restarting container makes
> this a crashloop page. The whole item is *"alive and not working"*; **if it is not alive, there
> is no item.**

It is not alive.

## What was measured

| | before | under the fault | after revert |
|---|---|---|---|
| `RestartCount` | **0** | **9 in ~58 seconds** | 0 (fresh container) |
| `State.Status` | `running` | **`restarting`** | `running` |
| `State.StartedAt` | `2026-09-01T05:27:47Z` — about two hours' uptime | rewritten every few seconds | `2026-09-01T07:32:51Z` |
| `calls_total` rate | 0.16 req/s | 0.109 req/s and draining — **never reached 0** | 0.18 req/s |
| alerts firing | 0 | **0** — G2 was never reached | 0 firing, 0 pending |

Injected `2026-09-01T07:31:53Z`, abandoned and reverted within the minute.

## Why it fails, from the service's own logs

```
{"message":"Kafka brokers: kafka:9093","severity":"info", ...07:32:17.517Z}
{"message":"kafka: client has run out of available brokers to talk to: EOF","severity":"fatal", ...07:32:18.335Z}
```

The pair repeats every one to seven seconds. **`severity: fatal`** is the whole finding:
`accountingservice` treats an unreachable broker as a fatal startup condition and exits. `restart:
always` brings it back, it fails again, and the result is a crashloop.

## What this closes, which is more than one candidate

The design argued that the catalog's three "silent service" pages leave one corner of a square
empty, and that a misconfigured consumer would fill it:

| the service is… | …and it is | occupied by |
|---|---|---|
| silent, **dead** | genuinely gone | `frauddetection-memory-squeeze` (OOM-killed) |
| silent, **alive and working** | the telemetry lying | `payment-telemetry-blackout` |
| silent, **alive and not working** | *the candidate* | **cannot be produced in this world** |

**The corner is empty because the world cannot fill it.** A consumer here does not sit alive and
idle when its broker is gone — it exits. So "silent, alive, and not working" is not a page this
demo can page, and the square has three corners, not four.

**And there is no dial.** The criteria said so before the run: the only parameter is the address,
and every wrong address produces the same fatal. A blackhole IP gives a dial timeout that still
ends in *"run out of available brokers"*; a wrong host gives a resolution failure that ends in the
same place. There is nothing to tune, which is why this is an abandonment rather than a second
attempt.

**The other consumer does not rescue it.** `frauddetectionservice` is the only other Kafka consumer,
and its page — `ServiceNoTraffic/frauddetectionservice` — is **already occupied** by
`frauddetection-memory-squeeze`. Even if it retried where accounting exits, the item would land on
a page the catalog already has.

## What behaved correctly, and is worth recording

**T7.37's world lock did exactly what it was built for.** Killing the recorder mid-run left a lock
held by a dead pid. The next acquisition reclaimed it automatically and **recorded the reclamation
in the new lock**:

```
{'reclaimed': {'pid': 50329, 'since': '2026-09-01T07:31:53Z',
               'reason': 'rehearse accounting-kafka-misconfig', 'was': 'dead'}}
```

The lock then released cleanly. This is the first time the dead-holder path has fired outside a
test.

**G5 passed: the world came back.** Zero alerts firing, zero pending, `accountingservice` back to
0.18 req/s against a 0.16 pre-fault baseline. The injection was reverted through the injector, the
override file was removed, and `injections.json` reads `active: {}`.

## What did *not* happen, stated because it would be easy to imply otherwise

**T7.55's freeze path was not exercised.** The freeze is wired into `faultline-eval` — the run path
— and recording a bundle goes through `evalharness.rehearse`, which does not build a freeze
manifest and never did. That is not a gap: a recording is not a scored experiment, and the bundle
manifest has carried `world` provenance since ADR-0014. **T7.55's first real use will be entry 4's
run, not this task**, and reporting otherwise would be a false claim about a check nobody ran.
