# The writer that was not single — 2026-09-23

**\$0, no model call, found because a revert would not go quiet.** T7.0's A6 recreated
`accounting` with a wrong database password, watched it page, and recreated it again with the
right one. The error alert drained on schedule. Then `ServiceNoTraffic/accounting` fired on a
service that was consuming and writing every order, and a `docker restart` did not clear it. **On
this world, any container recreated under an existing service name vanishes from the alert rules,
and it stays vanished.** Every remaining attempt (A7, A8) and every `bad_config` / `bad_deploy`
scenario the catalog will ever run on v2 recreates a container.

## What was measured, in order

| reading | result |
|---|---|
| `docker ps` | `accounting  running  Up 11 minutes` |
| `docker logs` | one processed order after another, right up to the present |
| `docker restart accounting`, then `watch.py 10` | `ServiceNoTraffic/accounting` on every poll |
| the auto-instrumentation's own log | `Export succeeded for http://otel-collector:4318/v1/traces` every five seconds |
| Tempo, `{resource.service.name="accounting"}`, last 15 min | three `order-consumed` traces, three spans each |
| `traces_span_metrics_calls_total{service_name="accounting",span_name="order-consumed"}` | **one series**, value **4748, flat**, labels `{job="opentelemetry-demo/accounting", span_kind, status_code}` — **no `instance`** |
| `target_info{job="accounting"}` | empty |

The process was healthy, exporting, and its spans were in the trace store. The loss was between
the spanmetrics connector and Prometheus.

## The mechanism

Prometheus's OTLP receiver names a series by `job` (`service.namespace/service.name`) and
`instance` (`service.instance.id`), and nothing else from the resource unless told to promote it.
**The .NET SDK sets no `service.instance.id`.** So every container that has ever run as
`accounting` — the original, the one with the bad password, the recreated one, the restarted one —
writes `traces_span_metrics_calls_total{job="opentelemetry-demo/accounting", …}` to the **same
series**.

The spanmetrics connector aggregates per *resource*, and a recreated container is a new resource
(a new `container.id`, a new `host.name`, a new `process.pid`). It keeps every resource it has ever
seen — `metrics_expiration` defaults to never — and emits them all on every flush, oldest first.
So each flush carries, for the same series and the same timestamp, the dead container's counter
(4748, never moving again) and then the live container's (small, rising). Prometheus keeps the
first and refuses the second as a duplicate. **Two writers, one series, and the dead one is
always first.**

That also rereads A6's fault window. The bad-password container's *error* spans had label sets no
earlier container had produced — `status_code="STATUS_CODE_ERROR"` — so those series had one
writer and were visible; its non-error spans collided and were not. **"100 % errors at
0.137 req/s" was not the service's ratio; it was the visible fraction.** The page was real (every
order did fail), the number was not.

## Why it did not bite before today

A1–A5 changed flags, paused, disconnected, corrupted a datastore and flooded a homepage. **None of
them recreated a container.** The 45-minute baseline ran on a world brought up once. A6 was the
first `compose up -d <service>` since the world's bring-up, and it broke the rules for that
service on the first try, twice, and permanently. The v1 world never had the problem because its
collector runs spanmetrics as a *processor* and Prometheus *scrapes* it — one writer by
construction.

## The fix, and why it is the demo's

`src/prometheus/prometheus-config.yaml` at tag 2.2.0 carries an `otlp:` block that promotes
`service.instance.id`, `host.name`, `container.name` and a dozen others onto the series, with a
comment pointing at the connector README's *single-writer limitation*, plus
`out_of_order_time_window: 30m`. **`compose/prometheus/prometheus-config-v2.yaml` replaced the
demo's file to add rules and Alertmanager, and dropped both without noticing** — its header
explains why the scrape jobs are gone and says nothing about `otlp:`, which is how the omission
looked deliberate. The block is restored verbatim (a guard in `tests/test_world_v2.py` pins it),
with the measurement in the file's own header.

With `host.name` promoted, each container is a series of its own. Every rule and capture query in
this repository aggregates by `service_name`, so the extra labels change no arithmetic: the dead
container's series goes flat and contributes zero to the sum, and the live one is seen. The
window is the demo's and is what lets two writers' samples in one flush both land.

**What the fix does not do**: it does not make the connector forget dead resources. Each recreate
adds a flat series that lives until Prometheus's retention drops it. Harmless to the rules;
visible in the raw series list; recorded so that nobody reads a second `accounting` series as a
second accounting.

## What this changes

- **Every attempt after A6 runs on the fixed config**, after a `/-/reload` and a settle. A6's
  own recovery is re-verified after the reload and recorded in its result with both clocks.
- **`confirm_recovery` and the gate** would have seen `ServiceNoTraffic` after every
  `bad_config` / `bad_deploy` restore on this world, forever. This is the sixth member of the
  session's silent-failure species — PromQL over a series that exists and does not move is
  indistinguishable from a silent service — and the first that the *demo* had already documented
  and we had removed.
- **Q89**: the injector's restore for compose-mechanism classes on v2 should verify that the
  target's `service_name` sum is rising *on a fresh series*, not merely that the container is
  running; and `recycle_effect(world)` for v2 should say that a restart adds a series.
