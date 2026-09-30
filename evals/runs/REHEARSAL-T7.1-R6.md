# Rehearsal - R6, `datastore_corruption` on a SQL table, through the injector and the agent's tools

**Written before the rehearsal is run, in the same change as the tool it rehearses. Nothing here
is a result.** A10 (`evals/attempts/A10-datastore-corruption-sql/RESULT.md`) admitted a SQL table
as a `datastore_corruption` store by hand. The T7.0 bar is that the injector's code does the same
thing, that its restore undoes it, and that what the attempt measured is reachable by the agent's
own tools, before a scenario is authored (`evals/runs/REHEARSALS-T7.0.md`, whose protocol this
follows unchanged and which stays as written). R6 is that rehearsal for
`v2-postgresql-catalog-corruption`, `datastore_corruption` row 3.

## What the tool is

`DatastoreCorruptionFault` gains a second mechanism, chosen by the definition naming a `table`, as
`resource_exhaustion` chooses between memory and CPU. It is A10's write and restore, with two
changes the registration asked for or that follow from it:

- **The saved copy lives in the injector's state**, not in the container: the column's every value
  keyed by `id`, read in the same query as the table's fingerprint, and written to the state file
  with the rest of the restore. A10 kept it in the container's `/tmp`; the registration asked for
  it outside the store's schema, and the state file is outside the store altogether.
- **The restore checks the fingerprint.** It writes the saved values back in one statement and
  refuses to call itself done unless the fingerprint matches the one read before the write; a
  refusal keeps the state entry, and with it the copy, for the next `stop`.

It refuses, before writing, a table that is not at rest (any row without a value - a second run
would save the corrupted state over the good one), a key that does not identify the rows, and any
name that is not a plain lower-case SQL identifier (the statements are built from them). After
writing it reads the table again and puts the copy back if the column is not empty. The client is
the stock `psql` in the database's own container, which carries no tracing agent (A10, Q118's
check). `tests/test_integration_sql_corruption.py` runs it against a real Postgres in a container
through the real Docker CLI. Before this registration its three tests' bodies were run against a
local Postgres 16 with `docker exec` replaced by the same client run locally: values with quotes,
pipes, newlines, tabs, dollar signs and non-ASCII letters came back byte for byte, a `NOT NULL`
column was refused with nothing written, and the world's own catalog, loaded from its init script,
fingerprinted as `f9b57aae49e7ad4305e3120a54fdc20d` - A10's printed value. The containerised run
is made on the Mac before this change merges, and its output goes with R6's transcript.

## What R6 must show

| id | class | pages as (from A10) | evidence the tools must return |
|---|---|---|---|
| `v2-postgresql-catalog-corruption` | `datastore_corruption` | `ServiceHighErrorRate` on frontend, frontend-proxy, load-generator, product-catalog and recommendation in one evaluation, +3:00; checkout +4:00; `ServiceNoTraffic` on accounting, currency, email, payment, quote and shipping ~+8, fraud-detection ~+10; no latency alert | (c) `logql_query recommendation` returns `converting NULL to string is unsupported` with the column's name; (d) `trace_query` on product-catalog returns its server spans in error with that text, and `Product Not Found: <id>` on lookups of ids the table holds, **with the database query beneath each one not in error** - the claim A10 left to this rehearsal; (a) the catalog's p95 unmoved; (b) `change_history` empty or unavailable, never a record |

## Protocol - `REHEARSALS-T7.0.md`'s seven steps, with these specifics

1. **Pre-state.** The world check (`python3 ~/Downloads/world_check.py`) must print `ALL PASS`, and
   `uv run faultline-inject status` must print `no active injections`. **The inject is made
   conditional on both** in the command block, so a failed check injects nothing - A10's first run
   is void because a block did not stop on its check.
2. **Inject**: `FAULTLINE_TOOLS_WORLD=v2 uv run faultline-inject start v2-postgresql-catalog-corruption`;
   its printed change line must show `all 10 rows` and the fingerprint
   `f9b57aae49e7ad4305e3120a54fdc20d -> ea4a8cf36bcb834d426c151c896148e4`, A10's pair. Then
   `status` shows it active.
3. **Observe**: `watch.py 12`, then `shape.py product-catalog`.
4. **Read back** from the inject's minute to now, through `evalharness.readback`, for
   `product-catalog --errors` (the service that pages and the reader whose contents are wrong),
   `recommendation --errors` (the log that names the column), and `postgresql` (the store: its
   log, and that nothing is recorded against it).
5. **Restore**: `stop v2-postgresql-catalog-corruption` - its line must show the fingerprint back
   at `f9b57aae...` - then `status` empty, then `stop` again: `not active`.
6. **Recover**: `watch.py 10`; every alert clear and quiet for the last five minutes (A10: all
   clear 4m30s).
7. **Record** under `evals/attempts/R6-datastore-corruption-sql/`: `transcript.txt` and a
   `RESULT.md` answering INJECTS, VISIBLE, RESTORES and A SCENARIO MAY BE AUTHORED, and nothing
   else.

## Prediction

- **INJECTS**: A10's page shape within a minute or two - five `ServiceHighErrorRate` alerts at
  about +3:00 with product-catalog among them, checkout's a minute later, the six order-only
  services silent at about +8:00 and fraud-detection at about +10:00, no latency alert, and no
  service in `shape.py`'s table that is the tool.
- **VISIBLE**: the (c) line through `logql_query`, as A10's `logs.py` read it (the same query
  path). The (d) claim is the one not yet seen: product-catalog's `ListProducts` spans carrying
  the scan text and its `GetProduct` spans `Product Not Found`, a database span beneath each and
  **not** in error. Confidence moderate: `otelsql` records the query, and the failure comes after
  the query returns, in `database/sql`'s conversion, which no span wraps - read at source, not
  yet seen. (b) unavailable: the platform Postgres is not running on the Mac.
- **RESTORES**: yes - fingerprint back at `f9b57aae...`, `status` empty, the second `stop` a
  no-op, all clear in four to five minutes, nothing restarted.

## What R6 decides

If it injects, is visible and restores, `v2-postgresql-catalog-corruption` may be authored as
`datastore_corruption` row 3 (dev), carrying `restore_data`. If the (d) claim fails, the scenario
may still be authored on (c) and the RESULT says (d) is weaker than A10 stated. If the injector's
page differs from A10's, that is recorded, not tuned. If the restore does not return the
fingerprint, nothing is authored until it does.
