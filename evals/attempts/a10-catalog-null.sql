-- A10 - make every row of catalog.products unreadable to product-catalog: its `description` set to
-- NULL, which the service scans into a Go `string` and cannot (`converting NULL to string is
-- unsupported`). The column is nullable in the schema, so the store accepts the write; only the
-- reader refuses it. One transaction; nothing runs on after it.
--
-- Run it with the database's own client, inside the database's container, fed on stdin so no
-- quoting crosses a shell boundary (the A4 void run's failure mode):
--     docker exec -i postgresql psql -U root -d otel -v ON_ERROR_STOP=1 \
--         < evals/attempts/a10-catalog-null.sql
--
-- It refuses to run unless all ten rows still carry a description (so a second run cannot save
-- the corrupted state over the good copy), saves the ten ids and descriptions to
-- /tmp/a10-description.csv inside the container for a10-catalog-restore.sql, prints the table's
-- fingerprint before and after, and commits.
\set QUIET on
\pset footer off
BEGIN;
DO $$
BEGIN
  IF (SELECT count(description) FROM catalog.products) <> 10
     OR (SELECT count(*) FROM catalog.products) <> 10 THEN
    RAISE EXCEPTION 'a10: catalog.products is not at rest (expected 10 rows, 10 descriptions)';
  END IF;
END $$;
\copy (SELECT id, description FROM catalog.products ORDER BY id) TO '/tmp/a10-description.csv' csv
SELECT to_char(now() AT TIME ZONE 'UTC', 'HH24:MI:SS') AS utc, 'before' AS a10,
       count(*) AS rows, count(description) AS descriptions,
       md5(string_agg(id || ':' || coalesce(description, '<null>'), '|' ORDER BY id)) AS fingerprint
  FROM catalog.products;
UPDATE catalog.products SET description = NULL;
SELECT to_char(now() AT TIME ZONE 'UTC', 'HH24:MI:SS') AS utc, 'after' AS a10,
       count(*) AS rows, count(description) AS descriptions,
       md5(string_agg(id || ':' || coalesce(description, '<null>'), '|' ORDER BY id)) AS fingerprint
  FROM catalog.products;
COMMIT;
\! echo "$(date -u +%H:%M:%S) a10: committed; saved copy $(wc -l < /tmp/a10-description.csv) rows"
