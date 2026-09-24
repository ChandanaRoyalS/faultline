# Pre-registration — A8b, disk fill on the directory kafka actually writes to

**Written before the attempt is run. Nothing here is a result.** A new attempt, not an edit to
`PREREGISTRATION-T7.0.md`, which is frozen. A8 as registered (`evals/attempts/A8-disk-fill/VOID.md`)
filled a tmpfs at `/tmp/kraft-combined-logs` while the broker wrote to `/tmp/kafka-logs`; the
injection never reached the target and the run is void. A8b is the same mechanism, aimed at the
path read off the running broker, with a precondition that cannot pass on the wrong path again.

Everything the A8 registration fixed — mechanism, target, paging services, comparator, what would
distinguish, the prediction — carries over unchanged and is restated here so this file stands alone.

## Protocol

Steps 1–6 of `PREREGISTRATION-T7.0.md` apply. The override change (tmpfs at `/tmp/kafka-logs`)
must be landed and kafka recreated to take it **before** the pre-state; the consumers are restarted
after kafka (T7.27), and the world must be quiet for five minutes after that before injection.

- **Precondition, two lines, both must hold or the attempt stops**:
  1. `docker logs kafka 2>&1 | grep -m1 'log.dirs'` prints `log.dirs = /tmp/kafka-logs` — the
     broker's own startup dump of its configuration, not a default.
  2. `docker exec kafka df -h /tmp/kafka-logs` shows a **256M tmpfs** at that path.
- **Mechanism**: fill the target's only writable data directory to capacity from inside the
  container. New tool (`dd` via `exec`), new surface (storage); matches no existing mechanism.
- **Target**: `kafka`. Paging services: `checkout` (produces orders), `accounting` and
  `fraud-detection` (consume them).
- **Inject**: `docker exec kafka dd if=/dev/zero of=/tmp/kafka-logs/t70-fill bs=1M count=300`
  (it stops early with *No space left on device*; that is the injection succeeding — **and this
  time the broker's next segment roll or snapshot write must fail, which its log will show**).
- **Revert**: `docker exec kafka rm /tmp/kafka-logs/t70-fill`; if kafka is crashlooping too fast
  for `exec` to land, `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 up -d --force-recreate kafka`
  (discards the tmpfs). Then `docker restart accounting fraud-detection checkout`.
- **Comparator**: `bad_config` on `checkout` (a wrong `KAFKA_ADDR` also stops orders).
- **What would distinguish**: (c) — kafka's own log says *No space left on device* /
  `KafkaStorageException` and halts; a misconfigured checkout logs connection failures while kafka
  is healthy. (b) — no change recorded. (a) — the consumers go silent too, which a checkout-side
  misconfig does not cause.

## Prediction (A8's, unchanged)

**PAGES** — `ServiceHighErrorRate/checkout` within 6 min as `PlaceOrder` fails to produce, and
`ServiceNoTraffic` on `accounting` and `fraud-detection` at ~8 min (A2 corrected the "3–5": the
`[5m]` window drains first, then `for: 3m`). DISTINCT on (a) and (c). REVERTS via recreate.
**Admissible.** Confidence moderate-high; the uncertainty is whether checkout treats a failed
produce as a request error or logs and returns success.

**Two things A8's void run adds to the record before this runs**: a Kafka broker's metadata log
rolls a segment every 15 s here (`KAFKA_METADATA_LOG_SEGMENT_MS=15000`) and snapshots every 2800
bytes, so a full directory should be hit within seconds, not minutes; and the consumer restart in
the revert produced `ServiceHighErrorRate/accounting` on its own at +4:30 on a healthy world, so
the recovery watch must expect that alert and it is not the fault's.

## What A8b decides

Exactly what A8 was to decide: pages, distinct, reverts → `disk_fill` admissible, ceiling nine.
Does not page → recorded, the tmpfs is removed in the same patch, eight classes stand.
