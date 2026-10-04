# Q124 - why Alertmanager was down, and its start (2026-10-04)

Two captures taken on the Mac by the owner, committed unchanged. Alertmanager's webhook URL is
printed by Alertmanager itself as `<redacted>` and `<secret>`.

| file | what it shows |
|---|---|
| `2026-10-04-the-exit-and-its-log.txt` | `docker inspect` of the stopped container and its last 120 log lines |
| `2026-10-04-restart-policies-and-the-start.txt` | the three containers' restart policies, the start, `/-/ready`, and the loaded receiver |

## What they say

- **It exited on 2026-09-28 at 22:20:21 with status 255, not out of memory** (`oom=false`). 255
  with no error is what a container shows when the Docker engine stops under it: a Docker Desktop
  restart, or the Mac shutting down.
- **It stayed down because its restart policy is `no`.** Prometheus and quote, from the same
  compose project, are `unless-stopped` and came back with the engine. Alertmanager did not, and
  nothing checked for it until Q122's probe.
- **Its log before the exit is every delivery refused**: `dial tcp 192.168.65.254:8000: connect:
  connection refused`, 2026-09-28 12:02 to 14:08. That address is Docker Desktop's host gateway,
  and port 8000 is Faultline's ingest (`compose/prometheus/alertmanager.yml` posts to
  `host.docker.internal:8000/api/v1/alerts`). So even while Alertmanager ran, no alert could reach
  Faultline unless the ingest was up on the host.
- **Started 2026-10-04 at 03:29:29Z**: running, `/-/ready` 200, receiver `faultline` loaded.

## What changed because of them

- `scripts/world_check.py` fails while Alertmanager is not running and ready (the build's part A),
  and **while its receiver, the ingest's `/healthz` on port 8000, does not answer** (part D). The
  registration names both halves; part A had checked the first only.
- **The restart policy is not changed.** `docker update --restart unless-stopped alertmanager`
  moves no digest, but it is a world change nobody has registered. The world check before every
  slot is what the owner chose (Q124's decision), and it catches the same failure.
