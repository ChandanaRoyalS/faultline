# RESULT - Q122's build: the v2 world's dependency graph, loaded by world

Read against [`PREREGISTRATION-Q122-v2-graph.md`](../../runs/PREREGISTRATION-Q122-v2-graph.md).

- **Step 1** (the presence probe) was run by the owner on the Mac on 2026-10-01 at 22:47:39 UTC.
  It is kept verbatim as
  [`q122-presence.txt`](../../../docs/evidence/t7.2-topology/q122-presence.txt).
- **Step 2** (the build) followed, on `e1b7c63`. $0, no model call.

## The answers

**Question 1: YES.** With the v2 snapshot loaded by world, triage's graph covers the v2 world.

- **The graph.** It holds 20 edges over 15 nodes, and every one of v2's application services but
  `accounting`, `image-provider`, `llm` and `flagd-ui` is `PRESENT`.
- **Blast radius from `checkout`** now reaches the order path: `frontend` and `frontend-proxy`
  above it, and its six callees below. At `4279baa` it reached nothing.
- **Every v2 service the catalog names has a presence that says why** it is or is not in the
  graph. All eight absent ones were measured by the probe, not assumed.

**Question 2: YES.** v1 is as it was:

- the same 15 edges, 13 nodes and 18 catalog entries;
- every existing test passing;
- **`cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc` in both worlds**, before and after.

`make check`: 2349 passed, against 2334 at `e1b7c63`, so 15 tests are new.

## Step 1, read

**The stop rule did not fire.**

- **B's pairs.** All 18 cross-service pairs that B found are in the snapshot.
- **The four not seen** are the four rarest flag reads, from ad, fraud-detection, product-reviews
  and recommendation, at 5 calls each in the snapshot's hour. Ten traces per service is not
  enough to catch them.
- **Every service the snapshot holds** had 20 traces.
- **valkey-cart, postgresql and kafka** had none of their own.

**What step 1 decided, by the registered table:**

| service | measured | entry |
|---|---|---|
| `load-generator` | its two edges excluded | `ARTIFACT_ONLY` |
| `accounting` | 20 traces; no cross-service pair. Its Kafka consumer spans sit under its own spans, each with **one link to another trace** | `UNLINKED` |
| `image-provider` | **20 traces**; no cross-service pair in 138 whole traces; no parent missing from any trace | `UNLINKED` |
| `llm` | no span; 1,012 log lines in the hour, ending `"POST /v1/chat/completions HTTP/1.1" 200`; product-reviews' client spans name `server.address` llm | `UNINSTRUMENTED` |
| `flagd-ui` | no span; container running; **0 log lines** in the hour | `UNEXERCISED`, the value added because a service landed here |
| `valkey-cart` | cart's client spans: `db.system` redis, `server.address` valkey-cart | `INFRASTRUCTURE` |
| `postgresql` | client spans with `db.system` postgresql from accounting, product-catalog and product-reviews | `INFRASTRUCTURE` |
| `kafka` | checkout's producer spans on `orders`; consumer spans in accounting and fraud-detection | `INFRASTRUCTURE` |

**The nine telemetry services** had no spans of their own, and stay out of the catalog as on v1.

## The predictions

**Step 1:**

| prediction | held? |
|---|---|
| `llm`, `image-provider` and `flagd-ui` emit no spans | **wrong for `image-provider`**: 20 traces in the hour. Held for `llm` and `flagd-ui`. The registered table placed it (`UNLINKED`) |
| Valkey: cart's client spans name it, `redis` or `valkey` | **held**: `redis`, `valkey-cart` |
| Postgres: accounting plus at least one other caller | **held**: product-catalog (203 spans) and product-reviews (11) |
| Kafka: checkout produces; the consumers sit in traces of their own, parent not in the trace or a link to checkout's producer | **held in form.** Every consumer span is in a trace without checkout. accounting's 10 and 10 of fraud-detection's sit under their own service's span with one link to another trace; fraud-detection's other 10 are roots with no link. **The probe counted links and did not resolve them**, so that they point at checkout's producer is not measured |
| every pair B finds is in the snapshot | **held** |

**Step 2:**

| prediction | held? |
|---|---|
| `blast_radius(["checkout"])`: frontend (1), frontend-proxy (2); product-catalog, currency, cart, email, payment, shipping; 8 unmeasured | **held**, in that order |
| `blast_radius(["quote"])`: shipping (1), checkout (2) | **held** |
| `blast_radius(["flagd"])`: ad, recommendation, cart, fraud-detection, product-reviews (1); frontend, checkout (2); 10 unmeasured | **held**, in that order |
| `blast_radius(["accounting"])`: nothing; `UNLINKED` | **held** |
| checkout and frontend-proxy `PRESENT`; load-generator `ARTIFACT_ONLY` | **held** |
| v1: 15 edges, 13 nodes, catalog unchanged, every existing test unmodified | **held, with one note**: `tests/test_services.py`'s `alert_thresholds` helper gained a `path` argument, defaulting to v1's rules, so the v2 test can reuse it. No v1 test body changed. `test_packaging`'s `REPO_DATA` gained its registered entry |
| `make check` passes | **held** |
| both stamps unmoved in both worlds | **held** |

## What was built

- **`context/graph.py`.**
  - `SNAPSHOT_V2`, loaded in place, with `SNAPSHOTS` mapping world to file.
  - `ARTIFACT_EDGES_V2`.
  - Self-edges are dropped in every world.
  - `EDGE_KINDS_BY_WORLD`: v2 has none, so every v2 edge is `UNMEASURED`.
  - `current_world()`.
  - `ServiceGraph` carries `world` and canonicalises in it, through `ServiceGraph.canonical`.
  - `from_snapshot(path=None, world=None)`.
- **`context/catalog.py`.**
  - `GraphPresence.UNLINKED` and `UNEXERCISED`.
  - `KNOWN_ABSENT_V2`, each reason citing the probe's part.
  - The catalog chooses the table by its graph's world, and `from_snapshot(world=None)`.
- **`context/services.py`**: `load_services(world=None)` and `catalog_path(world)`.
- **`knowledge/services-v2.yaml`**, the 32 services, generated from the snapshot of record:
  - 22 declared dependencies;
  - 19 applications carrying `alert-rules-v2.yml`'s thresholds;
  - no runbooks.
- **`Dockerfile`**: the v2 snapshot is copied into the image.
- **Tests.**
  - `test_context`: nine v2 tests and one for v1's defaults.
  - `test_services`: five.
  - `test_packaging`: one entry.

## Found on the way, queued

- **Q123: `alert-rules-v2.yml`'s reason for excluding `frontend-proxy` from `ServiceNoTraffic`
  is false on v2.** It says Envoy *"emits a few spans at startup and none after"*. The probe
  found 20 traces in the hour, with 118 `frontend-proxy → frontend` pairs in 138 traces, and the
  snapshot counts 9,881 such calls. Noticed at registration, confirmed here.
- **Q124: on the Mac's v2 world, `alertmanager` is not running.** The probe read
  `exited started 2026-09-22T07:04:52Z`, while the world's other containers started on 09-28 or
  later. Alertmanager is the route from Prometheus's alerts to Faultline's ingest webhook
  (`compose/prometheus/alertmanager.yml`), so while it is down no v2 alert reaches Faultline.
  The world check does not look at it: its `nothing firing` reads Prometheus's `ALERTS`, which
  do not need Alertmanager. This was not investigated further.
