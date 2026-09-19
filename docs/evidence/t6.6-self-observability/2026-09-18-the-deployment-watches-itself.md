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

## Addendum, 2026-09-18 ~10:50 UTC — the fix is on the VM

*"The image on the VM still has the defect"* stopped being true about an hour after it was
written. `adbb136` (#374, `faultline.pgread`) went out by §3.7's shape - no migration, `schema at
0010` before and after, seconds - and thirty seconds after the containers started, with `/metrics`
scraped at least twice and the orchestrator's queue polled several times:

```
select count(*) from pg_stat_activity where datname='faultline' and state='idle in transaction'
0
```

The same query read 2 for the entire life of the previous image. The next migration against this
deployment will not wait on the platform.

## Addendum 2, 2026-09-18 11:38 UTC — the fourth daemon, and the first gated image

`d89876cc` (#377) is on the VM: the first image CI could not have published with a red job
behind it, and the first on which `faultline-execute` exports. Within the minute of `up -d
--wait` returning:

```
executor-1  | tracing: exporting to http://otelcol:4317
executor-1  | {"ts": "2026-09-18T11:38:55.912+00:00", "level": "INFO", "logger": "uvicorn.error", "msg": "Started server process [1]", "component": "executor", ...}
idle in transaction: 0
trajectories with no outcome, or orphaned: (none)
```

The last line is the VM's answer to Q72: the deployment has never had a sweep killed under it,
so there was nothing for the reconciler to name - the development database's four are the only
orphans this project has produced, and they are closed (first-scrape note, addendum). Still not
shown: an `action.execute` span with anything in it. The kill switch is off and no action has been
approved on the VM since the deploy, so the span exists as code that runs and not yet as a trace
anyone has read; the first approved action puts one in Tempo, and it costs whatever the
investigation that proposes it costs.

One thing the JSON lines show that a test did not: uvicorn passes `color_message` as an `extra=`
field, so its startup lines carry a key with an ANSI escape in it. Faithful - the formatter puts
every extra on the line, as designed - and harmless, and noted here rather than filtered, because
a filter for one library's key is the kind of special case that accumulates.

## Addendum 3, 2026-09-19 ~19:57 UTC — the spans go to Tempo directly (Q77)

Applied by `git pull` and a recreate of the three daemons - no image change, `2ddc2e6` (#381) is
compose configuration - then a re-up of the world overlay for the collector alone. Read back
within the minute:

```
executor-1     | tracing: exporting to http://tempo:4317
orchestrator-1 | tracing: exporting to http://tempo:4317
faultline-1    | tracing: exporting to http://tempo:4317
otel-col networks: opentelemetry-demo            (faultline-deploy-net gone)
probe.direct-to-tempo -> in Tempo by search in 10 s
calls_total{service_name="faultline"}: 0 series
```

The last line is the observable ADR-0030 addendum 4 promised, already further along than
promised: the series is not frozen, it is gone - Prometheus had marked it stale in the thirty-one
hours since the platform last sent a span through the collector, so there is no counter left to
watch. The platform is no longer a service in the world's metrics. Its traces reach the same
Tempo they always did, by the same name the traces specialist reads. Jaeger holds nothing of the
platform's from here on. $0.00.
