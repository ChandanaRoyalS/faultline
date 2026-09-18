# The platform's own Prometheus — 2026-09-18

**Q73 closed live.** `prometheus-self` came up with `make up`, scraped the development read
surface on its first attempt once that surface was the current one, and Grafana's
`faultline-self-metrics` datasource was created by the same script that pushes the dashboards.
**$0.00.** Nothing digest-locked moved.

```
faultline host.docker.internal:8000 -> up = 1
usd in prometheus-self: 192.710375
```

The second line is the first time a platform counter has been read back from a Prometheus rather
than from `curl` against the API. It is the same $192.71 the first scrape recorded by hand this
morning, which is what a counter derived from the trajectory tables should say when no run has
happened between the two readings.

## What it took to get there, in order

**The row's own plan was wrong, and writing the pre-registration is what showed it.** Q73 asked
for four lines in the world's `prometheus-config.yaml` behind a pre-registered `up`-count check.
`generations.CURRENT_OBSERVABILITY` pins the digest those lines would move, for the headline
table; the check would have proven the measurement unchanged and could not have stopped the
digest from moving, so the choice was every recorded figure's stamp or every future run's
admission - for a scrape job. And the row had missed that the world's Prometheus is the one the
agent's `promql_query` reads: the platform's spend and outcome counters would have been one query
away from the agent. A Prometheus of the platform's own answers all three. ADR-0030 addendum 3.

**`up = 0` on the first scrape, and the reason was two daemons.** The scrape target is
`host.docker.internal:8000`, the development convention Alertmanager already posts to. The port
was held by a `faultline-ingest --postgres-dsn` **six days old** - from before any of T6.6 landed,
so it answered `/healthz` and 404'd `/metrics`, and Prometheus correctly read that as down. A
second full daemon, three days old, had been on 8001 since the first-trace session. Two read
surfaces had been serving the same database all week and nothing said so; the one that could not
serve `/metrics` was the one on the conventional port. Both stopped, one started, `up = 1` on the
next scrape.

**The new daemon's first failure came out as JSON.** Its bind attempt against the old one -
`[Errno 48] address already in use` - arrived as `{"level": "ERROR", "logger": "uvicorn.error",
"component": "api", ...}`, which is piece 4's `log_config=None` doing what it was for: uvicorn's
own lines in the same shape as ours, first seen on a real error rather than in a test.

## What a reader should now be able to see

`/grafana/d/faultline-self`: the four stats and four time-series panels filled from
`faultline-self-metrics`; the Loki panel empty on a development machine (the daemons run on the
host); the Tempo panel listing the first-trace run over any range that covers 05:27Z. The note
panel says where the numbers come from rather than why they might be missing, which is the
sentence it carried until this morning.

## What this does not show

**The VM.** Every reading here is from a development machine. `deploy/compose.yml` has the
service and `deploy/README.md` §3.4 has the datasource line with the container's name, and neither
has run. The first image built after #364 is the first that can trace and serve `/metrics` there;
that rollout is the remaining step of T6.6, and it is the same $0.
