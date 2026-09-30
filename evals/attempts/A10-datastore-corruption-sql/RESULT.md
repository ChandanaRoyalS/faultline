# A10 — product-catalog's rows made unreadable in Postgres — RESULT

**Run of record 2026-09-30 04:16:29 → 04:37:30 UTC, \$0.** The second run, `transcript.txt`,
registered in `evals/runs/PREREGISTRATION-T7.1-A10.md` before either run. The verdicts are the
pre-registered definitions applied to that transcript and nothing else.

**The first run, 03:47:35, is void** (`transcript-void-0347.txt`), decided before the second was
run: its inject went in while the world check printed NOT READY, with A9's leftover
`ServiceNoTraffic/kafka` firing, against step 1 of `PREREGISTRATION-T7.0.md`; that alert overlaps
this fault exactly (stopping orders silences kafka too). And its `watch.py 12` was interrupted at
+10:30, which also cancelled the revert until a second paste ran it at +13:07. The first mistake
was mine: the command block ran every line in turn and nothing in it stopped on the check. The
second run's block made the inject conditional on `ALL PASS` and on the inject's own success.
Nothing from the void run is used below.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes, at +3:00** | Pre-state ALL PASS, nothing firing. At 04:19:29 (+3:00) `ServiceHighErrorRate` fired on **five services in the same evaluation: frontend, frontend-proxy, load-generator, product-catalog and recommendation**; checkout's a minute later (+4:00). Then `ServiceNoTraffic` on accounting, currency, email, payment, quote and shipping at +8:00, and on fraud-detection at +10:00. **No latency alert at any point.** At +11:30 product-catalog stood at **50.00 %** errors, a **2 ms** p95 and 2.900 req/s; recommendation 66.67 %, frontend 56.25 %, frontend-proxy 54.55 %, checkout 50.00 % at a 3 ms p95, load-generator 29.64 %; every service an order reaches only once placed - payment, email, currency, quote, shipping, accounting, kafka, fraud-detection - at **0.000** req/s. **No service in the table is the tool**: `psql` in the database's container reported as nothing (Q118's check, passed). |
| **DISTINCT** | **yes on (c)** | recommendation's log carries `sql: Scan error on column index 2, name "description": converting NULL to string is unsupported` inside `failed to load products: failed to get products from rows: failed to scan product row:`, **668 lines** in the 20-minute read; the frontend's log carries the same text, 668 lines, in the three lines read as recommendation's error relayed (`details = ...`, `debug_error_string = ...`); and **`Error: 5 NOT_FOUND: Product Not Found: OLJCESPC7Z`** and **`... HQTGWGPNH4`** - two of the table's ten ids - **1,520 lines**. The reader's own words name a NULL it cannot scan and the column it sits in, and the catalog calls products it holds missing. The store's own stream held **4 lines** in 20 minutes; the three printed are routine checkpoints (`checkpoint starting: time` at 04:12:44 and 04:17:44, and one `checkpoint complete`), none naming the update or the table - the fourth was not printed. (b): nothing recorded as changed, by construction. (d) is stated from source and left to the class's rehearsal through `trace_query`, as registered. |
| **REVERTS** | **yes** | The restore at 04:28:00 (+11:31) printed `10 \| 10` and fingerprint **`f9b57aae49e7ad4305e3120a54fdc20d`** - equal to the inject's "before" line and to the registered prediction, the catalog as shipped. The no-traffic alerts cleared by 04:29:30 (+1:30 after the restore), checkout's error rate by 04:31:30 (+3:30), the rest by 04:32:30: **all clear 4m30s**, and quiet for the last five minutes of `watch.py 10`. No alert fired only in recovery. Nothing restarted: product-catalog, postgresql, recommendation and checkout kept their start times from before the attempt, fraud-detection its A9 count (14, started 03:18:59). |
| **ADMISSIBLE** | **yes** | It pages on the world's own services, it is distinct on (c), and it reverts to the exact bytes it began from. |

**Prediction scorecard.** PAGES within five minutes, product-catalog among the first: **right** -
+3:00, product-catalog in the first evaluation, checkout a minute later; product-catalog's ratio at
50 % as predicted from `OmitRows` (its database spans succeed, its server spans all fail). No
latency alert: **right**. No-traffic on payment and email, then accounting and fraud-detection,
from +6 to +10: **right** (+8:00 and +10:00) - and **incomplete**: currency, quote and shipping
went silent with them, the three being, on this world, reached only by an order that gets past its
product lookups. DISTINCT: **right** on recommendation's log and on `Product Not Found` for ids the
table holds; **not shown** for the frontend's own list failure - the three frontend lines read are
recommendation's error relayed, and whether the home page's `INTERNAL` reached the frontend's log
in its own words is not established by a three-line read. The store's stream: right as far as
read. REVERTS: **right** on every registered point.

## What the page looks like

**Five services at once, the culprit among them, nobody slow.** The ratios crossed at the first
evaluation after the onset and the rule's two minutes put five alerts in one poll; checkout, whose
orders fail at the first product lookup, a minute behind on a smaller share. Everything that
depends on an order being placed - the payment, the confirmation, the quote, the conversion, the
topic and both its readers - fell silent in the same two minutes, 8 to 10 minutes in, as their
windows drained. The only alert off that pattern was fraud-detection's error rate for one poll at
+6:00, before its no-traffic alert: consistent with the dead end recorded on
`v2-product-catalog-freeze` (with orders stopped, fraud-detection's flag stream is what errs), and
not read here. Kafka reached 0.000 req/s and raised no alert of its own inside the fault; not
chased.

**The shape against the comparators.** The freeze and the partition of the same service
(`v2-product-catalog-freeze`, `v2-product-catalog-partition`) starve the **same six** services -
accounting, currency, email, payment, quote, shipping - so that silence does not tell them apart.
What does: there, the callers page and the culprit does not, on errors *and* latency, and the
catalog itself goes `ServiceNoTraffic`; here the catalog pages on its own error rate in the first
evaluation, keeps emitting spans at 2.9 a second, and no p95 moves (the catalog's 2 ms, checkout's
3). The feature flag (`v2-product-catalog-flag-failure`) refuses one product in the flag's own
words and leaves lists alone, and paged only the frontend and the proxy; here every list failed
and single lookups failed as `Product Not Found`. A slow dependency errs nothing. And what names
the cause is in the callers' logs, in the reader's words.

## Loose end, on record and not chased

**Equal counts in two streams, twice.** The frontend and recommendation reads counted 668 lines each
here, and 592 each in the void run. The printed frontend lines carry recommendation's error text,
so each failed recommendation may be logged the same number of times by both, but that is not
established, and nothing above rests on a count: the verdicts rest on the lines being present
with the column's name.

## What A10 decides

**A SQL table is admissible as a `datastore_corruption` store.** By the registration, the injector
gains the tool next - the same one-transaction write and restore, the saved copy kept outside the
store's schema, the fingerprint checked on restore - then an R-rehearsal through it, then
`v2-postgresql-catalog-corruption` is authored with the class's `restore_data`. Row 3 goes forward;
row 4 (`v2-postgresql-reviews-corruption`) waits its turn.

## Timeline

| clock (UTC) | event |
|---|---|
| 04:16:29 | world check ALL PASS; inject committed, fingerprint `f9b57aae…` → `ea4a8cf3…`, 10 rows, 0 descriptions |
| 04:19:29 | `ServiceHighErrorRate` on frontend, frontend-proxy, load-generator, product-catalog, recommendation (+3:00) — **PAGES** |
| 04:20:29 | `ServiceHighErrorRate/checkout` (+4:00) |
| 04:22:29–04:22:59 | `ServiceHighErrorRate/fraud-detection`, cleared by 04:23:29 |
| 04:24:29 | `ServiceNoTraffic` on accounting, currency, email, payment, quote, shipping (+8:00) |
| 04:26:29 | `ServiceNoTraffic/fraud-detection` (+10:00) |
| ≈04:28 | shape, the four log reads |
| 04:28:00 | restore committed, fingerprint back to `f9b57aae…` (+11:31) |
| 04:29:30 | no-traffic alerts cleared |
| 04:31:30 | checkout's error rate cleared |
| 04:32:30 | all clear (4m30s after the restore); quiet to 04:37:30 |

## Addendum, 2026-09-30 - the registered fallback would not have done what it said

The registration's fallback - *recreate the container, whose init script reloads the catalog as
shipped* - rested on its claim that the container has no volume. Read off the running container
later the same day (`disk_fill` row 2's precondition), `/var/lib/postgresql/data` is an anonymous
Docker volume, which the postgres image declares, and `docker compose up --force-recreate` keeps a
container's anonymous volumes: the recreate would have restarted Postgres on the same corrupted
rows. A reload needs `--renew-anon-volumes`. The fallback was never used here, in R6, or in either
recording of the scenario - every restore wrote the saved copy back and matched the fingerprint -
so no verdict moves.
