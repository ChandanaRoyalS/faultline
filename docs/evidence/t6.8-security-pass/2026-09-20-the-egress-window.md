# T6.8 — the egress window: the platform network loses its route out

**2026-09-20 05:34–05:48 UTC, the VM (`deploy@ubuntu`), `~/faultline` at `a2afb74` then `725f213`;
image `ghcr.io/chandanaroyals/faultline:a2afb74999e592281fed4975dd0d237b269bb503`.** README §3.12,
run as written, one line at a time, after one false start: the same block had been pasted into the
Mac's terminal first (`cd ~/faultline` failed there, every following line failed or hit the wrong
project, and one empty `alertmanager.password` was left at the repository root and removed). The
VM check line `test "$(whoami)@$(hostname)" = "deploy@ubuntu"` was added to the procedure after
that and printed `on the VM`.

## What the window did

| step | result |
|---|---|
| `git pull --ff-only` | `f44b181..a2afb74`, 93 files - every T6.8 PR at once; the VM had not pulled since T6.7 |
| `alertmanager.password` from `.env` | 25 bytes, mode 600 |
| `FAULTLINE_IMAGE` → `a2afb74…` | `docker compose pull faultline egress`: both pulled (`ubuntu/squid:6.6-24.04_beta` 3.8 s, the image 16.5 s) |
| `docker compose down` | seven containers removed in 10.2 s (the orchestrator last); volumes kept |
| detach loop | six world containers off `faultline-deploy-net` |
| `network rm && create --internal` | `6bb262baac81…` |
| world `up -d --no-build` | 27/27; the six telemetry containers recreated onto the new network, the rest `Running` untouched |
| platform `up -d --wait` | 9/9 in 29.5 s; `faultline-deploy-egress` created; `egress-1 Healthy` at 29.5 s - **and then crash-looping** |

## The proxy crash-looped, and why

`docker compose ps` at 05:37 read `faultline-deploy-egress-1 Restarting (1)`. Its log, three times a
minute:

```
Logfile: opening log stdio:/dev/stdout
FATAL: Cannot open '/dev/stdout' for writing.
The parent directory must be writeable by the user 'proxy', which is the cache_effective_user
Squid Cache (Version 6.13): Terminated abnormally.
```

Squid starts as root, drops to `proxy`, then opens the access log **by path** - and `/dev/stdout`
inside the container is root's. `access_log stdio:/dev/stdout` was written so that `docker compose
logs egress` would be the record of every tunnel; it was never run against the image before the
window. (The image tag says 6.6; the binary reports 6.13.) For the eleven minutes it took to fix,
**the orchestrator had no route out at all**: `curl` from inside it printed `Could not resolve
proxy: egress` for the provider and `Could not resolve host: example.com` without the proxy. That is
the failure mode the `--internal` network is meant to fail into - nothing leaks when the proxy is
down; investigations end `provider_unavailable` and defer (T6.7) - and it was observed rather than
argued.

Fixed in `deploy/squid.conf` (`725f213`): `access_log stdio:/var/log/squid/access.log squid`, the
file the image makes writable for `proxy`; `tests/test_deploy.py` pins the path and refuses
`/dev/stdout`; README §3.12 and §4 read the file with `docker compose exec -T egress tail`. Applied
with `git pull && docker compose up -d egress` - a bind mount, no image change - and `egress-1 Up`.

## The checks, 05:47 UTC

| check | result | meaning |
|---|---|---|
| from the orchestrator, `https://api.anthropic.com/v1/models` through `HTTPS_PROXY` | **`401`** | the provider answered; the bytes left through the proxy and came back |
| the same container, `HTTPS_PROXY` unset, `https://example.com` | **`no route`** (`Could not resolve host`) | the network has no way off the host without the proxy |
| through the proxy, `https://example.com` | **`403`** (`CONNECT tunnel failed, response 403`) | a host not on the list is refused by squid |
| `/var/log/squid/access.log` | `TCP_TUNNEL/200 5012 CONNECT api.anthropic.com:443 - HIER_DIRECT/160.79.104.10` and `TCP_DENIED/403 3346 CONNECT example.com:443 - HIER_NONE/-` | one line per tunnel, the allowed one and the refused one, from `172.19.0.13` (the orchestrator) |
| anonymous `POST /api/v1/alerts` from inside the `faultline` container | **`401`** | the receiver demands the pair on the deployment (piece 1) |
| `docker compose logs --since 10m faultline \| grep -c ' 401 '` | `0` | Alertmanager, sending the pair from the mounted file, was not refused - though nothing had fired in those ten minutes either |
| `docker compose ps` | every service `Up`; `faultline`, `postgres`, `redis` `(healthy)`; `egress` `Up 23 seconds` after the fix | |

## What this window did not check

Whether Alertmanager's *next real delivery* is accepted (the `0` above is a ten-minute window with
nothing firing; §3.6's next incident is the test); whether the orchestrator's OTLP export to
`tempo:4317` survives `NO_PROXY` (grpc's proxy handling) - the next incident's `investigation` span
in Tempo/Jaeger is the test; Let's Encrypt renewal through caddy's second network - the next
renewal is the test. Each is a read of the next thing that happens, not a probe made here.
