# Pre-registration - A9, a datastore's contents corrupted where the store is a topic

**Written before the attempt is run. Nothing here is a result.** T7.1's `datastore_corruption` row
has one scenario, on valkey-cart (A4b, R4b, `v2-cart-store-corruption`); its rows 2 to 4 need a new
tool each, and the T7.0 bar is that a tool is attempted by hand, then rehearsed through the
injector, before a scenario is authored against it (`docs/design/t7.1-candidates.md`,
`datastore_corruption`; `evals/runs/REHEARSALS-T7.0.md`). A9 is row 2's attempt:
`v2-kafka-orders-corruption`, *malformed records on the `orders` topic: accounting and
fraud-detection fail to parse*. It is a new attempt under the protocol of `PREREGISTRATION-T7.0.md`,
which is frozen.

**The question.** When records that are not orders land on the topic every order travels, does
the world page - and on what - and does what a responder can read name a store whose contents are
wrong, rather than a consumer that broke?

## Read at source before registration (world-v2, 2026-09-30)

- **accounting** (`src/accounting/Consumer.cs`) consumes with `EnableAutoCommit = true`, parses
  each value with `OrderResult.Parser.ParseFrom` inside `ProcessMessage`, and **catches** any
  exception: it logs `Order parsing failed:` with the exception and moves to the next record. The
  `order-consumed` activity around it is not marked in error by that catch.
- **fraud-detection** (`src/fraud-detection/.../main.kt`) consumes with the client's defaults
  (auto-commit on), and calls `OrderResult.parseFrom(record.value())` inside the poll loop with
  **no catch**: the exception leaves `main`, `consumer.use` closes the consumer - which, with
  auto-commit on, should commit the position it had reached, past the bad record (unverified: the
  attempt reads the committed offsets) - and the process exits. Compose restarts it
  (`restart: unless-stopped`).
- So one bad record should cost fraud-detection one crash and one restart, not a crashloop on the
  same record; a bad record **every ten seconds** should keep it crashing.

## Protocol - the eight's, with the injection below

Steps 1 to 6 of `PREREGISTRATION-T7.0.md` apply unchanged: pre-state quiet (and, since T7.1, the
world check: `python3 ~/Downloads/world_check.py`), inject, `watch.py 12`, `shape.py
fraud-detection` and `shape.py accounting`, revert, `watch.py 10`, transcript and `RESULT.md` under
`evals/attempts/A9-datastore-corruption-topic/`.

- **Mechanism**: the broker's console producer writes a record whose value is the text
  `nonsense-order-<n>` onto `orders` every 10 s, 72 records over 12 minutes. The first byte, `n`,
  is a protobuf tag with wire type 6, which neither parser accepts.
- **Inject**: `docker exec -i kafka sh < evals/attempts/a9-orders-poison.sh` (terminal 2; it ends on
  its own).
- **Revert**: let the script end, or `Ctrl-C` it. Nothing else is planned: the records already
  written have been read past by both consumers (accounting skips, fraud-detection's close commits),
  so none is expected to be read again. Whether that holds is part of REVERTS, read after the watch:
  `docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092
  --describe --all-groups` - both groups at `LAG` 0. The records themselves stay on the topic until
  its retention or the broker's next recreate (its log directory is a tmpfs); that is recorded as a
  residue, as Q117 records planted log lines.
- **Comparators**: `v2-fraud-detection-memory-squeeze` (the same consumer crashlooping on a limit)
  and `v2-fraud-detection-partition` (the same consumer reaching nothing).
- **What would distinguish**: (c) - both consumers' logs name the same parse failure on the same
  topic, accounting's without crashing; a memory ceiling kills with no last words, a partition logs
  connection failures. (b) - nothing is recorded as changed.

## Prediction

- **PAGES**: yes, on **fraud-detection** - `ServiceHighErrorRate` if its consumer spans end in
  error as the process dies, otherwise `ServiceNoTraffic` once repeated restarts starve its window
  - within 8 minutes; **nothing on accounting** (it catches, and its activity is not in error), and
  nothing on checkout or the storefront (producing orders is unaffected). Confidence moderate: the
  consumer span's status on an uncaught exception, and how often docker's backoff lets the JVM live,
  are what is unknown.
- **DISTINCT** on (c): accounting's log carries `Order parsing failed:` with
  `InvalidProtocolBufferException` about every 10 s while its `Order details` lines continue;
  fraud-detection's carries the same exception type as an uncaught stack trace at every death.
- **REVERTS**: yes, by stopping the writer; fraud-detection back within a minute of the last record,
  its no-traffic or error alert clearing inside five.

## What A9 decides

If it pages, distinct and reverts, the topic is admissible as a `datastore_corruption` store and
the injector gains the tool (then R-rehearsal, then the scenario). If it does not page - the
likeliest reason being fraud-detection's restarts too quick for any rule - the finding is recorded
and row 2 is blocked, as the row allows. Which fix class a scenario on it carries (the corrupting
writer stopped; the bad records left or purged) is decided with the RESULT in hand, not now.
