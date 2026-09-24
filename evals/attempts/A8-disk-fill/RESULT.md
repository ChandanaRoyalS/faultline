# A8b — disk fill on kafka's log directory — RESULT

**Run 2026-09-24 00:39:31 → 01:05:25 UTC, \$0.** The first run (A8, 2026-09-23 06:13) was void: the
tmpfs and the fill were at a path kafka does not write to (`VOID.md`, `transcript-void-0613.txt`).
This is A8b, registered separately in `PREREGISTRATION-T7.0-A8b.md` with a precondition read off
the running broker, and the only run scored: `transcript.txt`. The verdicts are the pre-registered
definitions applied to the transcript and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes** | `ServiceHighLatency/checkout` at 00:46:02 (**+6:31**) and `ServiceHighErrorRate/checkout` at 00:46:32 (**+7:01**) — `checkout` produces to kafka directly, which the definition covers. `ServiceNoTraffic/accounting` at 00:48:02 (+8:31) and `/fraud-detection` at 00:51:02 (+11:31) — the consumers, starved. `ServiceHighErrorRate/fraud-detection` at +6:31, briefly, as its consumer errored against the halting broker before going silent |
| **DISTINCT from `bad_config` on `checkout`** | **yes, on (a) and (c)** | **(a)** both consumers silent (`ServiceNoTraffic` × 2) — a wrong `KAFKA_ADDR` on `checkout` starves nothing that reads from a healthy broker. **(c)** kafka's own log, read back through Loki under `service="kafka"`: **56 lines** of `java.io.IOException: No space left on device`, **28** of `KafkaStorageException: Error while writing to checkpoint file /tmp/kafka-logs/replication-offset-checkpoint`, and at 00:39:33 — **two seconds after the fill** — `ERROR Shutdown broker because all log dirs in /tmp/kafka-logs have failed`. A misconfigured checkout logs connection failures while kafka's log is clean. **(b)** no change recorded |
| **REVERTS** | **yes, by the registered fallback** | `rm` could not land — *"Container … is restarting, wait until the container is running"* — so `up -d --force-recreate kafka` ran at 00:55:51 as registered, discarding the tmpfs; the consumers were restarted. All clear by 00:59:55 (**4 min 04 s**); quiet the remaining **5 min 30 s** to 01:05:25 |
| **ADMISSIBLE** | **yes** | pages, distinct on two dimensions, reverts, and is a tool (`dd` via `exec`) and a surface (storage) no existing mechanism has. **`disk_fill` is the ninth class, and the ceiling is reached** |

**Prediction scorecard.** PAGES: right. `ServiceHighErrorRate/checkout` "within 6 min": **7:01**
— a minute late, and its latency alert came first at 6:31, which the registration did not name.
`ServiceNoTraffic` on the consumers "at ~8 min": accounting **8:31**, right; fraud-detection
11:31, late because it errored for two minutes first (its fetches failed loudly before its rate
drained). DISTINCT on (a) and (c): right, both read back. REVERTS via recreate: right — and the
registered *reason* for the fallback (crashloop too fast for `exec`) is exactly what happened.

## What the shape at minute twelve shows

| service | error ratio | p95 | req/s before → during | reading |
|---|---:|---:|---|---|
| `kafka` | — | — | — | halted; restarting every ~6–60 s against a full directory |
| `checkout` | **6.49 %** | **15000** (off scale) | 3.20 → 1.58 | `PlaceOrder`'s produce **hangs** to its timeout, then fails |
| `accounting`, `fraud-detection` | — | — | → **0.000** | starved: nothing to consume |
| `frontend-proxy` | 3.11 % | 12437 | 4.28 → 1.94 | Envoy timing out the hung checkouts |
| `load-generator` | 3.38 % | 15000 | 16.0 → 6.77 | the client's view |
| `frontend` | 0.00 % | 48 | 8.92 → 3.44 | throughput down, not erroring — the hang holds its capacity |

**A halted broker presents as a checkout hang, not a checkout error.** The producer blocks until
`delivery.timeout`, so the first thing the rules see is `checkout`'s p95 off the top of the
histogram, then the errors as the timeouts land — the same hang-and-cascade A2 and A3 produced
from a frozen or unreachable dependency, here from a dependency that is up, reachable, and cannot
write. The registration's one uncertainty — *"whether checkout treats a failed produce as a
request error or logs and returns success"* — resolved to *error, after a hang*.

## Two things the run measured beyond the verdict

**The fill halts kafka in two seconds, and the world takes six and a half minutes to notice.**
`Shutdown broker because all log dirs … have failed` at +2 s; the first alert at +6:31. The gap
is the `[5m]` window plus `for: 3m` on the producer side — the same detection floor every attempt
has measured, and a real property of these rules: a broker outage is a six-minute-old fact by the
time anything pages.

**The consumer restart did not produce the duplicate-key alert this time.** After A8's revert
(and after the kafka recreate at 00:22) `docker restart` of the consumers gave four minutes of
`ServiceHighErrorRate/accounting` — auto-committed offsets lagging, orders re-delivered, inserts
colliding on `order_pkey`. After A8b's revert it did not: the recreate discarded kafka's data, so
there was nothing to re-deliver. That is the mechanism confirmed from the other side, and it is
what `recycle_effect("v2")` must say (Q89): **a consumer restart on a broker that kept its data
costs ~4 minutes of error-rate alert on `accounting`; on a broker that lost its data it costs
nothing.**

## Collateral, recorded

**Tempo exited 137 twice** — once overnight (~16 h before the run) and again within minutes of
being restarted at 00:34:40. It is not in the alert path and no verdict here depends on it, but
every (d) read-back and the agent's `trace_query` do. **Q91.**

## Timeline

| clock (UTC) | event |
|---|---|
| 00:22:05 | kafka recreated with the tmpfs at `/tmp/kafka-logs`; consumers restarted; 4 min of duplicate-key errors, then quiet |
| 00:34:40 | tempo started (exited 137 again within minutes) |
| 00:34:41–00:39:11 | pre-state: quiet; both precondition lines hold |
| 00:39:31 | `dd` fills the tmpfs: 255 MiB, *No space left on device* |
| 00:39:33 | kafka: `Shutdown broker because all log dirs in /tmp/kafka-logs have failed` (+0:02) |
| 00:46:02 | `ServiceHighLatency/checkout`, `ServiceHighErrorRate/fraud-detection` (+6:31) |
| 00:46:32 | `ServiceHighErrorRate/checkout` (+7:01) — **PAGES** |
| 00:48:02 | `ServiceNoTraffic/accounting` (+8:31) |
| 00:51:02 | `ServiceNoTraffic/fraud-detection` (+11:31); four alerts; shape captured |
| 00:55 | (c) read back: 56 + 28 Loki lines under `service="kafka"` |
| 00:55:51 | `rm` refused (container restarting); `--force-recreate kafka`; consumers restarted |
| 00:59:55 | all clear (+4:04) — **REVERTS** |
| 01:05:25 | recovery window ends; 5.5 min quiet |

**Scoreboard, final for the attempts**: **nine classes** — the four existing, `feature_flag`
(A1), `process_freeze` (A2), `network_partition` (A3), `datastore_corruption` (A4b),
`disk_fill` (A8b). A5 inadmissible (no signal but rate); A6 and A7 inadmissible by definition,
A6 a `bad_config` scenario, A7 not a scenario until Q90. The tmpfs stays, as the override said it
would if the fill paged; it is now the class's precondition.
