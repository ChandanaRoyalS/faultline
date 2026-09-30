-- A10 revert - put back every `description` in catalog.products from the copy
-- a10-catalog-null.sql saved inside the container, in one transaction:
--     docker exec -i postgresql psql -U root -d otel -v ON_ERROR_STOP=1 \
--         < evals/attempts/a10-catalog-restore.sql
--
-- It refuses to write unless the saved copy holds the ten ids with ten descriptions, and prints the
-- table's fingerprint after the write: REVERTS needs it equal to the "before" line the inject
-- printed. The saved copy is left in place and removed by hand once the fingerprints match. If the
-- copy is missing or refused, the registered fallback is to recreate the container, whose init
-- script loads the catalog as shipped.
\set QUIET on
\pset footer off
BEGIN;
CREATE TEMP TABLE a10_saved (id text PRIMARY KEY, description text) ON COMMIT DROP;
\copy a10_saved FROM '/tmp/a10-description.csv' csv
DO $$
BEGIN
  IF (SELECT count(description) FROM a10_saved) <> 10
     OR (SELECT count(*) FROM a10_saved s JOIN catalog.products p USING (id)) <> 10 THEN
    RAISE EXCEPTION 'a10: the saved copy does not hold the ten ids with ten descriptions';
  END IF;
END $$;
UPDATE catalog.products p SET description = s.description FROM a10_saved s WHERE p.id = s.id;
SELECT to_char(now() AT TIME ZONE 'UTC', 'HH24:MI:SS') AS utc, 'restored' AS a10,
       count(*) AS rows, count(description) AS descriptions,
       md5(string_agg(id || ':' || coalesce(description, '<null>'), '|' ORDER BY id)) AS fingerprint
  FROM catalog.products;
COMMIT;
