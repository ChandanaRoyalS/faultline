# Pre-registration - A10, a datastore's contents corrupted where the store is a SQL table

**Written before the attempt is run. Nothing here is a result.** T7.1's `datastore_corruption` row
has one scenario, on valkey-cart (`v2-cart-store-corruption`); row 2, the `orders` topic, was
attempted by hand as A9 and is blocked (it paged nothing). Rows 3 and 4 need a new tool each, and
the T7.0 bar is that a tool is attempted by hand, then rehearsed through the injector, before a
scenario is authored against it (`docs/design/t7.1-candidates.md`, `datastore_corruption`;
`evals/runs/REHEARSALS-T7.0.md`). A10 is row 3's attempt: `v2-postgresql-catalog-corruption`,
*product-catalog's rows made unparseable*. It is a new attempt under the protocol of
`PREREGISTRATION-T7.0.md`, which is frozen.

**The question.** When the rows product-catalog reads are still in the store but no longer readable
by it, does the world page - and on what - and does what a responder can read name a store whose
contents are wrong, rather than a catalog that is down, slow, or switched off by a flag?

## Read at source before registration (world-v2, 2026-09-30)

- **The table** (`src/postgresql/init.sql`): `catalog.products`, ten rows, loaded once by the
  container's init script. `name`, `price_currency_code`, `price_units` (BIGINT) and `price_nanos`
  (INT) are `NOT NULL`; **`description`, `picture` and `categories` are nullable `TEXT`**. The
  service's role, `otelu`, has `SELECT` only on the schema: nothing in the world writes these rows
  after start-up. The container has no volume, so its data lives in the container and a recreate
  reloads the catalog as shipped.
- **The reader** (`src/product-catalog/main.go`, `database/sql` through `otelsql` with
  `OmitRows`): every call queries the database - there is no cache. `ListProducts`
  (`loadProductsFromDB`) reads all ten rows, `GetProduct` (`getProductFromDB`) one row by id,
  `SearchProducts` the rows whose name or description matches. Each row is scanned into Go
  `string`, `int64` and `int32` variables. **A NULL scanned into a `string` fails**
  (`database/sql`: `sql: Scan error on column index N, name "...": converting NULL to string is
  unsupported`), and the failure happens after the query returns, so the database span beneath it
  succeeds.
- **What the failure looks like to callers.** `ListProducts` marks its server span in error with
  the whole text and returns gRPC `INTERNAL` `failed to load products: ... converting NULL to string
  is unsupported`; one bad row fails every list, since every list reads every row. `GetProduct`
  discards the error: it marks its span in error with **`Product Not Found: <id>`** and returns gRPC
  `NOT_FOUND`, for an id the table holds. The service writes no log a tool can read.
- **Who reads it.** recommendation calls `ListProducts` on every `ListRecommendations` (the cache
  flag is off); the frontend calls `ListProducts` for the home page (browser traffic is on) and
  `GetProduct` for product pages, cart views, add-to-cart and recommendations; checkout calls
  `GetProduct` for each cart item in `prepOrderItems`, **before** it charges, so an order that
  cannot read its products fails before payment, shipping, email and the `orders` topic see it.
- **The design follows from that.** No value of the numeric columns fails its Go type, and the text
  columns accept any text, so **NULL in a nullable text column is the one write the schema accepts
  and the reader refuses**. One column, `description`, on **every row** - the candidate's *rows*,
  and row 1's precedent, which corrupted every record the service reads. The store stays up,
  answers at once and holds all ten products; only its contents are wrong for its reader.

## Protocol - the eight's, with the injection below

Steps 1 to 6 of `PREREGISTRATION-T7.0.md` apply unchanged: pre-state quiet (and, since T7.1, the
world check: `python3 ~/Downloads/world_check.py`), inject, `watch.py 12`, `shape.py
product-catalog`, the (c) reads below, revert, `watch.py 10`, transcript and `RESULT.md` under
`evals/attempts/A10-datastore-corruption-sql/`.

- **Mechanism**: `evals/attempts/a10-catalog-null.sql`, run by the database's own client inside the
  database's container as its superuser, one transaction: refuse unless all ten rows carry a
  description; save the ten ids and descriptions to `/tmp/a10-description.csv` in the container;
  print the table's fingerprint (an md5 over every id and description); `UPDATE catalog.products
  SET description = NULL`; print the fingerprint again; commit. The write is made once and stays:
  nothing in the world writes these rows, so no sweep is needed (row 1's store was rewritten by its
  own service, this one is not).
- **Inject**: `docker exec -i postgresql psql -U root -d otel -v ON_ERROR_STOP=1 <
  evals/attempts/a10-catalog-null.sql`.
- **The (c) reads, after `watch.py 12`**: `python3 evals/attempts/logs.py frontend "Scan error" 20
  3`, `logs.py recommendation "Scan error" 20 3`, `logs.py frontend "Product Not Found" 20 3`, and
  `logs.py postgresql "" 20 3` (the store's own stream).
- **Revert**: `docker exec -i postgresql psql -U root -d otel -v ON_ERROR_STOP=1 <
  evals/attempts/a10-catalog-restore.sql` - one transaction that refuses unless the saved copy holds
  the ten ids with ten descriptions, writes them back, and prints the fingerprint. REVERTS needs it
  **equal to the inject's "before" line**. Then, and only then, the saved copy is removed: `docker
  exec postgresql rm /tmp/a10-description.csv`. **Fallback**, if the copy is missing or refused:
  recreate the container, `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 up -d --no-deps
  --force-recreate postgresql`, whose init script reloads the catalog as shipped - and accounting's
  order tables empty, which is recorded with the fallback if it is used.
- **Tested before registration** on a throwaway Postgres loaded from the world's `init.sql`: the
  inject printed `10 | 10` and fingerprint **`f9b57aae49e7ad4305e3120a54fdc20d`** before and `10 |
  0` after; a second inject was refused by its guard and wrote nothing; the restore printed `10 |
  10` and the same `f9b57aae...` fingerprint, and a second restore did the same.
- **Q118, checked by construction and read in the run**: the client is the stock Postgres image's
  `psql`, with no tracing agent in that container, so the tool should report as no service. The
  run's `shape.py` table is read for any service named after the database or its client.
- **Comparators**: `v2-product-catalog-flag-failure` (the catalog refusing one product by a flag),
  `v2-product-catalog-partition` and `v2-product-catalog-freeze` (the catalog unreachable or hung),
  `v2-product-catalog-dependency-latency` (the catalog slow).
- **What would distinguish**: (c) - the callers' logs carry the reader's own words, a NULL that
  cannot be scanned into a named column, beside `Product Not Found` for products that exist; a flag
  names the flag, a partition or freeze logs deadlines and connection failures, latency logs
  nothing. (d), stated from source and left to the class's rehearsal through `trace_query`, as A4b
  left it: the catalog's server spans in error in a few milliseconds with its database query beneath
  them **succeeding**, and the catalog's call rate and p95 unmoved. (b) - nothing is recorded as
  changed: a row update leaves no change record.

## Prediction

- **PAGES**: yes, **`ServiceHighErrorRate` within five minutes**, first on some of product-catalog,
  recommendation, checkout, the frontend and frontend-proxy, with product-catalog among them - every
  one of its server spans fails and, with `OmitRows`, they are about half of what it emits, so its
  ratio sits far above the line. Then the load generator's. Then `ServiceNoTraffic` on the services
  an order reaches only once it is placed - payment and email certainly, accounting and
  fraud-detection as the topic goes quiet - from about +6 to +10. **No latency alert**: the failures
  are fast. Confidence: high on the page and on product-catalog paging; moderate on the no-traffic
  set and on no latency rule (a caller's retries may move a p95). Services not read at source that
  may also call the catalog (product-reviews' product questions, ad) are not predicted either way.
- **DISTINCT** on (c): the frontend's log carries `converting NULL to string is unsupported` with
  the column's name, `description`, inside the `INTERNAL` from the home page's list, from the first
  minute, and `Product Not Found:` for ids the table holds; recommendation's log carries the same
  scan text inside its failed call. The store's own stream carries **no line naming the update or
  the table**: Postgres logs no statements by default and an update is not an error; its routine
  checkpoint lines go on.
- **REVERTS**: yes. The restore's fingerprint equals the inject's "before" line - predicted
  `f9b57aae49e7ad4305e3120a54fdc20d`, the catalog as shipped; the errors stop at its commit, with
  nothing restarted (the service reads on every call and its connections are untouched); every alert
  clears inside `watch.py 10` - the error-rate alerts as their five-minute windows drain, the
  no-traffic alerts as orders flow again.

## What A10 decides

If it pages, distinct and reverts, a SQL table is admissible as a `datastore_corruption` store and
the injector gains the tool - the same write and restore, with the saved copy kept outside the
store's schema - then an R-rehearsal through it, then the scenario, carrying the class's
`restore_data`. If it does not page, the finding is recorded and row 3 is blocked, as the row
allows, and row 4 (`v2-postgresql-reviews-corruption`, which reads Postgres unverified) is next. If
the fingerprint does not come back equal, REVERTS is **no** whatever the alerts do, and the
fallback's recreate is recorded with it.
