# Alert storm — 2026-09-19T23:22Z

**200 distinct alerts, 16 in flight, seed 67, three passes.** `PREREGISTRATION-T6.7.md` §2 scored below. $0.00: no investigation ran.

| pass | posts | statuses | published | dedup | p50 | p99 | max | drained after |
|---|---|---|---|---|---|---|---|---|
| storm | 200 | {'200': 200} | 200 | 0 | 7.9 ms | 32.0 ms | 33.8 ms | 3.0 s |
| re-notification | 200 | {'200': 200} | 0 | 200 | 6.5 ms | 14.4 ms | 14.8 ms | 0.0 s |
| resolves | 200 | {'200': 200} | 200 | 0 | 7.5 ms | 19.1 ms | 21.8 ms | 5.0 s |

| prediction | held | detail |
|---|---|---|
| P1 every POST 200 | **yes** | storm: {'200': 200}, re-notification: {'200': 200}, resolves: {'200': 200} |
| P2 published/deduplicated per pass | **yes** | pass 1 200/0, pass 2 0/200, pass 3 200/0 |
| P3 incidents opened in [1, 6] | **yes** | 1 opened |
| P4 no episode in two incidents | **yes** | 0 shared |
| P5 queue peak = max(0, incidents - free slots), 0 at the end | **yes** | peak 0, expected 0 (0 slot(s) held before the storm), last sample 0 |
| P6 each pass drains within 60 s | **yes** | drained after [3.0, 0.0, 5.0] s |
| P7 receiver p99 < 500 ms | **yes** | storm p99 32.0 ms, re-notification p99 14.4 ms, resolves p99 19.1 ms |
| P8 every storm incident resolved | **yes** | states ['resolved'] |
| P9 no container restarted | **yes** | none |
| P10 pass 2 opened nothing | **yes** | 1 after pass 2, 1 at the end |

**Incidents opened: 1**

- `3779f7e3` resolved, 200 episodes, opened 23:22:13Z

Samples: 12; queue depth peak 0; restarts before/after: {'faultline-prometheus-self-1': 0, 'faultline-minio-1': 0, 'postgres': 0, 'faultline-redis-1': 0, 'faultline-postgres-1': 0} / {'faultline-prometheus-self-1': 0, 'faultline-minio-1': 0, 'postgres': 0, 'faultline-redis-1': 0, 'faultline-postgres-1': 0}.
