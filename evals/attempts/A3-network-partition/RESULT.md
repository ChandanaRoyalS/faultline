# A3 — network partition `docker network disconnect opentelemetry-demo product-catalog` — RESULT

**Run 2026-09-23 01:11:14 → 01:33:30 UTC, \$0.** One run, `transcript.txt`. The verdicts are the
pre-registered definitions applied to the transcript and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes** | `ServiceNoTraffic/product-catalog` firing at 01:20:50 — **9 min 36 s** after the disconnect, on the target. `ServiceHighLatency/frontend`, the direct caller, at 01:17:50 (+6:36). First alert anywhere at 01:15:50 (+4:36): `ServiceHighErrorRate` on `frontend-proxy` and `load-generator` |
| **DISTINCT from `dependency_latency`** | **yes, on (a) and (d)** | A delay gives slow spans that arrive; a partition gives no spans at all — the target's rate is `0.000` and `ServiceNoTraffic` fires on it, which a delay never causes |
| **DISTINCT from A2 (process freeze)** | **yes — on (c) alone, exactly as registered** | **(a)** identical: the same thirteen alerts on the same ten services, the same hang-and-cascade, the same numbers within noise (`frontend` 0.00% / 15000 ms / 10.3 → 2.6 req/s; `frontend-proxy` 24% vs 26%). **(b)** identical: neither leaves a change record. **(d)** identical: spans absent in both. **(c) differs**: A2's frozen process wrote nothing; A3's running process wrote `failed to upload metrics: context deadline exceeded` **once a minute for the whole fault** — the export failure to the collector that the registration named as the one thing that would separate them. Promtail reads container stdout through the docker socket and labels it `service="product-catalog"`, so the line reaches Loki and the agent's `logql_query` regardless of the container's network. **Read-back from Loki owed**, below |
| **REVERTS** | **yes, with the window's last half-minute owed** | Reconnected at 01:23:02. Every alert cleared by 01:28:59 (**5 min 57 s**). The window then held **four and a half** quiet minutes, 01:28:59–01:33:30. A4's pre-state supplies the rest |
| **ADMISSIBLE** | **yes** | pages, distinct from both comparators, reverts, and is a tool and surface no existing mechanism has |

**Prediction scorecard — two predictions were on the record, and the earlier one was right.**
The registration predicted *"the same alert shape as A2 … DISTINCT from A2 on (c) only"*. After A2,
I revised that in the A2 result to expect a *refusal* — fast errors at the caller, no collapse
behind it — on the reasoning that a disconnected host refuses where a frozen one hangs. **The
revision was wrong and the registration was right.** A3 hung exactly as A2 did. PAGES: right.
`ServiceNoTraffic` timing: 9:36 against A2's 7:36 — the same ~8-minute floor with two minutes of
variance in when the target's last span batch landed. Blast radius: thirteen alerts, as A2.

## Why a disconnect hangs rather than refuses

`frontend` holds long-lived gRPC connections to `product-catalog`. Removing the container from
the bridge network removes its interface, and packets on those established connections are
**dropped, not reset** — nothing sends a RST or an ICMP unreachable, so the client waits out its
deadline. New connections fare no better: the name is gone from Docker's embedded DNS, and the gRPC
client keeps retrying on the connection it already has. From `frontend`'s side the two faults are
the same fault: a peer that accepts and never answers. That is why every downstream number matches
A2 to within noise, and it is a property of how this world is networked rather than of either
mechanism.

## What the shape at minute twelve shows

Identical to A2's within noise; the table is in the transcript. The one difference is the target's
log, and it is the whole verdict:

```
2026/09/23 01:15:12 failed to upload metrics: context deadline exceeded: rpc error: code = DeadlineExceeded
2026/09/23 01:16:12 failed to upload metrics: context deadline exceeded: rpc error: code = DeadlineExceeded
… one line a minute, eight lines, the entire window
```

A frozen process cannot write that line. A partitioned one writes nothing else. **The distinction
is thin — one repeating log line on the culprit — and it is the same distinction a human operator
uses**: a hung process is silent; a cut-off one complains that it cannot reach anything. It is also
reachable by the agent only *after* it has found the culprit, since the page lands on `frontend`
and `frontend`'s own log says nothing about why product-catalog stopped answering (A1 finding 1,
A2 finding 3).

## Recovery matched A2 exactly

`ServiceNoTraffic` cleared within two minutes of the reconnect; then the same **second wave** —
`ServiceHighErrorRate` on `product-catalog`, `checkout`, `frontend`, `recommendation` from 01:26:59
to 01:28:29 — as every request that had hung woke at once past its deadline. All clear at 5:57
against A2's 5:36. **The thundering herd is a property of hang-type faults on this world, not of
`pause` specifically**, and the injector's recovery clock for both classes should allow ~6 min.

## Collateral, recorded and not counted

`ServiceHighErrorRate/fraud-detection` and `ServiceHighLatency/fraud-detection` for ~90 s
(01:19:50–01:21:20), and `ServiceHighLatency/flagd` and `/recommendation` for ~60 s. `fraud-detection`
consumes from Kafka and calls nothing in the request path; its blip is most likely its own
consumer sleeping against an empty topic once `checkout` stopped producing, which the `accounting`
analysis (`2026-09-22-the-span-that-was-not-latency.md`) shows is how these consumers' spans
behave. Not on the target, not on a direct caller, not counted.

## Still owed

**The Loki read-back for (c).** The line is in `docker logs`; the verdict says the agent can see
it, on the strength of Promtail's configuration. One LogQL query over 01:11–01:23 confirms it
reached Loki under the label the tool queries. If it did not, A2 and A3 **merge into one class**,
`unreachable`, as the registration says in advance.

**A1's Jaeger read-back**: 16686 is published on host port **51599**, not 16686, which is why the
query returned nothing. Re-run against `localhost:51599`.

## Timeline

| clock (UTC) | event |
|---|---|
| 01:11:14 | `docker network disconnect` |
| 01:15:50 | first alerts, `frontend-proxy` and `load-generator` error rate (+4:36) |
| 01:17:50 | `ServiceHighLatency/frontend` — direct caller (+6:36) |
| 01:20:50 | `ServiceNoTraffic` on seven services including the target (+9:36) — **PAGES** |
| 01:22:50 | thirteen alerts firing; shape and target log captured |
| 01:23:02 | `docker network connect` |
| 01:24:59 | no-traffic alerts cleared (+1:57) |
| 01:26:59 | second wave: error rate on the target and three others (thundering herd) |
| 01:28:59 | all clear (+5:57) — **REVERTS** |
| 01:33:30 | recovery window ends; 4.5 min quiet observed |
