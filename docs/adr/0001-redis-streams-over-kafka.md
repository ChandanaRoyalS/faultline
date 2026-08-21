# ADR-0001: Redis Streams over Kafka for the event bus

- **Status:** accepted
- **Date:** 2026-08-21

## Context
Alert ingestion must decouple from investigation: webhooks must return instantly,
investigations are slow and expensive, and work must survive worker crashes. The plan also
requires a global investigation concurrency cap with severity-ordered overflow (T2.2).
Kafka and Redis Streams both satisfy the durability and consumer-group requirements.

## Decision
Redis Streams. Consumer groups with explicit acks, pending-entry claim on worker death,
idempotent handlers keyed on (incident, step). Redis is already in the stack for queues
and caching, so the bus adds zero new operational surface.

## Consequences
Easier: one fewer distributed system to run, back up, and explain; trivial local dev.
Harder: no partitioned parallelism or replay-from-offset semantics; throughput ceiling far
below Kafka's. Revisit if: multiple producer services appear, replay of historical alert
streams becomes a product feature, or sustained ingest exceeds what a single Redis
comfortably handles (~tens of thousands of alerts/min — two orders beyond this system's needs).
