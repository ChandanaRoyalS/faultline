# R3 — `network_partition` rehearsed through the injector — RESULT

**Run 2026-09-24 06:50:34 → 07:13:33 UTC, \$0**, `v2-product-catalog-partition`, protocol
`evals/runs/REHEARSALS-T7.0.md` with its addendum; whole world (silent list empty before and
during). Terminal verbatim in `transcript.txt`. A3 admitted this class on (c) alone and confirmed the line in Loki with a helper; this run
reads it through the agent's tool.

| | verdict | from the record |
|---|---|---|
| **INJECTS** | **yes — A3's shape, which is the freeze's** | `start` at 06:50:34 (`docker network disconnect`, aliases captured). First alerts 06:55:13 (**+4:38**; A3 +4:36): `ServiceHighErrorRate` on `frontend-proxy` and `load-generator`; their latency alerts +5:38; **`ServiceHighLatency/frontend` 06:57:13 (+6:38; A3 +6:36)**; `ServiceNoTraffic/product-catalog` 06:58:13 (**+7:38**; A3 +9:36, R2b +7:35) with `currency`, `recommendation`, `shipping`, then `accounting`, `email`, `fraud-detection`, `payment`, `quote` at +8:38; sixteen alerts at minute twelve (R2b thirteen; `flagd` latency and `recommendation`'s error and latency the additions — `recommendation` calls the target and hung to 100 % / 15000 on its 0.004 req/s). Shape: `frontend` 0.00 % / 15000 / 10.83 → 2.29 (R2b 2.40, A3 2.6); `frontend-proxy` 27.61 % (A3 24, R2b 25.6); `load-generator` 30.81 %; `checkout` 0.062. Hang-and-cascade, indistinguishable from the freeze on (a), exactly as A3 measured by hand |
| **VISIBLE** | **yes on (c) — the distinguishing line, through `logql_query`; (a) and (d) as the freeze** | **(c)** `logql_query product-catalog` over the fault returns **fifteen lines**: at 06:50:45 (+11 s) `context deadline exceeded`, at 06:50:48 `traces export: context deadline exceeded`, and then **`failed to upload metrics: context deadline exceeded … DeadlineExceeded` at :58 of every minute** from 06:50:58 to 07:02:58 — the running target, cut off, saying so once a minute; R2b's freeze returned nothing over the same length of window. That is the class's distinctness, read through the agent's own tool for the first time (A3 read it with `docker logs`, then through Loki's API with `logs.py`; this is `faultline.tools.logql_query` itself). The text is `DeadlineExceeded`, not Q95's `Unimplemented`: the collector unreachable, not the wrong server. **(d)** `trace_query product-catalog`: no traces (it cannot export); from the caller, ten `frontend` error traces, `frontend/GET 15001.8ms [self 15001.8ms]`. **(a)** `frontend` p95 42.98 → 15000, `product-catalog` flat then no samples. **(b)** `change_history` unavailable, never a record |
| **RESTORES** | **yes — and without the Postgres restart** | `stop` at 07:03:51 → *reverted*, back on `opentelemetry-demo` with both aliases (new address 172.18.0.21); `status` → *no active injections*; second `stop` → *is not active; nothing to revert*. Second wave 07:07:03–07:08:33 (`checkout`, `frontend`, `product-catalog`, `recommendation` error and latency); all clear **07:09:03 (+5:12**; A3 +5:57, R2b +6:44); quiet to 07:13:33 (4 min 30 s in the window; R4's pre-state supplies the fifth). **`postgresql` `restarts` 5 → 5**: the reconnect did not kill the postmaster where the unpause did twice (Q96) — consistent with a partitioned catalog failing its queries fast rather than queueing them for the database to receive all at once |
| **A SCENARIO MAY BE AUTHORED** | **yes** | Injects A3's shape through the injector, restores cleanly and idempotently, and the one dimension that separates it from `process_freeze` — (c) — comes back through `logql_query` as fifteen timestamped lines. A scenario on this class is a scenario whose logs specialist must read the culprit's own log, and the planner's habit Q80 recorded (never dispatching to the culprit) is what it will test |

---

## Addendum — Postgres did restart, eight seconds after the reconnect (read at R4's pre-state)

The RESTORES row reads `restarts 5 → 5` at +5 s. R4's pre-state at 07:21 read **6**, and
`docker inspect` dates the start at **07:03:59.5** — 8.5 s after the reconnect at 07:03:51, 3 s
after this run's count was taken. So the reconnect *did* take the postmaster with it, later than
the unpause did (R2 +0.6 s, R2b +1.5 s) — the time the catalog's connection pool takes to
re-resolve and reconnect before its backlog reaches the database. Q96 is the freeze's *and* the
partition's restore, not the unpause alone; the row's inference about fast-failing queries is
withdrawn. Nothing fired between 07:09 and 07:21 (`replay.py`), so the restart itself paged
nothing this time. The RESTORES verdict stands; its last sentence does not.
