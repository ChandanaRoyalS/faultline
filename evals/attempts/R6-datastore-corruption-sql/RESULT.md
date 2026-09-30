# R6 — `datastore_corruption` on a SQL table, rehearsed through the injector — RESULT

**Run 2026-09-30 05:04:02 → 05:25:05 UTC, \$0**, `v2-postgresql-catalog-corruption`, protocol
`evals/runs/REHEARSAL-T7.1-R6.md` (`REHEARSALS-T7.0.md`'s seven steps), registered with the tool
before either ran; whole world. The inject was conditional on the world check's `ALL PASS` and on
`status` printing `no active injections`, and both held. Terminal and the three read-backs verbatim
in `transcript.txt`, with the tail of the tool's integration test run on the Mac before it merged
(3 passed, a real Postgres through Docker).

| | verdict | from the record |
|---|---|---|
| **INJECTS** | **yes — A10's shape** | `start` at 05:04:02 printed *set to NULL on all 10 rows (fingerprint f9b57aae49e7ad4305e3120a54fdc20d -> ea4a8cf36bcb834d426c151c896148e4 …)* - A10's pair, to the character - and `status` showed it active with its revert described. `ServiceHighErrorRate` at 05:07:33 (**+3:31**; A10 +3:00) on **the same five services in one evaluation**: frontend, frontend-proxy, load-generator, product-catalog, recommendation; checkout at +4:31 (A10 +4:00); `ServiceNoTraffic` on accounting, currency, email, payment, quote and shipping at +7:31 (A10 +8:00). Shape at +11:31: product-catalog **50.00 %** at a **2 ms** p95 and 2.750 req/s, recommendation 66.67 %, frontend 53.72 %, frontend-proxy 52.83 %, checkout 50.00 % at 2 ms, load-generator 28.50 %; the eight order-only services at 0.000 req/s; **no service in the table is the tool**. Two differences from A10, recorded and not tuned: fraud-detection raised `ServiceHighErrorRate` from +7:31 and **`ServiceHighLatency` for two polls (+8:31 to +9:01)** and both cleared by +9:31 - the registration predicted *no latency alert*, and this is one, off the catalog's path; and fraud-detection's `ServiceNoTraffic` did not fire inside the twelve minutes (A10 +10:00), though its rate read 0.000 at the shape |
| **VISIBLE** | **yes on (a), (c) and (d); (b) unavailable, as registered** | **(c)** `logql_query recommendation` returns, as the first line of the window at **05:04:03.99 - one second after the inject** - `Exception calling application: <_InactiveRpcError …` with `details = "failed to load products: failed to get products from rows: failed to scan product row: sql: Scan error on column index 2, name "description": converting NULL to string is unsupported"`, and the same at the window's end (05:14:57); `logql_query product-catalog`: no lines, the catalog writes none. **(d) - the claim A10 left to this rehearsal - holds, in every trace read.** product-catalog's `ListProducts` server span `ERROR: failed to load products: … Scan error on column index 2, name "description": converting NULL to string is unsupported` in 0.3-1.0 ms, and beneath it **`product-catalog/sql.conn.query` with no error**; its `GetProduct` span `ERROR: Product Not Found: <id>` for **HQTGWGPNH4, 2ZYFJ3GM2N, OLJCESPC7Z, L9ECAV7KIM and 9SIQT8TOJO** - five of the table's own ids - in 0.3-0.8 ms, again over a `sql.conn.query` with no error. Eighteen distinct traces across the two read-backs (ten each, two in both), every one naming the catalog's span as the **degrading hop** - `… -> product-catalog/oteldemo.ProductCatalogService/ListProducts` or `…/GetProduct`, 2-11 % of its trace, `(error)`: the culprit's reader in the hop line, as R4b's was. And checkout's orders: `PlaceOrder` `ERROR: failed to prepare order: failed to get product #"HQTGWGPNH4"` after a cart read that succeeded. **(a)** product-catalog's error ratio to **0.5** with its p95 **1.9-3.9 ms**; recommendation to 0.669 at 4.0-5.1 ms. **The store itself**: no spans, no span-metric series, and two log lines in the window, a routine checkpoint (05:07:48 and 05:07:52), none naming the update or the table. **(b)** `change_history`: *no change log configured, so this window was not observed* - unavailable, never a record, as the registration fixed in advance |
| **RESTORES** | **yes** | `stop` at 05:15:34 → *10 saved catalog.products.description values written back; fingerprint f9b57aae49e7ad4305e3120a54fdc20d, as before the write*; `status` → *no active injections*; second `stop` → *not active; nothing to revert*. The no-traffic alerts cleared by 05:16:35 (+1:01), checkout's error rate by 05:19:35, the rest by **05:20:35 - all clear inside 5m01s** of the restore (A10 4m30s; registered four to five), at the watch's 30 s grain. Quiet from 05:20:35 to the last poll at 05:25:05: **4m30s of quiet polls, not the protocol's five minutes** - the watch ended first; no alert was firing at its end, and the world check before any next recording re-reads it. No container restarted: product-catalog, postgresql, recommendation and checkout kept the start times they had before the attempt |
| **A SCENARIO MAY BE AUTHORED** | **yes** | The injector's tool reproduces A10 - the same write to the byte, the same page on the same five services within half a minute, the same six silenced - and undoes it to the same fingerprint, idempotently. The evidence the class was admitted on comes back through the agent's own tools, and the one claim A10 could only state from source is now seen: the catalog's spans fail over database queries that succeed, with `Product Not Found` on products the store holds. `v2-postgresql-catalog-corruption` may be authored as `datastore_corruption` row 3 (dev), carrying `restore_data` |

**Prediction scorecard.** INJECTS: **right**, with one registered prediction wrong - *no latency
alert* - on fraud-detection, whose error and latency alerts once orders stop are recorded on
`v2-product-catalog-freeze` and `-partition` as the same dead end; the catalog's path stayed fast.
VISIBLE: **right** on (c), (b), and **(d), predicted at moderate confidence and seen whole**.
RESTORES: **right**; all clear at the edge of the registered window.

## What R6 changes for the scenario

- **The page carries the culprit's reader, not the culprit's store.** product-catalog pages on its
  own error rate; the store the fault lives in emits no spans, no series, and no line about it. A
  responder who stops at the page finds a catalog that fails fast and answers `Product Not Found`
  for products it lists - and the database query under each failure succeeding.
- **The hop line names the catalog, not the database.** The trace tool's degrading hop ends at
  product-catalog's server span, because the database span beneath it is not in error. The
  ground truth is the store's contents; the evidence that points there is the error text, a NULL
  that cannot be scanned into a named column - in recommendation's log and in the catalog's own
  span status.
- **fraud-detection's alerts are recovery-shape noise the narrative must place.** Its short
  error and latency alerts arrive with the orders' silence, as on the freeze and the partition of
  the same service.

## Timeline

| clock (UTC) | event |
|---|---|
| 05:04:02 | world check ALL PASS, `status` empty; `start` — NULL on all 10 rows, `f9b57aae…` → `ea4a8cf3…` |
| 05:04:03.99 | recommendation's first logged failure: the scan error naming `description` |
| 05:07:33 | `ServiceHighErrorRate` on frontend, frontend-proxy, load-generator, product-catalog, recommendation (+3:31) — **PAGES** |
| 05:08:33 | `ServiceHighErrorRate/checkout` (+4:31) |
| 05:11:33 | `ServiceNoTraffic` on accounting, currency, email, payment, quote, shipping; `ServiceHighErrorRate/fraud-detection` (+7:31) |
| 05:12:33–05:13:03 | `ServiceHighLatency/fraud-detection`; both of its alerts gone by 05:13:33 |
| ≈05:15:33 | shape; read-back window 05:04..05:15 |
| 05:15:34 | `stop` — 10 values written back, fingerprint `f9b57aae…`; `status` empty; second `stop` a no-op |
| 05:16:35 | no-traffic alerts cleared |
| 05:19:35 | checkout and load-generator cleared |
| 05:20:35 | all clear; quiet to the last poll at 05:25:05 |
