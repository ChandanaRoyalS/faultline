# The deployment watches itself — 2026-09-18

**The VM runs `a1a6c412`**, the first image built after the T6.6 recheck and the first fully green
`main` since 2026-09-15. Every T6.6 surface is live on the deployment. **$0.00** — no model call
was made; the proof is the platform's own telemetry about itself, idle.

```
tracing: exporting to http://otelcol:4317        (faultline, orchestrator)
metrics: /metrics mounted                        (faultline)
healthz -> 200   metrics -> 404   api/v1/alerts -> 404
up{instance="faultline:8000", job="faultline"} = 1   (from prometheus-self, on the VM)
```

`/metrics` answers 404 from the internet and 200 to the one reader that should have it. The
`faultline-self-metrics` datasource points Grafana at `prometheus-self:9090` across the shared
network; both dashboards are provisioned at version 1 on the VM's Grafana.

## What it took, in the order it happened

**No image to deploy.** CI had been red on every `main` commit since the 15th — twenty-five runs
— because the integration job seeded the dev tree with an empty acceptance ledger and refused all
ten postmortems (Q67's shape, in CI). The `docker` job has no `needs:`, so images kept publishing
and nothing forced a look (Q75). Fixed by committing the ledger (#372); the next run was red on a
second thing the first had hidden — the retrieval gate still founded on the pre-T6.5 corpus,
reading the recorded re-score as a regression (#373). Then a GHCR `unknown blob` on the manifest
push, rerun, green.

**The VM was 111 commits behind and one deploy undocumented.** It ran `2e097dc` (#262) with no
§3.9 row; schema at 0007 with 0008–0010 pending, and 0009 renames a column, so a snapshot came
first (422 KB, `/tmp/snapshot-before-deploy-2026-09-18.sql.gz`).

**The migration waited 46 minutes on a lock the platform held against itself.** `faultline-migrate`
reached 0010 — `ALTER TABLE trajectories ADD COLUMN trace_id` — and stopped. `pg_stat_activity`:

| pid | state | age | last statement |
|---|---|---|---|
| 1012208 | active, waiting on `relation` lock | 46m | `ALTER TABLE trajectories ADD COLUMN IF NOT EXISTS trace_id …` |
| 1012192 | **idle in transaction** | 46m | `SELECT COALESCE(SUM(tokens_in), 0), … FROM trajectory_steps` |
| 1012190 | **idle in transaction** | 46m | `SELECT id, state, opened_at, … FROM incidents` |

1012192 is the API's connection and its last statement is **`/metrics`'s token sum**: piece 3 ran
three `SELECT`s per scrape on a psycopg connection that nothing committed, so the first scrape
after the container started opened a transaction that held `ACCESS SHARE` on `trajectories` and
`trajectory_steps` for the life of the process. 1012190 is the orchestrator's `queued()` poll,
the same shape from older code. **The surface built so the platform could watch itself blocked
the migration that gives its trajectories a trace id.** `pg_terminate_backend` on both released
the `ALTER` within a second; `schema at 0010`, ten acceptances imported, 60 documents and 311
chunks seeded — the Mac's corpus to the chunk.

The fix is `faultline.pgread.reading`: every read path rolls its transaction back when the block
ends, on success or exception, so a long-lived reader holds nothing between reads. Unit tests hold
every Postgres store to it by counting rollbacks through a fake; the integration store test asserts
`transaction_status == IDLE` on a real connection after each read. deploy/README §3.9 carries the
diagnosis and the two commands, for the next time something else holds a lock.

**The image on the VM still has the defect.** `a1a6c412` predates the fix; the next image after it
lands is the one to deploy, and until then a migration against the live deployment will wait
again. Documented rather than hidden, because a rollout note that ends *fixed* while the running
image is not would be the kind of sentence this repository exists not to write.

## What this does and does not show

**Shown**: the deployment traces (the daemons export to the world's collector), serves and scrapes
its own metrics, writes JSON lines, holds the T6.5 corpus with its acceptances, and closes
`/metrics` at the edge — each read back from the VM, not from a Mac.

**Not shown**: a trace from a real investigation on the VM. The orchestrator has emitted no spans
because no incident has opened since the deploy; the first one that does will put an `incident`
root with its `investigation` beneath it into the VM's Tempo, beside the outage's own trace — the
demo beat the plan row names. That costs one investigation (~$0.70) and either happens on its own
with the next real alert or by §3.6's injected fault. Neither was spent today.
