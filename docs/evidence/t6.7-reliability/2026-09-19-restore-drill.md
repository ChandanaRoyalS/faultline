# The restore drill — 2026-09-19

**README §3.7's restore procedure, executed for the first time, over the live database, on the
VM. 18 seconds from the first command to every container healthy; every table at its count.
$0.00.** T6.7 piece 2; the plan row's *"documented restore procedure actually executed once"*.

```
21:23:12  docker compose stop faultline orchestrator executor prometheus-self      10.3 s
21:23:23  gunzip -c faultline-2026-09-19T2122Z.sql.gz | psql -v ON_ERROR_STOP=1     0.48 s  exit 0
          docker compose up -d --wait                                                7.1 s
21:23:30  schema at 0010
          diff counts-before counts-after                                            identical
```

## What was written first

The design note (§2) said the drill would run *"the runbook's own words"*, and the working session
said, before the first command: **the runbook as printed cannot work** - its first line is `docker
compose down`, which removes the Postgres container, and its second line `exec`s into that
container. Predicted, then routed around: the drill used `stop` on the four services that read or
write the database and left Postgres up. The runbook had never been run and was wrong in its first
word; §3.7 is rewritten from what was typed.

## The snapshot

`pg_dump -U faultline --clean --if-exists faultline | gzip` at 21:22 UTC while the platform was
running: **979,201 bytes**, seventeen tables, taken into `~/snapshots/` rather than `/tmp`. Row
counts before, exact:

| table | rows | | table | rows |
|---|---|---|---|---|
| action_audit | 4 | | incidents | 17 |
| alembic_version | 1 | | postmortem_acceptances | 10 |
| applied_events | 236 | | trajectories | 15 |
| change_records | 10 | | trajectory_proposals | 13 |
| eval_configs | 0 | | trajectory_retrievals | 28 |
| eval_runs | 0 | | trajectory_steps | 295 |
| incident_acknowledgements | 1 | | trajectory_tool_calls | 94 |
| incident_chunks | 311 | | | |
| incident_episodes | 119 | | | |
| incident_rejections | 1 | | | |

Everything the deployment has ever recorded about itself: yesterday's first action and its two
investigations, the loop's four incidents, the T6.5 corpus and its acceptances, the four audit
rows. After the restore, the same seventeen numbers.

## What it took, and what it showed

**`stop` is ten seconds, and all of it is the orchestrator.** `faultline`, `executor` and
`prometheus-self` stopped in under a second each; the orchestrator took 10.2 s, which is its
consumer loop finishing a blocking read (`block_ms = 5000`) and Docker's grace period. A restore
that needs to be faster than that would send `SIGKILL`, and nothing here needs to be.

**The restore is half a second.** `--clean --if-exists` drops and recreates every table inside
one `psql` session; with the writers stopped nothing holds a lock, so the 2026-09-18 shape (a
migration waiting 46 minutes on the platform's own idle transactions) cannot arise. `ON_ERROR_STOP`
was set so that a failure would have been an exit code rather than a database that is partly the
snapshot; the log carries one blank line and `(1 row)`.

**`up -d --wait` is seven seconds**, and `faultline-migrate` says `schema at 0010` and applies
nothing, because `alembic_version` is a table in the dump like any other. The public page answers
502 from Caddy for the eighteen seconds and the world is untouched throughout.

**One check in the block was wrong and the platform was right.** `curl localhost:8000/healthz`
from the host returned nothing, because the deployment publishes no port 8000 - Caddy is the only
door (§3.2). The runbook's line is `docker compose exec faultline curl localhost:8000/healthz`.

## What changed because of it

- §3.7 says `stop`, names the four services, sets `ON_ERROR_STOP`, checks health from inside the
  container, and carries the timings above.
- `deploy/snapshot.sh` runs the same dump nightly from cron into `~/snapshots/` with a seven-day
  window and refuses to keep a dump under 10 KB. README §4, MVP-CUT and THREAT-MODEL no longer say
  *"no backups beyond a manual snapshot"*; they say *nightly snapshots on the same disk and none
  off it*, which is what is true.
- The one pre-deploy snapshot that existed, `/tmp/snapshot-before-deploy-2026-09-18.sql.gz`, is
  superseded by `~/snapshots/faultline-2026-09-19T2122Z.sql.gz`; §3.9 still names it for the
  rollback boundary it was taken for.

## What this does not show

A restore across a schema boundary - the case §3.7 exists for - was not drilled: the snapshot and
the running code were at the same revision, so `faultline-migrate` had nothing to say. The
procedure is the same; what differs is that the old code meets the schema the dump carries, and
that is the constraint §3.7 already spells out. A restore onto a different host was not drilled
either, and cannot be while the snapshots live on the same disk as the database.
