# Pre-registration - Q122's build: the v2 world's dependency graph, loaded by world

**Written before any code is changed and before step 1 is run. Nothing here is a result.** This
is item 2 of `docs/design/t7.2-topology.md`, "what the decision costs". Item 1 and the snapshot
of record were settled by [Q121's RESULT](../attempts/Q121-quote-restart/RESULT.md).

**The two questions.**

1. With the v2 snapshot loaded by world, does triage's graph cover the v2 world? That means its
   blast radius reaches the order path from `checkout`, and every v2 service the catalog names
   has a presence that says why it is or is not in the graph.
2. Does v1 stay exactly as it was? Same graph, same catalog, every existing test unchanged,
   and the capability stamp and the prompt digest unmoved.

## Decided by the owner, 2026-10-01, before this registration

- **The v2 snapshot is loaded in place**, from
  `docs/evidence/t7.2-topology/q121-v2-dependencies-1h.json`. This keeps ADR-0017's rule that
  the capture and the runtime input are one file, with no second copy to drift. The design
  note's *"committed beside v1's"* is met as a second committed snapshot of the same standing.
  It is not met as a copy in v1's directory. The Dockerfile ships that one file.
- **`accounting` gets a new presence, `GraphPresence.UNLINKED`**: it emits spans, but no other
  service's span is its parent or child. `ARTIFACT_ONLY` was the alternative. It was rejected
  because its definition (*"its only edges were excluded as artifacts of how the world is
  run"*) does not describe a self-edge.

## Read before registration

- **The snapshot of record** holds 38 entries: 22 cross-service edges and 16 self-edges, over
  17 services (`q121-v2-graph.txt`, the 1 h block).
- **After the rules below** it holds **20 edges over 15 nodes**. `load-generator` leaves with its
  two edges, and `accounting` leaves with its self-edge, which is its only edge.
- **A correction to the design note.** It says *"Those two services* [accounting and
  fraud-detection] *sit in the graph on self-edges alone"*. That is true of `accounting` only.
  `fraud-detection → flagd` (5 calls in the hour) keeps `fraud-detection` in the graph. What
  stays true is that **neither has an incoming edge**: checkout's Kafka hop to both is not in
  the graph. The note is corrected when this registration lands.
- **A measurement owed and not made.** The design note says `llm` and `image-provider` *"are each
  measured, not assumed, when the snapshot of record is taken"*. Q121's registration, which
  took the snapshot, did not include that measurement. I wrote that registration, and the
  omission is mine. Step 1 makes it up, before any code.
- **An erratum in Q122's row and the design note.** Both say the gap was measured *"with
  `FAULTLINE_WORLD=v2`"*. The setting is `ToolSettings.world`, read from
  **`FAULTLINE_TOOLS_WORLD`**.
  - The measurement was run with the right setting; only the text names it wrong.
  - Read again at `4279baa` with `FAULTLINE_TOOLS_WORLD=v2`, the result is the same: `get` is
    `None` for checkout, cart, email and product-catalog, `frontend` alone is `PRESENT`, and
    `blast_radius(["checkout"], 2)` reaches nothing.
  - Both texts are corrected with this registration.
- **Where the world comes from.** `injector.world.canonical_service` already follows
  `ToolSettings.world`, which defaults to `v1`; a world is opted into (T7.0 #6). The graph and the
  catalog follow the same setting, so **with the setting unset, nothing about v1 changes**.
- **What reads the graph or the catalog**:
  - `agents/triage.py` (blast radius, presence, `start_from`);
  - `context/policy.py`, `agents/contracts.py:480` and `executor/core.py:256`;
  - `evalharness/visibility.py:56`, `storm.py:668` and `run.py:634`.

  None changes. Each follows the world the process runs in.
- **No digest covers the graph.**
  - `capability_version()` hashes the tool surface, `CAPTURE_SET` and `TOOL_BEHAVIOUR_REVISION`.
  - `prompt_digest()` hashes the `*_SYSTEM` prompts and the `_CONTRACTS` schemas.
  - `GraphPresence` is in none of `_CONTRACTS`; `TriageJudgement` carries no presence.
  - **Read at `4279baa`**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, the same
    with `FAULTLINE_TOOLS_WORLD=v2`.
- **`knowledge/services.yaml` has no runtime reader**: only `tests/test_services.py` loads it. Its
  v2 counterpart is a document under the same tests.

## Step 1: the presence probe, read-only, on the Mac

`graph_presence.py`, committed with this registration
(`docs/evidence/t7.2-topology/graph_presence.py.txt`), reads Tempo over the last hour and
changes nothing:

- **A.** For each of v2's 32 services, whether Tempo holds a trace with its spans. For one that
  has none, the script reads its container's state and its log-line count for the hour, plus the
  last five lines for `llm`, `image-provider` and `flagd-ui`.
- **B.** A census of up to ten whole traces per service with spans: every cross-service
  parent-to-child pair, each marked as in or not in the snapshot of record.
- **C.** From the same traces:
  - the client spans naming a datastore or a peer;
  - the producer and consumer spans, with each consumer's parent service and its links.

**Run**: `python3 ~/Downloads/graph_presence.py > ~/Downloads/q122-presence.txt 2>&1`, read
before step 2. It needs no world check, because it changes nothing. If the Mac has slept since
09:05, quote's skew may be back. That does not touch the census: spans are paired by ID, not
by time.

**The stop rule.** Stop and read before any code if:

- **B finds a cross-service pair not in the snapshot.** The snapshot of record would then be
  missing an edge.
- **A finds no spans for a service the snapshot holds.**
- **A finds spans for `valkey-cart`, `postgresql` or `kafka`.** Their `INFRASTRUCTURE` reason
  would then be wrong.

## What step 1 decides, stated now

| service | the rule | `KNOWN_ABSENT_V2` entry |
|---|---|---|
| `load-generator` | its two edges are excluded as the synthetic client, as v1's was | `ARTIFACT_ONLY` |
| `accounting` | spans in A and no cross-service pair in B | `UNLINKED`, the reason quoting C's consumer parent and links |
| `valkey-cart`, `postgresql`, `kafka` | no spans of their own in A | `INFRASTRUCTURE`, each naming the callers C shows; a datastore no caller names is recorded so, not assumed |
| `llm`, `image-provider`, `flagd-ui`, each | spans in A, no pair in B | `UNLINKED` |
| | no spans; the logs show requests served | `UNINSTRUMENTED` |
| | no spans; the logs show no request | **`UNEXERCISED`**, a value added only if a service lands here: nothing reached it in the hour, so whether it emits spans is not measured |
| the nine telemetry services | as on v1 | not in the catalog. Spans of their own in A are recorded and change nothing |

`frontend-proxy` needs no entry: it is a node, `PRESENT`, through `frontend-proxy → frontend`.

## Step 2: the build

1. **`context/graph.py`**:
   - `SNAPSHOT` stays v1's. `SNAPSHOT_V2` is the snapshot of record, in place, and
     `SNAPSHOTS` maps world to file.
   - `ARTIFACT_EDGES` stays v1's. `ARTIFACT_EDGES_V2` holds `load-generator → frontend-proxy`
     and `load-generator → flagd`.
   - **Self-edges are dropped at load in every world.** v1's capture has none, so v1 loses
     nothing.
   - **`EDGE_KINDS` applies to v1 only**, and every v2 edge loads `UNMEASURED`.
   - **`ServiceGraph` carries the world it was loaded for, and canonicalises in that world**, not
     in the process's. A v1 graph loaded in a v2 process still answers in v1's names.
   - `from_snapshot(path=None, world=None)`: by default, the process's world and its snapshot.
2. **`context/catalog.py`**:
   - `GraphPresence.UNLINKED`, plus `UNEXERCISED` only if step 1 needs it.
   - `KNOWN_ABSENT` stays v1's. `KNOWN_ABSENT_V2` holds step 1's entries, and the catalog chooses
     the table by its graph's world.
   - `ServiceCatalog.from_snapshot(world=None)`.
3. **`context/services.py`**: `load_services(world=None)`, reading `knowledge/services-v2.yaml`
   for v2.
4. **`knowledge/services-v2.yaml`**, the 32 services of `SERVICE_CONTAINERS_V2`:
   - **The fields.**
     - `kind`, `tier` and `owner` are taken from v1's counterpart where one exists.
     - The services new in v2 are assigned:
       - `flagd` and `flagd-ui` as v1's flag service (application, platform);
       - `product-reviews` and `llm` as storefront core;
       - `image-provider` as storefront edge;
       - `valkey-cart` and `postgresql` as infrastructure;
       - `opensearch` and `otel-collector` as telemetry.
     - **`depends_on`** is every measured cross-service edge between two catalog services. That
       is v1's convention, which kept `loadgenerator → frontend`, so `load-generator` declares
       `flagd` and `frontend-proxy`.
     - **`runbooks: []` everywhere.** No v2 runbook exists, and v1's runbooks carry v1's edge
       tables.
     - **The SLOs** are `alert-rules-v2.yml`'s thresholds for every application service.
5. **`Dockerfile`**: one `COPY` line for the v2 snapshot.
6. **The tests, v2 counterparts beside the v1 ones, which stay as they are**:
   - **`test_context`**:
     - the snapshot guard: 38 entries, 20 edges, 15 nodes;
     - no self-edge, no v2 artifact edge, `load-generator` not a node, `frontend-proxy` a node;
     - every node in `SERVICE_CONTAINERS_V2`, and every edge `UNMEASURED`;
     - the JSON and `q121-v2-graph.txt`'s 1 h table agree;
     - each `KNOWN_ABSENT_V2` presence;
     - the blast radii below;
     - a graph answers in its own world.
   - **`test_services`**: the v2 directory against `SERVICE_CONTAINERS_V2`, its containers, its
     `depends_on` against the measured v2 edges, its SLOs against `alert-rules-v2.yml`, and its
     owners `demo/`.
   - **`test_packaging`**: `REPO_DATA` names the v2 snapshot. Its derived check finds the new
     `repo_root()` path regardless.
   - **`test_runbooks`**: no counterpart, because no v2 service runbook exists to carry an edge
     table. Stated here so its absence is a decision, not a gap.
7. **The records**:
   - the design note's correction;
   - Q122's row, with its erratum and the build's result;
   - `docs/PLAN.md`;
   - `evals/attempts/Q122-v2-graph/RESULT.md`.

**Nothing else changes**: no prompt, no contract, no tool, no world, no alert rule.

## Predictions, stated now

**Step 1:**

- **`llm`, `image-provider` and `flagd-ui` emit no spans in the hour.**
- **Valkey**: cart's client spans name it (`db.system` `redis` or `valkey`).
- **Postgres**: client spans from `accounting` name it, with at least one other caller.
- **Kafka**:
  - `checkout` holds producer spans;
  - `accounting`'s and `fraud-detection`'s consumer spans sit in traces of their own, with their
    parent not in the trace or with a link to checkout's producer span.
- **Every pair B finds is in the snapshot.**

**Step 2, on v2** (`hop_radius` 2). Each line is in the order the method returns it, because order
is part of its contract:

| query | predicted |
|---|---|
| `blast_radius(["checkout"])` | also affected: `frontend` (1), `frontend-proxy` (2). Candidate causes: `product-catalog`, `currency`, `cart`, `email`, `payment`, `shipping`. 8 unmeasured edges crossed |
| `blast_radius(["quote"])` | also affected: `shipping` (1), `checkout` (2) |
| `blast_radius(["flagd"])` | also affected: `ad`, `recommendation`, `cart`, `fraud-detection`, `product-reviews` (1), then `frontend`, `checkout` (2). 10 unmeasured edges |
| `blast_radius(["accounting"])` | nothing; the catalog says `UNLINKED` |
| `catalog.get("checkout")`, `get("frontend-proxy")` | `PRESENT`, both |
| `catalog.get("load-generator")` | `ARTIFACT_ONLY` |

**Step 2, on v1:**

- The graph keeps 15 edges and 13 nodes, and the catalog is unchanged.
- Every existing test passes unmodified.
- `make check` passes.
- **`capability_version()` stays `cap:91279a09`, and `runtime_version()` stays
  `faultline/0.0.1+prompts:9ce16b66bbcc`, in both worlds.**

**A consequence, named so it is not a surprise.** `flagd`'s radius is most of the storefront,
and every edge in it is an unmeasured flag read. v1 never showed this, because its flag service
emitted no spans. Whether a flag read is synchronous is the kind of fact `EDGE_KINDS` holds, and
nothing on v2 has measured it. It is reported, as all unmeasured edges are, and not changed
here.

## Acceptance

The build is **done** when:

- step 1's stop rule did not fire, or the owner decided after it did;
- the code above passes `make check`;
- the RESULT reads each prediction against what was measured, held or not.

A prediction that misses is recorded, not chased.

## Noticed, not in scope

- **`alert-rules-v2.yml` excludes `frontend-proxy` from `ServiceNoTraffic`** because Envoy *"emits
  a few spans at startup and none after"*. The snapshot of record has
  `frontend-proxy → frontend` at 9,881 calls in the hour. On v2 the proxy traces every request.
  It is not changed here; the RESULT queues it.
- **Out of scope**:
  - astronomy-shop under SREGym (the design note's item 3);
  - DeathStarBench (item 4);
  - Q121's guard;
  - edge kinds on v2;
  - v2 runbooks.
