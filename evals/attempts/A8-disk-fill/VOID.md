# A8 first run — VOID, and why

**The fill succeeded and nothing paged, and that is not the registered "does not page" outcome,
because the fill was on a directory kafka does not use.**

The registration, the override's comment and the precondition all said kafka's data lives at
`/tmp/kraft-combined-logs`, "apache/kafka:3.9.1's `log.dirs` default". The broker's own log, read
at minute twelve, says `dir=/tmp/kafka-logs` on every line and had been saying it since bring-up.
The image's documented default holds for its shipped `server.properties`; configured through
`KAFKA_*` environment variables, as the demo configures it, the image generates its properties
and logs to `/tmp/kafka-logs`. The 2026-09-22 "confirmation" (`/var/lib/kafka/data` was 4.0K) ruled
out one path and proved nothing about another, and the precondition `df -h /tmp/kraft-combined-logs`
proved that the tmpfs existed, not that anything wrote to it. **256 MiB of zeros in an empty
directory is not a disk-full broker.** Same species as A4's first run: an injection whose success
was measured on the injection's own terms rather than the target's.

Two corrections, both mine:

- **The path** (`world-v2.override.yml`, patch with this file): the tmpfs moves to `/tmp/kafka-logs`.
  Kafka is recreated to take the mount, and its data starts empty — which it already does on every
  recreate, since the demo declares no volume.
- **The precondition** (`PREREGISTRATION-T7.0-A8b.md`): it now reads `log.dirs` **from the running
  broker's startup log** and requires it to equal the tmpfs mount point. A path a fault is aimed at
  is read off the process, not off a default.

One thing this run measured anyway: `docker restart accounting fraud-detection checkout`, the
registered consumer-restart step, put `ServiceHighErrorRate/accounting` into firing four and a half
minutes later at 32.84 % with nothing injected. That is the recycle's own effect, not the fault's,
and it is diagnosed before A8b starts and recorded with `recycle_effect("v2")` in mind.
