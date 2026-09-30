---
origin: scenario:v2-postgresql-catalog-corruption
split: dev
fault_class: datastore_corruption
recorded_from: 2026-09-30T06:52:53+00:00
capability: cap:91279a09
onset_to_page: 3m45s
page_to_fix: 5m00s
fix_to_all_clear: 4m46s
---

# Every product description in the catalog database is NULL - the catalog cannot read its rows

## What was observed

The page came 3m45s after onset and it was five lines in one evaluation: `ServiceHighErrorRate` on
**recommendation**, **product-catalog**, **load-generator**, **frontend-proxy** and **frontend**.
A minute later **checkout** joined them. About four minutes after the page, `ServiceNoTraffic`
fired on six services at once - **accounting, currency, email, payment, quote and shipping** - and
a minute after that `ServiceHighErrorRate` on **fraud-detection**. Thirteen alerts on thirteen
services by the fix; no latency alert on any of them.

The ratios climbed together from the first minute and settled by T+5: product-catalog at exactly
50 %, recommendation at 67 %, the frontend and the proxy at 49 to 55 %, checkout at 50 %, the load
generator at 28 to 30 %. Nothing got slower. The catalog's p95 **fell**, from about 4.4 ms to
1.9 ms, and checkout's from about 25 ms to 3.5 ms: the failures were the fastest thing either did.
The catalog's rate fell from about 5.5 spans a second to 2.8. Cart, ad and product-reviews kept
their rates, and their error ratios at or near zero.

Everything an order reaches after it is prepared - payment, email, currency, quote, shipping, and
accounting and fraud-detection on the order topic - fell from its usual rate to **zero** by T+5,
with no errors and then no latency value at all. Nothing was failing there; nothing was arriving.

## What was checked

**The catalog, because it paged.** Its error traces were product lookups: the frontend's product
pages and add-to-cart calls, and checkout preparing an order. In each, the catalog's
`GetProduct` server span was in error in 0.3 to 0.8 ms with `Product Not Found: <id>`, and
**beneath it was one `sql.conn.query` span that was not in error**. The database had been asked
and had answered; the catalog then reported the product missing. A search for catalog error
spans under 5 ms returned as many traces as a search for any catalog error - both at the search's
cap of 500 - and a search for a database span in error returned **none**. The catalog's
`ListProducts` spans failed as well, in 94 traces, one under each recommendations request. The
products the catalog called missing were its own, and all ten of them were among them.

**The frontend and the proxy, because they paged.** Their error traces were the same lookups seen
from above: `GET /api/products/{productId}`, `/api/cart` and `/api/checkout` in error in a few
milliseconds, ending at the catalog's span. The frontend's log carried `Error: 5 NOT_FOUND:
Product Not Found: <id>` 1,112 times between onset and fix, for all ten products in the catalog,
98 to 128 times each, and none in the five minutes before.

**Recommendation, because it paged.** Its log, from seven seconds after onset, carried the
reader's own words on every request:

```
Exception calling application: <_InactiveRpcError of RPC that terminated with:
	status = StatusCode.INTERNAL
	details = "failed to load products: failed to get products from rows: failed to scan
	product row: sql: Scan error on column index 2, name "description": converting NULL to
	string is unsupported"
```

376 such lines to the fix, none before and none after, and the frontend's log relayed the same
text. Column 2 of the catalog's product rows is `description`: the catalog was reading rows whose
description was NULL and could not put a NULL into a string.

**Checkout, because it paged.** Its failed orders read the cart without trouble - `GetCart` and
its store command fine - and then failed on the first product lookup: `PlaceOrder` in error with
`failed to prepare order: failed to get product #"<id>"` over the catalog's `Product Not Found`.
Nothing after that step ran: no charge, no shipment, no confirmation, no order published.
Accounting, which logs every order it consumes, logged 43 in the five minutes before the onset
and **none** between onset and fix.

**The catalog's database.** Its own log carried routine checkpoints and nothing else: no error, no
line about a table. It did less than usual - the checkpoint that fell inside the fault was skipped,
nothing having been written since the last one, and the next, just after the fix, wrote 42
buffers where checkpoints at rest write 120 to 165. A store with nothing to write, not a store in
trouble. It exports no runtime series.

**The late alerts on fraud-detection.** With orders stopped, its only span in the window was its
flag-service stream, which the flag service closes and reopens on a ten-minute timer (`stream
closed due to server-side timeout`); its error ratio read 100 % and its p95 the stream's length.
That is an idle consumer's ratio, not a fault of its own.

**What changed.** Nothing that change history can see: no deploy, no configuration, no flag, no
restart.

## Root cause

The product catalog's rows in its Postgres database were corrupted: the `description` column of
every row in `catalog.products` had been set to NULL. The column accepts NULL, so the database
took the write and went on answering every query at once. The catalog service scans each row's
description into a string and cannot scan a NULL, so every read of a row failed after the query
had returned: every product list failed with the scan error naming the column, and every single
lookup failed and was reported as `Product Not Found` for products the table holds. Product
pages, cart views, recommendations and every order failed fast, and orders failed before payment,
so everything an order reaches afterwards went silent. Nothing was deployed, configured or
flagged, and neither the catalog nor its database was down or slow.

## Resolution

The rows' descriptions were written back from a copy taken before the corruption, and the table
checked equal to that copy. Class of fix: **restore_data**. Restarting the catalog would have
changed nothing - it would read the same NULLs on its next query; restarting the database would
have changed nothing - the NULLs were its data; there was no configuration or release to revert.

The recovery was clean on the catalog's path. One product lookup failed at the moment of the
restore and none after; orders flowed again at once, and the no-traffic alerts cleared within a
minute; checkout's error rate cleared two and a half minutes after the restore, the rest as their
five-minute windows drained; all clear 4m46s. **One alert fired only in recovery**:
`ServiceHighLatency` on fraud-detection, under a minute after the restore and for under a minute,
its p95 still carrying the flag stream's length as its window turned over. Nothing restarted.

## Detection notes

- Onset to first page: **3m45s** - five error-rate alerts in one evaluation.
- Services on the page: **five**, the reader of the corrupted store among them. By the fix:
  thirteen alerts on thirteen services, six of them a silence.
- Alerts that fired only during recovery: **one**, fraud-detection's latency, an idle consumer's.
- Did the loudest service turn out to be the culprit? **Partly.** The catalog paged, and it was
  the catalog's data that was wrong - but the catalog's code, process and database connection were
  all healthy. The thing to fix was a table, not a service.
- Would the page alone have led you to the right service? **To the catalog, yes; to the fault, no.**
  The page names the catalog; what names the store is one log line one hop over.
- **"Not Found" for things that exist.** The catalog said ten products were missing - the same ten
  it lists. The database span under every refusal succeeded. A lookup that fails after the
  database answers is a lookup that could not read the answer.
- **The reader's words name the fault.** "Converting NULL to string is unsupported" on "column
  index 2, name description": the contents of the store, not its reachability.
- **Faster, not slower.** Every failure was quicker than a success. A store that is down or slow
  shows as latency; one whose contents are wrong shows as fast errors.
- **Silence behind a failure is starvation.** The six silent services failed nothing; orders stopped
  reaching them. They are consequences, not suspects.
- **The fix is the data.** Restore the rows; restarting or reverting anything leaves them as they
  are.
